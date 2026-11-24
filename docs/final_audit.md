# Final audit – grading, consistency, reproducibility (2026-11-24)

Auditor: coding agent acting as course grader and release auditor (feature freeze; no features added).
Audited: repository `https://github.com/Hind2102/shms`, tag `v1.3.0` = `80e703cc30b0b62e547131d612ab968f22a94c63`;
report draft `~/Desktop/Final SEP/report/SHMS_Final_Report_DRAFT.pdf` / `.docx` (11 pages, produced 18 Nov 2026,
i.e. before v1.2.0 and v1.3.0); proposal `~/Desktop/Final SEP/Site Hazard Management System (SHMS) Proposal.pdf`
(no proposal .docx exists in that folder). Fix release: `v1.3.1` (this commit's tag; it contains this file, so its own
hash cannot be written here – see the final message / handover).

## Step 1 – Grader's brief

| Requirement | Finding | Status |
|---|---|---|
| One PDF ≤ 100 MB, report + appendices | 1.08 MB, 11 A4 pages | ✅ |
| Clickable GitHub URL + exact commit in §4 | URL present; commit is **`e0a538c…` (v1.1.1)**, not the submitted version | ❌ must change to v1.3.1 |
| Repo accessible to graders | unauthenticated `git clone` (credential helpers disabled) and anonymous HTTP 200 | ✅ |
| Version at that commit matches report | report describes v1.1.1 features and numbers; v1.2–v1.3 features (physical-condition reporting, report pins, redrawn plan, real-photo liquid challenge) absent | ❌ |
| Repo contents: source, tests, README, dependency file, config example with placeholders, samples, test + evaluation scripts, configs, results | all present (`pyproject.toml`, `.env.example`, `data/samples/`, `evaluation/`, `evaluation/results/`) | ✅ |
| Large data/models: download instructions + version | SH17 (Kaggle), weights via `scripts/download_models.py` with SHA-256, Hard Hat Workers (HF), warehouse (HF), Mendeley v4 DOI + archive SHA-256 | ✅ |
| No venvs, caches, passwords, API keys | none tracked now or in history; regex secret scan of all history: 0 hits | ✅ |
| README contents (team + contributions, structure, prerequisites, install, configuration, usage, testing, evaluation, exact commands, tested OS/Python, hardware, data/model/external access, paid APIs) | all present | ✅ |
| Structure: title + team, unnumbered Abstract, sections 1–5 with required content | present and in order | ✅ |
| Main report ≤ 4 pages incl. abstract + conclusion | conclusion ends on p. 4 | ✅ (no slack left) |
| Essential results in main report | yes, but the real-photo liquid result and physical-condition reporting are missing (see Step 4) | ⚠ |

Formatting, measured in the PDF (pdfplumber) and the DOCX (python-docx):

| Rule | Measured | Pages | Status |
|---|---|---|---|
| A4, single column | 21.0 × 29.7 cm, 1 column | all | ✅ |
| Margins 2.5 cm | text box 2.48–2.50 cm L/R, 2.55–2.58 cm top, ≥ 2.53 cm bottom | all | ✅ |
| Body and abstract **Times New Roman** 12 pt justified | DOCX specifies Times New Roman; the **PDF embeds `LiberationSerif` / `LiberationMono`** (LibreOffice substitution on a machine without Times New Roman) | 1–11 | ❌ re-export with Word |
| Line spacing 1.15, 0 pt before / 6 pt after, no first-line indent | body ✅; **objective list items O1–O5 have 2 pt after** | 1 | ❌ minor |
| No blank lines | 7 empty paragraphs, all holding an image or a page break | – | ✅ |
| Title 16 pt bold centred; team 12 pt centred | ✅ | 1 | ✅ |
| Headings 14 pt bold left, subsections 12 pt bold left, 12/6 pt | ✅ | all | ✅ |
| Tables/captions TNR ≥ 10 pt single | 10 pt, 1.0 | all | ✅ (font substitution as above) |
| Code monospace ≥ 10 pt single | Courier New 10 pt in tables; inline code 11 pt in 1.15-spaced body lines | 1–6, 9 | ⚠ inline code sits in 1.15 lines |
| Page numbers bottom right | right-aligned at 2.5 cm, 1.0 cm above the edge | all | ✅ |
| Same formatting in appendices; no cover page | ✅ | 5–11 | ✅ |
| No placeholders | **4 `[PENDING: …]` placeholders** | 4, 9 (×2), 11 | ❌ |

