import httpx
import pytest
from fastapi.testclient import TestClient

from app import ai, discover, gemini
from app.database import SessionLocal
from app.main import app
from app.models import DiscoveredCity


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _trip(client, city="jaipur"):
    return client.post("/api/plan", json={"city": city, "start_date": "2026-11-05", "days": 2}).json()


def test_pdf_export_returns_a_pdf(client):
    trip = _trip(client)
    trip["brief"] = client.post("/api/ai/brief", json={"trip": trip}).json()
    r = client.post("/api/export/pdf", json={"trip": trip})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert 'filename="travelsphere-jaipur-2026-11-05.pdf"' in r.headers["content-disposition"]
    assert r.content.startswith(b"%PDF")


def test_pdf_export_handles_non_latin_names(client):
    trip = _trip(client, "tokyo")
    trip["days"][0]["items"][1]["place"]["name"] = "浅草寺 Sensō-ji"
    assert client.post("/api/export/pdf", json={"trip": trip}).status_code == 200


def test_pdf_export_rejects_empty_trip(client):
    r = client.post("/api/export/pdf", json={"trip": {}})
    assert r.status_code == 400
    assert "Plan the trip first" in r.json()["detail"]


def test_status_reports_rules_when_ai_is_off(client):
    assert client.get("/api/ai/status").json()["provider"] == "rules"


def _fake_transport(responses):
    """Serve canned responses in order and record which model each request hit."""
    calls = []

    def handler(request: httpx.Request):
        calls.append(request.url.path.split("/")[-1].split(":")[0])
        return responses.pop(0)

    return httpx.MockTransport(handler), calls


def test_gemini_falls_through_busy_models(monkeypatch):
    ok = {"candidates": [{"content": {"parts": [{"text": '{"days": []}'}]}}]}
    transport, calls = _fake_transport([httpx.Response(503, json={}), httpx.Response(404, json={}),
                                        httpx.Response(200, json=ok)])
    real_client = httpx.Client
    monkeypatch.setattr(gemini.httpx, "Client", lambda **kw: real_client(transport=transport, **kw))
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODELS", "a-busy,b-retired,c-ok")

    out = gemini.generate_json("system", "user", ai.TripBrief)

    assert out.days == []
    assert calls == ["a-busy", "b-retired", "c-ok"]


def test_gemini_failure_falls_back_to_rules(monkeypatch):
    monkeypatch.setenv("TRAVELSPHERE_AI", "on")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(gemini, "generate_json", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("all busy")))
    source, prefs = ai.parse_request("2 days in Rome, must see the Colosseum")
    assert source == "rules"
    assert prefs["city"] == "rome"


def _fake_guide(name="Bengaluru", n=8, far=0):
    centre = (12.9716, 77.5946)
    places = [ai_place(f"Sight {i}", centre[0] + i * 0.004, centre[1] + i * 0.003) for i in range(n)]
    places += [ai_place(f"Far {i}", 20.0, 80.0) for i in range(far)]
    return discover.GenCity(name=name, country="India", tz="Asia/Kolkata", currency="INR", symbol="₹",
                            lat=centre[0], lng=centre[1], places=places)


def ai_place(name, lat, lng):
    return discover.GenPlace(name=name, kind="Park", tags=["nature", "bogus"], lat=lat, lng=lng, duration=999,
                             price=-5, open="25:00", close="18:00", closed_days=[0, 9], best="noon",
                             popularity=42, blurb="A place.")


@pytest.fixture()
def fake_ai(monkeypatch):
    monkeypatch.setattr(discover.ai, "provider", lambda: "gemini")
    monkeypatch.setattr(discover, "_geocode", lambda q: {"lat": 12.9716, "lng": 77.5946, "country": "India"})
    yield monkeypatch
    with SessionLocal() as db:  # saved guides are reloaded on every request, so remove them too
        db.query(DiscoveredCity).delete()
        db.commit()
    for cid in [c for c, v in list(discover.CITIES.items()) if v.get("generated")]:
        discover.CITIES.pop(cid)
        discover.PLACES.pop(cid)


def test_discover_builds_cleans_and_caches_a_city(client, fake_ai):
    calls = []
    fake_ai.setattr(discover.ai, "call_llm", lambda *a, **k: calls.append(a) or _fake_guide(far=2))

    r = client.post("/api/cities/discover", json={"name": "banglre"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] is True and body["places"] == 8  # the 2 far-away places were dropped
    city = body["city"]
    assert city["id"] == "bengaluru" and city["generated"] and city["tz"] == "Asia/Kolkata"

    place = client.get("/api/cities/bengaluru/places").json()[0]
    assert place["tags"] == ["nature"] and place["duration"] == 300 and place["price"] == 0
    assert (place["open"], place["close"], place["closed_days"], place["best"], place["popularity"]) == \
        ("09:00", "18:00", [0], "any", 10)

    trip = client.post("/api/plan", json={"city": "bengaluru", "start_date": "2026-11-05", "days": 2}).json()
    assert trip["city"]["id"] == "bengaluru" and trip["metrics"]["stops"] > 0

    again = client.post("/api/cities/discover", json={"name": "Bengaluru"}).json()
    assert again["created"] is False and len(calls) == 1


def test_discover_reports_unknown_city(client, fake_ai):
    fake_ai.setattr(discover.ai, "call_llm", lambda *a, **k: _fake_guide(name="Nowhere", n=0))
    r = client.post("/api/cities/discover", json={"name": "zzqqxx"})
    assert r.status_code == 404 and "Check the spelling" in r.json()["detail"]


def test_discover_needs_an_ai_key(client):
    r = client.post("/api/cities/discover", json={"name": "Lisbon"})
    assert r.status_code == 503 and "GEMINI_API_KEY" in r.json()["detail"]
