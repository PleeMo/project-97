# Beverage Quality Verification & Traceability System

Track a beverage batch from raw-material lot through production, QC, cold-chain
transport and retail — with a **public QR consumer verification page**, an
**ML risk-scoring model**, **cold-chain IoT monitoring**, **anti-counterfeit
scan analysis**, a **recall workflow**, and downloadable **lab certificates**.

**Stack:** FastAPI · SQLAlchemy · SQLite (swap to Postgres with one env var) ·
JWT auth · scikit-learn RandomForest · React 18 + Vite + Tailwind.

```
beverage-traceability/
├── backend/          FastAPI API + ML model + seed + smoke test
├── frontend/         React dashboard + public verify page + e2e test
├── docker-compose.yml  one-command full stack
└── README.md
```

## Features

**Roles & auth** — admin / producer (QC) / distributor / retailer, JWT-based,
registration included. Every mutating endpoint is role-gated.

**Batch traceability**
- Auto-generated batch codes (`BQ-2026-12345`) + auto-generated QR code
- Raw-material lots → supplier → batch lineage
- Supply-chain event log: produced → quality check → shipped → received → sold
- **Full batch timeline** — one chronological feed per batch (production,
  QC tests, logistics, QR scans, cold-chain breaches, recalls), newest first,
  colour-coded by kind and severity with per-kind counts

**Quality control**
- Log pH / Brix / microbial CFU / storage temperature per test
- **ML risk score (0–100)** from a RandomForest model, with a rule-based
  fallback if the model hasn't been trained — plus a live *what-if* preview
  as you type readings
- **Lab certificate upload** per test (PDF/PNG/JPEG, ≤5 MB), downloadable again
- Dashboard shows holdout accuracy, 5-fold cross-validation and feature
  importances — admins can **retrain the model from the UI**

**Cold chain (IoT)**
- Temperature readings from a simulated sensor gateway, charted per batch
  with the safe band (0–8 °C) and breach markers
- Simulate a healthy shipment or a refrigeration failure from the UI
- Standalone CLI simulator for live demos: `python -m app.simulate_cold_chain`

**Anti-counterfeit**
- Every public verification is recorded (client timezone, user agent, *hashed*
  IP — raw IPs are never stored)
- Per-batch analysis: scan velocity + geographic spread → low / medium / high
  risk with human-readable flags
- Consumers see a warning on the verify page when a code is lighting up from
  several countries at once (a cloned QR's signature)

**Public consumer verification** (`/verify/:batchCode`, no login)
- Origin, QC status, risk score, full journey timeline, verification counter,
  recall / counterfeit warnings

**Recall workflow** — flags every downstream location a batch has touched.

**Supplier scorecard** — every supplier shows the lots it delivered, how many
batches came from them, total kg, QC pass rate, average risk score and any
recalls — `GET /suppliers/stats`.

**CSV data exports** — five audited, authenticated downloads
(`/export/batches.csv`, `quality-tests.csv`, `scans.csv`, `temperatures.csv`,
`recalls.csv`), each a dated attachment; temperature rows carry an
`in_safe_range` flag. The Batches page has a one-click *Export CSV* button.

**Printable QR label sheet** — `/print/qr/:id` renders a print-optimized
sheet of 8 labels (QR + batch code + verify URL) outside the app chrome;
hit *Print sheet* and only the labels go to the printer.

**Alerts feed** — one list of everything needing attention: cloned-QR flags,
QC failures, cold-chain breaches, expiring stock and active recalls,
sorted critical-first, with a live count badge in the sidebar.

**Batch lifecycle rules** — the API refuses invalid transitions: untested or
QC-failed batches can't be shipped, recalled batches are frozen (no movement,
no re-testing, no double recall), and system events can't be faked through
the generic endpoint. The UI only offers the moves that are legal right now.

**Dashboard** — batches by status, average risk, total scans, flagged batches,
24 h cold-chain breaches, ML model card, plus four charts (14-day scan trend,
14-day cold-chain breach trend, status donut, risk-profile bars) — all
hand-rolled SVG, no chart library.