## Step 2 – Lecturer's feedback on the proposal

| Point | In the report? | Status |
|---|---|---|
| Name the hazard image dataset | SH17 named (§3.2) with size; Hard Hat Workers (CC0), synthetic warehouse set named; **SH17 licence/version not stated in the main report** | ⚠ add licence |
| P/R on a held-out labelled test set | Table 1 (1,620 held-out images) with CIs | ✅ |
| Why acceptance and latency are not the main evidence | only implicit (O5 "added after proposal feedback"; acceptance labelled simulated) | ⚠ say it in one sentence |
| ≥ 3 annotators / agreement | Appendix E: single-expert audit "does not replace an annotation study with at least three annotators"; conclusion: future work. **Main report p. 4 still shows `[PENDING]` for the audit** | ⚠ needs the audit result or an explicit "not performed" |

No new annotations were created; the derived SH17 labels come from the dataset's boxes. This must not be implied as a
multi-annotator study (it is not, anywhere).

## Step 3 – Proposal commitments

| Commitment (proposal) | Status | Evidence |
|---|---|---|
| Photo upload | delivered | `/report`; `test_html_report_flow` |
| Time AND location recorded | delivered | `created_at`; area + optional plan pin (`x`,`y`, migration `0006_report_pin`); `tests/test_site_pins.py` |
| AI suggests a hazard class; reporter confirms or corrects | delivered | `test_reporter_can_correct_ai`, `test_ai_acceptance_recorded` |
| Consequence chosen; likelihood from area history | delivered | `test_likelihood_grows_with_similar_history` |
| 5 × 5 matrix "based on ADOSH-SF", every level defined | partly – structure follows ADOSH-SF; band wording/deadlines **not checked against the guideline text** (owner task) | `/matrix`, `test_risk_matrix_page_separates_guidance_from_project_choices` |
| Fixed on the spot with action + closing photo | delivered (then verified by a second person) | `test_fixed_on_spot_records_how_and_awaits_verification` |
| Otherwise routed to Area Owner who plans, closes, documents | delivered | `test_owner_closes_with_documented_action`, `test_workflow_v2.py` |
| Live dashboard + heat map of refinery layout: open hazards, risk levels, trends by area | delivered / partly – plan view with open-risk, overdue, report-volume overlays per area; weekly trend is site-wide; per-area trend = repeat hotspots | `test_home_and_map.py`, `test_site_layout.py` |
| Operators/visitors see live hazards and required PPE before entering | delivered | area pages, entry route check; `test_site_layout.py` |
| Supervisors alerted to high-risk; every action traceable | delivered | `test_high_risk_alerts_supervisor_and_owner`, `test_events_record_from_and_to_for_every_transition` |
| Area Owners one view; management concentration and trend | delivered | role home pages; `test_each_role_gets_its_own_home_page` |
| Supports ADOSH-SF compliance and audits | partly (audit trail exists; no compliance mapping) | – |
| Compare YOLO vs a VLM on labelled images | delivered (YOLOv8s, YOLOv9e, Qwen2.5-VL 7B) | Table A3, `summary_subset.md` |
| "Fine-tune or prompt the best one" | partly – published weights reused (no fine-tuning); VLM prompted (v2, conditions c2) | `docs/verification.md` |
| Hazard category list "from OSHA, HSE and ISO 45001" | **not delivered and not explained** – no file or report section mentions OSHA, HSE or ISO 45001 | ❌ report must explain |
| Python backend, relational DB, laptops and phones, Git | delivered | FastAPI, SQLite, phone screenshots, CI |
| User stories + data model | delivered (17 stories) | `docs/requirements.md` |
| "Connect the model and deploy the application" | partly – local deployment (uvicorn) and Docker/Compose; **no hosted deployment**; report does not say so explicitly | ⚠ |
| ≥ 80 % accepted unchanged | simulated only (97.2 %, lenient); real acceptance recorded per report | `acceptance_yolo_sh17_yolo9e.json` |
| Suggestion ≤ 20 s | delivered (YOLOv9e p95 0.15 s; VLM p95 11.1 s) | metrics files |
| Report on dashboard/heat map ≤ 5 min | delivered (< 5 s) | `test_full_workflow_and_dashboard_update` |
| Synthesized data "reviewed by a safety supervisor for realism" | **not evidenced** – no record of a review | ❌ owner must state done/not done |
| Scope: unsafe conditions (spills, steam leaks, missing grating) | partly – PPE AI released; six physical conditions reportable **manually** in every area (incl. floor liquid, missing grating); experimental floor-liquid/walkway inference (synthetic pass; **real photos 0/5**); steam leaks not covered | `taxonomy.json`, `docs/external_floor_liquid.md` |

