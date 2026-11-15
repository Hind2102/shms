# SHMS – Site Hazard Management System

AI-assisted web platform for reporting hazards from a photo, scoring them on a 5 × 5 consequence × likelihood
risk matrix, routing them to the accountable Area Owner, documenting **how** each one was closed, and showing
site-wide risk on a live dashboard and heat map of a (synthesized) alumina refinery.

The AI suggests three PPE hazards (worker without **hard hat**, without **hi-vis vest**, **bare hands**). It was
evaluated on the held-out split of the public, peer-reviewed **SH17** dataset with precision, recall and F1
(see [Evaluation](#evaluation)). Two local AI back-ends are compared: **YOLO** detectors trained on SH17, and a
**vision-language model served by Ollama** (`qwen2.5vl:7b`). No paid API is used.

| | |
|---|---|
| **Team** | Hind Alhmoudi (sole member) – requirements, hazard taxonomy and risk matrix, architecture, all code, tests, evaluation, label audit, report |
| **Course** | Software Engineering and Programming – Master in Applied Artificial Intelligence |
| **Tested on** | macOS 26 (Apple M5 Pro, 24 GB) with Python 3.12; Ubuntu 24.04 with Python 3.11–3.13 (GitHub Actions also runs macOS) |
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
  web/                    HTML routes (pages.py), JSON API (api.py), shared dependencies
  templates/, static/     Jinja2 pages and CSS (no JavaScript build)
  seed.py                 synthesized refinery layout, users and 6-month hazard history
evaluation/               offline evaluation on SH17
  prepare_sh17.py         builds the held-out test manifest and dataset statistics
  evaluate.py             runs a detector, writes predictions + metrics (P/R/F1, 95% CIs, latency, mAP)
  compare.py              comparison tables and figures
  label_audit.py          expert audit of the ground-truth labels (accuracy, Cohen's kappa)
  metrics.py, sh17.py     metric functions and dataset reader
  data/                   manifest, dataset stats, audit results (committed)
  results/                metrics.json per run, summary.md, figures (committed)
scripts/download_models.py  downloads and checksums the SH17 YOLO weights
tests/                    pytest suite (unit, workflow, API end-to-end, detectors, evaluation pipeline)
docs/architecture.md      architecture diagram, component responsibilities, design decisions
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
git clone https://github.com/<your-account>/shms.git
cd shms
python3 -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -e ".[dev,yolo]" matplotlib
python scripts/download_models.py --all   # SH17 YOLO weights, verified by SHA-256
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
| `SHMS_YOLO_WEIGHTS` | `models/sh17_yolo8s.pt` | YOLO weights file |
| `SHMS_YOLO_CONF` | `0.35` | YOLO operating threshold (chosen on the threshold sweep, see results) |
| `SHMS_YOLO_DEVICE` | auto | `cpu`, `mps` (Apple GPU) or `cuda:0` |
| `SHMS_OLLAMA_MODEL` | `qwen2.5vl:7b` | Ollama model tag |
| `SHMS_DATABASE_URL` | `sqlite:///shms.db` | Any SQLAlchemy URL |
| `SHMS_UPLOAD_DIR` | `uploads` | Where photos are stored |

Risk-matrix definitions, bands and target close-out times are in `shms/config/risk_matrix.json`; hazard
categories are in `shms/config/taxonomy.json`. Both can be changed without code changes.

## Usage

```bash
uvicorn shms.asgi:app --reload       # or: make run
```

Open <http://127.0.0.1:8000>. On first start the database is created and filled with a synthesized refinery
(9 areas, 9 users, ~240 historical hazards). Pick a role on the sign-in page (demo sign-in, no passwords).

Main workflow:

1. **Report** – as *Ahmed (Operator)*: *+ Report hazard* → choose area → take/upload a photo (try
   `data/samples/`). The AI marks what it found on the photo.
2. **Confirm and score** – keep or correct the suggested hazard type, choose the worst credible consequence.
   Likelihood is computed from the area's history and the risk level is shown. Tick *I already fixed it on the
   spot* to close it immediately with the action taken and a closing photo.
3. **Route and close** – otherwise the hazard goes to the Area Owner (e.g. *Khalid* for Digestion). High and
   Extreme hazards alert the safety supervisor (*Sara*). The owner plans an action and closes the hazard with a
   description of the control and a closing photo. Every step is kept in the audit trail.
4. **Monitor** – the dashboard shows KPIs, the heat map (click an area for its live hazards and required PPE),
   weekly trend, repeat hotspots and the hazard register with filters.

The JSON API is documented at <http://127.0.0.1:8000/docs>.

To reset the demo: stop the server and delete `shms.db` and `uploads/`.

## Testing

```bash
pytest                 # or: make test
```

98 tests, under a minute, no model or GPU needed (the YOLO tests run automatically when the weights are present). They
cover every cell of the risk matrix, the PPE rules, the workflow state machine and permissions, the HTTP API
end-to-end (report → confirm → route → close → dashboard), the detectors (Ollama mocked at HTTP level), the
metric functions against hand-computed values, and the evaluation pipeline on a miniature fake dataset.
GitHub Actions runs the suite on Ubuntu and macOS with Python 3.11 and 3.12.

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
python -m evaluation.evaluate --root $SH17 --detector yolo --weights models/sh17_yolo8s.pt --map
python -m evaluation.evaluate --root $SH17 --detector yolo --weights models/sh17_yolo9e.pt --map
python -m evaluation.evaluate --root $SH17 --detector yolo --weights models/sh17_yolo8s.pt --subset
python -m evaluation.evaluate --root $SH17 --detector yolo --weights models/sh17_yolo9e.pt --subset
python -m evaluation.evaluate --root $SH17 --detector ollama --model qwen2.5vl:7b --subset   # ~needs Ollama
python -m evaluation.compare && python -m evaluation.compare --only-subset
```

(`make eval-prepare eval-yolo eval-vlm eval-compare SH17=~/datasets/sh17` runs the same.)
Runs are cached in `predictions.jsonl` and resume if interrupted. The subset is a fixed random sample of 300
held-out images (seed 42), used to compare all models on identical images because the VLM is slower.

### Label audit

The derived labels were checked by a safety professional on 100 random held-out images:

```bash
python -m evaluation.label_audit build --root $SH17     # writes evaluation/data/label_audit.html
# open it, click Agree/Disagree per label, Download CSV -> evaluation/data/label_audit_results.csv
python -m evaluation.label_audit score                  # accuracy, 95% Wilson CI, Cohen's kappa
```

### Success criteria and results

| Criterion | Target | Result |
|---|---|---|
| Precision per PPE hazard (held-out SH17, best model) | ≥ 0.80 | see `evaluation/results/summary.md` |
| Recall per PPE hazard | ≥ 0.75 | see `evaluation/results/summary.md` |
| AI latency per photo, p95 (steady state, stated hardware) | ≤ 20 s | see `evaluation/results/summary.md` |
| New report visible on dashboard | immediately (< 5 s) | verified by `tests/test_api.py::test_full_workflow_and_dashboard_update` |
| Derived test labels agree with expert | report accuracy and κ | `evaluation/results/label_audit.json` |
| Automated tests | all pass in CI | GitHub Actions badge / `pytest` |

## Data, privacy and limitations

* All people, areas and records in the app are synthesized; no refinery data is included.
* Photos are processed locally; nothing is sent to external services.
* Demo sign-in has no passwords; a deployment would use the company's single sign-on.
* The AI covers PPE only. Unsafe conditions (caustic spills, steam leaks, missing grating) have no public
  labelled dataset and are classified by the reporter; a labelled refinery dataset with ≥ 3 annotators is
  future work.
* SH17 images come from Pexels (manufacturing settings), not refineries, so field performance may differ.

## Acknowledgements

SH17 dataset and YOLO weights: H. M. Ahmad and A. Rahimi, <https://github.com/ahmadmughees/SH17dataset>.
Ultralytics YOLO (AGPL-3.0). Ollama and Qwen2.5-VL.
