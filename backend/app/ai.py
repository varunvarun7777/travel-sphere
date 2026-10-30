"""Natural-language trip parsing and day briefs.

Uses Gemini Flash when GEMINI_API_KEY is set, else Claude (official ``anthropic`` SDK,
structured outputs) when ANTHROPIC_API_KEY is set. TRAVELSPHERE_AI=off disables both. With no
provider — or on any provider error — a deterministic rules engine answers instead.
"""
from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from collections import Counter
from datetime import date, timedelta
from typing import Literal, Optional

from pydantic import BaseModel, Field

from . import gemini
from .cities import CITIES, PLACES, TAGS
from .planner import WEEKDAYS, hm, parse_hm

log = logging.getLogger("travelsphere.ai")

MODEL = "claude-opus-5-5"
PACE_VALUES = ("relaxed", "balanced", "packed")
MODE_VALUES = ("auto", "walk", "transit", "drive")
# Total seconds per AI request including model fallbacks; keeps under the 60 s Vercel function limit.
AI_BUDGET_S = 45.0


def provider() -> str | None:
    """Which model answers AI requests: "gemini", "claude", or None (rules only)."""
    if os.getenv("TRAVELSPHERE_AI", "").lower() == "off":
        return None
    if gemini.available():
        return "gemini"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "claude"
    return None


def claude_available() -> bool:
    return provider() == "claude"


def call_llm(name: str, system: str, user: str, output_model: type[BaseModel], timeout: float = 45.0,
             budget: float | None = None):
    if name == "gemini":
        return gemini.generate_json(system, user, output_model, timeout=timeout, budget=budget)
    return _call_claude(system, user, output_model, timeout=min(timeout, budget) if budget else timeout)


# ============================================================== Claude plumbing
class ParsedPrefs(BaseModel):
    city: Optional[str] = Field(default=None, description="Id of a listed city, or null")
    new_city: Optional[str] = Field(default=None, description="Correctly spelled 'City, Country' when the traveller "
                                                              "names a city that is not listed; otherwise null")
    days: Optional[int] = None
    start_date: Optional[str] = Field(default=None, description="YYYY-MM-DD")
    pace: Optional[Literal["relaxed", "balanced", "packed"]] = None
    mode: Optional[Literal["auto", "walk", "transit", "drive"]] = None
    interests: list[str] = Field(default_factory=list)
    must_see: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)


class DayBrief(BaseModel):
    date: str
    title: str
    summary: str
    tips: list[str]


class TripBrief(BaseModel):
    days: list[DayBrief]


def _call_claude(system: str, user: str, output_model: type[BaseModel], timeout: float = 45.0):
    """Structured-output call. Raises on refusal / missing output so callers fall back."""
    import anthropic

    client = anthropic.Anthropic(timeout=timeout, max_retries=1)
    common = dict(model=MODEL, max_tokens=8000, output_config={"effort": "low"}, system=system,
                  messages=[{"role": "user", "content": user}], output_format=output_model)
    # Server-side refusal fallback (beta). Supported by the installed SDK's beta.messages.parse.
    resp = client.beta.messages.parse(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **common)
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        raise RuntimeError(f"Claude returned no usable output (stop_reason={resp.stop_reason})")
    return resp.parsed_output


# ============================================================== text helpers
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().replace("œ", "oe").replace("’", "'")
    s = re.sub(r"[^a-z0-9']+", " ", s)
    return f" {s.strip()} "


def _has(text: str, phrase: str) -> bool:
    return f" {phrase.strip()} " in text


NUM_WORDS = {"one": 1, "a": 1, "an": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
             "couple": 2, "few": 3}
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
MONTH_RE = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"

CITY_ALIASES = {
    "paris": ["paris", "france", "parisian"],
    "rome": ["rome", "roma", "italy", "vatican"],
    "tokyo": ["tokyo", "japan", "shibuya", "shinjuku"],
    "jaipur": ["jaipur", "pink city", "rajasthan"],
}

PACE_WORDS = {
    "relaxed": ["slow", "relaxed", "relaxing", "easy", "easygoing", "easy going", "chill", "leisurely", "laid back",
                "unhurried", "gentle", "slow paced", "not too busy", "take it easy"],
    "packed": ["packed", "busy", "as much as possible", "see everything", "intense", "fast", "fast paced",
               "action packed", "jam packed", "maximum", "everything"],
    "balanced": ["balanced", "moderate", "normal pace", "medium pace"],
}