v1.3.0 claims against the pre-specification `e74aa34`: model, frozen prompt c2, seed, 1024 px, selection rule (indoor
annotated originals, exact and dHash ≤ 4 de-duplication, ≤ 32 by ascending SHA-256), outcome reporting (count,
denominator, Wilson interval, errors separately, no precision/specificity) all match
`evaluation/results/external_floor_liquid_v4/summary.json` (5 eligible, 0 detected, 0 errors, Wilson 0–0.434). Only 5
images qualified (cap 32); stated in README and `docs/external_floor_liquid.md`. **The report does not mention this
study at all.**

## Step 4 – Report ↔ repository consistency (at v1.3.0)

Checked programmatically from the files at the tag (`git show v1.3.0:…`):

| Claim | Page | Source | Match |
|---|---|---|---|
| Table 1, all 4 rows (pos/neg, P, R, spec + CI, MCC, F1, always-yes F1) | 3 | `evaluation/results/yolo_sh17_yolo9e/metrics.json` | ✅ |
| Table 2 Hard Hat Workers row | 4 | `external_hardhat_yolo_sh17_yolo9e/metrics.json` | ✅ |
| Table 2 SH17 head-shown row | 4 | `label_rule_audit_yolo_sh17_yolo9e.json` | ✅ |
| Table 2 synthetic spill / walkway rows | 4 | `conditions_qwen2.5vl_7b_c2_test/metrics.json` | ✅ |
| Acceptance 97.2 % [96.2–97.9] of 1,492 | 4 | `acceptance_yolo_sh17_yolo9e.json` | ✅ |
| 8 users: 22 req/s, p95 371 ms, 0 errors | 4 | `load_test_yolo_sh17_yolo9e.json` | ✅ |
| Robustness ≤ 0.031 macro-F1 | 4 | `robustness_sh17_yolo8s.json` | ✅ |
| YOLOv9e 0.15 s p95 | 3 | `yolo_sh17_yolo9e/metrics.json` (154 ms) | ✅ |
| 62–89 % prevalence; 1,620 images; always-yes F1 0.76–0.94 | 3 | `sh17_test_stats.json`, metrics | ✅ |
| Qwen2.5-VL v2 "MCC 0.59–0.87" | 4 | `ollama_qwen2.5vl_7b_promptv2_subset/metrics.json`: vest MCC 0.58496 → **0.58** | ❌ rounding |
| "15 user stories" | 1 | `docs/requirements.md`: **17** | ❌ |
| "288 tests" | 1, 3, 4 | fresh clone of v1.3.0: **312**; v1.3.1: **313** | ❌ |
| "nine pull requests merged" | 3 | GitHub: 13 by v1.3.0, 14 with v1.3.1 | ❌ |
| Commit `e0a538c` (v1.1.1) | 4 | submitted tag is v1.3.1 | ❌ |
| Appendix tables A1–A4, B1–B2, E1 | 5–9 | same files as above | ✅ (A3 vest MCC 0.585 shown correctly) |
| Coverage | – | not stated in the report (README/log: 72 %) | – |

