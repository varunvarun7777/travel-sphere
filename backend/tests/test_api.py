import pytest
from fastapi.testclient import TestClient

from app import ai
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


PLAN_BODY = {"city": "paris", "start_date": "2026-11-13", "days": 2, "pace": "balanced", "mode": "auto",
             "interests": ["art", "views"], "must_see": ["eiffel"], "avoid": [], "base": None, "custom_places": []}


def _register(client, email="alice@example.com", password="secret123", name="Alice"):
    return client.post("/api/auth/register", json={"name": name, "email": email, "password": password})


def _auth(client, email):
    r = _register(client, email=email)
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_cities_and_places(client):
    cities = client.get("/api/cities").json()
    assert {c["id"] for c in cities} == {"paris", "rome", "tokyo", "jaipur"}
    assert set(cities[0]) == {"id", "name", "country", "lat", "lng", "tz", "currency", "symbol"}
    places = client.get("/api/cities/rome/places").json()
    p = places[0]
    assert set(p) == {"id", "name", "kind", "tags", "lat", "lng", "duration", "price", "open", "close",
                      "closed_days", "best", "popularity", "blurb", "custom"}
    assert client.get("/api/cities/atlantis/places").status_code == 400


def test_plan_contract(client):
    r = client.post("/api/plan", json=PLAN_BODY)
    assert r.status_code == 200, r.text
    trip = r.json()
    assert set(trip) == {"city", "prefs", "base", "days", "unplaced", "custom_places", "metrics"}
    assert trip["prefs"]["start_date"] == "2026-11-13"
    assert trip["base"] == {"id": "base", "name": "City centre", "lat": 48.8566, "lng": 2.3522}
    assert set(trip["metrics"]) == {"stops", "km", "walk_km", "travel_min", "fees", "naive_km", "saved_pct"}
    day = trip["days"][0]
    assert set(day) == {"date", "label", "weekday", "sunset", "start", "end", "stops", "locked", "items",
                        "metrics", "warnings"}
    assert day["label"] == "Fri 13 Nov"
    assert set(day["metrics"]) == {"stops", "km", "walk_km", "travel_min", "fees", "finish", "naive_km"}
    kinds = {it["type"] for it in day["items"]}
    assert {"travel", "stop"} <= kinds
    for it in day["items"]:
        if it["type"] == "travel":
            assert set(it) == {"type", "mode", "km", "minutes", "from", "to"}
        elif it["type"] == "stop":
            assert set(it) == {"type", "id", "place", "arrive", "start", "end", "wait", "warnings"}
        else:
            assert set(it) == {"type", "start", "end", "suggestion"}
    assert any("eiffel" in d["stops"] for d in trip["days"])


def test_plan_with_base_and_custom(client):
    body = dict(PLAN_BODY, base={"name": "Hotel", "lat": 48.87, "lng": 2.33},
                custom_places=[{"id": "custom:cafe", "name": "Cafe", "lat": 48.86, "lng": 2.35}])
    trip = client.post("/api/plan", json=body).json()
    assert trip["base"]["name"] == "Hotel"
    assert trip["custom_places"][0]["duration"] == 60
    assert any("custom:cafe" in d["stops"] for d in trip["days"])


def test_plan_errors(client):
    assert client.post("/api/plan", json=dict(PLAN_BODY, city="atlantis")).status_code == 400
    r = client.post("/api/plan", json=dict(PLAN_BODY, must_see=["nope"]))
    assert r.status_code == 400 and "nope" in r.json()["detail"]
    assert client.post("/api/plan", json=dict(PLAN_BODY, days=9)).status_code == 422


def test_schedule(client):
    body = {"city": "rome", "date": "2026-11-12", "pace": "balanced", "mode": "walk", "base": None,
            "start": "09:30", "end": "18:30", "stops": ["trevi", "colosseum", "pantheon", "piazza_navona"],
            "locked": ["colosseum"], "custom_places": [], "optimize": True}
    r = client.post("/api/schedule", json=body)
    assert r.status_code == 200, r.text
    day = r.json()
    assert day["start"] == "09:30" and day["end"] == "18:30"
    assert day["stops"][1] == "colosseum"
    assert day["metrics"]["km"] <= day["metrics"]["naive_km"] + 1e-9
    r = client.post("/api/schedule", json=dict(body, optimize=False))
    assert r.json()["stops"] == body["stops"]
    assert client.post("/api/schedule", json=dict(body, stops=["trevi", "bogus"])).status_code == 400
    assert client.post("/api/schedule", json=dict(body, city="nowhere")).status_code == 400
    many = [p["id"] for p in client.get("/api/cities/rome/places").json()][:13]
    assert client.post("/api/schedule", json=dict(body, stops=many, locked=[])).status_code == 400


def test_geocode_handles_errors(client, monkeypatch):
    import httpx

    class Boom:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx, "AsyncClient", Boom)
    assert client.get("/api/geocode", params={"q": "hotel", "city": "paris"}).json() == []
    assert client.get("/api/geocode", params={"q": "", "city": "paris"}).json() == []
    assert client.get("/api/geocode", params={"q": "x", "city": "nowhere"}).status_code == 400


