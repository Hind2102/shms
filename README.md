# SHMS – Site Hazard Management System

AI-assisted web platform for reporting unsafe physical conditions and missing PPE from a photo, scoring it on a 5 × 5 consequence ×
likelihood risk matrix, routing it to the accountable Area Owner, documenting **how** each case was closed, and
showing site-wide risk on a live dashboard and heat map of a (synthesized) alumina refinery.

The AI checks a photo against the PPE that the area requires: **hard hat**, **eye / face protection** (caustic
splash) and **gloves**. These three passed a release gate on the held-out split of the public, peer-reviewed **SH17**
dataset; a fourth check, the **hi-vis vest**, was evaluated and *not* released. Every AI suggestion is confirmed by a
person, and every closure is verified by someone other than the person who closed it. **Read the evaluation with its
limits:** on an independent dataset the hard-hat check over-reported violations badly (precision 0.28), and the
stricter SH17 analysis shows similar weaknesses – see [External validation](#external-validation-and-stricter-checks-phase-2).
Two local AI back-ends are compared: **YOLO** detectors trained on SH17 and a **vision-language model served by Ollama**
(`qwen2.5vl:7b`). An **experimental**, off-by-default model checks for visible floor liquid and obstructed walkways. Workers can always report these and other physical conditions manually. The frozen model missed all five water-positive images in a separate real indoor photo challenge. No paid API is used.

| | |
|---|---|
| **Team** | Hind Alhmoudi (sole member) – requirements, hazard taxonomy and risk matrix, architecture, all code, tests, evaluation, label-audit tooling and report preparation |
| **Course** | Software Engineering and Programming – Master in Applied Artificial Intelligence |
| **Tested on** | macOS 26.6 on an Apple M5 Pro (24 GB) with Python 3.12.14 (see `docs/verification.md`); GitHub Actions on Ubuntu and macOS with Python 3.11 and 3.12, plus a Docker build and smoke test, on every push and pull request |
| **Paid APIs** | None |
| **Licence** | GNU AGPL-3.0 (`LICENSE`), because the app uses Ultralytics YOLO (AGPL-3.0) |

---

## Running the demo

**There is no hosted demo.** A free Hugging Face Space was planned, but Hugging Face now requires a paid (PRO) plan
for Docker Spaces: creating one returned *402 Payment Required* on 2026-11-27. Run the demo on your own machine
instead. It uses the real AI (YOLOv8s), and you can make it reachable from a phone for a short time (below).

**Demo mode** (`SHMS_DEMO_MODE=1`) is for showing the app to others:
- every page shows *"Public demo – do not upload confidential, personal or site photos; data resets on restart."*;
- the demo database, photos and outbox are **deleted and re-seeded on every start**;
- it refuses to start without `SHMS_SECRET_KEY`, with the mock detector, or when pointed at the project's own
  `shms.db`, `uploads/` or `outbox/`, so it can never wipe your normal data.

Leave demo mode off for normal local use and grading (see [Usage](#usage)).

**With Python** (after [Installation](#installation); the YOLOv8s weights come from `python scripts/download_models.py --all`):

```bash
source .venv/bin/activate
mkdir -p demo                                   # demo-only data, git-ignored, wiped on every start
SHMS_DEMO_MODE=1 SHMS_DETECTOR=yolo SHMS_YOLO_WEIGHTS=models/sh17_yolo8s.pt SHMS_RATE_LIMIT_PER_MIN=30 \
SHMS_SECRET_KEY="$(openssl rand -base64 32)" \
SHMS_DATABASE_URL=sqlite:///demo/shms_demo.db SHMS_UPLOAD_DIR=demo/uploads SHMS_MAIL_OUTBOX=demo/outbox \
uvicorn shms.asgi:app --port 8765 --proxy-headers
```

**With Docker** (weights mounted read-only; the data lives only inside the container):

```bash
docker build -t shms .
SHMS_SECRET_KEY="$(openssl rand -base64 32)" docker run --rm -p 8765:8000 \
  -v "$PWD/models:/app/models:ro" -e SHMS_SECRET_KEY -e SHMS_DEMO_MODE=1 -e SHMS_RATE_LIMIT_PER_MIN=30 \
  -e SHMS_YOLO_WEIGHTS=/app/models/sh17_yolo8s.pt shms
```

Then open <http://localhost:8765>. Both commands were run on 2026-11-27: banner shown, data reset, YOLOv8s loaded.

| Username | Role | Try |
|---|---|---|
| `ahmed` | reporter | *Report hazard* → take or choose a photo → AI suggestions → confirm |
| `khalid` | Area Owner (Digestion side) | *My queue* → act on a report, close it with a control |
| `sara` | safety supervisor | verify closures, AI monitoring, control-room board |
| `yousef` | manager (read-only) | dashboard, site plan, risk matrix |

The password for all accounts is the documented demo value `shms-demo-2026` (not a secret).

**Optional: a temporary public link (Cloudflare quick tunnel).** To try the app from a phone or show it to someone
remotely, while the Python demo above is running on port 8765:

```bash
cloudflared tunnel --url http://localhost:8765     # prints a random https://….trycloudflare.com address
```

> **Warning.**
> - The link works **only while your Mac is awake and running the app and the tunnel**.
> - **Photos and everything else sent through it leave your machine** and pass through Cloudflare.
> - Anyone with the link can reach the demo. Use demo mode only, never your normal data, and stop the tunnel
>   (Ctrl-C) when you are done.
> - `cloudflared` is not installed by this project; install it yourself if you want this
>   (e.g. `brew install cloudflared`).
>
> Over the tunnel's https address, "Use my current location" works on phones.

**What the demo cannot do.**
- It runs YOLOv8s, not the larger YOLOv9e used for the main evaluation.
- No e-mail is sent; notifications appear in the app only.
- The experimental unsafe-condition model and the Ollama vision-language model are off.
- Submissions are limited to 30 per minute per IP address.

*Hugging Face Space (needs a PRO plan).* `scripts/deploy_hf_space.sh` and `deploy/hf-space/` deploy the same demo
to a Docker Space. The token comes from `hf auth login` and is never stored in this repo; the SH17 weights are
downloaded at build time from the authors' release and checksum-verified. The script is kept for a future paid
plan; it has not been used.

## Project structure

```
shms/                     the web application (Python package)
  main.py, asgi.py        app factory and ASGI entry point
  settings.py             configuration from SHMS_* environment variables / .env
  models.py, db.py        SQLAlchemy data model (users, areas, hazards, events, notifications)
  escalate.py, notify.py  overdue escalation (CLI + page-load check) and notifications with a test mail outbox
  auth.py, tokens.py      passwords (scrypt), signed sessions, CSRF tokens, hashed API tokens (+ CLI)
  policy.py               who may see which hazard and photo
  migrations/             Alembic migrations (`alembic upgrade head`; configuration in alembic.ini)
  services.py             workflow state machine, routing, alerts, dashboard queries
  risk.py, taxonomy.py    risk matrix and hazard categories (data in shms/config/*.json)
  detection/              HazardDetector interface + YOLO, Ollama and mock implementations, PPE rules
  web/                    HTML routes (pages.py), JSON API (api.py), telemetry + /metrics, shared dependencies
  templates/, static/     Jinja2 pages and CSS (no JavaScript build)
  seed.py                 synthesized refinery layout, users and 6-month hazard history
evaluation/               offline evaluation on SH17
  prepare_sh17.py         builds the held-out test manifest and dataset statistics
  evaluate.py             runs a detector, writes predictions + metrics (P/R/F1, 95% CIs, latency, mAP)
  compare.py              comparison tables and figures
  label_audit.py          expert audit of the ground-truth labels (accuracy, Cohen's kappa)
  robustness.py           F1 on dark / blurred / compressed / distant versions of the test photos
  load_test.py            throughput and latency of the running service with concurrent users
  acceptance.py           SIMULATED reporter acceptance on the held-out split
  release_gate.py         decides which hazard types the app may use
  label_rule_audit.py     why model and derived labels disagree; stricter-label sensitivity analysis
  external_hardhat.py     pre-registered external validation (hard hat) on an independent dataset
  conditions.py           EXPERIMENTAL unsafe-conditions experiment (synthetic data)
  metrics.py, sh17.py     metric functions and dataset reader
  data/                   committed manifests and dataset statistics; completed human audit CSV
  results/                metrics.json per run, summary_full.md / summary_subset.md, figures (committed)
scripts/download_models.py  downloads and checksums the SH17 YOLO weights
tests/                    pytest suite (unit, workflow, API end-to-end, detectors, evaluation pipeline)
docs/architecture.md      architecture diagram, component responsibilities, design decisions
docs/requirements.md      user stories and data model, each story linked to code and tests
docs/verification.md      verification log: every command, number and decision behind the results
docs/*_plan.md            pre-registered plans (external validation, unsafe conditions), committed before the runs
docs/screenshots/         desktop and phone screenshots of the main pages
docs/course_mapping.md    which course lecture is applied where
Dockerfile, docker-compose.yml   container build (non-root, health check) and Compose stack (+ optional Ollama)
AGENTS.md                 rules for coding agents working in this repository
data/samples/             small sample photos for trying the app
```

## Prerequisites

* macOS, Linux or Windows with **Python 3.11 or newer** (`python3 --version`).
  macOS ships Python 3.9, which fails during installation with a misleading "setup.py not found" error. On macOS:
  `brew install python@3.12` and use `python3.12` in the installation step below.
* ~2 GB disk for the app with YOLO (PyTorch). Add ~6 GB for Ollama + `qwen2.5vl:7b`, and the SH17 dataset
  (download size shown on Kaggle) to reproduce the evaluation.
* Hardware: the app needs no GPU. Measured per photo on the test MacBook (Apple M5 Pro): CPU only – YOLOv9e ~0.2 s,
  YOLOv8s ~0.04 s; inside the Docker image (CPU, Linux VM) YOLOv9e 1.3–2.2 s. Slower machines will be slower; YOLOv8s
  is the fallback for weak hardware. The vision-language model needs
  ≥ 16 GB RAM (Apple silicon) or an 8 GB GPU; it was measured on an Apple M5 Pro with 24 GB.

## Installation

Repository: <https://github.com/Hind2102/shms>.

```bash
git clone https://github.com/Hind2102/shms.git
cd shms
python3 -m venv .venv                  # macOS: python3.12 -m venv .venv (see Prerequisites)
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -e ".[dev,yolo]" matplotlib
python scripts/download_models.py --all   # SH17 YOLOv9e (used) + YOLOv8s (fallback), SHA-256 verified
cp .env.example .env
```

Optional – the vision-language model:

```bash
# install Ollama from https://ollama.com/download, then
ollama pull qwen2.5vl:7b
```

## Configuration

All settings are environment variables (or lines in `.env`); see [`.env.example`](.env.example).

| Variable | Default | Meaning |
|---|---|---|
| `SHMS_DETECTOR` | `mock` | AI used by the app: `yolo`, `ollama` or `mock` (no model, for tests) |
| `SHMS_YOLO_WEIGHTS` | `models/sh17_yolo9e.pt` | YOLO weights file (YOLOv8s is the faster fallback) |
| `SHMS_YOLO_CONF` | `0.35` | YOLO operating threshold (fixed before the evaluation; the threshold sweep on the test split later showed it is at or near the best F1) |
| `SHMS_YOLO_DEVICE` | auto | `cpu`, `mps` (Apple GPU) or `cuda:0` |
| `SHMS_OLLAMA_MODEL` | `qwen2.5vl:7b` | Ollama model tag |
| `SHMS_OLLAMA_PROMPT` | `v2` | Prompt version (`v1` kept to reproduce the first evaluation) |
| `SHMS_AI_RELEASE_FILE` | `shms/config/ai_release.json` | Release-gate decision: which hazard types the app may use |
| `SHMS_DATABASE_URL` | `sqlite:///shms.db` | Any SQLAlchemy URL |
| `SHMS_UPLOAD_DIR` | `uploads` | Where photos are stored |
| `SHMS_MAIL_OUTBOX` | `outbox` | Test mail backend: notifications are written here as `.eml` files (nothing is sent) |
| `SHMS_SECRET_KEY` | generated | Signs session cookies and CSRF tokens. If unset, a random key is created once in `instance/secret_key` (git-ignored) |
| `SHMS_INSTANCE_DIR` | `instance` | Where that generated key is kept (Docker: `/data/instance`) |
| `SHMS_EXPERIMENTAL_CONDITIONS` | `0` | `1` enables the EXPERIMENTAL unsafe-condition check (liquid on the floor, obstructed walkway; needs Ollama) |
| `SHMS_DEMO_HEADER_AUTH` | `0` | `1` lets the API accept an `X-User-Id` header instead of a token – tests and local scripts only |
| `SHMS_SHIFT_START_HOUR` | `6` | Start of the day shift in local time; 12-hour shifts (project setting for the supervisor's "since start of shift" counts) |
| `SHMS_SITE_UTC_OFFSET_H` | `4` | Site time zone offset from UTC, used for shift and "today" views (the database stores UTC) |
| `SHMS_DEMO_MODE` | `0` | `1` = public demo: warning banner on every page, data wiped and re-seeded on every start; requires `SHMS_SECRET_KEY` and a real detector |
| `SHMS_RATE_LIMIT_PER_MIN` | `0` | Form/API submissions allowed per client IP per minute (`0` = no limit; the demo uses 30) |

The risk matrix follows the **ADOSH-SF Technical Guideline "Process of Risk Management", version 4.0 (15 July 2024)**:
consequence levels and definitions from Table 1 (human health and safety; production loss and cost shown as guidance),
likelihood levels from Table 2, and the Table 3 grid with its band names (Low 1–3, Moderate 4–6, High 8–12, Extreme
15–25; score 5 is Moderate, 9 and 10 High and 16 Extreme, read from the table's cell colours) and action texts. The
`/matrix` page separates this from what the project defined: the history-based likelihood (similar hazards in the
same area in the last 365 days: 0 → 1, 1 → 2, 2 → 3, 3–5 → 4, ≥ 6 → 5), the close-out targets (the guideline sets no time frames) and the alert rule (High/Extreme, or
consequence ≥ 4 in any band, after Sec. 5(b)). Closures record the control type from the hierarchy of controls
(Sec. 5.3.4(c)) and the residual risk (Appendix 2). Source, page numbers and the PDF's SHA-256:
[docs/risk_matrix_source.md](docs/risk_matrix_source.md). Values are in `shms/config/risk_matrix.json`; hazard
categories are in `shms/config/taxonomy.json`.

> **Likelihood:** ADOSH-SF likelihood describes how likely harm is; SHMS estimates it from how often similar hazards were reported in the same area in the last 365 days – a project heuristic, not the guideline's definition.

**Upgrading an existing database:** `alembic upgrade head` (back up the `.db` file first). Migration `0008_adosh_v4`
adds the closure fields and re-scores every confirmed hazard to the v4.0 matrix, writing an audit event
"risk re-scored to ADOSH-SF v4.0 matrix" with old → new values; existing closures keep the control type and residual
risk empty ("not recorded"). Migration `0009_ata_site_map` (v1.5.0) renames the nine existing areas to the zone names
of the approved map (codes, ids, hazards and pins kept), adds the six new zones (EVP, HYD, ALS, LIM, WKS, WTR) with
project-assumed PPE, and moves existing report pins proportionally into their zone on the new map.

**Field use (v1.6.0).** Pages are built for gloves, sunlight, one hand and little time:
- every control is at least 48 × 48 px, and phone text is at least 16 px;
- on phones, a bottom bar carries the main action ("Report a hazard", or the page's submit);
- reporting starts with the photo, and the area is pre-selected from your last report;
- consequence is chosen on large labelled cards;
- risk badges always show the word and a shape icon (○ Low, ◆ Moderate, ▲ High, ■ Extreme);
- the "Check before entering" card shows required PPE as our own blue-circle pictograms with labels.

See [docs/ux_review.md](docs/ux_review.md) for the heuristic review and the before/after task timings.

## Usage

```bash
uvicorn shms.asgi:app --reload       # or: make run
```

Open <http://127.0.0.1:8000>. (If port 8000 is busy, add `--port 8765` and open that port instead.) On first start the database is created and filled with a synthesized refinery
(15 reporting zones, 9 users, 210 historical hazards over 6 months; history regenerated in v1.4.1 and extended to the new zones in v1.5.0 – see *What is implemented*). Sign in with one of the **demo accounts** below. The password is the
same for all of them and is a documented demo value, **not a secret**: `shms-demo-2026`.

| Username | Person (synthesized) | Role |
|---|---|---|
| `ahmed`, `fatima`, `ravi` | operators / contractor | reporter |
| `khalid`, `mariam`, `omar`, `noura` | Area Owners | area owner |
| `sara` | safety supervisor | supervisor |
| `yousef` | refinery manager | manager (read-only) |

Passwords are stored as salted scrypt hashes; sessions are signed cookies (12 h); every form carries a CSRF token.
A database upgraded from an older version has usernames but no passwords: set one with
`python -m shms.tokens set-password <username>`.

Main workflow:

1. **Report** – as *Ahmed (Operator)*: *Report hazard* → choose area → take/upload a photo (try
   `data/samples/`). Photograph the floor or access route for a physical condition, or a person and task for missing PPE.
   SHMS reads GPS latitude/longitude and the original capture timestamp from supported photo EXIF metadata before storing the resized JPEG. Review these on the confirmation page. A timestamp without an offset is shown in camera local time. Missing tags leave fields unavailable. The reporting area and optional illustrative map pin are selected separately. The server records the submission time independently. Existing databases require Alembic revision `0007_photo_capture` (see *Upgrading an existing database*).
2. **Confirm and score** – choose the condition you observed or confirm a PPE suggestion, choose the worst credible consequence. Likelihood is set by the system (a project heuristic, see *Configuration*) and is
   computed from the area's history and the risk level and target close date are shown. Tick *I already fixed it
   on the spot* to record the action taken and a closing photo.
3. **Plan, close, verify** – the hazard goes to the Area Owner (e.g. *Khalid* for Digestion); High and Extreme
   hazards, and any hazard with consequence 4 or 5, alert the safety supervisor (*Sara*); the alert says why. The owner
   plans an action (action owner + deadline) and closes it with what was done, the type of control (elimination …
   PPE) and the residual consequence. A closure is final only after **verification** by the supervisor or the reporter – never
   by the person who closed it; they can also **reject** it (back to open, reason required). A verified hazard can
   be **reopened** with a reason. Every status change is a rule in `services.ALLOWED_TRANSITIONS` and is kept in
   the audit trail with from/to status, who and when.
   `draft → open → planned → pending verification → closed`, with `pending verification → open` (reject) and
   `closed → open` (reopen).
4. **Monitor** – each role starts on its own **home page**: the reporter sees their reports and closures to
   check; the Area Owner their open hazards by deadline; the supervisor the verification queue, urgent and escalated
   hazards; the manager site priorities, overdue actions and closure performance (verified closures by the target
   date, median days to verified closure). The **site plan** (`/site`) is a zoomable view of the owner-approved
   **concept map** (`shms/static/ata_concept_map.svg`, generated by `scripts/site_plan/make_map5.py`) with filters (time window, risk level) and three overlays – open risk, overdue,
   report volume – each stating its calculation, window and site total; an area with nothing recorded is hatched and
   labelled as such, never as "safe", and report volume is shown in a neutral colour because it is not a measure of
   danger. The dashboard (`/dashboard`) keeps the KPIs, trend, repeat hotspots and the hazard register.
   **Control-room board** (`/board`, v1.6.0): a read-only large-screen page with the site map (open-risk overlay), the
   active Extreme/High list and the overdue count. It refreshes every 60 s (pausable), has a dark-background option
   and requires sign-in.
   Select a reporting zone to inspect required PPE, active cases, overdue actions and recent closures.
   **Check before entering** can draw a suggested route from the south gate along the road centre-lines that avoids
   every road beside a zone with active High or Extreme cases, or says honestly why no route is available. Follow site
   rules and permits.
   Reports can include an optional point inside the chosen zone's polygon, selected by tap or by entering coordinates.
   The map groups nearby pins and links to the contributing cases.
   **Concept layout only — roads, equipment and facility positions are indicative and require a verified site plot
   plan.** The map is an illustrative concept based on public photographs, not a verified plot plan; zone codes and
   PPE lists are project assumptions. 15 reporting zones (BXH, DIG, GRD, CLR, FLT, PRC, EVP, CAL, HYD, ALS, TNK, LIM,
   PWR, WKS, WTR) and one support area (LAB). See [site layout](docs/site_layout.md) and
   [desktop and phone screenshots](docs/screenshots/).

**Overdue escalation** (project rule): an open or planned hazard past its target date is escalated to the safety
supervisors (level 1) and, 7 days later, to the manager (level 2), once each. It runs on page loads (at most once a
minute) and can be scheduled, e.g. with cron: `python -m shms.escalate`. Notifications appear in the app and are
also written as `.eml` files to `outbox/` – a **test mail backend**; no e-mail is ever sent (demo addresses use the
reserved `shms.example` domain).

Supervisors and the manager also see **AI monitoring** (latency, errors and reporter acceptance against the SLOs
in `shms/config/slo.json`). The JSON API is documented at <http://127.0.0.1:8000/docs>. API calls and the
Prometheus metrics at `/metrics` need a per-user **API token** (only its SHA-256 is stored):

```bash
python -m shms.tokens create sara --label scripts          # prints the token once
curl -H "Authorization: Bearer <token>" http://127.0.0.1:8000/api/dashboard
```

**Who can see and do what** (enforced on the server, `shms/policy.py` and `shms/services.py`): every page and API
call needs sign-in; confirmed hazards are visible to everyone signed in (a site hazard board); unconfirmed drafts
and their photos only to their reporter and supervisors; photos are served only through `/photos/…` with the same
checks. Actions follow the workflow table above; the manager is read-only.

### Run with Docker (optional)

```bash
python scripts/download_models.py          # weights are mounted into the container, not baked in
docker compose up --build                  # http://localhost:8000
docker compose --profile vlm up            # also starts Ollama (then: SHMS_DETECTOR=ollama)
```

The image is built and smoke-tested by CI on every push (verified locally on 2026-11-18: build OK, 2.3 GB, health
check *healthy*, runs as non-root). Compose publishes port 8000; if that port is busy, change `"8000:8000"` to e.g.
`"8765:8000"` in `docker-compose.yml`.

To reset the demo: stop the server and move `shms.db` and `uploads/` aside (e.g. into `backups/`, which git
ignores), or point `SHMS_DATABASE_URL` at a new file such as `sqlite:///shms_demo.db`.

**Upgrading an existing database.** Schema changes are Alembic migrations (`shms/migrations/`). After pulling a new
version, back up the database file and run

```bash
cp shms.db backups/shms_$(date +%F).db     # rollback = put this copy back (and check out the older code)
alembic upgrade head                        # migrates the database in SHMS_DATABASE_URL, keeps all rows
```

The app refuses to start on a database that is not at the newest migration and prints this instruction. Databases
created before migrations existed (no `alembic_version` table) are recognised and upgraded too.

## Testing

```bash
pytest                 # or: make test
```

The 446-test suite runs without a model or GPU (the YOLO tests run automatically when the weights are present); about 2 minutes on
GitHub's Ubuntu runners, 30–80 s on the test laptop depending on load. They cover every cell of the risk matrix against the ADOSH-SF Table 3 grid, the alert rules, the hierarchy-of-controls and residual-risk closure fields, the
PPE rules, area-specific PPE checks, idempotent reporting, database constraints and migrations (an old database is
upgraded with identical rows, and the v4.0 re-scoring with its audit events), every state-machine transition and every action from every wrong state, permissions
per role, sign-in, CSRF, API tokens, upload checks, escalation and the test mail outbox, the role home pages and plan
view, the HTTP API end-to-end, the detectors (Ollama mocked at HTTP level), the metric functions against
hand-computed values, the evaluation pipeline on miniature fake datasets, and the experimental feature flag.
GitHub Actions runs lint (`ruff`) and the suite on Ubuntu and macOS with Python 3.11 and 3.12, then builds the
Docker image and smoke-tests the running container.

```bash
ruff check . && ruff format --check .      # lint and formatting
```

v1.4.0 statement coverage is **72%** (2,480 of 3,421 statements on a fresh clone; 2,482 on the development machine). Phase 6 candidate statement coverage was **72%** (2,269 of 3,166 statements). Baseline statement coverage was **71%** for `shms` and `evaluation` together (2,154 of 3,043 statements). Reproduce on the review base with `pytest --cov=shms --cov=evaluation` after installing pytest-cov. [Coverage by module](evaluation/results/phase6_baseline_coverage/statements.md).

## Evaluation

### Data

**SH17** (Ahmad & Rahimi, *Journal of Safety Science and Resilience*, 2024; 8,099 images, 17 PPE / body-part
classes, CC BY-NC-SA 4.0). The released YOLO weights were trained on SH17's training list only; we evaluate on
the **held-out list** (`val_files.txt`, 1,620 images) that the weights never saw.

1. Create a free Kaggle account, open <https://www.kaggle.com/datasets/mugheesahmad/sh17-dataset-for-ppe-detection>,
   click *Download*, and unzip into `~/datasets/sh17` (it must contain `images/`, `labels/`, `val_files.txt`).
   Alternatively, `data/download_from_pexels.py` in the [SH17 repository](https://github.com/ahmadmughees/SH17dataset)
   downloads the images from the original source.
2. Image-level ground truth (hazard present / absent) is derived from the boxes with the same rules the app uses
   (`shms/detection/rules.py`).

### Commands

```bash
export SH17=~/datasets/sh17
python -m evaluation.prepare_sh17 --root $SH17                         # manifest + statistics
python -m evaluation.evaluate --root $SH17 --detector yolo --weights models/sh17_yolo9e.pt --map
python -m evaluation.evaluate --root $SH17 --detector yolo --weights models/sh17_yolo8s.pt --map
python -m evaluation.evaluate --root $SH17 --detector yolo --weights models/sh17_yolo9e.pt --subset
python -m evaluation.evaluate --root $SH17 --detector yolo --weights models/sh17_yolo8s.pt --subset
# vision-language model (needs Ollama): develop on the dev split, then one final run on the test subset
python -m evaluation.evaluate --root $SH17 --detector ollama --prompt v2 --split dev
python -m evaluation.evaluate --root $SH17 --detector ollama --prompt v2 --subset
python -m evaluation.evaluate --root $SH17 --detector ollama --prompt v1 --subset   # first prompt, for comparison
python -m evaluation.compare && python -m evaluation.compare --only-subset
python -m evaluation.release_gate --run yolo_sh17_yolo9e --dry-run  # inspect the decision and preserve owner notes
python -m evaluation.acceptance --run yolo_sh17_yolo9e            # SIMULATED reporter acceptance (proposal criterion)
```

(`make eval-prepare eval-yolo eval-vlm eval-compare SH17=~/datasets/sh17` runs the same.)
Runs are cached in `predictions.jsonl` and resume if interrupted. The subset is a fixed random sample of 300
held-out images (seed 42), used to compare all models on identical images because the VLM is slower.

### Non-functional tests

```bash
python -m evaluation.robustness --root $SH17 --weights models/sh17_yolo8s.pt --device mps   # dark / blur / JPEG / far
# with the app running (SHMS_DETECTOR=yolo); add --url http://127.0.0.1:<port> if it is not on port 8000:
python -m evaluation.load_test --image data/samples/<photo>.jpg --users 1 4 8 --requests 40 --token <API token>
```

`prepare_sh17.py` also checks for **train/test leakage**: exact file overlap and near-duplicate photos
(perceptual hash); add `--drop-near-dups` to `evaluate.py` to score without them.

### Label audit

The derived labels are checked by one safety professional (the author) on 100 random held-out images. This
measures agreement between the dataset-derived labels and one expert; it does not create new ground truth and is
not a multi-annotator study. **Completed.** The reviewer agreed with 81/100 hard-hat labels, 61/100 eye-protection labels and 86/100 glove labels. The original export also retains 100 decisions for the rejected vest check. [Audit summary](evaluation/results/SH17_photo_audit.md) · [All scored decisions by category](evaluation/results/label_audit.json).

```bash
python -m evaluation.label_audit build --root $SH17     # writes evaluation/data/label_audit.html
# open it, click Agree/Disagree per label, Download CSV -> evaluation/data/label_audit_results.csv
python -m evaluation.label_audit score                  # accuracy, 95% Wilson CI, Cohen's kappa
```

### Why F1 alone is misleading here

Most SH17 photos show people *without* PPE (the test split has only 154 helmets and 97 safety vests across
1,620 images), so 62–89 % of test photos contain each violation. A model that always answers "violation" would
already score F1 0.76–0.94. Every result therefore also reports **specificity** (share of compliant photos
correctly left alone), **MCC** (0 = no better than always answering "violation") and the always-"yes" F1.

### Results (held-out SH17 split, 1,620 photos; YOLO confidence 0.35; Apple M5 Pro)

| Hazard | Model | Precision | Recall | Specificity | MCC | F1 (always-yes F1) | Release gate |
|---|---|---:|---:|---:|---:|---:|---|
| No hard hat | YOLOv9e | 0.964 | 0.968 | 0.887 | 0.859 | 0.966 (0.864) | ✅ approved – *validated on SH17 only – failed external validation (Hard Hat Workers): unverified suggestion* |
| No eye / face protection | YOLOv9e | 0.959 | 0.957 | 0.934 | 0.891 | 0.958 (0.761) | ✅ approved |
| No gloves | YOLOv9e | 0.965 | 0.957 | 0.885 | 0.833 | 0.961 (0.870) | ✅ approved |
| No hi-vis vest | YOLOv9e | 0.950 | 0.970 | **0.582** | 0.599 | 0.960 (0.942) | ❌ rejected |

YOLOv9e latency p95 0.15 s per photo; YOLOv8s (fallback) is slightly weaker on every hazard (MCC 0.51–0.82).
Full tables with 95 % bootstrap confidence intervals: `evaluation/results/summary_full.md` (all 1,620 photos)
and `summary_subset.md` (the shared 300-photo subset, including the vision-language model).

**Release gate.** `python -m evaluation.release_gate --run yolo_sh17_yolo9e` applies the thresholds in
`evaluation/release_gate.json` (precision ≥ 0.80, recall ≥ 0.75, specificity ≥ 0.80, p95 ≤ 20 s) and writes
`shms/config/ai_release.json`; the app only enables approved hazard types. The vest check wrongly flags 42 % of
the test photos that contain no vest violation (74 of 177), so it is **not released**. The seeded refinery areas require flame-resistant
coveralls rather than hi-vis vests, so no area requires a vest and the vest is not offered on the report form. The precision/recall
targets were set for this evaluation; the proposal's own AI criteria are reporter acceptance (≥ 80 %, monitored
in the app) and latency (≤ 20 s). The specificity threshold was added after the first test results.

**Vision-language model.** With prompt v1 (refinery framing) Qwen2.5-VL 7B missed two thirds of violations
(recall ≈ 0.33, MCC 0.13–0.25). Prompt v2 removes the framing and asks about each person separately; developed on a
**dev set of 100 training-split images** and run once on the 300-photo test subset, it reached a macro MCC of 0.731
(YOLOv9e 0.823 on the same photos) at 5.6 s per photo (p50). Prompt v2 was written after seeing v1 fail on test
photos, so the test subset is not untouched for its design.

**Simulated reporter acceptance** (the proposal's ≥ 80 % criterion, `evaluation/acceptance.py`): if a reporter keeps
the AI's top suggestion whenever it names a violation that is really in the photo, the simulated acceptance rate is
97.2 % over photos with a released violation (1 450 / 1 492, including 27 photos with no suggestion in the denominator). This is a **simulation** and lenient by construction; real acceptance is recorded per
report and shown on *AI monitoring*.

### External validation and stricter checks (Phase 2)

* **External validation of the hard-hat check – FAIL.** Pre-registered in `docs/external_validation_plan.md` before
  any image was downloaded, run once on 5 000 images of the independent *Hard Hat Workers* dataset (CC0): precision
  **0.281**, recall 0.977, specificity **0.445** (`evaluation/results/external_hardhat_yolo_sh17_yolo9e/`). The model
  misses most hard hats in these small (416 px) photos (it detects about 39 % of them), so it flags compliant workers.
  The SH17 results above do not transfer to this data. **Owner decision (2026-11-18):** the hard-hat check stays
  enabled, but the app labels it everywhere it appears (confirm page, area page, hazard page) as "validated on SH17
  only – failed external validation (Hard Hat Workers): unverified suggestion"; the label comes from the `notes`
  field of `shms/config/ai_release.json`. The release-gate code and results are unchanged; re-running the gate
  rewrites that file and drops the note, which must then be re-added.
  Eye protection and gloves have no external validation (no public labelled set was found that maps to them).
* **Stricter label analysis on SH17** (`evaluation/label_rule_audit.py`): on photos where the relevant body part is
  labelled, specificity is lower than in the released figures – hard hat 0.750 (64 negatives), eye protection 0.828,
  gloves 0.636 (only 11 negatives). Much of the released specificity comes from photos without any person.

### Experimental: unsafe conditions (off by default)

Spilled liquid on the floor and objects obstructing a walkway were tested with the local vision-language model on a
**synthetic** warehouse dataset (CC BY 4.0) under a pre-registered plan (`docs/unsafe_conditions_plan.md`): prompt
tuned on 60 training images, then run once on 186 test images – liquid on the floor: precision 0.976, recall 0.932,
specificity 0.993; obstruction: precision 0.826, recall 0.792, specificity 0.942. Because the images are synthetic,
this is **not** validation for real sites and is never part of the release gate. With `SHMS_EXPERIMENTAL_CONDITIONS=1`
the confirmation page can show an experimental observation. It never pre-selects a physical condition or identifies the substance. Manual reporting works with the flag off and when inference fails.

**External liquid check:** the frozen model missed all five labelled indoor water photos in the versioned Mendeley archive. No inference errors occurred. Recall was 0/5 (descriptive 95% Wilson interval 0–43.4%). There were no dry controls to estimate false alarms. Keep the condition detector experimental. [Protocol and reproduction](docs/external_floor_liquid.md) · [Per-image predictions](evaluation/results/external_floor_liquid_v4/summary.json).

For Docker, start the optional service with `docker compose --profile vlm up -d`, then run `docker compose exec ollama ollama pull qwen2.5vl:7b` and `SHMS_EXPERIMENTAL_CONDITIONS=1 docker compose --profile vlm up -d app`. Restore the default by recreating the app with the flag set to 0.

### Success criteria

| Criterion | Target | Result |
|---|---|---|
| Precision / recall per released hazard (held-out SH17) | ≥ 0.80 / ≥ 0.75 | ✅ 0.96 / 0.96–0.97 (YOLOv9e) |
| Same check on an independent dataset (hard hat only) | ≥ 0.80 / ≥ 0.75 / spec ≥ 0.80 | ❌ precision 0.281, recall 0.977, specificity 0.445 |
| Specificity per released hazard | ≥ 0.80 | ✅ 0.885–0.934; vest 0.582 ❌ → not released |
| AI latency per photo, p95 | ≤ 20 s | ✅ 0.15 s (YOLOv9e) |
| Robustness: F1 drop on dark / blurred / compressed / distant photos | report | ≤ 0.031 (YOLOv8s, `robustness_*.json`) |
| Load: 8 concurrent users | no errors | ✅ 0 errors; p95 371 ms (YOLOv9e), 181 ms (YOLOv8s) (`load_test_*.json`) |
| Train/test leakage | none | ✅ 0 file overlaps, 0 near-duplicates (pre-training overlap of YOLO/Qwen unknown) |
| Reporter accepts AI suggestion without change (proposal) | ≥ 80 % | simulated 97.2 % (lenient, not field data); real acceptance recorded per report on *AI monitoring* |
| New report visible on dashboard | visible on next dashboard request (proposal: within 5 min) | Functional visibility verified in `tests/test_api.py::test_full_workflow_and_dashboard_update`; elapsed time not separately measured |
| Derived test labels agree with expert | report accuracy and κ | 100 photos per category. Agreement and κ were 81%, 0.35 for hard hats, 61%, 0.13 for eyes/face and 86%, 0.55 for gloves. |
| Automated tests and lint | all pass | ✅ `pytest` (305 in Phase 6), `ruff`; GitHub Actions green on every merged pull request, including the Docker smoke test |

Detection mAP50 (object level, 17 classes – a different quantity from the image-level results above) measured
with the published weights was 63.6 (YOLOv9e) and 54.9 (YOLOv8s), 6–8 points below the SH17 paper (70.9 / 63.7)
on a split with the same 1,620 images and 15,358 boxes. Device, batch size, image size and the ultralytics
version that saved the weights (8.2.38: 65.0 / 55.9) were tested and do not explain the gap. **Not reproduced;
cause unknown** (details in `docs/verification.md`).

## What is implemented, simulated, experimental or planned

| Status | What |
|---|---|
| **Implemented + tested** | photo report with AI suggestion and manual fallback; risk scoring on the ADOSH-SF v4.0 5 × 5 matrix, alerts for High/Extreme or consequence ≥ 4, control type (hierarchy of controls) and residual risk at closure; workflow draft → open → planned → pending verification → closed with reject/reopen, four-eyes verification and a from/to audit trail; overdue escalation; in-app notifications; sign-in with hashed passwords, signed sessions, CSRF, hashed API tokens, per-object access rules, safe uploads; Alembic migrations; role home pages, process plan, area details, optional pins, illustrative walkway routing, dashboard, risk-matrix page; AI monitoring and `/metrics`; release gate; offline evaluation on SH17 and the external dataset; Docker image; CI |
| **Simulated** | all people, areas, layout and 6-month hazard history (synthesized); reporter acceptance on held-out data; e-mail (written to a local outbox, never sent); demo accounts with one documented password |
| **Experimental** | liquid-on-the-floor and obstructed-walkway check (synthetic warehouse benchmark and a small positive-only external liquid check; flag off by default); the vision-language model as a PPE detector |
| **Human checks done** | SH17 label audit by the author personally (commit `4693bc8`; single reviewer, not a multi-annotator study); realism review by a refinery safety supervisor, November 2026 – it covered the site layout and the **earlier** synthetic history (v1.4.0 and before); the history was regenerated afterwards in v1.4.1 (realistic frequencies per area, consequences mostly C2–C3, mixed closure controls) and that regenerated history has not been reviewed; risk matrix checked against the ADOSH-SF v4.0 PDF ([source](docs/risk_matrix_source.md)) |
| **Planned / not done** | single sign-on; real refinery photos with multi-annotator labels; external validation of eye protection and gloves |

## Data, privacy and limitations

* All people, areas and records in the app are synthesized; no refinery data is included.
* Photos are processed locally; nothing is sent to external services.
* Demo accounts share one documented demo password; a deployment would use the company's single sign-on and set
  `SHMS_SECRET_KEY`. Uploaded photos are checked (JPEG/PNG/WebP, ≤ 20 MB, ≤ 40 megapixels) and re-encoded.
* In every area, workers can manually choose floor liquid, obstructed walkway, open machine-panel cover, floor opening or missing grating, visible corrosion, or another physical condition. These use the usual risk, assignment, closure and verification workflow. An open panel does not establish energisation, and surface appearance does not identify a substance. Only area-required, released PPE checks can become the AI's top suggestion.
* Validation on refinery photos and independent human review of project-created labels remain future work. The model cannot certify a site as safe.
* SH17 images come from Pexels (manufacturing settings), not refineries, so field performance may differ.

## Licences of data and models

| Item | Used for | Licence / terms (as stated by the source) |
|---|---|---|
| SH17 dataset (Ahmad & Rahimi 2024), Kaggle `mugheesahmad/sh17-dataset-for-ppe-detection` | evaluation (held-out split), label audit | CC BY-NC-SA 4.0; images from Pexels (Pexels licence notice applies); research and education only. Full dataset downloaded separately; three demonstration images included in data/samples |
| SH17 YOLO weights (`yolo8s.pt`, `yolo9e.pt`, GitHub release v1 of `ahmadmughees/SH17dataset`) | the app's detector, evaluation | no licence is stated in the repository; used here for non-commercial academic evaluation only; not committed (downloaded and checksummed by `scripts/download_models.py`) |
| Ultralytics YOLO | running the weights | AGPL-3.0 |
| Qwen2.5-VL 7B via Ollama (`qwen2.5vl:7b`) | vision-language comparison | Apache 2.0 (`ollama show qwen2.5vl:7b --license`) |
| Hard Hat Workers (Make ML), Hugging Face `Voxel51/hard-hat-detection` | external validation of the hard-hat check | CC0 1.0. Not redistributed here |
| Warehouse Safety Hazard Detection (J. S. Sohal), Hugging Face `Jsohal174/warehouse-safety-hazard-dataset` | experimental unsafe-conditions test | CC BY 4.0; synthetic images (Blender + Google Gemini). Not redistributed here |
| Patil & Bhutad, Mendeley v4, DOI 10.17632/y6zyrnxbfm.4 | external positive-only indoor water challenge | CC BY 4.0; original photos downloaded separately |
| This project's code | – | GNU AGPL-3.0 (`LICENSE`), chosen because the app depends on Ultralytics (AGPL-3.0) |

## Acknowledgements

SH17 dataset and YOLO weights: H. M. Ahmad and A. Rahimi, <https://github.com/ahmadmughees/SH17dataset>.
Ultralytics YOLO (AGPL-3.0). Ollama and Qwen2.5-VL.
