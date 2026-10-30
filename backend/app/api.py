"""HTTP API (mounted under /api)."""
from __future__ import annotations

import secrets
from datetime import date, datetime, timezone
from typing import Any, Literal, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import ai, discover, gemini, pdf
from .cities import CITIES, city_places
from .database import get_db
from .models import Trip, User
from .planner import PlannerError, plan, schedule
from .security import create_token, current_user, hash_password, verify_password

router = APIRouter(prefix="/api")

HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


# ------------------------------------------------------------------ schemas
class BaseIn(BaseModel):
    name: str = "My base"
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class CustomPlaceIn(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    duration: int = Field(default=60, ge=5, le=600)


class PlanRequest(BaseModel):
    city: str
    start_date: date
    days: int = Field(ge=1, le=7)
    pace: Literal["relaxed", "balanced", "packed"] = "balanced"
    mode: Literal["auto", "walk", "transit", "drive"] = "auto"
    interests: list[str] = Field(default_factory=list)
    must_see: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    base: Optional[BaseIn] = None
    custom_places: list[CustomPlaceIn] = Field(default_factory=list)


class ScheduleRequest(BaseModel):
    city: str
    date: date
    pace: Literal["relaxed", "balanced", "packed"] = "balanced"
    mode: Literal["auto", "walk", "transit", "drive"] = "auto"
    base: Optional[BaseIn] = None
    start: Optional[str] = Field(default=None, pattern=HHMM)
    end: Optional[str] = Field(default=None, pattern=HHMM)
    stops: list[str] = Field(default_factory=list)
    locked: list[str] = Field(default_factory=list)
    custom_places: list[CustomPlaceIn] = Field(default_factory=list)
    optimize: bool = True


class ParseIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class BriefIn(BaseModel):
    trip: dict[str, Any]


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=6, max_length=200)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class TripIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    data: dict[str, Any]


class TripUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    data: Optional[dict[str, Any]] = None


class TripOut(BaseModel):
    id: int
    title: str
    city: str
    start_date: str
    days: int
    share_slug: str
    updated_at: datetime
    data: Optional[dict[str, Any]] = None


# ------------------------------------------------------------------ helpers
def _bad(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _city_or_400(city_id: str) -> dict:
    city = CITIES.get(city_id)
    if not city:
        raise HTTPException(status_code=400, detail=f"Unknown city '{city_id}'")
    return city


def _trip_out(t: Trip, with_data: bool = True) -> TripOut:
    return TripOut(id=t.id, title=t.title, city=t.city, start_date=t.start_date, days=t.days,
                   share_slug=t.share_slug, updated_at=t.updated_at, data=t.data if with_data else None)


def _trip_meta(data: dict) -> tuple[str, str, int]:
    prefs = data.get("prefs") or {}
    city = (data.get("city") or {}).get("id") if isinstance(data.get("city"), dict) else data.get("city")
    city = city or prefs.get("city")
    if not city or city not in CITIES:
        raise HTTPException(status_code=400, detail="Trip data must include a known city")
    days = data.get("days") if isinstance(data.get("days"), list) else []
    start = (days[0].get("date") if days and isinstance(days[0], dict) else None) or prefs.get("start_date") or ""
    n = len(days) or int(prefs.get("days") or 0)
    return city, str(start)[:10], n


def _own_trip(db: Session, trip_id: int, user: User) -> Trip:
    t = db.get(Trip, trip_id)
    if t is None or t.user_id != user.id:
        raise HTTPException(status_code=404, detail="Trip not found")
    return t


# ------------------------------------------------------------------ cities & planning
@router.get("/cities")
def list_cities():
    return list(CITIES.values())


class DiscoverIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)


@router.post("/cities/discover")
def discover_city(body: DiscoverIn, db: Session = Depends(get_db)):
    try:
        city, created = discover.discover(db, body.name)
    except discover.DiscoverError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    return {"city": city, "created": created, "places": len(city_places(city["id"]))}


@router.get("/cities/{city_id}/places")
def list_places(city_id: str):
    _city_or_400(city_id)
    return city_places(city_id)


@router.post("/plan")
def make_plan(req: PlanRequest):
    try:
        return plan(req)
    except PlannerError as exc:
        raise _bad(exc)