def test_ai_status_and_parse_rules(client):
    assert client.get("/api/ai/status").json() == {"provider": "rules", "model": None, "claude": False}
    r = client.post("/api/ai/parse", json={"text": "3 days in Rome, ancient ruins and street food, by metro, "
                                                   "must see the Colosseum but skip the Vatican Museums, relaxed"})
    body = r.json()
    assert body["source"] == "rules"
    prefs = body["prefs"]
    assert prefs["city"] == "rome" and prefs["days"] == 3
    assert prefs["pace"] == "relaxed" and prefs["mode"] == "transit"
    assert {"history", "food"} <= set(prefs["interests"])
    assert prefs["must_see"] == ["colosseum"]
    assert prefs["avoid"] == ["vatican_museums"]
    assert set(prefs) == {"city", "new_city", "days", "start_date", "pace", "mode", "interests", "must_see", "avoid"}


def test_parse_variants():
    _, p = ai.parse_request("A weekend in the Pink City from 2026-12-05, Amber Fort, shopping and markets, taxi")
    assert p["city"] == "jaipur" and p["days"] == 2 and p["start_date"] == "2026-12-05"
    assert p["must_see"] == ["amber_fort"] and p["mode"] == "drive" and "shopping" in p["interests"]
    _, p = ai.parse_request("a week, eiffel tower and louvre, packed, on foot, museums")
    assert p["city"] == "paris" and p["days"] == 7 and p["pace"] == "packed" and p["mode"] == "walk"
    assert set(p["must_see"]) == {"eiffel", "louvre"} and "art" in p["interests"]


def test_claude_failure_falls_back(monkeypatch):
    monkeypatch.setattr(ai, "claude_available", lambda: True)

    def boom(*a, **k):
        raise RuntimeError("no network")

    monkeypatch.setattr(ai, "_call_claude", boom)
    source, prefs = ai.parse_request("two days in tokyo")
    assert source == "rules" and prefs["city"] == "tokyo"


def test_brief_rules(client):
    trip = client.post("/api/plan", json=PLAN_BODY).json()
    r = client.post("/api/ai/brief", json={"trip": trip})
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "rules"
    assert [d["date"] for d in body["days"]] == [d["date"] for d in trip["days"]]
    for d in body["days"]:
        assert len(d["title"].split()) <= 6
        assert 2 <= len(d["tips"]) <= 3
        assert d["summary"]
    tips = " ".join(t for d in body["days"] for t in d["tips"])
    assert "Eiffel" in tips


def test_auth_flow(client):
    r = _register(client, email="Bob@Example.com")
    assert r.status_code == 201
    data = r.json()
    assert data["token_type"] == "bearer" and data["user"]["email"] == "bob@example.com"
    assert _register(client, email="bob@example.com").status_code == 409
    assert _register(client, email="short@example.com", password="123").status_code == 422

    r = client.post("/api/auth/login", data={"username": "bob@example.com", "password": "secret123"})
    assert r.status_code == 200
    token = r.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["email"] == "bob@example.com"
    assert client.post("/api/auth/login", data={"username": "bob@example.com", "password": "wrong!"}).status_code == 401
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_trips_crud_and_share(client):
    h1 = _auth(client, "carol@example.com")
    h2 = _auth(client, "dave@example.com")
    trip = client.post("/api/plan", json=PLAN_BODY).json()

    assert client.post("/api/trips", json={"title": "Paris", "data": trip}).status_code == 401
    r = client.post("/api/trips", json={"title": "Paris weekend", "data": trip}, headers=h1)
    assert r.status_code == 201, r.text
    saved = r.json()
    assert saved["city"] == "paris" and saved["start_date"] == "2026-11-13" and saved["days"] == 2
    assert saved["share_slug"] and saved["data"]["city"]["id"] == "paris"
    tid = saved["id"]

    listing = client.get("/api/trips", headers=h1).json()
    assert len(listing) == 1 and listing[0]["data"] is None
    assert client.get("/api/trips", headers=h2).json() == []

    assert client.get(f"/api/trips/{tid}", headers=h1).json()["title"] == "Paris weekend"
    assert client.get(f"/api/trips/{tid}", headers=h2).status_code == 404
    assert client.get("/api/trips/99999", headers=h1).status_code == 404

    r = client.put(f"/api/trips/{tid}", json={"title": "Renamed"}, headers=h1)
    assert r.status_code == 200 and r.json()["title"] == "Renamed"
    assert client.put(f"/api/trips/{tid}", json={"title": "Hijack"}, headers=h2).status_code == 404

    shared = client.get(f"/api/share/{saved['share_slug']}")
    assert shared.status_code == 200 and shared.json()["title"] == "Renamed"
    assert client.get("/api/share/does-not-exist").status_code == 404

    assert client.delete(f"/api/trips/{tid}", headers=h2).status_code == 404
    assert client.delete(f"/api/trips/{tid}", headers=h1).status_code == 204
    assert client.get(f"/api/trips/{tid}", headers=h1).status_code == 404
    assert client.post("/api/trips", json={"title": "Bad", "data": {"days": []}}, headers=h1).status_code == 400
