"""Seed a demo account (demo@travelsphere.app / demo1234) with one saved sample trip.

Run from the backend folder:  python seed.py
"""
from __future__ import annotations

import secrets
from datetime import date, timedelta

from sqlalchemy import select

from app.database import SessionLocal, init_db
from app.models import Trip, User
from app.planner import plan
from app.security import hash_password

DEMO_EMAIL = "demo@travelsphere.app"
DEMO_PASSWORD = "demo1234"


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == DEMO_EMAIL))
        if user is None:
            user = User(name="Demo Traveller", email=DEMO_EMAIL, password_hash=hash_password(DEMO_PASSWORD))
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"Created demo user {DEMO_EMAIL} / {DEMO_PASSWORD}")
        else:
            print(f"Demo user {DEMO_EMAIL} already exists")

        if not db.scalar(select(Trip).where(Trip.user_id == user.id)):
            start = date.today() + timedelta(days=14)
            req = {
                "city": "paris", "start_date": start.isoformat(), "days": 3, "pace": "balanced", "mode": "auto",
                "interests": ["art", "food", "views"], "must_see": ["eiffel", "louvre"], "avoid": [],
                "base": None, "custom_places": [],
            }
            data = plan(req)
            trip = Trip(user_id=user.id, title="Paris highlights — 3 days", city="paris",
                        start_date=data["days"][0]["date"], days=len(data["days"]),
                        share_slug=secrets.token_urlsafe(8), data=data)
            db.add(trip)
            db.commit()
            print(f"Saved sample trip '{trip.title}' (share slug: {trip.share_slug})")
        else:
            print("Demo user already has saved trips")
    finally:
        db.close()


if __name__ == "__main__":
    main()
