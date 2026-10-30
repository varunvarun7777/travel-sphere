"""Printable PDF of a planned trip: an overview page, then one page per day line.

Each day shows a schematic route map (stops projected from lat/lng, walk legs dashed,
transit and drive legs solid) beside a timed list of stops, plus day notes when the
trip carries them.
"""
from __future__ import annotations

import io
import math
import unicodedata
from datetime import date

from reportlab.graphics.shapes import Circle, Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

LINE_COLOURS = ["#DA291C", "#0072CE", "#00965E", "#7D3C98", "#D9661F", "#00A3AD", "#A05A2C"]
INK = colors.HexColor("#11181F")
STEEL = colors.HexColor("#5A6570")
RULE = colors.HexColor("#CDD3D0")
SIGNAL = colors.HexColor("#FFC20E")
CONCRETE = colors.HexColor("#E6E9E7")

PAGE_W, PAGE_H = A4
MARGIN = 16 * mm
CONTENT_W = PAGE_W - 2 * MARGIN


def _txt(value) -> str:
    """Standard PDF fonts only cover Windows-1252; transliterate or drop anything else."""
    out = []
    for ch in str(value if value is not None else ""):
        if ch == "₹":
            out.append("Rs ")
            continue
        try:
            ch.encode("cp1252")
            out.append(ch)
        except UnicodeEncodeError:
            out.append(unicodedata.normalize("NFKD", ch).encode("ascii", "ignore").decode())
    return "".join(out).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


STYLES = {
    "eyebrow": ParagraphStyle("eyebrow", fontName="Courier", fontSize=8, textColor=STEEL, leading=10),
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=30, leading=34, textColor=INK),
    "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=INK),
    "h3": ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=INK),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9.5, leading=13, textColor=INK, alignment=TA_LEFT),
    "small": ParagraphStyle("small", fontName="Helvetica", fontSize=8, leading=10.5, textColor=STEEL),
    "mono": ParagraphStyle("mono", fontName="Courier", fontSize=8.5, leading=10.5, textColor=INK),
    "warn": ParagraphStyle("warn", fontName="Helvetica-Bold", fontSize=8, leading=10.5, textColor=INK,
                           backColor=SIGNAL, borderPadding=(1, 3, 1, 3)),
}


def _p(text, style="body"):
    return Paragraph(text, STYLES[style])


def _money(amount, city: dict) -> str:
    amount = amount or 0
    if not amount:
        return "Free"
    value = f"{amount:,.0f}" if amount >= 100 or float(amount).is_integer() else f"{amount:,.2f}"
    return f"{city.get('currency', '')} {value}".strip()


def _duration(minutes) -> str:
    minutes = int(round(minutes or 0))
    h, m = divmod(minutes, 60)
    return f"{h} h {m:02d} min" if h else f"{m} min"


def _dates(trip: dict) -> str:
    days = trip.get("days") or []
    if not days:
        return ""
    first, last = date.fromisoformat(days[0]["date"]), date.fromisoformat(days[-1]["date"])
    if first == last:
        return first.strftime("%a %d %b %Y")
    return f"{first.strftime('%d %b')} - {last.strftime('%d %b %Y')}"


# ------------------------------------------------------------------ route map
def _project(points: list[tuple[float, float]], width: float, height: float, pad: float):
    lat0 = sum(p[0] for p in points) / len(points)
    kx = math.cos(math.radians(lat0))
    xs = [p[1] * kx for p in points]
    ys = [p[0] for p in points]
    span = max(max(xs) - min(xs), max(ys) - min(ys), 1e-4)
    scale = min(width - 2 * pad, height - 2 * pad) / span
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2

    def to_xy(lat: float, lng: float):
        return width / 2 + (lng * kx - cx) * scale, height / 2 + (lat - cy) * scale

    return to_xy