**UX** — search + status filter + pagination on batches, role-aware
navigation, a traceability strip on every batch (raw material → supplier →
dates, with expiry chips), QR code download as PNG. Branded SVG logo and
favicon, SEO/social meta tags, a collapsible mobile nav with backdrop, a
shared banner component for errors and notices, and a footer with a **live
API status dot** (polls `/health`) plus a link to the API docs.

**Platform & ops**
- `GET /health` is a real readiness probe: version, database `SELECT 1`,
  ML model presence, process uptime — 200 when ok, 503 when degraded
- Every response carries an `X-Request-ID` (client-supplied ids are echoed),
  with one structured access-log line per request: `METHOD path -> status in Xms rid=`
- **Rate limiting** on the public verify endpoint (per-IP sliding window,
  `429` + `Retry-After`) so QR scanners can't hammer the API
- **Server-side pagination + sorting** on `GET /batches` (`page`, `page_size`,
  `sort`, `order` — whitelisted columns) returning
  `{items, total, page, page_size, pages}`; omit `page` for the legacy full list
- **CI** — `.github/workflows/ci.yml` runs pytest, the API smoke test and the
  frontend production build on every push/PR
- **Deploy checklist** — `python scripts/deploy_check.py` verifies Python,
  packages, secrets, DB, ML artifacts, app import and frontend build
  (`--strict` gates deploys on failures)
## Quick start

### Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

python -m app.ml.train_model      # trains the model -> app/ml/model.pkl + metrics.json
python -m app.seed                # demo users, batches, cold-chain + scan telemetry
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm install
cp .env.example .env              # points the frontend at http://localhost:8000
npm run dev
```

Open http://localhost:5173

### Or both with Docker

```bash
docker compose up --build         # frontend :5173, backend :8000
```

### Demo logins (password for all: `password123`)

| Role | Email |
|---|---|
| Admin | admin@demo.com |
| Producer / QC | producer@demo.com |
| Distributor | distributor@demo.com |
| Retailer | retailer@demo.com |

The seed script prints 4 demo batch codes — one delivered, one in transit,
one failed QC, one recalled. Try them at http://localhost:5173/verify.

### Demo scripts (great for a project defense)

1. **Verify a product** — open `/verify/<code>` from the seed output.
2. **Catch a cloned QR** — the in-transit batch was seeded with 12 scans from
   5 countries in 24 h. Its batch page shows a *high risk* anti-counterfeit
   verdict, the dashboard counts it as flagged, and the public verify page
   shows the consumer warning.
3. **Break the cold chain** — on a batch page hit *Simulate failure*, watch
   the chart leave the safe band, then trigger a recall.
4. **Retrain the model** — as admin, *↻ Retrain model* on the dashboard:
   fresh metrics in ~2 s.
5. **Attach a certificate** — ➕ on any QC test row, then 📎 to download it.
6. **Walk the full timeline** — open any batch: production → QC → scans →
   breaches → recall in one expandable feed.
7. **Hand out QR labels** — *Print label sheet 🖨* on a batch page prints 8
   scannable labels; *Export CSV* on the Batches page feeds an audit
   spreadsheet.

## Testing

Three suites, all green at the time of writing:

```bash
# 1. Unit/API tests (56 tests) — no server needed, isolated test DB
cd backend
pip install -r requirements-dev.txt
python -m pytest

# 2. API end-to-end (70 checks) — server must be running on :8000
cd backend && python scripts/smoke_test.py http://localhost:8000

# 3. Browser end-to-end (61 checks) — both servers must be running
cd frontend && npm run e2e        # drives Chrome against :5173
```

After runs 2 and 3, restore the pristine demo data:

```bash
cd backend && python -c "import sqlite3; sqlite3.connect('traceability.db').executescript(open('scripts/cleanup_smoke_data.sql').read())"
```

## Configuration

Backend reads `.env` (see `backend/.env.example`) or plain environment vars:

| Var | Purpose | Default |
|---|---|---|
| `JWT_SECRET` | signs JWTs — **change in production** | dev placeholder |
| `CORS_ORIGINS` | comma-separated allowed origins | `*` |
| `FRONTEND_URL` | absolute URL baked into QR codes | *(relative)* |
| `DATABASE_URL` | SQLite file or Postgres DSN | `sqlite:///./traceability.db` |
| `IP_HASH_SALT` | salts hashed scan IPs | dev salt |
| `VERIFY_RATE_LIMIT` | verify requests allowed per window (per IP) | `60` |
| `VERIFY_RATE_WINDOW` | rate-limit window in seconds | `60` |