MODE_WORDS = {
    "walk": ["walk", "walking", "on foot", "walkable", "stroll"],
    "transit": ["metro", "subway", "train", "trains", "transit", "public transport", "public transportation", "bus",
                "buses", "tube", "tram", "underground"],
    "drive": ["car", "taxi", "taxis", "drive", "driving", "uber", "cab", "cabs", "rideshare", "auto rickshaw",
              "tuk tuk", "rental car"],
}

INTEREST_WORDS = {
    "art": ["art", "arts", "museum", "museums", "gallery", "galleries", "paintings", "painting", "sculpture",
            "impressionist", "exhibitions"],
    "history": ["history", "historic", "historical", "ruins", "ancient", "roman", "medieval", "palace", "palaces",
                "fort", "forts", "heritage", "castle", "castles", "archaeology"],
    "architecture": ["architecture", "buildings", "architectural", "gothic", "baroque", "design"],
    "nature": ["park", "parks", "garden", "gardens", "nature", "green", "outdoors", "trees", "lake"],
    "food": ["food", "eat", "eating", "foodie", "street food", "cuisine", "restaurants", "restaurant", "dining",
             "snacks", "culinary", "lunch", "dinner", "cafes", "sushi", "pasta", "gelato"],
    "nightlife": ["bars", "bar", "nightlife", "drinks", "clubs", "club", "night out", "pubs", "pub", "cocktails",
                  "izakaya", "party", "late night"],
    "religion": ["temple", "temples", "church", "churches", "shrine", "shrines", "cathedral", "cathedrals",
                 "religion", "religious", "spiritual", "basilica", "mosque", "sacred"],
    "shopping": ["shopping", "shop", "shops", "market", "markets", "bazaar", "bazaars", "souvenirs", "boutiques",
                 "fashion", "textiles", "jewellery", "jewelry"],
    "views": ["views", "view", "rooftop", "rooftops", "sunset", "sunsets", "skyline", "panorama", "panoramic",
              "viewpoint", "lookout", "observation deck"],
    "local": ["local", "locals", "hidden gems", "hidden gem", "off the beaten path", "off the beaten track",
              "neighbourhood", "neighbourhoods", "neighborhood", "neighborhoods", "authentic", "like a local"],
}

PLACE_ALIASES = {
    "eiffel": ["eiffel"], "louvre": ["louvre", "mona lisa"], "orsay": ["orsay"],
    "notre_dame": ["notre dame"], "sainte_chapelle": ["sainte chapelle"], "sacre_coeur": ["sacre coeur"],
    "montmartre": ["montmartre", "place du tertre"], "arc_triomphe": ["arc de triomphe", "arc"],
    "catacombs": ["catacombs of paris", "paris catacombs"], "luxembourg": ["luxembourg"],
    "rodin": ["rodin"], "orangerie": ["orangerie", "water lilies"], "invalides": ["invalides", "napoleon s tomb"],
    "palais_garnier": ["garnier", "opera house", "paris opera"], "marais": ["marais"],
    "enfants_rouges": ["enfants rouges"], "rue_cler": ["rue cler"], "latin_quarter": ["latin quarter"],
    "canal_st_martin": ["canal saint martin", "canal st martin"], "seine_cruise": ["seine cruise", "boat cruise",
                                                                                   "river cruise"],
    "versailles": ["versailles"],
    "colosseum": ["colosseum", "colosseo", "coliseum"], "roman_forum": ["roman forum", "forum", "palatine"],
    "pantheon": ["pantheon"], "trevi": ["trevi"], "spanish_steps": ["spanish steps"],
    "vatican_museums": ["vatican museums", "vatican museum", "sistine"], "st_peters": ["st peter", "st peters",
                                                                                       "saint peter", "st peter s"],
    "castel_sant_angelo": ["sant angelo", "castel sant angelo"], "borghese": ["borghese gallery", "galleria borghese",
                                                                              "borghese"],
    "pincio": ["pincio"], "piazza_navona": ["navona"], "campo_de_fiori": ["campo de fiori", "campo de  fiori"],
    "trastevere": ["trastevere"], "testaccio_market": ["testaccio"], "capitoline": ["capitoline"],
    "caracalla": ["caracalla"], "san_callisto": ["san callisto", "catacombs of san callisto", "appian way"],
    "ghetto": ["jewish ghetto"], "monti": ["monti"],
    "senso_ji": ["senso ji", "sensoji", "asakusa"], "meiji_jingu": ["meiji"], "shibuya_crossing": ["shibuya crossing",
                                                                                                   "scramble"],
    "shibuya_sky": ["shibuya sky"], "tokyo_national_museum": ["tokyo national museum", "national museum"],
    "ueno_park": ["ueno park", "ueno"], "ameyoko": ["ameyoko"], "tsukiji_outer": ["tsukiji"],
    "imperial_east_gardens": ["imperial palace", "east gardens", "imperial gardens"],
    "teamlab_planets": ["teamlab", "team lab"], "golden_gai": ["golden gai"], "omoide_yokocho": ["omoide yokocho",
                                                                                                "memory lane",
                                                                                                "piss alley"],
    "takeshita": ["takeshita", "harajuku"], "akihabara": ["akihabara", "akiba"], "skytree": ["skytree", "sky tree"],
    "shinjuku_gyoen": ["shinjuku gyoen", "gyoen"], "tokyo_tower": ["tokyo tower"], "hamarikyu": ["hamarikyu"],
    "mori_art": ["mori art", "mori museum", "roppongi hills"],
    "amber_fort": ["amber fort", "amer fort", "amber palace", "amer palace"], "jaigarh_fort": ["jaigarh"],
    "panna_meena": ["panna meena", "stepwell"], "anokhi_museum": ["anokhi"], "nahargarh": ["nahargarh"],
    "hawa_mahal": ["hawa mahal", "palace of winds"], "city_palace": ["city palace"],
    "jantar_mantar": ["jantar mantar"], "albert_hall": ["albert hall"], "jal_mahal": ["jal mahal", "water palace"],
    "patrika_gate": ["patrika"], "birla_mandir": ["birla"], "galtaji": ["galtaji", "galta ji", "monkey temple"],
    "johari_bazaar": ["johari"], "bapu_bazaar": ["bapu bazaar"], "masala_chowk": ["masala chowk"],
    "mi_road_food": ["lassiwala", "mi road"], "sisodia_rani": ["sisodia"], "chokhi_dhani": ["chokhi dhani"],
}