Figures: Figure 1 (architecture) still correct in substance but does not show manual physical-condition reporting or
plan pins; A1 is byte-identical to `fig_mcc_subset.png`; A2 is an older render of the PR curves (content
consistent); **D2 and the plan panel of D3 show the v1.1 block layout, not the v1.3 Bayer-process plan with pins,
walkways and entry route**; the confirm-page screenshot is a placeholder although `docs/screenshots/desktop_confirm.png`
exists.

Report vs README: README (v1.3.0) states the real-photo liquid result (0/5), manual physical-condition reporting in
every area, 312 tests and coverage; the report states none of these. Hard-hat caveat, vest rejection, synthetic-only
evidence and post-hoc decisions are disclosed in both. Pending human tasks: README says label audit and ADOSH-SF check
pending; the report uses `[PENDING]` placeholders instead.

## Step 5 – Reproducibility (done, not reasoned)

| Step | Result |
|---|---|
| Unauthenticated clone of `v1.3.0` | ✅ `80e703c`; anonymous repository page HTTP 200 |
| README install, Python 3.12.14 (`python3.12 -m venv`, `pip install -e ".[dev,yolo]" matplotlib`) | ✅ 29 s |
| `python scripts/download_models.py --all` | ✅ both downloaded, "checksum OK" |
| `pytest` | ✅ **312 passed** in 67.6 s |
| `ruff check .` / `ruff format --check .` | ✅ / ✅ (100 files) |
| `uvicorn shms.asgi:app --reload --port 8765` (README notes the port option), sign-in `sara` / documented demo password via the form with CSRF | ✅ 303 → home |
| Main pages `/`, `/report`, `/site` (3 overlays), `/dashboard`, `/hazards`, `/queue`, `/matrix`, `/monitoring`, `/notifications`, `/areas/DIG` | ✅ all 200; unauthenticated `/api/dashboard` 401; 0 tracebacks |
| `python -m evaluation.release_gate --run yolo_sh17_yolo9e --dry-run` | ✅ reproduces Table 1 values and the decision (3 approved, vest rejected) |
| `python -m evaluation.compare` (README command) | ❌ **`KeyError: 'run'` on a clean clone** → fixed in v1.3.1; regenerated summaries byte-identical to v1.3.0 |
| `docker build` + smoke (health, login, 401 without token, token from CLI, dashboard, `/metrics`, health status, non-root) | ✅ healthy, user `app`, 0 tracebacks |
| GitHub Actions for `80e703c` | ✅ runs 45241175644 (push master) and 45245747985 (tag): all 5 jobs green |
| Fresh clone on Python 3.11.16 (no weights linked) | ✅ 311 passed, 1 skipped (`SH17 weights not downloaded`, expected) |

Friction points: (1) the broken `compare` command (fixed); (2) port 8000 is often busy – the README already gives
`--port 8765`; (3) `SHMS_DETECTOR` defaults to `mock` in code but `.env.example` sets `yolo` – consistent with the
README install flow (weights downloaded first), noted only.

Hygiene: no `.env`, tokens, databases, uploads, outbox, `instance/`, backups, weights, datasets, galleries or archives
in git now or in history; secret scan 0 hits. **Personal data:** the only e-mail address in the repository is the
university address in commit author/committer metadata (133 commits); no other personal address appears anywhere.
Removing it would require rewriting history and moving every tag (forbidden by the audit rules) – owner decision.

## Step 6 – Grade (as the lecturer would)

