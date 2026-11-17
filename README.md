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
| **Tested on** | macOS (Apple M5 Pro, 24 GB) with Python 3.12; Ubuntu 24.04 with Python 3.11–3.13 (GitHub Actions also runs macOS) |
| **Paid APIs** | None |

---

## Project structure

```
shms/                     the web application (Python package)
  main.py, asgi.py        app factory and ASGI entry point
  settings.py             configuration from SHMS_* environment variables / .env
  models.py, db.py        SQLAlchemy data model (users, areas, hazards, events, notifications)
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
  results/                metrics.json per run, summary.md, figures (committed)
scripts/download_models.py  downloads and checksums the SH17 YOLO weights
tests/                    pytest suite (unit, workflow, API end-to-end, detectors, evaluation pipeline)
docs/architecture.md      architecture diagram, component responsibilities, design decisions
docs/course_mapping.md    which course lecture is applied where
Dockerfile, docker-compose.yml   container build (non-root, health check) and Compose stack (+ optional Ollama)
AGENTS.md                 rules for coding agents working in this repository
data/samples/             small sample photos for trying the app
```

## Prerequisites

* macOS, Linux or Windows with **Python 3.11 or newer** (`python3 --version`).
  On macOS without a recent Python: `brew install python@3.12`.
* ~2 GB disk for the app with YOLO (PyTorch). Add ~6 GB for Ollama + `qwen2.5vl:7b`, and the SH17 dataset
  (download size shown on Kaggle) to reproduce the evaluation.
* Hardware: any laptop runs the app with YOLOv8s on CPU (~0.25 s per photo). The vision-language model needs
  ≥ 16 GB RAM (Apple silicon) or an 8 GB GPU; it was measured on an Apple M5 Pro with 24 GB.

## Installation

```bash
git clone https://github.com/Hind2102/shms.git
cd shms
python3 -m venv .venv
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
| `SHMS_YOLO_CONF` | `0.35` | YOLO operating threshold (chosen on the threshold sweep, see results) |
| `SHMS_YOLO_DEVICE` | auto | `cpu`, `mps` (Apple GPU) or `cuda:0` |
| `SHMS_OLLAMA_MODEL` | `qwen2.5vl:7b` | Ollama model tag |
| `SHMS_OLLAMA_PROMPT` | `v2` | Prompt version (`v1` kept to reproduce the first evaluation) |
| `SHMS_AI_RELEASE_FILE` | `shms/config/ai_release.json` | Release-gate decision: which hazard types the app may use |
| `SHMS_DATABASE_URL` | `sqlite:///shms.db` | Any SQLAlchemy URL |
| `SHMS_UPLOAD_DIR` | `uploads` | Where photos are stored |

Risk-matrix definitions, bands and target close-out times are in `shms/config/risk_matrix.json`; hazard
categories are in `shms/config/taxonomy.json`. Both can be changed without code changes.

## Usage

```bash
uvicorn shms.asgi:app --reload       # or: make run
```

Open <http://127.0.0.1:8000>. (If port 8000 is busy, add `--port 8765` and open that port instead.) On first start the database is created and filled with a synthesized refinery
(9 areas, 9 users, ~240 historical hazards). Pick a role on the sign-in page (demo sign-in, no passwords).

Main workflow:

1. **Report** – as *Ahmed (Operator)*: *+ Report hazard* → choose area → take/upload a photo (try
   `data/samples/`). The AI checks it against the PPE that area requires and marks what it found.
2. **Confirm and score** – keep or correct the suggested PPE hazard, choose the worst credible consequence.
   Likelihood is computed from the area's history and the risk level is shown. Tick *I already fixed it on the
   spot* to close it immediately with the action taken and a closing photo.
3. **Route and close** – otherwise the hazard goes to the Area Owner (e.g. *Khalid* for Digestion). High and
   Extreme hazards alert the safety supervisor (*Sara*). The owner plans an action and closes the hazard with a
   description of the control and a closing photo. Every step is kept in the audit trail.
4. **Monitor** – the dashboard shows KPIs, the heat map (click an area for its live hazards, required PPE and
   what the AI checks there),
   weekly trend, repeat hotspots and the hazard register with filters.

Supervisors and the manager also see **AI monitoring** (latency, errors and reporter acceptance against the SLOs
in `shms/config/slo.json`). The JSON API is documented at <http://127.0.0.1:8000/docs>; Prometheus metrics are at
<http://127.0.0.1:8000/metrics>.