NEGATORS = r"(?:skip|skipping|avoid|avoiding|not|no|without|except|hate|exclude|excluding|don ?t want|dont want|never|nothing)"


def _place_city(pid: str) -> str | None:
    for cid, plist in PLACES.items():
        if any(p["id"] == pid for p in plist):
            return cid
    return None


def _match_places(text: str, city: str | None) -> list[str]:
    hits = []
    for cid, plist in PLACES.items():
        if city and cid != city:
            continue
        for p in plist:
            phrases = [_norm(p["name"]).strip()] + PLACE_ALIASES.get(p["id"], [])
            if any(ph and _has(text, ph) for ph in phrases):
                hits.append(p["id"])
    # "arc" or "forum" alone are weak; drop if a stronger alias of another place matched the same words
    return hits


def _parse_date(raw: str, text: str, today: date) -> str | None:
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", raw)
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3])).isoformat()
        except ValueError:
            pass
    day = month = None
    m = re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{MONTH_RE}\b", text)
    if m:
        day, month = int(m[1]), MONTHS[m[2][:3]]
    else:
        m = re.search(rf"\b{MONTH_RE}\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", text)
        if m:
            day, month = int(m[2]), MONTHS[m[1][:3]]
    if day and month:
        for year in (today.year, today.year + 1):
            try:
                d = date(year, month, day)
            except ValueError:
                return None
            if d >= today:
                return d.isoformat()
        return None
    if _has(text, "tomorrow"):
        return (today + timedelta(days=1)).isoformat()
    if _has(text, "today"):
        return today.isoformat()
    if _has(text, "this weekend") or _has(text, "next weekend"):
        ahead = (5 - today.weekday()) % 7
        if _has(text, "next weekend"):
            ahead += 7 if ahead else 7
        return (today + timedelta(days=ahead)).isoformat()
    m = re.search(r"\bnext (monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", text)
    if m:
        wd = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"].index(m[1])
        ahead = (wd - today.weekday()) % 7 or 7
        return (today + timedelta(days=ahead)).isoformat()
    return None


def _parse_days(text: str) -> int | None:
    m = re.search(r"\b(\d{1,2}|one|two|three|four|five|six|seven|a|an|couple|few)(?: of)?\s*(?:full\s+)?(day|days|night|nights)\b",
                  text)
    if m:
        v = m[1]
        n = int(v) if v.isdigit() else NUM_WORDS[v]
        return max(1, min(7, n))
    if re.search(r"\b(a|one|1)\s+week\b", text) or _has(text, "week long") or _has(text, "weeklong"):
        return 7
    if _has(text, "long weekend"):
        return 3
    if _has(text, "weekend"):
        return 2
    if _has(text, "day trip") or _has(text, "today") or _has(text, "tomorrow"):
        return 1
    return None


