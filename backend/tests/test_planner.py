from datetime import date, timedelta

import pytest

from app.cities import CITIES, PLACES, place_index
from app.planner import (PACES, build_place_map, make_base, make_ctx, make_leg, optimize, parse_hm, plan,
                         schedule, simulate, sunset_minutes)


def req(city="paris", start="2026-11-12", days=3, pace="balanced", mode="auto", interests=None,
        must_see=None, avoid=None, base=None, custom_places=None):
    return {"city": city, "start_date": start, "days": days, "pace": pace, "mode": mode,
            "interests": interests or [], "must_see": must_see or [], "avoid": avoid or [],
            "base": base, "custom_places": custom_places or []}


def stops_of(day):
    return [it for it in day["items"] if it["type"] == "stop"]


@pytest.mark.parametrize("city", list(CITIES))
@pytest.mark.parametrize("days", range(1, 8))
def test_every_city_plans_1_to_7_days(city, days):
    trip = plan(req(city=city, days=days, interests=["art", "food"]))
    assert len(trip["days"]) == days
    assert trip["metrics"]["stops"] == sum(len(d["stops"]) for d in trip["days"])
    seen = [s for d in trip["days"] for s in d["stops"]]
    assert len(seen) == len(set(seen)), "a place appears twice"
    for d in trip["days"]:
        assert d["stops"], "no day should be empty when the city has enough places"
        assert len(d["stops"]) <= PACES["balanced"]["max_stops"]
        assert [it["id"] for it in stops_of(d)] == d["stops"]
        assert d["label"] and len(d["sunset"]) == 5
    assert trip["base"]["id"] == "base" and trip["base"]["name"] == "City centre"


def test_leg_modes():
    assert make_leg(1.0, "auto")[0] == "walk"
    assert make_leg(3.0, "auto")[0] == "transit"
    assert make_leg(0.5, "transit")[0] == "walk"
    mode, km, minutes = make_leg(4.6, "walk")
    assert (mode, minutes) == ("walk", 60)
    assert make_leg(19.0, "transit")[2] == 69
    assert make_leg(22.0, "drive")[2] == 67


def test_sunset_is_plausible():
    # Paris: ~21:58 around midsummer, ~16:55 in mid-December
    assert abs(sunset_minutes(date(2026, 6, 21), 48.8566, 2.3522, "Europe/Paris") - parse_hm("21:58")) <= 6
    assert abs(sunset_minutes(date(2026, 12, 15), 48.8566, 2.3522, "Europe/Paris") - parse_hm("16:54")) <= 6
    # Tokyo late October ~16:55
    assert abs(sunset_minutes(date(2026, 10, 29), 35.6812, 139.7671, "Asia/Tokyo") - parse_hm("16:52")) <= 8


def test_closed_days_avoided_louvre_not_on_tuesday():
    # 2026-11-09 is a Monday -> trip covers Mon, Tue, Wed
    for d0 in range(0, 7):
        start = (date(2026, 11, 9) + timedelta(days=d0)).isoformat()
        trip = plan(req(start=start, days=3, interests=["art"], must_see=["louvre", "orsay"]))
        for d in trip["days"]:
            for s in d["stops"]:
                assert d["weekday"] not in place_index("paris")[s]["closed_days"], (start, d["label"], s)
        placed = {s for d in trip["days"] for s in d["stops"]}
        assert {"louvre", "orsay"} <= placed


def test_vatican_not_on_sunday_and_tokyo_gardens():
    trip = plan(req(city="rome", start="2026-11-14", days=2, must_see=["vatican_museums", "borghese"]))  # Sat, Sun
    by_id = {s: d for d in trip["days"] for s in d["stops"]}
    assert by_id["vatican_museums"]["weekday"] != 6
    trip = plan(req(city="tokyo", start="2026-11-16", days=3, must_see=["imperial_east_gardens",
                                                                     "tokyo_national_museum"]))  # Mon..Wed
    for d in trip["days"]:
        for s in d["stops"]:
            assert d["weekday"] not in place_index("tokyo")[s]["closed_days"]


def test_must_see_closed_every_day_goes_to_unplaced():
    trip = plan(req(start="2026-11-10", days=1, must_see=["louvre"]))  # Tuesday only
    assert any(u["id"] == "louvre" and "Closed" in u["reason"] for u in trip["unplaced"])
    assert all("louvre" not in d["stops"] for d in trip["days"])


def test_must_see_and_avoid_respected():
    trip = plan(req(days=2, must_see=["catacombs"], avoid=["eiffel", "louvre"]))
    placed = {s for d in trip["days"] for s in d["stops"]}
    assert "catacombs" in placed
    assert not placed & {"eiffel", "louvre"}


def test_optimised_km_not_worse_than_naive():
    places = build_place_map("paris", [])
    city = CITIES["paris"]
    ctx = make_ctx(city, date(2026, 11, 12), "packed", "walk", make_base(city, None), places)
    given = ["luxembourg", "arc_triomphe", "notre_dame", "rue_cler", "marais", "invalides", "latin_quarter"]
    naive = simulate(ctx, given).km
    best = optimize(ctx, given)
    assert sorted(best) == sorted(given)
    assert simulate(ctx, best).km <= naive + 1e-9
    # trip-level metric too
    trip = plan(req(days=3, interests=["art", "food"]))
    assert trip["metrics"]["km"] <= trip["metrics"]["naive_km"]
    assert 0 <= trip["metrics"]["saved_pct"] <= 100