### Run with Docker (optional)

```bash
python scripts/download_models.py          # weights are mounted into the container, not baked in
docker compose up --build                  # http://localhost:8000
docker compose --profile vlm up            # also starts Ollama (then: SHMS_DETECTOR=ollama)
```

The image is built and smoke-tested by CI on every push.

To reset the demo: stop the server and delete `shms.db` and `uploads/`. After upgrading SHMS, delete an old
`shms.db` too; the app refuses to start on an outdated schema and says so.

## Testing

```bash
pytest                 # or: make test
```

112 tests, under a minute, no model or GPU needed (the YOLO tests run automatically when the weights are present). They
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
```

(`make eval-prepare eval-yolo eval-vlm eval-compare SH17=~/datasets/sh17` runs the same.)
Runs are cached in `predictions.jsonl` and resume if interrupted. The subset is a fixed random sample of 300
held-out images (seed 42), used to compare all models on identical images because the VLM is slower.

### Non-functional tests

```bash
python -m evaluation.robustness --root $SH17 --weights models/sh17_yolo8s.pt --device mps   # dark / blur / JPEG / far
# with the app running (SHMS_DETECTOR=yolo):
python -m evaluation.load_test --image data/samples/<photo>.jpg --users 1 4 8 --requests 40
```

`prepare_sh17.py` also checks for **train/test leakage**: exact file overlap and near-duplicate photos
(perceptual hash); add `--drop-near-dups` to `evaluate.py` to score without them.

### Label audit

The derived labels were checked by a safety professional on 100 random held-out images:

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
people who wear a vest, so it is **not released**: areas that require vests show it as "not AI-checked yet".

**Vision-language model.** With prompt v1 (refinery framing) Qwen2.5-VL 7B missed two thirds of violations
(recall ≈ 0.33, MCC 0.13–0.25). Prompt v2 removes the framing and asks about each person separately. To avoid
tuning on the test set, prompts are developed on a **dev set of 100 training-split images**
(`--split dev`) and only the final prompt is run once on the test subset.

### Success criteria

| Criterion | Target | Result |
|---|---|---|
| Precision / recall per released hazard (held-out SH17) | ≥ 0.80 / ≥ 0.75 | ✅ 0.96 / 0.96–0.97 (YOLOv9e) |
| Specificity per released hazard | ≥ 0.80 | ✅ 0.885–0.934; vest 0.582 ❌ → not released |
| AI latency per photo, p95 | ≤ 20 s | ✅ 0.15 s (YOLOv9e) |
| Robustness: F1 drop on dark / blurred / compressed / distant photos | report | ≤ 0.031 (YOLOv8s, `robustness_*.json`) |
| Load: 8 concurrent users | no errors | ✅ 0 errors, p95 181 ms (`load_test_*.json`) |
| Train/test leakage | none | ✅ 0 file overlaps, 0 near-duplicates |
| New report visible on dashboard | immediately (< 5 s) | ✅ `tests/test_api.py::test_full_workflow_and_dashboard_update` |
| Derived test labels agree with expert | report accuracy and κ | `evaluation/results/label_audit.json` |
| Automated tests and lint | all pass in CI | ✅ `pytest`, `ruff`, Docker smoke test |

Detection mAP50 measured with the same weights was 63.6 (YOLOv9e) and 54.9 (YOLOv8s), about 7 points below
the values in the SH17 paper (70.9 / 63.7). Apple GPU vs CPU and image size were ruled out; the likely cause is
a difference in the evaluated split or label version.

## Data, privacy and limitations

* All people, areas and records in the app are synthesized; no refinery data is included.
* Photos are processed locally; nothing is sent to external services.
* Demo sign-in has no passwords; a deployment would use the company's single sign-on.
* Scope is limited on purpose to hazards with a public, peer-reviewed labelled test set. Unsafe conditions
  (caustic spills, steam leaks, missing grating) have no such dataset; collecting one with ≥ 3 annotators and
  measuring their agreement is future work. Fire/smoke (D-Fire) was considered and excluded: fires are handled
  by alarms and emergency response, and steam plumes in a refinery would cause frequent false alarms.
* SH17 images come from Pexels (manufacturing settings), not refineries, so field performance may differ.

## Acknowledgements

SH17 dataset and YOLO weights: H. M. Ahmad and A. Rahimi, <https://github.com/ahmadmughees/SH17dataset>.
Ultralytics YOLO (AGPL-3.0). Ollama and Qwen2.5-VL.