| Criterion (weight) | Score /100 | What costs marks | What would raise it | Effort |
|---|---:|---|---|---|
| Architecture and design (20 %) | 85 | dense §2; diagram omits manual physical-condition path and pins; OSHA/HSE/ISO category plan silently dropped | one sentence on the category change; add the manual-condition path to Figure 1 (optional) | 0.5 h |
| Implementation, code quality, documentation (30 %) | 82 | report describes v1.1.1, not the submitted code; broken README reproduction command (fixed); figures outdated | update report numbers/hash/features; replace D2/D3; fill placeholders | 2 h |
| Testing and evaluation (30 %) | 80 | label audit not done and shown as `[PENDING]`; real-photo liquid result (0/5) missing from the report while the synthetic pass is shown; Qwen MCC rounding; acceptance only simulated (disclosed) | add the 0/5 row; complete or explicitly state the audit; fix rounding | 1–2.5 h (audit 1–1.5 h by owner) |
| Reproducibility (10 %) | 85 → 95 with v1.3.1 | `compare` failed on a clean clone | fixed in v1.3.1 | done |
| Clarity, specificity, formatting (10 %) | 65 | PDF fonts are Liberation, not Times New Roman; 4 placeholders; list spacing 2 pt; page 4 has no slack | re-export with Word; remove placeholders; trim to stay within 4 pages | 1 h |
| **Weighted total** | **≈ 81 / 100** now; **≈ 89–91** after the fixes below | | | |

## Step 7 – Lists

### Blocking issues

| # | Issue | Fixed / needs owner |
|---|---|---|
| B1 | `evaluation.compare` crashed on a clean clone | **fixed** (v1.3.1, regression test, outputs byte-identical) |
| B2 | Report §4 names commit `e0a538c` (v1.1.1) | needs owner approval of the hash change → v1.3.1 commit |
| B3 | Report numbers out of date: 288 tests (pp. 1, 3, 4), 15 user stories (p. 1), nine PRs (p. 3), Qwen MCC 0.59 (p. 4) | needs owner approval (number changes) |
| B4 | Report omits v1.3 work: manual physical-condition reporting in every area, plan pins, and the pre-registered real-photo liquid challenge (0/5) | needs owner approval (claim changes) |
| B5 | `[PENDING]` placeholders: label audit (pp. 4, 9), confirm screenshot (p. 9), supervisor review (p. 11) | owner: audit result or "not performed"; review done/not done; screenshot can be inserted (exists) |
| B6 | PDF embeds Liberation fonts instead of Times New Roman | formatting fix: re-export via Microsoft Word on this Mac (TNR installed) – will apply |
| B7 | Figures D2/D3 show the v1.1 plan, not the submitted UI | replace with v1.3 screenshots (`desktop_site_open_risk.png`, phone set) – will apply with owner OK (captions unchanged in meaning) |
| B8 | Proposal's OSHA/HSE/ISO 45001 category list not addressed | needs owner approval of one sentence in "Changes from the proposal" |

### Non-blocking improvements (ranked by marks gained per hour)

1. One sentence in §3.2: why acceptance and latency are not evidence of accuracy (lecturer feedback) – 5 min.
2. SH17 licence (CC BY-NC-SA 4.0) and version (Kaggle release) in §3.2 – 5 min.
3. "Deployment is local (uvicorn or Docker Compose); no hosted deployment" in §4 – 5 min.
4. List items O1–O5 spacing 2 pt → 6 pt – 5 min.
5. Mention coverage (72 %) in §3.1 – 5 min.
6. Insert the existing confirm-page screenshot in Appendix D – 10 min.
7. Optional: add the manual physical-condition path to Figure 1 – 30 min.

### What only the owner can do

| Task | Time |
|---|---|
| Label audit clicks (100 images × 4 labels), then agent runs `python -m evaluation.label_audit score` | 1–1.5 h + 10 min |
| Check risk-matrix bands and wording against the ADOSH-SF guideline text | 30 min |
| Say whether a safety supervisor reviewed the synthesized records/layout (if not, the report must say so) | 5 min |
| Approve the report wording changes listed below | 15 min |
| Decide on the university e-mail in commit metadata (keep, or accept a history rewrite that moves tags) | 5 min |
| Create a new Kaggle token (the old one was typed into a chat) | 5 min |
| Upload the final PDF | 5 min |

### Report corrections (marked; wording changes await approval)