def test_heuristic_path_for_many_stops():
    places = build_place_map("rome", [])
    city = CITIES["rome"]
    ctx = make_ctx(city, date(2026, 11, 12), "packed", "walk", make_base(city, None), places)
    given = ["trevi", "ghetto", "spanish_steps", "monti", "piazza_navona", "pantheon", "pincio", "campo_de_fiori",
             "capitoline", "trastevere"]
    best = optimize(ctx, given)  # 10 free stops -> NN + 2-opt + relocate
    assert sorted(best) == sorted(given)
    assert simulate(ctx, best).cost <= simulate(ctx, given).cost


def test_locked_stops_keep_their_index():
    day = schedule({"city": "paris", "date": "2026-11-12", "pace": "packed", "mode": "auto", "base": None,
                    "start": None, "end": None,
                    "stops": ["luxembourg", "eiffel", "marais", "sainte_chapelle", "arc_triomphe", "rodin"],
                    "locked": ["eiffel", "rodin"], "custom_places": [], "optimize": True})
    assert day["stops"][1] == "eiffel"
    assert day["stops"][5] == "rodin"
    assert day["locked"] == ["eiffel", "rodin"]
    assert sorted(day["stops"]) == sorted(["luxembourg", "eiffel", "marais", "sainte_chapelle", "arc_triomphe", "rodin"])


def test_schedule_without_optimize_keeps_order():
    order = ["arc_triomphe", "notre_dame", "eiffel", "marais"]
    day = schedule({"city": "paris", "date": "2026-11-12", "stops": order, "optimize": False})
    assert day["stops"] == order
    assert day["metrics"]["naive_km"] == day["metrics"]["km"]


def test_sunset_place_scheduled_near_sunset():
    # Jaipur in November: sunset ~17:35, Nahargarh is a sunset viewpoint
    trip = plan(req(city="jaipur", start="2026-11-12", days=2, must_see=["nahargarh"], interests=["views"]))
    day = next(d for d in trip["days"] if "nahargarh" in d["stops"])
    stop = next(it for it in stops_of(day) if it["id"] == "nahargarh")
    diff = abs(parse_hm(stop["start"]) - (parse_hm(day["sunset"]) - 45))
    assert diff <= 60, (stop, day["sunset"])

    # single-day schedule: Eiffel Tower should be pushed towards golden hour
    day = schedule({"city": "paris", "date": "2026-12-01", "stops": ["eiffel", "louvre", "rue_cler"],
                    "pace": "balanced"})
    eiffel = next(it for it in stops_of(day) if it["id"] == "eiffel")
    assert abs(parse_hm(eiffel["start"]) - (parse_hm(day["sunset"]) - 45)) <= 45


def test_times_respect_opening_hours():
    for city in CITIES:
        trip = plan(req(city=city, start="2026-11-12", days=3, pace="balanced", interests=["history", "food"]))
        idx = place_index(city)
        for d in trip["days"]:
            for it in stops_of(d):
                p = idx[it["id"]]
                assert parse_hm(it["start"]) >= parse_hm(p["open"]), (city, it)
                if not it["warnings"]:
                    assert parse_hm(it["end"]) <= parse_hm(p["close"]), (city, it)
                assert it["wait"] == parse_hm(it["start"]) - parse_hm(it["arrive"])


def test_lunch_inserted_with_suggestion():
    trip = plan(req(city="rome", start="2026-11-12", days=1, interests=["food", "history"]))
    lunches = [it for it in trip["days"][0]["items"] if it["type"] == "lunch"]
    assert len(lunches) == 1
    assert parse_hm(lunches[0]["start"]) >= parse_hm("12:15")
    assert lunches[0]["suggestion"].startswith("Lunch near")


def test_far_place_uses_transit_or_drive():
    day = schedule({"city": "jaipur", "date": "2026-11-12", "stops": ["chokhi_dhani"], "mode": "auto",
                    "pace": "packed"})
    travel = [it for it in day["items"] if it["type"] == "travel"]
    assert travel[0]["mode"] == "transit" and travel[0]["km"] > 15
    day = schedule({"city": "jaipur", "date": "2026-11-12", "stops": ["chokhi_dhani"], "mode": "drive",
                    "pace": "packed"})
    assert all(it["mode"] == "drive" for it in day["items"] if it["type"] == "travel")


def test_nightlife_extends_day():
    trip = plan(req(city="tokyo", days=1, interests=["nightlife"]))
    assert trip["days"][0]["end"] >= "22:00"


def test_custom_place_included():
    custom = {"id": "custom:hotel-bar", "name": "Hotel bar", "lat": 48.8600, "lng": 2.3400, "duration": 45}
    trip = plan(req(days=2, custom_places=[custom]))
    placed = {s for d in trip["days"] for s in d["stops"]}
    assert "custom:hotel-bar" in placed
    item = next(it for d in trip["days"] for it in stops_of(d) if it["id"] == "custom:hotel-bar")
    assert item["place"]["custom"] is True
    assert trip["custom_places"][0]["id"] == "custom:hotel-bar"


def test_deterministic():
    a = plan(req(city="tokyo", days=4, pace="packed", interests=["food", "art", "views"]))
    b = plan(req(city="tokyo", days=4, pace="packed", interests=["food", "art", "views"]))
    assert a == b


def test_place_data_shape():
    tags = {"art", "history", "architecture", "nature", "food", "nightlife", "shopping", "views", "religion", "local"}
    for city, plist in PLACES.items():
        assert 17 <= len(plist) <= 22
        assert sum("food" in p["tags"] for p in plist) >= 3
        for p in plist:
            assert set(p["tags"]) <= tags
            assert p["best"] in {"any", "morning", "sunset", "evening"}
            assert parse_hm(p["open"]) < parse_hm(p["close"])
            assert abs(p["lat"] - CITIES[city]["lat"]) < 0.5 and abs(p["lng"] - CITIES[city]["lng"]) < 0.5
    assert all(p["id"] != "pompidou" for p in PLACES["paris"])
