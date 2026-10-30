# TravelSphere — AI sightseeing day planner & map optimizer

TravelSphere turns "3 relaxed days in Rome, ancient ruins and street food, must see the Colosseum" into an
hour-by-hour itinerary: which places to see, which day to see them, in what order, how to get between
them, where to grab lunch, and when to be at the viewpoint for sunset. The route is shown on a map
and you can drag, lock and re-optimise stops, save trips and share a read-only link.

## Features

- **4 cities, ~80 real attractions** — Paris, Rome, Tokyo, Jaipur, each place with coordinates, visit
  length, ticket price (local currency), opening hours, weekly closing days, best time of day
  (morning / sunset / evening), popularity and tags.
- **Multi-day planner** — picks places from your interests, must-sees and things to skip, splits them
  into geographically tight days, steers clear of closing days and orders every day for the least
  travel and waiting.
- **Day re-scheduler** — reorder or lock stops, add your own places (geocoded with OpenStreetMap
  Nominatim), change the start/end time and re-time or re-optimise a single day.
- **Realistic timing** — walking / transit / driving legs, waits for opening time, lunch breaks with a
  nearby food suggestion, sunset times calculated for each date, and warnings for closed days and late
  finishes.
- **AI assistant (optional)** — free-text trip requests are parsed into preferences, and each day gets a
  short brief with booking and timing tips. Uses Gemini Flash when `GEMINI_API_KEY` is set (trying the
  next model in `GEMINI_MODELS` when one is busy), else Claude when `ANTHROPIC_API_KEY` is set, and
  falls back to a built-in rules engine otherwise, so the app always works.
- **PDF export** — "Download PDF" produces an A4 itinerary: an overview page with trip metrics and a
  route map of every day line, then one page per day with its timed stops, travel legs, lunch, warnings,
  day notes and a schematic route map.
- **Accounts & sharing** — JWT auth, saved trips, public share links.

## How the optimiser works (`backend/app/planner.py`)

1. **Distances & legs.** Straight-line (haversine) distance × 1.3 detour factor. Walking 4.6 km/h;
   transit 19 km/h + 9 min overhead; driving 22 km/h + 7 min overhead. `auto` walks up to 1.6 km and
   takes transit beyond that. Transit legs under 0.8 km are walked.
2. **Simulating a day.** For a candidate order, the day is played forward from your base: travel →
   arrive → wait for opening → visit. Lunch goes in once it's past 12:15 (or during a long wait), with
   the nearest food spot within 1.2 km as a suggestion. The **cost** of an order is:
   travel minutes + 0.6 × waiting minutes + penalties for visiting on a closing day (+400), staying past
   closing time (+200 + 4/min), morning places after 11:00, evening places before 18:00, sunset places
   away from *sunset − 45 min*, and running past the end of your day (3/min). Sunset times come from the
   NOAA solar equations plus the city's time zone.
3. **Ordering a day.** Locked stops keep their position. With ≤ 7 free stops every permutation is tried
   (exact optimum). With more, a nearest-neighbour route is improved with **2-opt** (segment reversal) and
   **relocate** moves until nothing gets better, always judged by the full simulated cost.
4. **Planning a trip.**
   - *Score* = popularity + 4 × matching interests. Must-sees always go in, skipped places never do,
     places closed on every trip date are left out.
   - Places are picked greedily up to the time budget (days × hours available, after lunch and travel).
   - Places are split into days with **capacity-balanced k-means**: farthest-point seeds, regret-ordered
     assignment (places with the most to lose choose first), time-weighted capacity, 12 iterations. No
     day is left empty.
   - Clusters are matched to dates to minimise closing-day clashes (every permutation is checked); any
     remaining clash is moved to a day when the place is open.
   - Each day is optimised. If one runs more than 30 min long, its lowest-value stop is moved to a day
     with spare time, or dropped into **unplaced** with a reason ("Didn't fit in Tue's schedule").
   - `naive_km` is the distance you'd cover visiting each day's stops in score order; `saved_pct`
     compares it with the optimised route.
   - Fully deterministic: the same request always gives the same plan.

## Running locally