def rules_parse(raw: str, today: date | None = None) -> dict:
    today = today or date.today()
    text = _norm(raw)

    # split into clauses; whatever follows a negator inside a clause ("skip the Louvre",
    # "not too busy") is negative, the rest is positive
    pos_parts, neg_parts = [], []
    for seg in re.split(r"[,.;:!?\n()]+|\bbut\b|\bthough\b", raw, flags=re.IGNORECASE):
        n = _norm(seg)
        m = re.search(rf" {NEGATORS} ", n)
        if m:
            pos_parts.append(n[:m.start()])
            neg_parts.append(n[m.end():])
        else:
            pos_parts.append(n)
    pos_text = " " + re.sub(r"\s+", " ", " ".join(pos_parts)).strip() + " "
    neg_text = " " + re.sub(r"\s+", " ", " ".join(neg_parts)).strip() + " "

    city = None
    for cid, aliases in CITY_ALIASES.items():
        if any(_has(text, a) for a in aliases):
            city = cid
            break

    must = _match_places(pos_text, city)
    avoid = _match_places(neg_text, city)
    if city is None:
        found = [c for c in (_place_city(p) for p in must + avoid) if c]
        if found:
            city = Counter(found).most_common(1)[0][0]
            must = [p for p in must if _place_city(p) == city]
            avoid = [p for p in avoid if _place_city(p) == city]
    must = [p for p in dict.fromkeys(must) if p not in avoid]
    avoid = list(dict.fromkeys(avoid))

    pace = None
    if any(_has(neg_text, w) for w in ("busy", "packed", "rushed", "hectic")) or any(_has(text, w) for w in PACE_WORDS["relaxed"]):
        pace = "relaxed"
    elif any(_has(pos_text, w) for w in PACE_WORDS["packed"]):
        pace = "packed"
    elif any(_has(pos_text, w) for w in PACE_WORDS["balanced"]):
        pace = "balanced"

    mode = None
    for m in ("drive", "transit", "walk"):
        if any(_has(pos_text, w) for w in MODE_WORDS[m]):
            mode = m
            break

    interests = [tag for tag in TAGS if any(_has(pos_text, w) for w in INTEREST_WORDS[tag])]

    return {
        "city": city,
        "days": _parse_days(text),
        "start_date": _parse_date(raw, text, today),
        "pace": pace,
        "mode": mode,
        "interests": interests,
        "must_see": must,
        "avoid": avoid,
    }


def _validate_prefs(p: dict) -> dict:
    city = p.get("city") if p.get("city") in CITIES else None
    new_city = None if city else " ".join(str(p.get("new_city") or "").split())[:80] or None
    valid_ids = {x["id"] for x in PLACES[city]} if city else {x["id"] for plist in PLACES.values() for x in plist}
    days = p.get("days")
    try:
        days = max(1, min(7, int(days))) if days is not None else None
    except (TypeError, ValueError):
        days = None
    sd = p.get("start_date")
    try:
        sd = date.fromisoformat(sd).isoformat() if sd else None
    except (TypeError, ValueError):
        sd = None
    must = [i for i in dict.fromkeys(p.get("must_see") or []) if i in valid_ids]
    avoid = [i for i in dict.fromkeys(p.get("avoid") or []) if i in valid_ids and i not in must]
    return {
        "city": city,
        "new_city": new_city,
        "days": days,
        "start_date": sd,
        "pace": p.get("pace") if p.get("pace") in PACE_VALUES else None,
        "mode": p.get("mode") if p.get("mode") in MODE_VALUES else None,
        "interests": [t for t in dict.fromkeys(p.get("interests") or []) if t in TAGS],
        "must_see": must,
        "avoid": avoid,
    }


PARSE_SYSTEM = """You turn a traveller's free-text request into structured trip preferences for TravelSphere, \
a sightseeing itinerary planner. Only use the ids listed below. Use null for anything the traveller did not \
state or clearly imply. Interests must come from: {tags}. Pace: relaxed | balanced | packed. \
Mode: auto | walk | transit | drive (walk = on foot, transit = metro/train/bus, drive = car/taxi). \
must_see = places the traveller explicitly wants; avoid = places they want to skip. \
Resolve relative dates against today's date ({today}); dates are YYYY-MM-DD. days is 1-7 ("weekend" = 2, "a week" = 7).
Travellers often misspell places ("banglre" = Bengaluru, "pari" = Paris): match listed cities generously. If the city they name is not listed, set city to null and new_city to its correctly spelled "City, Country"; must_see and avoid then stay empty.

Cities and places (id: name):
{catalog}"""