| # | Page | Current text | Proposed text | Reason |
|---|---|---|---|---|
| R1 | 1 | "288 automated tests run in CI." | "313 automated tests run in CI." | test count at v1.3.1 |
| R2 | 1 | "SHMS was built from 15 user stories" | "SHMS was built from 17 user stories" | `docs/requirements.md` |
| R3 | 2 | "Spills and obstructed walkways were tried as a time-boxed experiment on the only labelled set found (synthetic) and are off by default." | "Reporters can record six physical conditions (floor liquid, obstructed walkway, open panel cover, floor opening or missing grating, corrosion, other) manually in every area; AI inference for spills and walkways remains an off-by-default experiment. The planned OSHA/HSE/ISO 45001 category list was not built: the categories are the evaluated PPE checks plus these conditions." | v1.3 feature; proposal commitment |
| R4 | 3 | "288 pytest tests run in about two minutes without a GPU." | "313 pytest tests (72 % statement coverage) run in about two minutes without a GPU." | count; coverage |
| R5 | 3 | "nine pull requests merged only when green" | "14 pull requests merged only when green" | GitHub |
| R6 | 3 | "SH17 (Ahmad & Rahimi, 2024) has 8,099 industrial photos" | "SH17 (Ahmad & Rahimi, 2024; Kaggle release, CC BY-NC-SA 4.0) has 8,099 industrial photos" | lecturer: name dataset with licence |
| R7 | 3 | (none) | after the gate thresholds: "Acceptance rate and latency show usability, not accuracy, so they are reported as secondary criteria." | lecturer feedback |
| R8 | 4 | "Qwen2.5-VL reached MCC 0.59–0.87" | "Qwen2.5-VL reached MCC 0.58–0.87" | file value 0.585 → 0.58 |
| R9 | 4 | Table 2 has no real-photo liquid row | add row "Floor liquid: real indoor photos (Mendeley v4) – 5 / 0 – – – recall 0/5 [0–0.43] – – – Missed all" and in the caption "row 5 pre-registered (e74aa34), positives only, so precision and specificity are unknown" | v1.3.0 result; omission of a negative result |
| R10 | 4 | "Label audit: [PENDING: …]" | either the result, or "Label audit: not performed; no new annotations were created, and a study with at least three annotators remains future work." | placeholder; lecturer feedback |
| R11 | 4 | "Submitted version: commit e0a538cb7198e4426da66a946c77179744c865e8 (tag v1.1.1)" | "Submitted version: commit <v1.3.1 hash> (tag v1.3.1)" | submitted version |
| R12 | 4 | "Delivered: … 288 tests …" | "Delivered: … 313 tests …"; add "Deployment is local (uvicorn or Docker Compose); no hosted deployment was made." | count; honesty about deployment |
| R13 | 9 | "[PENDING: new screenshot of the confirm page …]" | insert `docs/screenshots/desktop_confirm.png` with caption "Figure D4. Confirm page: YOLOv9e evidence boxes and the hard-hat 'unverified suggestion' label." | placeholder |
| R14 | 9 | "[PENDING: per-hazard accuracy …]" | result table, or "Not performed (see Section 3.3)." | placeholder |
| R15 | 11 | "[PENDING: Hind to confirm the review]" | "Done on <date> by <role>" or "Not done" | placeholder; proposal commitment |
| R16 | 11 | "Hazards from photos of unsafe conditions … Partly: experimental spill and walkway check, synthetic evidence only, off by default" | "Partly: six conditions reportable manually in every area; experimental spill/walkway inference passed on synthetic images but missed all 5 real indoor water photos; off by default" | v1.3 |
| R17 | 8–9 | Figures D2, D3 (v1.1 plan) | v1.3 screenshots `desktop_site_open_risk.png`, `phone_site_open_risk.png` + existing phone home/queue | current UI |
| F1 | 1–11 | PDF fonts Liberation | re-export from Word (Times New Roman embedded) | formatting |
| F2 | 1 | O1–O5 list items 2 pt after | 6 pt after | formatting |

Page budget: R3, R7, R9 and R12 add about 7 lines to pages 2–4, which are full; compensating trims will be proposed
with the edited draft and the 4-page limit re-checked in the regenerated PDF.