@router.post("/schedule")
def make_schedule(req: ScheduleRequest):
    try:
        return schedule(req)
    except PlannerError as exc:
        raise _bad(exc)


@router.get("/geocode")
async def geocode(q: str = Query("", max_length=200), city: str = Query(...)):
    c = _city_or_400(city)
    if not q.strip():
        return []
    params = {
        "q": q, "format": "jsonv2", "limit": 6, "bounded": 1,
        "viewbox": f"{c['lng'] - 0.3},{c['lat'] + 0.3},{c['lng'] + 0.3},{c['lat'] - 0.3}",
    }
    headers = {"User-Agent": "TravelSphere/1.0 (student project)"}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get("https://nominatim.openstreetmap.org/search", params=params, headers=headers)
            r.raise_for_status()
            rows = r.json()
        out = []
        for row in rows[:6]:
            name = row.get("name") or (row.get("display_name") or "").split(",")[0]
            out.append({"name": name or row.get("display_name", ""), "lat": float(row["lat"]), "lng": float(row["lon"])})
        return out
    except Exception:
        return []


# ------------------------------------------------------------------ AI
@router.get("/ai/status")
def ai_status():
    name = ai.provider()
    return {"provider": name or "rules", "model": gemini.model_name() if name == "gemini" else ai.MODEL if name else None,
            "claude": name == "claude"}


@router.post("/ai/parse")
def ai_parse(body: ParseIn):
    source, prefs = ai.parse_request(body.text)
    return {"source": source, "prefs": prefs}


@router.post("/ai/brief")
def ai_brief(body: BriefIn):
    try:
        source, days = ai.brief(body.trip)
    except Exception:
        source, days = "rules", []
    return {"source": source, "days": days}


# ------------------------------------------------------------------ export
@router.post("/export/pdf")
def export_pdf(body: BriefIn):
    if not body.trip.get("days"):
        raise HTTPException(status_code=400, detail="This trip has no days to export. Plan the trip first.")
    try:
        content = pdf.build_pdf(body.trip)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Couldn't read this trip for the PDF: {exc}") from exc
    return Response(content, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{pdf.filename(body.trip)}"'})


# ------------------------------------------------------------------ auth
@router.post("/auth/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    email = body.email.lower().strip()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = User(name=body.name.strip(), email=email, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenOut(access_token=create_token(user.id), user=UserOut.model_validate(user))


@router.post("/auth/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == form.username.lower().strip()))
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password",
                            headers={"WWW-Authenticate": "Bearer"})
    return TokenOut(access_token=create_token(user.id), user=UserOut.model_validate(user))


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return UserOut.model_validate(user)


# ------------------------------------------------------------------ trips
@router.post("/trips", response_model=TripOut, status_code=201)
def create_trip(body: TripIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    city, start, n = _trip_meta(body.data)
    t = Trip(user_id=user.id, title=body.title.strip(), city=city, start_date=start, days=n,
             share_slug=secrets.token_urlsafe(8), data=body.data)
    db.add(t)
    db.commit()
    db.refresh(t)
    return _trip_out(t)


@router.get("/trips", response_model=list[TripOut])
def list_trips(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Trip).where(Trip.user_id == user.id).order_by(Trip.updated_at.desc(), Trip.id.desc()))
    return [_trip_out(t, with_data=False) for t in rows]


@router.get("/trips/{trip_id}", response_model=TripOut)
def get_trip(trip_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _trip_out(_own_trip(db, trip_id, user))


@router.put("/trips/{trip_id}", response_model=TripOut)
def update_trip(trip_id: int, body: TripUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = _own_trip(db, trip_id, user)
    if body.title is not None:
        t.title = body.title.strip()
    if body.data is not None:
        t.city, t.start_date, t.days = _trip_meta(body.data)
        t.data = body.data
    t.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(t)
    return _trip_out(t)


@router.delete("/trips/{trip_id}", status_code=204)
def delete_trip(trip_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = _own_trip(db, trip_id, user)
    db.delete(t)
    db.commit()
    return None


@router.get("/share/{slug}", response_model=TripOut)
def shared_trip(slug: str, db: Session = Depends(get_db)):
    t = db.scalar(select(Trip).where(Trip.share_slug == slug))
    if t is None:
        raise HTTPException(status_code=404, detail="Shared trip not found")
    return _trip_out(t)