def parse_request(text: str, today: date | None = None) -> tuple[str, dict]:
    today = today or date.today()
    name = provider()
    if name:
        try:
            catalog = "\n".join(
                f"- {cid} ({c['name']}): " + "; ".join(f"{p['id']}: {p['name']}" for p in PLACES[cid])
                for cid, c in CITIES.items())
            system = PARSE_SYSTEM.format(tags=", ".join(TAGS), today=today.isoformat(), catalog=catalog)
            out = call_llm(name, system, text, ParsedPrefs, budget=AI_BUDGET_S)
            return name, _validate_prefs(out.model_dump())
        except Exception as exc:  # never fail the request because of the AI
            log.warning("%s parse failed, using rules: %s", name, exc)
    return "rules", _validate_prefs(rules_parse(text, today))


# ============================================================== briefs
TAG_TITLES = {
    "art": "Art", "history": "History", "architecture": "Architecture", "nature": "Green Escapes",
    "food": "Food", "nightlife": "Nightlife", "shopping": "Shopping", "views": "Views",
    "religion": "Sacred Sites", "local": "Local Life",
}

BOOKING_TIPS = {
    "borghese": "Galleria Borghese is timed entry only — book your slot online days ahead.",
    "vatican_museums": "Book Vatican Museums tickets online to skip the line; cover shoulders and knees.",
    "teamlab_planets": "teamLab Planets sells timed tickets — book ahead and wear trousers you can roll up.",
    "sainte_chapelle": "Reserve a Sainte-Chapelle time slot online; the security queue is long.",
    "catacombs": "Catacombs tickets are timed and sell out — book online in advance.",
    "eiffel": "Book Eiffel Tower summit tickets online well ahead; same-day slots go fast.",
    "shibuya_sky": "Shibuya Sky sunset slots sell out — book the time slot weeks ahead.",
    "colosseum": "Colosseum tickets are timed and named — book on the official site and bring ID.",
    "louvre": "Louvre entry needs a timed ticket — book online and use the Carrousel entrance.",
    "orsay": "Book Musée d'Orsay tickets online to skip the ticket queue.",
    "versailles": "Book a timed Versailles Palace ticket and go early; the gardens take hours.",
    "amber_fort": "Reach Amber Fort right at opening to beat the heat and the tour buses.",
    "tsukiji_outer": "Go early — many Tsukiji stalls sell out and close by early afternoon.",
    "st_peters": "St. Peter's has a strict dress code and a long security line — arrive early.",
    "chokhi_dhani": "Chokhi Dhani is busiest at weekends; arrive by opening for the folk shows.",
    "golden_gai": "Many Golden Gai bars charge a seat fee and some are regulars-only — look for English signs.",
    "notre_dame": "Notre-Dame entry is free; reserve a free time slot online to skip the line.",
}

CITY_TIPS = {
    "paris": ["Buy a Navigo Easy card for cheap metro hops.", "Many museums are free on the first Sunday of the month."],
    "rome": ["Refill water bottles at the free nasoni fountains.", "Validate bus tickets on board or risk a fine."],
    "tokyo": ["Load a Suica or Pasmo card for trains and convenience stores.", "Carry some cash — small eateries are often cash-only."],
    "jaipur": ["Agree auto-rickshaw fares before you get in, or use a ride-hailing app.", "Carry water and a scarf for sun and dust."],
}


def _stops_of(day: dict) -> list[dict]:
    return [it for it in day.get("items", []) if it.get("type") == "stop"]


