# SHMS – Site Hazard Management System

AI-assisted web platform for reporting PPE non-compliance from a photo, scoring it on a 5 × 5 consequence ×
likelihood risk matrix, routing it to the accountable Area Owner, documenting **how** each case was closed, and
showing site-wide risk on a live dashboard and heat map of a (synthesized) alumina refinery.

**Every hazard type in the app is detected by AI and passed a release gate on labelled data.** The AI checks a
photo against the PPE that the area requires: **hard hat**, **eye / face protection** (caustic splash) and
**gloves**. A fourth check, the **hi-vis vest**, was evaluated and *not* released because it wrongly flags too many
compliant workers. Evaluation uses the held-out split of the public, peer-reviewed **SH17** dataset with
precision, recall, specificity and MCC (see [Evaluation](#evaluation)). Two local AI back-ends are compared: **YOLO** detectors trained on SH17, and a
**vision-language model served by Ollama** (`qwen2.5vl:7b`). No paid API is used.

| | |
|---|---|
| **Team** | Hind Alhmoudi (sole member) – requirements, hazard taxonomy and risk matrix, architecture, all code, tests, evaluation, label audit, report |
| **Course** | Software Engineering and Programming – Master in Applied Artificial Intelligence |
| **Tested on** | macOS 26.6 on an Apple M5 Pro (24 GB) with Python 3.12.14 (verified 2026-11-17, see `docs/verification.md`). The GitHub Actions workflow (Ubuntu + macOS, Python 3.11 and 3.12) runs once the code is pushed. |
| **Paid APIs** | None |

---

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
  metrics.py, sh17.py     metric functions and dataset reader
  data/                   manifest, dataset stats, audit results (committed)
  results/                metrics.json per run, summary_full.md / summary_subset.md, figures (committed)
scripts/download_models.py  downloads and checksums the SH17 YOLO weights
tests/                    pytest suite (unit, workflow, API end-to-end, detectors, evaluation pipeline)
docs/architecture.md      architecture diagram, component responsibilities, design decisions
docs/requirements.md      user stories and data model, each story linked to code and tests
docs/verification.md      verification log: every command, number and decision behind the results
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

Repository: <https://github.com/Hind2102/shms> (created; code not pushed yet – **pending**).

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
| `SHMS_DEMO_HEADER_AUTH` | `0` | `1` lets the API accept an `X-User-Id` header instead of a token – tests and local scripts only |

The risk-matrix page separates what follows the ADOSH-SF guideline (the 5 × 5 consequence × likelihood structure)
from what this project defined (level wording, bands, deadlines, and the history-based likelihood, which is a
**project heuristic**, not a validated likelihood). Risk-matrix definitions, bands and target close-out times are in `shms/config/risk_matrix.json`; hazard
categories are in `shms/config/taxonomy.json`. Both can be changed without code changes.

## Usage

```bash
uvicorn shms.asgi:app --reload       # or: make run
```

Open <http://127.0.0.1:8000>. (If port 8000 is busy, add `--port 8765` and open that port instead.) On first start the database is created and filled with a synthesized refinery
(9 areas, 9 users, ~240 historical hazards). Sign in with one of the **demo accounts** below. The password is the
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

1. **Report** – as *Ahmed (Operator)*: *+ Report hazard* → choose area → take/upload a photo (try
   `data/samples/`). The AI checks it against the PPE that area requires and marks what it found.
2. **Confirm and score** – keep or correct the suggested PPE hazard (or choose one yourself if the AI found nothing
   or failed – the page lists what the AI does *not* check), choose the worst credible consequence. Likelihood is
   computed from the area's history and the risk level and target close date are shown. Tick *I already fixed it
   on the spot* to record the action taken and a closing photo.
3. **Plan, close, verify** – the hazard goes to the Area Owner (e.g. *Khalid* for Digestion); High and Extreme
   hazards alert the safety supervisor (*Sara*). The owner plans an action (action owner + deadline) and closes it
   with what was done. A closure is final only after **verification** by the supervisor or the reporter – never
   by the person who closed it; they can also **reject** it (back to open, reason required). A verified hazard can
   be **reopened** with a reason. Every status change is a rule in `services.ALLOWED_TRANSITIONS` and is kept in
   the audit trail with from/to status, who and when.
   `draft → open → planned → pending verification → closed`, with `pending verification → open` (reject) and
   `closed → open` (reopen).
4. **Monitor** – each role starts on its own **home page**: the reporter sees their reports and closures to
   check; the Area Owner their open hazards by deadline; the supervisor the verification queue, urgent and escalated
   hazards; the manager site priorities, overdue actions and closure performance (verified closures by the target
   date, median days to verified closure). The **site plan** (`/site`) is a zoomable plan view of the
   *illustrative* refinery layout with filters (time window, risk level) and three overlays – open risk, overdue,
   report volume – each stating its calculation, window and site total; an area with nothing recorded is hatched and
   labelled as such, never as "safe", and report volume is shown in a neutral colour because it is not a measure of
   danger. The dashboard (`/dashboard`) keeps the KPIs, trend, repeat hotspots and the hazard register.
   Screenshots (desktop and phone): `docs/screenshots/`.

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

265 tests, under a minute, no model or GPU needed (the YOLO tests run automatically when the weights are present). They
cover every cell of the risk matrix, the PPE rules, area-specific PPE checks, idempotent reporting, database
constraints, AI monitoring and `/metrics`, the workflow state machine and permissions, the HTTP API
end-to-end (report → confirm → route → close → dashboard), the detectors (Ollama mocked at HTTP level), the
metric functions against hand-computed values, and the evaluation pipeline on a miniature fake dataset.
GitHub Actions runs lint (`ruff`) and the suite on Ubuntu and macOS with Python 3.11 and 3.12, then builds the
Docker image and smoke-tests the running container.

```bash
ruff check . && ruff format --check .      # lint and formatting
```

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
python -m evaluation.release_gate --run yolo_sh17_yolo9e          # decides which hazard types the app uses
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
not a multi-annotator study. Status: **pending** (no results file yet).

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
| No hard hat | YOLOv9e | 0.964 | 0.968 | 0.887 | 0.859 | 0.966 (0.864) | ✅ approved |
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
(recall ≈ 0.33, MCC 0.13–0.25). Prompt v2 removes the framing and asks about each person separately. To avoid
tuning on the test set, prompts are developed on a **dev set of 100 training-split images**
(`--split dev`) and only the final prompt is run once on the test subset.

### External validation and stricter checks (Phase 2)

* **External validation of the hard-hat check – FAIL.** Pre-registered in `docs/external_validation_plan.md` before
  any image was downloaded, run once on 5 000 images of the independent *Hard Hat Workers* dataset (CC0): precision
  **0.281**, recall 0.977, specificity **0.445** (`evaluation/results/external_hardhat_yolo_sh17_yolo9e/`). The model
  misses most hard hats in these small (416 px) photos (it detects about 39 % of them), so it flags compliant workers.
  The app's release decision is unchanged, as pre-registered; the SH17 results above do not transfer to this data.
  Eye protection and gloves have no external validation (no public labelled set was found that maps to them).
* **Stricter label analysis on SH17** (`evaluation/label_rule_audit.py`): on photos where the relevant body part is
  labelled, specificity is lower than in the released figures – hard hat 0.750 (64 negatives), eye protection 0.828,
  gloves 0.636 (only 11 negatives). Much of the released specificity comes from photos without any person.

### Success criteria

| Criterion | Target | Result |
|---|---|---|
| Precision / recall per released hazard (held-out SH17) | ≥ 0.80 / ≥ 0.75 | ✅ 0.96 / 0.96–0.97 (YOLOv9e) |
| Specificity per released hazard | ≥ 0.80 | ✅ 0.885–0.934; vest 0.582 ❌ → not released |
| AI latency per photo, p95 | ≤ 20 s | ✅ 0.15 s (YOLOv9e) |
| Robustness: F1 drop on dark / blurred / compressed / distant photos | report | ≤ 0.031 (YOLOv8s, `robustness_*.json`) |
| Load: 8 concurrent users | no errors | ✅ 0 errors; p95 371 ms (YOLOv9e), 181 ms (YOLOv8s) (`load_test_*.json`) |
| Train/test leakage | none | ✅ 0 file overlaps, 0 near-duplicates (pre-training overlap of YOLO/Qwen unknown) |
| Reporter accepts AI suggestion without change (proposal) | ≥ 80 % | not measurable offline; recorded per report and shown on *AI monitoring* |
| New report visible on dashboard | immediately (< 5 s; proposal: 5 min) | ✅ `tests/test_api.py::test_full_workflow_and_dashboard_update` |
| Derived test labels agree with expert | report accuracy and κ | pending (`python -m evaluation.label_audit score`) |
| Automated tests and lint | all pass | ✅ locally: `pytest` (120), `ruff`; CI and Docker smoke test run after the first push |

Detection mAP50 (object level, 17 classes – a different quantity from the image-level results above) measured
with the published weights was 63.6 (YOLOv9e) and 54.9 (YOLOv8s), 6–8 points below the SH17 paper (70.9 / 63.7)
on a split with the same 1,620 images and 15,358 boxes. Device, batch size, image size and the ultralytics
version that saved the weights (8.2.38: 65.0 / 55.9) were tested and do not explain the gap. **Not reproduced;
cause unknown** (details in `docs/verification.md`).

## Data, privacy and limitations

* All people, areas and records in the app are synthesized; no refinery data is included.
* Photos are processed locally; nothing is sent to external services.
* Demo accounts share one documented demo password; a deployment would use the company's single sign-on and set
  `SHMS_SECRET_KEY`. Uploaded photos are checked (JPEG/PNG/WebP, ≤ 20 MB, ≤ 40 megapixels) and re-encoded.
* The hazard list contains only the PPE checks that passed the release gate, so other hazards (including a missing
  hi-vis vest, which no seeded area requires, and unsafe conditions) cannot currently be reported in the app, not even manually.
* Scope is limited on purpose to hazards with a public, peer-reviewed labelled test set. Unsafe conditions
  (caustic spills, steam leaks, missing grating) have no such dataset; collecting one with ≥ 3 annotators and
  measuring their agreement is future work. Fire/smoke (D-Fire) was considered and excluded: fires are handled
  by alarms and emergency response, and steam plumes in a refinery would cause frequent false alarms.
* SH17 images come from Pexels (manufacturing settings), not refineries, so field performance may differ.

## Licences of data and models

| Item | Used for | Licence / terms (as stated by the source) |
|---|---|---|
| SH17 dataset (Ahmad & Rahimi 2024), Kaggle `mugheesahmad/sh17-dataset-for-ppe-detection` | evaluation (held-out split), label audit | CC BY-NC-SA 4.0; images from Pexels (Pexels licence notice applies); research and education only. Not redistributed here – downloaded by each user |
| SH17 YOLO weights (`yolo8s.pt`, `yolo9e.pt`, GitHub release v1 of `ahmadmughees/SH17dataset`) | the app's detector, evaluation | no licence is stated in the repository; used here for non-commercial academic evaluation only; not committed (downloaded and checksummed by `scripts/download_models.py`) |
| Ultralytics YOLO | running the weights | AGPL-3.0 |
| Qwen2.5-VL 7B via Ollama (`qwen2.5vl:7b`) | vision-language comparison | Apache 2.0 (`ollama show qwen2.5vl:7b --license`) |
| Hard Hat Workers (Make ML), Hugging Face `Voxel51/hard-hat-detection` | external validation of the hard-hat check | CC0 1.0. Not redistributed here |
| This project's code | – | written by the author for the course; no licence file has been chosen yet |

## Acknowledgements

SH17 dataset and YOLO weights: H. M. Ahmad and A. Rahimi, <https://github.com/ahmadmughees/SH17dataset>.
Ultralytics YOLO (AGPL-3.0). Ollama and Qwen2.5-VL.
