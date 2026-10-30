"""Add any city on demand: the AI drafts a guide of real sights, the map service checks it.

The AI returns the city's metadata and ~20 attractions with coordinates, hours and prices.
Nominatim (OpenStreetMap) confirms the city exists and fixes its centre; places far from that
centre are dropped and every field is clamped to what the planner expects. Results are saved
in the database and registered alongside the built-in cities, so each city is built only once.
"""
from __future__ import annotations

import logging
import os
import re
import unicodedata
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import ai
from .cities import BEST, CITIES, KINDS, PLACES, TAGS
from .models import DiscoveredCity
from .planner import haversine

log = logging.getLogger("travelsphere.discover")

NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "TravelSphere/1.0 (student project)"
MAX_KM_FROM_CENTRE = 60
MIN_PLACES = 6
# Total seconds the AI may spend on one guide. Vercel stops functions at maxDuration (60 s in vercel.json).
GUIDE_BUDGET_S = float(os.getenv("DISCOVER_BUDGET_S", "50"))
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class DiscoverError(Exception):
    """A user-facing reason the city could not be added; ``status`` is the HTTP code to return."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class GenPlace(BaseModel):
    name: str
    kind: str = Field(description="One of: " + ", ".join(KINDS))
    tags: list[str] = Field(description="1-4 of: " + ", ".join(TAGS))
    lat: float
    lng: float
    duration: int = Field(description="Typical visit length in minutes")
    price: float = Field(description="Standard adult entry ticket in local currency; 0 if free")
    open: str = Field(description="Opening time HH:MM (24h)")
    close: str = Field(description="Closing time HH:MM (24h); 23:59 if always open")
    closed_days: list[int] = Field(description="Weekdays it is closed, Mon=0 .. Sun=6")
    best: str = Field(description="any | morning | sunset | evening")
    popularity: int = Field(description="1-10, how essential for a first-time visitor")
    blurb: str = Field(description="One vivid sentence, under 25 words")


class GenCity(BaseModel):
    name: str = Field(description="Common English name of the city, correctly spelled")
    country: str
    tz: str = Field(description="IANA time zone, e.g. Asia/Kolkata")
    currency: str = Field(description="ISO 4217 code, e.g. INR")
    symbol: str = Field(description="Currency symbol, e.g. ₹")
    lat: float
    lng: float
    places: list[GenPlace]


GUIDE_SYSTEM = """You are a meticulous local travel researcher building data for TravelSphere, a sightseeing \
itinerary planner. For the city the user names (fix any misspelling), list 18 to 22 real, currently open \
places a first-time visitor would want to see within about 25 km of the centre: a mix of the major sights, \
museums, parks, viewpoints, neighbourhoods and religious sites, plus at least 3 well-known food streets, \
markets or iconic eateries tagged "food". Only include places that really exist, with accurate coordinates \
(4+ decimals). Use typical opening hours and real weekly closing days; leave closed_days empty if none. \
Use "sunset" for places best at sunset, "evening" for night markets and nightlife, "morning" for places \
that get crowded or hot later. If the name is not a real city or town, return an empty places list."""


# ------------------------------------------------------------------ helpers
def _slug(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", ascii_text).strip("_")[:30] or "city"


def _norm_name(text: str) -> str:
    return _slug(text.split(",")[0])


def _fallback_tz(lng: float) -> str:
    offset = round(lng / 15)
    return "Etc/GMT" + (f"{-offset:+d}" if offset else "")  # Etc/GMT signs are inverted


def _geocode(query: str) -> dict | None:
    try:
        r = httpx.get(NOMINATIM, params={"q": query, "format": "jsonv2", "limit": 1, "addressdetails": 1,
                                         "accept-language": "en"},
                      headers={"User-Agent": USER_AGENT}, timeout=10.0)
        r.raise_for_status()
        rows = r.json()
    except (httpx.HTTPError, ValueError):
        return None
    if not rows:
        return None
    row = rows[0]
    return {"lat": float(row["lat"]), "lng": float(row["lon"]),
            "country": (row.get("address") or {}).get("country")}


def _clean_place(city_id: str, raw: GenPlace, centre: tuple[float, float], used: set[str]) -> dict | None:
    if not raw.name.strip() or haversine(*centre, raw.lat, raw.lng) > MAX_KM_FROM_CENTRE:
        return None
    pid = f"{city_id}__{_slug(raw.name)}"
    if pid in used:
        return None
    used.add(pid)
    tags = [t for t in dict.fromkeys(t.lower() for t in raw.tags) if t in TAGS][:4] or ["local"]
    open_, close = (raw.open, raw.close) if HHMM.match(raw.open) and HHMM.match(raw.close) else ("09:00", "18:00")
    if close <= open_:
        close = "23:59"
    return {
        "id": pid, "name": raw.name.strip()[:120],
        "kind": raw.kind if raw.kind in KINDS else "Landmark",
        "tags": tags, "lat": round(raw.lat, 6), "lng": round(raw.lng, 6),
        "duration": max(15, min(300, int(raw.duration or 60))),
        "price": max(0.0, float(raw.price or 0)),
        "open": open_, "close": close,
        "closed_days": sorted({d for d in raw.closed_days if 0 <= d <= 6})[:6],
        "best": raw.best if raw.best in BEST else "any",
        "popularity": max(1, min(10, int(raw.popularity or 5))),
        "blurb": raw.blurb.strip()[:240], "custom": False,
    }


def _register(city: dict, places: list[dict]) -> None:
    CITIES[city["id"]] = city
    PLACES[city["id"]] = places


def find_existing(name: str) -> dict | None:
    key = _norm_name(name)
    return next((c for c in CITIES.values() if _norm_name(c["name"]) == key or c["id"] == key), None)


# ------------------------------------------------------------------ public API
def load_saved(db: Session) -> int:
    """Register saved cities this process hasn't loaded yet.

    Cheap enough to run per request: on serverless hosts each instance has its own memory,
    so a city another instance just built only reaches this one through the database.
    """
    missing = [cid for cid in db.scalars(select(DiscoveredCity.id)) if cid not in CITIES]
    if missing:
        for row in db.scalars(select(DiscoveredCity).where(DiscoveredCity.id.in_(missing))):
            _register(row.data["city"], row.data["places"])
    return len(missing)


def discover(db: Session, query: str) -> tuple[dict, bool]:
    """Return (city, created). Raises DiscoverError with a user-facing message."""
    query = " ".join(query.split())[:100]
    if len(query) < 2:
        raise DiscoverError("Type the name of a city to add.")
    existing = find_existing(query)
    if existing:
        return existing, False

    provider = ai.provider()
    if not provider:
        raise DiscoverError("Adding a new city needs an AI key (GEMINI_API_KEY) on the server. "
                            "Pick one of the cities above instead.", 503)
    try:
        guide = ai.call_llm(provider, GUIDE_SYSTEM, f"City: {query}", GenCity, timeout=35.0,
                            budget=GUIDE_BUDGET_S)  # a stuck model hands over to the next
    except Exception as exc:
        log.warning("City guide generation failed for %r: %s", query, exc)
        raise DiscoverError("The AI service didn't answer in time. Try again in a minute.", 502) from exc

    if not guide.places:
        raise DiscoverError(f"Couldn't find a city called “{query}”. Check the spelling and try again.", 404)
    existing = find_existing(guide.name)
    if existing:  # e.g. a misspelling of a city we already have
        return existing, False

    geo = _geocode(f"{guide.name}, {guide.country}")
    if geo is None and haversine(guide.lat, guide.lng, guide.places[0].lat, guide.places[0].lng) > MAX_KM_FROM_CENTRE:
        raise DiscoverError(f"Couldn't place “{guide.name}” on the map. Try a nearby larger city.", 404)
    centre = (geo["lat"], geo["lng"]) if geo else (guide.lat, guide.lng)

    city_id = _slug(guide.name)
    while city_id in CITIES:
        city_id += "_x"
    used: set[str] = set()
    places = [p for p in (_clean_place(city_id, raw, centre, used) for raw in guide.places) if p]
    if len(places) < MIN_PLACES:
        raise DiscoverError(f"Couldn't build a reliable guide for {guide.name} — too few sights checked out. "
                            "Try again, or try a nearby larger city.", 422)

    try:
        ZoneInfo(guide.tz)
        tz = guide.tz
    except (ZoneInfoNotFoundError, ValueError):
        tz = _fallback_tz(centre[1])
    currency = re.sub(r"[^A-Z]", "", guide.currency.upper())[:3] or "USD"
    city = {"id": city_id, "name": guide.name.strip()[:60], "country": (geo or {}).get("country") or guide.country,
            "lat": round(centre[0], 5), "lng": round(centre[1], 5), "tz": tz, "currency": currency,
            "symbol": (guide.symbol or currency).strip()[:4], "generated": True}

    db.add(DiscoveredCity(id=city_id, query=query, data={"city": city, "places": places},
                          created_at=datetime.now(timezone.utc)))
    db.commit()
    _register(city, places)
    return city, True