def _day_points(trip: dict, day: dict) -> tuple[dict, list[tuple[str, str, str]], list[str]]:
    """Coordinates by id, the travel legs (from, to, mode) and stop ids in order."""
    base = trip.get("base") or {}
    coords = {"base": (base.get("lat"), base.get("lng"))}
    stops, legs = [], []
    for item in day.get("items", []):
        if item.get("type") == "stop":
            place = item.get("place") or {}
            coords[item["id"]] = (place.get("lat"), place.get("lng"))
            stops.append(item["id"])
        elif item.get("type") == "travel":
            legs.append((item.get("from"), item.get("to"), item.get("mode")))
    return {k: v for k, v in coords.items() if None not in v}, legs, stops


def _route_drawing(trip: dict, days: list[tuple[int, dict]], width: float, height: float, numbers=True) -> Drawing:
    drawing = Drawing(width, height)
    drawing.add(Rect(0, 0, width, height, fillColor=CONCRETE, strokeColor=RULE, strokeWidth=0.6))
    per_day = [(i, *_day_points(trip, d)) for i, d in days]
    all_points = [xy for _, coords, _, _ in per_day for xy in coords.values()]
    if not all_points:
        return drawing
    to_xy = _project(all_points, width, height, pad=16)

    for i, coords, legs, _ in per_day:
        colour = colors.HexColor(LINE_COLOURS[i % len(LINE_COLOURS)])
        for a, b, mode in legs:
            if a not in coords or b not in coords:
                continue
            (x1, y1), (x2, y2) = to_xy(*coords[a]), to_xy(*coords[b])
            line = Line(x1, y1, x2, y2, strokeColor=colour, strokeWidth=2.2 if mode == "walk" else 3.2)
            if mode == "walk":
                line.strokeDashArray = [1.5, 2.5]
            drawing.add(line)

    for i, coords, _, stops in per_day:
        colour = colors.HexColor(LINE_COLOURS[i % len(LINE_COLOURS)])
        for n, sid in enumerate(stops, 1):
            if sid not in coords:
                continue
            x, y = to_xy(*coords[sid])
            drawing.add(Circle(x, y, 6.5 if numbers else 3.5, fillColor=colors.white, strokeColor=colour, strokeWidth=2))
            if numbers:
                drawing.add(String(x, y - 2.6, str(n), fontName="Helvetica-Bold", fontSize=7, fillColor=INK,
                                   textAnchor="middle"))

    if "base" in per_day[0][1]:
        x, y = to_xy(*per_day[0][1]["base"])
        drawing.add(Rect(x - 4.5, y - 4.5, 9, 9, fillColor=INK, strokeColor=colors.white, strokeWidth=1.5))
    drawing.add(String(width - 6, 5, "Schematic - not to exact scale", fontName="Helvetica", fontSize=6,
                       fillColor=STEEL, textAnchor="end"))
    return drawing


