"""TravelSphere itinerary optimiser.

Pipeline for a multi-day plan:
  1. score + select places (interests, must-see, time budget, opening days)
  2. split into days with capacity-balanced geographic k-means
  3. assign day clusters to dates minimising closed-day conflicts
  4. order each day by minimising a simulated-day cost (travel + waiting + penalties)
     - exact brute force for <= 7 free stops, otherwise NN + 2-opt + relocate
  5. drop low-value stops from overrunning days

Everything is deterministic: no randomness, and every tie is broken by a stable key.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .cities import CITIES, city_places

# ---------------------------------------------------------------- constants
DETOUR = 1.3
WALK_KMH = 4.6
TRANSIT_KMH, TRANSIT_OVERHEAD = 19.0, 9
DRIVE_KMH, DRIVE_OVERHEAD = 22.0, 7
AUTO_WALK_MAX_KM = 1.6
TRANSIT_MIN_KM = 0.8

PACES = {
    "relaxed": {"start": 10 * 60, "end": 18 * 60, "lunch": 75, "max_stops": 4},
    "balanced": {"start": 9 * 60, "end": 19 * 60, "lunch": 60, "max_stops": 6},
    "packed": {"start": 8 * 60 + 30, "end": 21 * 60, "lunch": 45, "max_stops": 8},
}
MODES = ("auto", "walk", "transit", "drive")
NIGHTLIFE_END = 22 * 60
LUNCH_AFTER = 12 * 60 + 15
LUNCH_LATEST = 13 * 60
LUNCH_RADIUS_KM = 1.2
TRAVEL_BUFFER = 25          # minutes of travel budgeted per stop during selection
WAIT_WEIGHT = 0.6
CLOSED_PENALTY = 400
CLOSING_PENALTY = 200
CLOSING_PER_MIN = 4
OVERRUN_PER_MIN = 3
MORNING_LIMIT = 11 * 60
EVENING_FROM = 18 * 60
DROP_TOLERANCE = 30
BRUTE_FORCE_MAX = 7
KMEANS_ITERS = 12

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WEEKDAYS_LONG = ["Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays"]


class PlannerError(ValueError):
    """Raised for invalid input (unknown city / place ids); maps to HTTP 400."""


# ---------------------------------------------------------------- helpers
def hm(t: float) -> str:
    t = int(round(t))
    return f"{(t // 60) % 24:02d}:{t % 60:02d}"


def parse_hm(s: str) -> int:
    h, m = s.strip().split(":")
    h, m = int(h), int(m)
    if not (0 <= h <= 24 and 0 <= m < 60):
        raise PlannerError(f"Invalid time '{s}'")
    return h * 60 + m


def haversine(lat1, lng1, lat2, lng2) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def route_km(a: dict, b: dict) -> float:
    return haversine(a["lat"], a["lng"], b["lat"], b["lng"]) * DETOUR


def make_leg(km: float, mode: str) -> tuple[str, float, int]:
    """Return (mode, km, minutes) for a leg of ``km`` road distance."""
    if mode == "auto":
        mode = "walk" if km <= AUTO_WALK_MAX_KM else "transit"
    if mode == "transit" and km < TRANSIT_MIN_KM:
        mode = "walk"
    if mode == "walk":
        minutes = km / WALK_KMH * 60
    elif mode == "transit":
        minutes = km / TRANSIT_KMH * 60 + TRANSIT_OVERHEAD
    else:  # drive
        minutes = km / DRIVE_KMH * 60 + DRIVE_OVERHEAD
    return mode, km, int(round(minutes))


def sunset_minutes(day: date, lat: float, lng: float, tz: str) -> int:
    """Local sunset (minutes after midnight) via the NOAA solar approximation."""
    n = day.timetuple().tm_yday
    g = 2 * math.pi / 365 * (n - 1)
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                       - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
            + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    lat_r = math.radians(lat)
    cos_ha = (math.cos(math.radians(90.833)) / (math.cos(lat_r) * math.cos(decl))
              - math.tan(lat_r) * math.tan(decl))
    ha = math.degrees(math.acos(max(-1.0, min(1.0, cos_ha))))
    utc_min = 720 - 4 * (lng - ha) - eqtime
    offset = datetime(day.year, day.month, day.day, 12, tzinfo=ZoneInfo(tz)).utcoffset()
    local = utc_min + offset.total_seconds() / 60
    return int(round(local)) % (24 * 60)


def day_label(d: date) -> str:
    return f"{WEEKDAYS[d.weekday()]} {d.day} {d.strftime('%b')}"


def to_date(v) -> date:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v))
    except ValueError as exc:
        raise PlannerError(f"Invalid date '{v}' (expected YYYY-MM-DD)") from exc


def custom_place(c: dict) -> dict:
    return {
        "id": str(c["id"]), "name": c.get("name") or "My place", "kind": "Landmark", "tags": [],
        "lat": float(c["lat"]), "lng": float(c["lng"]), "duration": int(c.get("duration") or 60),
        "price": 0, "open": "00:00", "close": "23:59", "closed_days": [], "best": "any",
        "popularity": 5, "blurb": "A place you added.", "custom": True,
    }


def build_place_map(city_id: str, custom_places: list | None) -> dict[str, dict]:
    if city_id not in CITIES:
        raise PlannerError(f"Unknown city '{city_id}'")
    places = {p["id"]: p for p in city_places(city_id)}
    for c in custom_places or []:
        c = c if isinstance(c, dict) else c.model_dump()
        cp = custom_place(c)
        if cp["id"] in places:
            raise PlannerError(f"Custom place id '{cp['id']}' clashes with an existing place")
        places[cp["id"]] = cp
    return places


def check_ids(ids, places: dict, what: str = "place") -> None:
    unknown = [i for i in ids if i not in places]
    if unknown:
        raise PlannerError(f"Unknown {what} id(s): {', '.join(unknown)}")


def make_base(city: dict, base) -> dict:
    if base:
        b = base if isinstance(base, dict) else base.model_dump()
        return {"id": "base", "name": b.get("name") or "My base", "lat": float(b["lat"]), "lng": float(b["lng"])}
    return {"id": "base", "name": "City centre", "lat": city["lat"], "lng": city["lng"]}


# ---------------------------------------------------------------- day context
@dataclass
class DayCtx:
    day: date
    start: int
    end: int
    lunch: int
    mode: str
    base: dict
    places: dict
    sunset: int
    food: list = field(default_factory=list)
    _legs: dict = field(default_factory=dict)
    _info: dict = field(default_factory=dict)

    @property
    def weekday(self) -> int:
        return self.day.weekday()

    def loc(self, pid: str) -> dict:
        return self.base if pid == "base" else self.places[pid]

    def leg(self, a: str, b: str) -> tuple[str, float, int]:
        key = (a, b)
        v = self._legs.get(key)
        if v is None:
            v = make_leg(route_km(self.loc(a), self.loc(b)), self.mode)
            self._legs[key] = v
        return v

    def info(self, pid: str):
        v = self._info.get(pid)
        if v is None:
            p = self.places[pid]
            v = (parse_hm(p["open"]), parse_hm(p["close"]), int(p["duration"]),
                 frozenset(p["closed_days"]), p["best"], float(p["price"] or 0))
            self._info[pid] = v
        return v


def make_ctx(city: dict, day: date, pace: str, mode: str, base: dict, places: dict,
             start: int | None = None, end: int | None = None, nightlife: bool = False) -> DayCtx:
    if pace not in PACES:
        raise PlannerError(f"Unknown pace '{pace}'")
    if mode not in MODES:
        raise PlannerError(f"Unknown mode '{mode}'")
    cfg = PACES[pace]
    s = cfg["start"] if start is None else start
    e = cfg["end"] if end is None else end
    if nightlife:
        e = max(e, NIGHTLIFE_END)
    if e <= s:
        raise PlannerError("Day end must be after day start")
    food = [p for p in places.values() if "food" in p["tags"]]
    food.sort(key=lambda p: p["id"])
    return DayCtx(day=day, start=s, end=e, lunch=cfg["lunch"], mode=mode, base=base, places=places,
                  sunset=sunset_minutes(day, city["lat"], city["lng"], city["tz"]), food=food)


# ---------------------------------------------------------------- simulation
@dataclass
class Sim:
    cost: float
    km: float
    walk_km: float
    travel_min: int
    fees: float
    finish: int
    items: list
    warnings: list


def lunch_suggestion(ctx: DayCtx, near: str, exclude: set) -> str | None:
    if near == "base":
        return None
    here = ctx.places[near]
    best = None
    for f in ctx.food:
        if f["id"] in exclude:
            continue
        d = route_km(here, f)
        if d <= LUNCH_RADIUS_KM and (best is None or d < best[0]):
            best = (d, f)
    if best:
        return f"Lunch near {here['name']} — try {best[1]['name']}"
    return f"Lunch near {here['name']}"


def simulate(ctx: DayCtx, order, build: bool = False) -> Sim:
    t = ctx.start
    cost = 0.0
    km = walk = 0.0
    travel = 0
    fees = 0.0
    items: list = []
    day_warn: list = []
    lunched = ctx.lunch <= 0 or ctx.start >= LUNCH_AFTER
    prev = "base"
    wd = ctx.weekday
    in_day = set(order) if build else None

    def lunch_item(at, near):
        if build:
            items.append({"type": "lunch", "start": hm(at), "end": hm(at + ctx.lunch),
                          "suggestion": lunch_suggestion(ctx, near, in_day)})

    def lunch():
        nonlocal t, lunched
        lunch_item(t, prev)
        t += ctx.lunch
        lunched = True

    def go(dest):
        nonlocal t, cost, km, walk, travel, prev
        mode, k, m = ctx.leg(prev, dest)
        if build:
            items.append({"type": "travel", "mode": mode, "km": round(k, 2), "minutes": m,
                          "from": prev, "to": dest})
        t += m
        cost += m
        km += k
        travel += m
        if mode == "walk":
            walk += k

    for pid in order:
        if not lunched and t >= LUNCH_AFTER and prev != "base":
            lunch()
        o, c, dur, closed, best, price = ctx.info(pid)
        if prev == "base":
            # leave the base later rather than queueing outside a closed door
            t = max(t, o - ctx.leg("base", pid)[2])
            if t >= LUNCH_AFTER:
                lunched = True  # the day starts after lunch
        go(pid)
        arrive = t
        start = max(arrive, o)
        if best == "sunset":
            # linger (if the day allows) so the visit lines up with golden hour
            desired = min(ctx.sunset - 45, ctx.end - dur - 20, c - dur)
            if desired > start:
                start = desired
        wait = start - arrive
        idle = wait
        if not lunched and max(arrive, LUNCH_AFTER) + ctx.lunch <= start:
            lunch_item(max(arrive, LUNCH_AFTER), pid)  # eat during the wait
            lunched = True
            idle -= ctx.lunch
        cost += WAIT_WEIGHT * idle
        end = start + dur
        warns = []
        if wd in closed:
            cost += CLOSED_PENALTY
            warns.append(f"Closed on {WEEKDAYS_LONG[wd]}")
        elif end > c:
            over = end - c
            cost += CLOSING_PENALTY + CLOSING_PER_MIN * over
            if start >= c:
                warns.append(f"Closes at {hm(c)} — you'd arrive after closing")
            else:
                warns.append(f"Closes at {hm(c)} — visit runs {over} min past closing")
        if best == "morning" and arrive > MORNING_LIMIT:
            cost += 40 + 0.5 * (arrive - MORNING_LIMIT)
        elif best == "evening" and start < EVENING_FROM:
            cost += 40 + 0.5 * (EVENING_FROM - start)
        elif best == "sunset":
            cost += abs(start - (ctx.sunset - 45))
        fees += price
        if build:
            p = ctx.places[pid]
            items.append({"type": "stop", "id": pid, "place": p, "arrive": hm(arrive), "start": hm(start),
                          "end": hm(end), "wait": int(wait), "warnings": warns})
            day_warn.extend(f"{p['name']}: {w}" for w in warns)
        t = end
        prev = pid

    if order:
        if not lunched and t > LUNCH_LATEST:
            lunch()
        go("base")
    finish = t
    if finish > ctx.end:
        over = finish - ctx.end
        cost += OVERRUN_PER_MIN * over
        day_warn.append(f"Day runs {over} min past your {hm(ctx.end)} end time")
    return Sim(cost=cost, km=km, walk_km=walk, travel_min=travel, fees=fees, finish=finish,
               items=items, warnings=day_warn)


# ---------------------------------------------------------------- ordering
def optimize(ctx: DayCtx, ids, locked=()) -> list[str]:
    """Best visiting order. Locked ids keep their index; the rest are permuted."""
    ids = list(ids)
    lockset = set(locked) & set(ids)
    slots = [i for i, x in enumerate(ids) if x not in lockset]
    free = [ids[i] for i in slots]
    if len(free) <= 1:
        return ids

    def assemble(seq):
        o = list(ids)
        for s, x in zip(slots, seq):
            o[s] = x
        return o

    def cost(seq):
        return simulate(ctx, assemble(seq)).cost

    if len(free) <= BRUTE_FORCE_MAX:
        best_c, best_seq = None, None
        for perm in itertools.permutations(free):
            c = cost(perm)
            if best_c is None or c < best_c - 1e-9:
                best_c, best_seq = c, perm
        return assemble(best_seq)

    # Greedy nearest-neighbour construction respecting locked positions.
    remaining = list(free)
    nn: list[str] = []
    prev = "base"
    for i, x in enumerate(ids):
        if x in lockset:
            prev = x
            continue
        nxt = min(remaining, key=lambda r: (ctx.leg(prev, r)[2], ctx.leg(prev, r)[1], remaining.index(r)))
        remaining.remove(nxt)
        nn.append(nxt)
        prev = nxt

    best_c, best_seq = None, None
    for start_seq in (nn, free):
        seq, c = _local_search(list(start_seq), cost)
        if best_c is None or c < best_c - 1e-9:
            best_c, best_seq = c, seq
    return assemble(best_seq)


def _local_search(seq: list, cost, max_passes: int = 60):
    bc = cost(seq)
    m = len(seq)
    for _ in range(max_passes):
        improved = False
        # 2-opt: reverse a segment
        for i in range(m - 1):
            for j in range(i + 1, m):
                cand = seq[:i] + seq[i:j + 1][::-1] + seq[j + 1:]
                c = cost(cand)
                if c < bc - 1e-9:
                    seq, bc, improved = cand, c, True
        # relocate: move one stop elsewhere
        for i in range(m):
            for j in range(m):
                if i == j:
                    continue
                cand = list(seq)
                x = cand.pop(i)
                cand.insert(j, x)
                c = cost(cand)
                if c < bc - 1e-9:
                    seq, bc, improved = cand, c, True
        if not improved:
            break
    return seq, bc


# ---------------------------------------------------------------- day output
def build_day(ctx: DayCtx, order, locked=(), naive_km: float | None = None) -> dict:
    order = list(order)
    sim = simulate(ctx, order, build=True)
    if naive_km is None:
        naive_km = sim.km
    return {
        "date": ctx.day.isoformat(),
        "label": day_label(ctx.day),
        "weekday": ctx.weekday,
        "sunset": hm(ctx.sunset),
        "start": hm(ctx.start),
        "end": hm(ctx.end),
        "stops": order,
        "locked": [x for x in order if x in set(locked)],
        "items": sim.items,
        "metrics": {
            "stops": len(order),
            "km": round(sim.km, 2),
            "walk_km": round(sim.walk_km, 2),
            "travel_min": sim.travel_min,
            "fees": round(sim.fees, 2),
            "finish": hm(sim.finish),
            "naive_km": round(naive_km, 2),
        },
        "warnings": sim.warnings,
    }


# ---------------------------------------------------------------- clustering
def _xy(p: dict, lat0: float, lng0: float) -> tuple[float, float]:
    return ((p["lng"] - lng0) * math.cos(math.radians(lat0)) * 111.32, (p["lat"] - lat0) * 110.57)


def split_days(stops: list[str], k: int, places: dict, weight: dict, ref: dict,
               max_count: int = 8) -> list[list[str]]:
    """Capacity-balanced geographic k-means (farthest-point seeds, regret-ordered assignment)."""
    n = len(stops)
    if k <= 1:
        return [list(stops)]
    if n == 0:
        return [[] for _ in range(k)]
    if n <= k:
        return [[s] for s in stops] + [[] for _ in range(k - n)]

    xy = {s: _xy(places[s], ref["lat"], ref["lng"]) for s in stops}

    def d(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1])

    # capacity: time-weighted balance first, with a hard per-day stop count
    cap_n = max(math.ceil(n / k), min(max_count, math.ceil(n / k) + 1))
    total_w = sum(weight[s] for s in stops)
    cap_w = max(total_w / k * 1.15, max(weight[s] for s in stops))

    cx = sum(xy[s][0] for s in stops) / n
    cy = sum(xy[s][1] for s in stops) / n
    seeds = [max(stops, key=lambda s: (round(d(xy[s], (cx, cy)), 9), s))]
    while len(seeds) < k:
        rest = [s for s in stops if s not in seeds]
        seeds.append(max(rest, key=lambda s: (round(min(d(xy[s], xy[q]) for q in seeds), 9), s)))
    centres = [xy[s] for s in seeds]

    groups: list[list[str]] = [[] for _ in range(k)]
    prev_assign = None
    for _ in range(KMEANS_ITERS):
        dist = {s: [d(xy[s], centres[c]) for c in range(k)] for s in stops}

        def regret(s):
            ds = sorted(dist[s])
            return ds[1] - ds[0]

        order = sorted(stops, key=lambda s: (-round(regret(s), 9), s))
        groups = [[] for _ in range(k)]
        cnt = [0] * k
        wsum = [0.0] * k
        for s in order:
            ranked = sorted(range(k), key=lambda c: (round(dist[s][c], 9), c))
            choice = next((c for c in ranked if cnt[c] < cap_n and (cnt[c] == 0 or wsum[c] + weight[s] <= cap_w)), None)
            if choice is None:
                choice = next(c for c in ranked if cnt[c] < cap_n)
            groups[choice].append(s)
            cnt[choice] += 1
            wsum[choice] += weight[s]
        assign = tuple(tuple(sorted(g)) for g in groups)
        new_centres = []
        for c, g in enumerate(groups):
            if g:
                new_centres.append((sum(xy[s][0] for s in g) / len(g), sum(xy[s][1] for s in g) / len(g)))
            else:
                new_centres.append(centres[c])
        centres = new_centres
        if assign == prev_assign:
            break
        prev_assign = assign

    # never leave a day empty when there are enough stops
    while any(not g for g in groups):
        e = next(i for i, g in enumerate(groups) if not g)
        donor = max(range(k), key=lambda i: (len(groups[i]), -i))
        if len(groups[donor]) <= 1:
            break
        mv = min(groups[donor], key=lambda s: (round(d(xy[s], centres[e]), 9), s))
        groups[donor].remove(mv)
        groups[e].append(mv)
        centres[e] = xy[mv]
    return groups


# ---------------------------------------------------------------- full plan
def _get(req, key, default=None):
    if isinstance(req, dict):
        return req.get(key, default)
    return getattr(req, key, default)


def plan(req) -> dict:
    city_id = _get(req, "city")
    city = CITIES.get(city_id)
    if not city:
        raise PlannerError(f"Unknown city '{city_id}'")
    start_date = to_date(_get(req, "start_date"))
    n_days = int(_get(req, "days", 1))
    if not 1 <= n_days <= 7:
        raise PlannerError("days must be between 1 and 7")
    pace = _get(req, "pace", "balanced") or "balanced"
    mode = _get(req, "mode", "auto") or "auto"
    if pace not in PACES:
        raise PlannerError(f"Unknown pace '{pace}'")
    if mode not in MODES:
        raise PlannerError(f"Unknown mode '{mode}'")
    interests = [i for i in (_get(req, "interests") or [])]
    customs_in = [c if isinstance(c, dict) else c.model_dump() for c in (_get(req, "custom_places") or [])]
    places = build_place_map(city_id, customs_in)
    must_see = list(dict.fromkeys(_get(req, "must_see") or []))
    avoid = list(dict.fromkeys(_get(req, "avoid") or []))
    check_ids(must_see, places)
    check_ids(avoid, places)
    base = make_base(city, _get(req, "base"))

    cfg = PACES[pace]
    nightlife = "nightlife" in interests
    dates = [start_date + timedelta(days=i) for i in range(n_days)]
    weekdays = [d.weekday() for d in dates]
    day_start = cfg["start"]
    day_end = max(cfg["end"], NIGHTLIFE_END) if nightlife else cfg["end"]

    must = list(dict.fromkeys([c["id"] for c in customs_in] + must_see))
    must_set = set(must)
    avoid_set = set(avoid) - must_set
    # make room for must-see places that only open late
    for m in must:
        o = parse_hm(places[m]["open"])
        day_end = max(day_end, min(o + int(places[m]["duration"]) + 15, 24 * 60 - 1))

    iset = set(interests)
    score = {pid: p["popularity"] + 4 * len(iset & set(p["tags"])) for pid, p in places.items()}
    unplaced: list[dict] = []

    # ---- selection
    pool = []
    for pid in sorted(places, key=lambda x: (0 if x in must_set else 1, -score[x], -places[x]["popularity"], x)):
        p = places[pid]
        if pid in avoid_set:
            continue
        if all(wd in p["closed_days"] for wd in weekdays):
            if pid in must_set:
                days_txt = ", ".join(WEEKDAYS[w] for w in sorted(set(weekdays)))
                unplaced.append({"id": pid, "name": p["name"],
                                 "reason": f"Closed on {days_txt} — every day of your trip"})
            continue
        if pid not in must_set and parse_hm(p["open"]) + int(p["duration"]) > day_end + DROP_TOLERANCE:
            continue  # only opens after your day ends
        pool.append(pid)

    capacity = n_days * cfg["max_stops"]
    budget = n_days * (day_end - day_start - cfg["lunch"])
    def need_of(pid):
        km = route_km(base, places[pid])
        return int(places[pid]["duration"]) + max(TRAVEL_BUFFER, make_leg(km, mode)[2] if km > 4 else 0)

    selected, used = [], 0
    for pid in pool:
        need = need_of(pid)
        if pid in must_set:
            selected.append(pid)
            used += need
        elif len(selected) < capacity and used + need <= budget:
            selected.append(pid)
            used += need

    # ---- split into days
    weight = {pid: need_of(pid) for pid in selected}
    groups = split_days(selected, n_days, places, weight, base, cfg["max_stops"])

    # ---- clusters -> dates, minimising closed-day conflicts
    def conflicts(g, wd):
        return sum(1 for s in g if wd in places[s]["closed_days"])

    k = len(groups)
    best_perm, best_c = tuple(range(k)), None
    for perm in itertools.permutations(range(k)):
        c = sum(conflicts(groups[perm[d]], weekdays[d]) for d in range(k))
        if best_c is None or c < best_c:
            best_perm, best_c = perm, c
            if c == 0:
                break
    day_groups = [list(groups[best_perm[d]]) for d in range(k)]

    def centroid(g):
        if not g:
            return base["lat"], base["lng"]
        return sum(places[s]["lat"] for s in g) / len(g), sum(places[s]["lng"] for s in g) / len(g)

    for d in range(k):
        for s in sorted(day_groups[d], key=lambda x: (-score[x], x)):
            if weekdays[d] not in places[s]["closed_days"]:
                continue
            open_days = [j for j in range(k) if weekdays[j] not in places[s]["closed_days"]]
            if not open_days:
                unplaced.append({"id": s, "name": places[s]["name"],
                                 "reason": f"Closed on {WEEKDAYS_LONG[weekdays[d]]}"})
                day_groups[d].remove(s)
                continue

            def dist_to(j):
                la, ln = centroid(day_groups[j])
                return haversine(la, ln, places[s]["lat"], places[s]["lng"])

            with_room = [j for j in open_days if len(day_groups[j]) < cfg["max_stops"]]
            cands = with_room or open_days
            j = min(cands, key=lambda j: (round(dist_to(j), 6), len(day_groups[j]), j))
            day_groups[d].remove(s)
            day_groups[j].append(s)

    # ---- never leave a day empty when other days have stops to spare
    for d in range(k):
        if day_groups[d]:
            continue
        donors = sorted((j for j in range(k) if len(day_groups[j]) > 1), key=lambda j: (-len(day_groups[j]), j))
        for j in donors:
            movable = [s for s in day_groups[j] if weekdays[d] not in places[s]["closed_days"]]
            if not movable:
                continue
            la, ln = centroid(day_groups[j])
            mv = max(movable, key=lambda s: (round(haversine(la, ln, places[s]["lat"], places[s]["lng"]), 6), s))
            day_groups[j].remove(mv)
            day_groups[d].append(mv)
            break

    # ---- order each day
    ctxs = [make_ctx(city, dt, pace, mode, base, places, start=day_start, end=day_end, nightlife=nightlife)
            for dt in dates]
    by_score = lambda ids: sorted(ids, key=lambda x: (-score[x], x))  # noqa: E731
    orders = [optimize(ctxs[d], by_score(day_groups[d])) for d in range(k)]
    sims = [simulate(ctxs[d], orders[d]) for d in range(k)]

    # ---- repair overrunning days: move a stop to a day with slack, else drop it
    for _ in range(len(selected) + 1):
        over = [d for d in range(k)
                if sims[d].finish > ctxs[d].end + DROP_TOLERANCE and any(s not in must_set for s in orders[d])]
        if not over:
            break
        d = max(over, key=lambda i: (sims[i].finish - ctxs[i].end, -i))
        droppable = sorted((s for s in orders[d] if s not in must_set), key=lambda s: (score[s], s))
        moved = False
        for s in droppable:
            targets = sorted((j for j in range(k) if j != d and weekdays[j] not in places[s]["closed_days"]
                              and len(orders[j]) < cfg["max_stops"]),
                             key=lambda j: (sims[j].finish - ctxs[j].end, j))
            for j in targets:
                cand = optimize(ctxs[j], orders[j] + [s])
                cs = simulate(ctxs[j], cand)
                if cs.finish <= ctxs[j].end and len(cs.warnings) <= len(sims[j].warnings):
                    orders[j], sims[j] = cand, cs
                    rest = [x for x in orders[d] if x != s]
                    orders[d] = optimize(ctxs[d], rest)
                    sims[d] = simulate(ctxs[d], orders[d])
                    moved = True
                    break
            if moved:
                break
        if not moved:
            victim = droppable[0]
            orders[d] = optimize(ctxs[d], [x for x in orders[d] if x != victim])
            sims[d] = simulate(ctxs[d], orders[d])
            unplaced.append({"id": victim, "name": places[victim]["name"],
                             "reason": f"Didn't fit in {WEEKDAYS[weekdays[d]]}'s schedule"})

    # ---- fill any day left empty by the repair step
    for d in range(k):
        if orders[d]:
            continue
        for j in sorted(range(k), key=lambda j: (-len(orders[j]), j)):
            movable = [s for s in orders[j] if weekdays[d] not in places[s]["closed_days"] and s not in must_set]
            if len(orders[j]) <= 1 or not movable:
                continue
            mv = min(movable, key=lambda s: (score[s], s))
            orders[j] = optimize(ctxs[j], [x for x in orders[j] if x != mv])
            orders[d] = [mv]
            break

    days_out = []
    for d in range(k):
        naive = simulate(ctxs[d], by_score(orders[d])).km
        days_out.append(build_day(ctxs[d], orders[d], (), naive))

    return {
        "city": dict(city),
        "prefs": _prefs_echo(req),
        "base": base,
        "days": days_out,
        "unplaced": unplaced,
        "custom_places": customs_in,
        "metrics": trip_metrics(days_out),
    }


def _prefs_echo(req) -> dict:
    if isinstance(req, dict):
        return dict(req)
    return req.model_dump(mode="json")


def trip_metrics(days: list[dict]) -> dict:
    km = sum(d["metrics"]["km"] for d in days)
    naive = sum(d["metrics"]["naive_km"] for d in days)
    return {
        "stops": sum(d["metrics"]["stops"] for d in days),
        "km": round(km, 2),
        "walk_km": round(sum(d["metrics"]["walk_km"] for d in days), 2),
        "travel_min": sum(d["metrics"]["travel_min"] for d in days),
        "fees": round(sum(d["metrics"]["fees"] for d in days), 2),
        "naive_km": round(naive, 2),
        "saved_pct": max(0, int(round((naive - km) / naive * 100))) if naive > 0 else 0,
    }


# ---------------------------------------------------------------- single day
def schedule(req) -> dict:
    city_id = _get(req, "city")
    city = CITIES.get(city_id)
    if not city:
        raise PlannerError(f"Unknown city '{city_id}'")
    customs_in = [c if isinstance(c, dict) else c.model_dump() for c in (_get(req, "custom_places") or [])]
    places = build_place_map(city_id, customs_in)
    stops = list(dict.fromkeys(_get(req, "stops") or []))
    if len(stops) > 12:
        raise PlannerError("At most 12 stops per day")
    locked = list(dict.fromkeys(_get(req, "locked") or []))
    check_ids(stops, places)
    check_ids(locked, places)
    base = make_base(city, _get(req, "base"))
    start = _get(req, "start")
    end = _get(req, "end")
    ctx = make_ctx(city, to_date(_get(req, "date")), _get(req, "pace", "balanced") or "balanced",
                   _get(req, "mode", "auto") or "auto", base, places,
                   start=parse_hm(start) if start else None, end=parse_hm(end) if end else None)
    naive = simulate(ctx, stops).km
    order = optimize(ctx, stops, locked) if _get(req, "optimize", True) else stops
    return build_day(ctx, order, locked, naive)