### Backend (FastAPI)

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python seed.py                      # demo user demo@travelsphere.app / demo1234 + a sample Paris trip
uvicorn app.main:app --reload       # http://localhost:8000  (docs at /docs)
```

Environment variables (all optional):

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./travelsphere.db` | e.g. `postgresql://user:pass@localhost:5432/travelsphere` |
| `SECRET_KEY` | dev key | JWT signing key — set a long random value in production |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated list of allowed frontend origins |
| `GEMINI_API_KEY` | — | Turns on Gemini for trip parsing and day briefs (takes priority over Claude) |
| `GEMINI_MODELS` | `gemini-3.5-flash,gemini-flash-latest,gemini-flash-lite-latest` | Models tried in order when one is overloaded or retired |
| `ANTHROPIC_API_KEY` | — | Turns on Claude when no Gemini key is set |
| `TRAVELSPHERE_AI` | `on` | Set to `off` to always use the rules engine |

Put these in `backend/.env` (copy `backend/.env.example`); it is loaded at startup and git-ignored.

Tests:

```bash
cd backend
pytest -q
```

### Frontend (React + Vite)

```bash
cd frontend
npm install
npm run dev                          # http://localhost:5173, talks to the API on :8000
```

### Docker (PostgreSQL + API)

```bash
docker compose up                    # API on http://localhost:8000, Postgres on :5432
```

Pass `ANTHROPIC_API_KEY=... docker compose up` to turn on Claude.

## Deploying to Vercel (no server to manage)

Vercel hosts both halves from this one repository: the React app is built into static files, and the
FastAPI backend runs as a Python function (`api/index.py`) on the same domain under `/api`. The setup
lives in `vercel.json`, `requirements.txt` (root) and `.vercelignore`.

1. **Create a free Postgres database.** Vercel functions can't keep files, so accounts, saved trips and
   AI city guides need a hosted database. [Neon](https://neon.tech) works well: create a project and copy
   its connection string (`postgresql://…?sslmode=require`). You can also add Neon from the Vercel
   dashboard (Storage → Create database), which sets `DATABASE_URL` for you.
2. **Put the code on GitHub** and import the repository at [vercel.com/new](https://vercel.com/new).
   Leave the root directory as the repository root; `vercel.json` sets the build commands.
3. **Add environment variables** (Project → Settings → Environment Variables):

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | Your Neon connection string |
   | `SECRET_KEY` | A long random string (for example the output of `python -c "import secrets; print(secrets.token_urlsafe(48))"`) |
   | `GEMINI_API_KEY` | Your Gemini key |
   | `GEMINI_MODELS` | Optional, defaults to `gemini-3.5-flash,gemini-flash-latest,gemini-flash-lite-latest` |

4. **Deploy.** Tables are created on the first request.
5. **Optional demo account:** run the seed script once against the same database from your computer:

   ```bash
   cd backend
   DATABASE_URL="postgresql://…" python seed.py
   ```

Or deploy from the terminal with the Vercel CLI: `vercel` for a preview, `vercel --prod` for production
(add the variables with `vercel env add NAME`).

Notes:
- Without `DATABASE_URL` the app still runs, using a throw-away SQLite file in `/tmp`; sign-ups,
  saved trips and new city guides then disappear whenever Vercel starts a fresh instance.
- Functions may run for up to 60 s (`maxDuration` in `vercel.json`). AI calls are capped below that and
  fall back to the next Gemini model, or to the built-in rules, when a model is slow.
- Map tiles come from OpenStreetMap and place search from Nominatim; both are fine for a project or demo
  but have fair-use limits, so switch to a paid tile/geocoding provider for heavy traffic.

## API overview (all under `/api`)

| Method | Route | Description |
|---|---|---|
| GET | `/cities`, `/cities/{id}/places` | Cities and their places |
| POST | `/plan` | Full multi-day trip |
| POST | `/schedule` | Re-time / re-optimise one day (lock stops, custom places) |
| GET | `/geocode?q=&city=` | Place search near the city (Nominatim) |
| POST | `/ai/parse`, `/ai/brief`; GET `/ai/status` | Free-text request → preferences; day briefs |
| POST | `/export/pdf` | Body `{trip}` → the itinerary as a PDF download |
| POST | `/auth/register`, `/auth/login`; GET `/auth/me` | Accounts (JWT bearer) |
| CRUD | `/trips`, `/trips/{id}` | Saved trips (owner only) |
| GET | `/share/{slug}` | Public read-only trip |
| GET | `/health` | Health check (outside `/api`) |

Opening hours and prices are typical values for a student project — check official sites before visiting.