def rules_brief(trip: dict) -> list[dict]:
    city = trip.get("city") or {}
    city_name = city.get("name", "the city")
    city_id = city.get("id", "")
    out = []
    used_city_tips: set = set()
    for day in trip.get("days", []):
        stops = _stops_of(day)
        places = [s.get("place") or {} for s in stops]
        tags = Counter(t for p in places for t in p.get("tags", []))
        top = [t for t, _ in sorted(tags.items(), key=lambda kv: (-kv[1], TAGS.index(kv[0]) if kv[0] in TAGS else 99))][:2]
        if not stops:
            title = f"Free day in {city_name}"
        elif len(top) >= 2:
            title = f"{TAG_TITLES.get(top[0], top[0].title())} & {TAG_TITLES.get(top[1], top[1].title())} in {city_name}"
        elif top:
            title = f"{TAG_TITLES.get(top[0], top[0].title())} in {city_name}"
        else:
            title = f"Exploring {city_name}"
        title = " ".join(title.split()[:6])

        walk = (day.get("metrics") or {}).get("walk_km", 0)
        if stops:
            first, last = places[0].get("name", "your first stop"), places[-1].get("name", "your last stop")
            if len(stops) == 1:
                summary = f"A focused day at {first}."
            else:
                summary = f"Start at {first} and wind up at {last} after {len(stops)} stops."
            summary += f" Expect about {walk:g} km on foot."
        else:
            summary = "No stops planned — a free day to wander, rest or add your own places."

        tips: list[str] = []
        for s, p in zip(stops, places):
            pid = s.get("id") or p.get("id")
            if pid in BOOKING_TIPS:
                tips.append(BOOKING_TIPS[pid])
        for s, p in zip(stops, places):
            if p.get("best") == "sunset" and day.get("sunset"):
                try:
                    by = hm(parse_hm(day["sunset"]) - 30)
                    tips.insert(0, f"Be at {p.get('name')} by {by} for sunset ({day['sunset']}).")
                except Exception:
                    pass
        for s, p in zip(stops, places):
            for w in s.get("warnings") or []:
                tips.insert(0, f"Heads up: {p.get('name')} — {w}.")
        for t in CITY_TIPS.get(city_id, []):
            if len(tips) >= 2:
                break
            if t not in used_city_tips:
                tips.append(t)
                used_city_tips.add(t)
        if len(tips) < 2:
            tips.append("Wear comfortable shoes and keep a power bank handy.")
        if len(tips) < 2:
            tips.append("Check opening hours on the day — they can change on holidays.")
        out.append({"date": day.get("date", ""), "title": title, "summary": summary,
                    "tips": list(dict.fromkeys(tips))[:3]})
    return out


BRIEF_SYSTEM = """You write short, vivid daily briefs for a sightseeing itinerary. For EVERY day given, return \
an object with the same date, a title of at most 6 words, a summary of at most 2 sentences, and 2-3 practical \
tips (booking, timing, sunset, closing times, local etiquette). Base everything only on the provided plan; do not \
invent stops."""


def _trip_digest(trip: dict) -> str:
    city = trip.get("city") or {}
    days = []
    for day in trip.get("days", []):
        stops = []
        for s in _stops_of(day):
            p = s.get("place") or {}
            stops.append({"name": p.get("name"), "kind": p.get("kind"), "time": f"{s.get('start')}-{s.get('end')}",
                          "closes": p.get("close"), "best": p.get("best"), "warnings": s.get("warnings") or []})
        lunch = next((it.get("suggestion") for it in day.get("items", []) if it.get("type") == "lunch"), None)
        days.append({"date": day.get("date"), "label": day.get("label"), "sunset": day.get("sunset"),
                     "stops": stops, "lunch": lunch, "walk_km": (day.get("metrics") or {}).get("walk_km"),
                     "warnings": day.get("warnings") or []})
    return json.dumps({"city": city.get("name"), "days": days}, ensure_ascii=False)


def brief(trip: dict) -> tuple[str, list[dict]]:
    fallback = rules_brief(trip)
    name = provider()
    if name and trip.get("days"):
        try:
            out = call_llm(name, BRIEF_SYSTEM, _trip_digest(trip), TripBrief, budget=AI_BUDGET_S)
            by_date = {d.date: d for d in out.days}
            result = []
            for fb in fallback:
                d = by_date.get(fb["date"])
                if d is None:
                    result.append(fb)
                    continue
                tips = [t.strip() for t in d.tips if t and t.strip()][:3]
                if len(tips) < 2:
                    tips = (tips + fb["tips"])[:3]
                result.append({"date": fb["date"],
                               "title": " ".join(d.title.split()[:6]) or fb["title"],
                               "summary": _two_sentences(d.summary) or fb["summary"],
                               "tips": tips})
            return name, result
        except Exception as exc:
            log.warning("%s brief failed, using rules: %s", name, exc)
    return "rules", fallback


def _two_sentences(s: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", (s or "").strip())
    return " ".join(parts[:2]).strip()


__all__ = ["call_llm", "provider", "claude_available", "parse_request", "brief", "rules_parse", "rules_brief", "WEEKDAYS"]