# ------------------------------------------------------------------ sections
def _metrics_table(cells: list[tuple[str, str]]) -> Table:
    row_labels = [_p(_txt(label).upper(), "eyebrow") for label, _ in cells]
    row_values = [_p(f"<b>{_txt(value)}</b>", "h3") for _, value in cells]
    table = Table([row_labels, row_values], colWidths=[CONTENT_W / len(cells)] * len(cells))
    table.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), 0.6, RULE), ("LINEBELOW", (0, -1), (-1, -1), 0.6, RULE),
        ("LINEAFTER", (0, 0), (-2, -1), 0.6, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _overview(trip: dict) -> list:
    city = trip.get("city") or {}
    prefs = trip.get("prefs") or {}
    metrics = trip.get("metrics") or {}
    flow = [
        _p("TRAVELSPHERE  -  DAILY SIGHTSEEING PLAN", "eyebrow"), Spacer(1, 4),
        _p(_txt(trip.get("title") or city.get("name", "Your trip")), "title"),
        _p(_txt(f"{city.get('name', '')}, {city.get('country', '')}  -  {_dates(trip)}"), "body"),
        Spacer(1, 3),
        _p(_txt(f"Pace: {prefs.get('pace', 'balanced')}  -  Getting around: {prefs.get('mode', 'auto')}"
                + (f"  -  Interests: {', '.join(prefs['interests'])}" if prefs.get("interests") else "")
                + f"  -  Starting from: {(trip.get('base') or {}).get('name', 'City centre')}"), "small"),
        Spacer(1, 10),
    ]
    cells = [("Stops", str(metrics.get("stops", 0))), ("Distance", f"{metrics.get('km', 0)} km"),
             ("On foot", f"{metrics.get('walk_km', 0)} km"), ("Moving", _duration(metrics.get("travel_min"))),
             ("Entry fees", _money(metrics.get("fees"), city))]
    if metrics.get("saved_pct"):
        cells.append(("Vs list order", f"{metrics['saved_pct']}% shorter"))
    flow += [_metrics_table(cells), Spacer(1, 12)]

    days = trip.get("days") or []
    flow.append(_route_drawing(trip, list(enumerate(days)), CONTENT_W, 92 * mm, numbers=False))
    flow.append(Spacer(1, 10))

    rows = [[_p("LINE", "eyebrow"), _p("DAY", "eyebrow"), _p("STOPS", "eyebrow"), _p("HOURS", "eyebrow")]]
    notes = {d["date"]: d for d in ((trip.get("brief") or {}).get("days") or [])}
    for i, day in enumerate(days):
        names = [(it.get("place") or {}).get("name", "") for it in day.get("items", []) if it.get("type") == "stop"]
        title = notes.get(day["date"], {}).get("title")
        label = f"<b>{_txt(day.get('label', day['date']))}</b>" + (f"<br/>{_txt(title)}" if title else "")
        rows.append([_roundel(i), _p(label), _p(_txt(", ".join(names)) or "-"),
                     _p(_txt(f"{day.get('start', '')}-{(day.get('metrics') or {}).get('finish', day.get('end', ''))}"), "mono")])
    table = Table(rows, colWidths=[14 * mm, 36 * mm, CONTENT_W - 78 * mm, 28 * mm], repeatRows=1)
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
                               ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    flow.append(table)

    unplaced = trip.get("unplaced") or []
    if unplaced:
        flow += [Spacer(1, 10), _p("Didn't make the cut", "h3")]
        flow += [_p(_txt(f"{u.get('name')}: {u.get('reason')}"), "small") for u in unplaced]
    return flow


def _roundel(i: int, size: float = 16) -> Drawing:
    drawing = Drawing(size + 2, size + 2)
    drawing.add(Circle(size / 2 + 1, size / 2 + 1, size / 2, fillColor=colors.HexColor(LINE_COLOURS[i % len(LINE_COLOURS)]),
                       strokeColor=None))
    drawing.add(String(size / 2 + 1, size / 2 - 2.5, str(i + 1), fontName="Helvetica-Bold", fontSize=9,
                       fillColor=colors.white, textAnchor="middle"))
    return drawing


def _stop_rows(day: dict, city: dict) -> tuple[list, list]:
    rows, styles = [], []
    n = 0
    for item in day.get("items", []):
        kind = item.get("type")
        if kind == "stop":
            n += 1
            place = item.get("place") or {}
            detail = " - ".join(x for x in [place.get("kind"), _duration(place.get("duration")),
                                            _money(place.get("price"), city),
                                            f"Open {place.get('open')}-{place.get('close')}"] if x)
            cell = [_p(f"<b>{n}. {_txt(place.get('name', item.get('id')))}</b>", "h3"), _p(_txt(detail), "small")]
            if place.get("blurb"):
                cell.append(_p(_txt(place["blurb"]), "small"))
            cell += [_p(_txt(w), "warn") for w in item.get("warnings") or []]
            rows.append([_p(f"{_txt(item.get('start'))}<br/>{_txt(item.get('end'))}", "mono"), cell])
        elif kind == "travel":
            mode = {"walk": "walk", "transit": "transit", "drive": "drive"}.get(item.get("mode"), item.get("mode"))
            rows.append(["", _p(_txt(f"{item.get('minutes')} min {mode}  -  {item.get('km')} km"), "small")])
            styles.append(("TOPPADDING", (0, len(rows) - 1), (-1, len(rows) - 1), 0))
        elif kind == "lunch":
            text = "<b>Lunch break</b>" + (f"<br/>{_txt(item['suggestion'])}" if item.get("suggestion") else "")
            rows.append([_p(f"{_txt(item.get('start'))}<br/>{_txt(item.get('end'))}", "mono"),
                         _p(text, "body")])
    return rows, styles


def _day_page(trip: dict, i: int, day: dict) -> list:
    city = trip.get("city") or {}
    m = day.get("metrics") or {}
    colour = colors.HexColor(LINE_COLOURS[i % len(LINE_COLOURS)])
    band = Table([[_roundel(i, 22), _p(f"<b>{_txt(day.get('label', day['date']))}</b>", "h2"),
                   _p(_txt(f"Line {i + 1}  -  sunset {day.get('sunset', '')}"), "eyebrow")]],
                 colWidths=[12 * mm, CONTENT_W - 62 * mm, 50 * mm])
    band.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, 0), 3, colour),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("ALIGN", (2, 0), (2, 0), "RIGHT")]))
    flow = [band, Spacer(1, 6),
            _p(_txt(f"{m.get('stops', 0)} stops  -  {m.get('km', 0)} km  -  {m.get('walk_km', 0)} km on foot  -  "
                    f"{_duration(m.get('travel_min'))} moving  -  {_money(m.get('fees'), city)} entry  -  "
                    f"back by {m.get('finish', '')}"), "mono"),
            Spacer(1, 6)]
    flow += [_p(_txt(w), "warn") for w in day.get("warnings") or []]

    note = next((d for d in ((trip.get("brief") or {}).get("days") or []) if d.get("date") == day["date"]), None)
    if note:
        tips = "".join(f"<br/>- {_txt(t)}" for t in note.get("tips") or [])
        flow += [Spacer(1, 4), _p(f"<b>{_txt(note.get('title', ''))}</b><br/>{_txt(note.get('summary', ''))}{tips}"), Spacer(1, 6)]

    rows, extra = _stop_rows(day, city)
    timeline = Table(rows or [["", _p("No stops planned for this day.")]], colWidths=[18 * mm, CONTENT_W * 0.56 - 18 * mm])
    timeline.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBEFORE", (1, 0), (1, -1), 3, colour),
                                  ("LEFTPADDING", (1, 0), (1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 3),
                                  ("BOTTOMPADDING", (0, 0), (-1, -1), 3), *extra]))
    route = _route_drawing(trip, [(i, day)], CONTENT_W * 0.42, 95 * mm)
    layout = Table([[timeline, route]], colWidths=[CONTENT_W * 0.58, CONTENT_W * 0.42])
    layout.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    flow.append(layout)
    return [KeepTogether(flow[:4]), *flow[4:]]


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(STEEL)
    canvas.drawString(MARGIN, 9 * mm, "Planned with TravelSphere. Opening hours and prices are typical values - check before you go.")
    canvas.drawRightString(PAGE_W - MARGIN, 9 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build_pdf(trip: dict) -> bytes:
    buf = io.BytesIO()
    city = (trip.get("city") or {}).get("name", "Trip")
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN,
                            bottomMargin=16 * mm, title=f"{city} itinerary", author="TravelSphere")
    story = _overview(trip)
    for i, day in enumerate(trip.get("days") or []):
        story += [PageBreak(), *_day_page(trip, i, day)]
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


def filename(trip: dict) -> str:
    city = (trip.get("city") or {}).get("id") or "trip"
    days = trip.get("days") or []
    start = days[0]["date"] if days else "plan"
    return f"travelsphere-{city}-{start}.pdf"