Frontend: `VITE_API_URL` (see `frontend/.env.example`).

## Project structure

**Backend** (`backend/app/`)
- `models.py` — User, Supplier, RawMaterialBatch, Batch, QualityTest,
  SupplyChainEvent, QRCode, RecallLog, TemperatureReading, QRScan
- `schemas.py` — Pydantic request/response models
- `auth.py` — JWT + role-based access control
- `routers/` — auth, suppliers (+scorecard stats), batches (+timeline),
  quality (+certificates +model info), supply_chain (lifecycle-guarded), qr,
  verify (public), recall, dashboard (+analytics), cold_chain, scans, alerts,
  export (CSV)
- `tests/` — pytest suite (FastAPI TestClient, isolated DB)
- `ml/train_model.py` — synthetic multi-profile dataset, holdout + 5-fold CV,
  feature importances → `model.pkl` + `metrics.json`
- `ml/predict.py` — model loading, scoring, `model_info()`, rule-based fallback
- `seed.py` — demo data (users, batches, certificates, cold chain, scans)
- `simulate_cold_chain.py` — IoT simulator CLI (bulk or live `--push`)
- `scripts/smoke_test.py` — API end-to-end checks
- `scripts/deploy_check.py` — pre-deployment readiness checklist

**Frontend** (`frontend/src/`)
- `api.js` — fetch wrapper for every endpoint
- `pages/` — Login (with registration), DashboardHome (stats + charts + ML
  card), Batches (search/filter/pagination + CSV export), BatchDetail (QC +
  certificates + supply chain + cold-chain chart + anti-counterfeit +
  traceability strip + full timeline + QR + recall), Suppliers (+scorecard),
  Recalls, Alerts, Verify (public), PrintQr (printable label sheet)
- `components/` — Layout (role-aware nav + alert badge + mobile drawer +
  API-status footer), Logo (SVG brand mark), Banner (error/notice banners),
  StatusBadge, RiskGauge, Charts (SVG trend/donut/bars/sparkline)
- `scripts/e2e.mjs` — puppeteer-core browser checks

## Deploying

```bash
# backend  -> Render / Railway / Fly.io
#          -> set JWT_SECRET, CORS_ORIGINS, FRONTEND_URL, DATABASE_URL (Postgres)
# frontend -> Vercel / Netlify (build: npm run build, output: dist)
#          -> set VITE_API_URL to the deployed API origin at build time
```

GitHub Actions (`.github/workflows/ci.yml`) runs the pytest suite, the API
smoke test and the frontend build on every push to `main` and on PRs.

Before any real deployment, run the readiness checklist:

```bash
cd backend && python scripts/deploy_check.py --strict
```

It fails the build on missing packages, a default/short `JWT_SECRET` or a
missing model, and warns on demo-grade settings. Then:

- set a strong `JWT_SECRET` and `IP_HASH_SALT`
- restrict `CORS_ORIGINS` to your frontend domain
- set `FRONTEND_URL` so QR codes encode absolute, scannable URLs
- move certificate storage from SQLite/base64 to object storage if you expect
  real volume

## Notes

- `python -m app.seed` is safe to re-run — it skips if the DB has data
  (delete `backend/traceability.db` to reseed from scratch).
- SQLite is the zero-config default; the code doesn't change when you point
  `DATABASE_URL` at Postgres.
- The ML model trains on synthetic, domain-plausible data with per-beverage
  safe windows — swap `generate_synthetic_data()` for a real lab dataset and
  re-run `python -m app.ml.train_model`.
