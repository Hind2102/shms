# SHMS – Verification log

Purpose: every number and claim the final report may use, with the command that produced it, the file it lives
in, and what remains uncertain. Earlier reported numbers are treated as claims and re-checked here.

Branch: `feature/verification` (created from `master` at `c19e9be`). Nothing pushed.

## Environment (applies to every step)

| Item | Value |
|---|---|
| Hardware | MacBook Pro, Apple M5 Pro, 24 GB RAM (`sysctl hw.memsize` = 25 769 803 776) |
| OS | macOS 26.6.2 |
| Python | 3.12.14 in `.venv` (created with `uv venv --python 3.12`, uv 0.12.10) |
| Packages | torch 2.15.0, ultralytics 8.4.214, fastapi 0.163.1, sqlalchemy 2.1.8, pillow 13.0.0, numpy 2.5.4 |
| YOLO device | `mps` (Apple GPU). A CPU re-run of YOLOv8s detection mAP gave the identical value (0.549), see Step 3 |
| Ollama | 0.40.16, model `qwen2.5vl:7b` (6.0 GB, digest 5ced39dfa4ba) |

---

## Step 0 – Inspection (no changes)

- `git status`: clean. `git log`: `c19e9be` (robustness/load/leakage), `b2f307b` (course update), `ffa8792`
  (results), `de90451`, `6f18c27` – as expected.
- Read `README.md`, `docs/architecture.md`, `AGENTS.md`. `AGENTS.md` asks for work on a `feature/<name>`
  branch, so this work is on `feature/verification`.
- Untracked-but-ignored local state found: `shms.db` (15 Nov), `uploads/` (121 load-test photos), `runs/`
  (Ultralytics validation output), `.env`.

## Step 1 – Prepared update applied

```bash
git switch -c feature/verification
git am ../shms_gate_update.patch          # -> 19450e9 "Honest evaluation and release gate: ..."
source .venv/bin/activate && uv pip install -e ".[dev,yolo]" matplotlib
pytest                                    # 119 passed, 1 failed (see below)
ruff check . && ruff format --check .     # All checks passed / 46 files already formatted
```

`test_release_gate.py::test_shipped_release_matches_shipped_results` **failed instead of skipping** before the
re-score: the committed `metrics.json` files pre-date the new metrics (no specificity/MCC), so the gate approves
nothing (`[] != ['no_hard_hat', 'no_eye_protection', 'no_gloves']`). Re-checked after Step 3 – see there.

## Step 2 – Database: backed up, not deleted

```bash
mkdir -p backups && cp -p shms.db backups/shms_2026-11-17.db      # backups/ added to .gitignore
shasum -a 256 shms.db backups/shms_2026-11-17.db                  # identical: a3d05d763c08cb65…
```

Contents of the old database (read-only query of the backup):

| Table | Rows |
|---|---:|
| areas | 9 |
| users | 9 |
| hazards | 240 |
| hazard_events | 1 010 |
| notifications | 200 |

Hazards with a `photo_path`: **0**. All 240 hazards are seeded demo history (`shms/seed.py`, dates 2026-05-19 to
2026-11-15); there are no real user-created reports, so no CSV export was needed. The 121 files in `uploads/`
are `detect_*_load.jpg` images written by the load test, not reports.

Switch to a fresh demo database:

- `.env`: `SHMS_DATABASE_URL=sqlite:///shms_demo.db` (only this line changed; previous `.env` copied to
  `backups/env_before_2026-11-17.bak`). The URL is relative, so start the app from the project folder.
- Verified: app starts, `/login` 200, `/metrics` 200; `shms_demo.db` created and ignored by git (`*.db`).
- Outdated-schema refusal, tested on a scratch **copy** of the backup (so the backup cannot be modified):
  start-up stops with `shms.db.SchemaMismatch: The database … was created by an older SHMS version (table
  'hazards' lacks ['idem_key']) …`. Checksum of the copy unchanged afterwards.
- Observation: the message advises "delete the file". Given the backup policy, "move or back up the file" would
  be safer wording (not changed – not a bug).

**Rollback path.** The backup has the pre-`b2f307b` schema, which current code refuses by design. To return
to it: `git switch --detach ffa8792` (last commit with that schema) and set
`SHMS_DATABASE_URL=sqlite:///backups/shms_2026-11-17.db` (or restore `backups/env_before_2026-11-17.bak` to
`.env`). Original `shms.db` is also still in place, untouched.

## Step 3 – Evaluation integrity

### 3.1 Provenance

| Item | Evidence |
|---|---|
| Dataset | Kaggle `mugheesahmad/sh17-dataset-for-ppe-detection`, downloaded 2026-11-15 (~20:50–21:08 local) with Kaggle CLI 2.2.5 into `~/Desktop/Final SEP/datasets/sh17` (13 GB, outside the repo). `images/` 8 099, `labels/` 8 099, `meta-data/` 8 099, `train_files.txt` 6 479 lines, `val_files.txt` 1 620 lines (SHA-256 prefixes `6599473388c5b2ca`, `b8c7936d6842e8db`). Also present, unused: `voc_labels/`. Ultralytics wrote `labels.cache` into the dataset folder during mAP validation (only change made to the dataset folder). |
| Weights | `python scripts/download_models.py --all` → "already present, checksum OK" for both. `sh17_yolo8s.pt` SHA-256 `dfaf451b…f4e40a4b` (22.5 MB), `sh17_yolo9e.pt` `5ac6ac23…4f33f39d` (117.3 MB); digests match the script, which pins the authors' GitHub release v1. Checkpoint metadata: saved by ultralytics **8.2.38** on 2024-06-22/23, `imgsz=640`, 200 epochs. |
| Code behind results | All five prediction runs (`yolo_sh17_yolo{8s,9e}[_subset]`, `ollama_qwen2.5vl_7b_subset`) were produced on 2026-11-15 with the code at `de90451` (timestamps in each `metrics.json → environment.date`); committed in `ffa8792`. `robustness_sh17_yolo8s.json` and `load_test_yolo_sh17_yolo8s.json` were produced with `b2f307b` (committed `c19e9be`). Metrics re-scored with `19450e9` (Step 3.5); originals preserved in `backups/evidence_results_c19e9be/` with `backups/evidence_results_c19e9be.sha256`. |
| Seeds | Test subset: `random.Random(42).sample` (300 of 1 620). Dev split: 100 images from the train list (`prepare_sh17.py`). Label audit sample: seed 7. Bootstrap CIs: 1 000 resamples, seed 0. Ollama: `temperature 0, seed 42`. YOLO inference is deterministic given weights and image. |

### 3.2 Splits and leakage

```bash
R=~/Desktop/"Final SEP"/datasets/sh17
python -m evaluation.prepare_sh17 --root $R
git diff --stat evaluation/data/sh17_test_manifest.csv      # empty -> identical test set
```

- Test manifest unchanged (empty diff). Ground-truth columns hash `cc30023fad5d1b11` – identical at `ffa8792`,
  `b2f307b` and HEAD (see 3.6).
- `sh17_dev_manifest.csv`: 100 rows, 100 unique, **100 in `train_files.txt`, 0 in `val_files.txt`**.
- Exact overlap train ∩ test (by file name): **0**. Near-duplicates (dHash 64-bit, Hamming ≤ 4 bits) of any
  training image inside the test split: **0**.
- Limits of these checks: file-name overlap misses re-encoded copies; dHash catches resized/re-compressed
  copies but not crops, flips, or different photos of the same scene/person; the threshold of 4 bits was not
  calibrated on this dataset. Overlap between the test images and whatever data the YOLO backbone (COCO
  pre-training) or Qwen2.5-VL were **pre-trained** on is **unknown** – SH17 images come from Pexels, which is
  widely scraped, so VLM exposure to some test photos cannot be excluded.

Subset representativeness (300 vs full 1 620; two-proportion z-test subset vs remaining 1 320):

| Hazard | Full | Subset | Diff | p |
|---|---:|---:|---:|---:|
| no_hard_hat | 0.760 | 0.790 | +0.030 | 0.19 |
| no_eye_protection | 0.615 | 0.650 | +0.035 | 0.17 |
| no_gloves | 0.769 | 0.793 | +0.024 | 0.27 |
| no_hi_vis_vest | 0.891 | 0.897 | +0.006 | 0.72 |

No difference is significant, but all four are higher in the subset (the hazards are correlated, so this is one
tendency, not four). Subset numbers are therefore slightly optimistic for precision; full-split numbers are the
primary YOLO result.

### 3.3 Tuning disclosure

- `conf = 0.35` was the default in the first commit (`6f18c27`), before any results existed in this repository.
  The threshold sweep (computed on the **test** split) later showed it is at or near the best F1 (Step 3.5).
  ⚠ The README describes it as "chosen on the threshold sweep", which reads as test-set tuning and contradicts
  the git history – wording to be corrected (Step 8).
- The choice of **YOLOv9e over YOLOv8s** and the **specificity ≥ 0.80** criterion in the release gate were
  decided **after** seeing test-split results (`evaluation/release_gate.json → _why` says so). For those two
  decisions the test split is not untouched; the reported YOLOv9e numbers carry a small selection bias. A
  clean confirmation would need a further held-out set that does not exist for SH17.
- The VLM prompt v2 was written after seeing v1 failures on test images (Step 5 of the earlier session); it is
  tuned on the dev split only and run once on the test subset (Step 6).

### 3.4 Label definition (boxes → image-level labels)

SH17 annotates objects, not violations. `shms/detection/rules.py::hazards_from_boxes` derives four yes/no labels
per image, applied identically to ground-truth boxes and model boxes:

- `no_hard_hat`: a head box (≥ 0.04 % of image) with no helmet covering it (≥ 30 % of helmet inside the head box
  extended upwards by 50 % of its height).
- `no_eye_protection`: a face box (≥ 0.04 %) with no glasses / face-guard covering ≥ 30 %.
- `no_gloves`: a hand box (≥ 0.02 %) with no glove covering ≥ 30 %.
- `no_hi_vis_vest`: a person box (≥ 0.4 %) whose torso contains no safety-vest / safety-suit centre.

Limits: (1) occlusion – a head or hand hidden behind an object yields no label at all; (2) **absence of a helmet
box is not proof of absence of a helmet** (an unlabelled or occluded helmet becomes a "violation");
(3) the rule does not know whether PPE is required in the scene (many SH17 photos are offices, shops, homes);
(4) one violating person makes the whole image positive; (5) thresholds were set by hand, not calibrated.
`helmets_overlapping_a_head_pct = 80.5` shows heads are usually labelled under helmets, which the rule relies
on. The label audit (Step 7) will quantify agreement with an expert.

### 3.5 Re-scored results (no model re-run)

```bash
for w in sh17_yolo9e sh17_yolo8s; do
  python -m evaluation.evaluate --root $R --detector yolo --weights models/$w.pt --rescore
  python -m evaluation.evaluate --root $R --detector yolo --weights models/$w.pt --subset --rescore
done
python -m evaluation.evaluate --root $R --detector ollama --prompt v1 --subset --rescore
python -m evaluation.compare && python -m evaluation.compare --only-subset
```

Checks: every precision, recall, F1, latency, detection-mAP and threshold-sweep value is **identical** to the
pre-rescore files in `backups/evidence_results_c19e9be/` (0 mismatches); TP/FP/FN/TN, specificity and MCC were
recomputed independently from `predictions.jsonl` + manifest and match `metrics.json` (0 mismatches).
Outputs: `evaluation/results/summary_full.md|json`, `summary_subset.md|json`, `fig_mcc_{full,subset}.png`,
`fig_pr_{full,subset}.png`. 95 % CIs are percentile bootstrap over images (1 000 resamples).

**Image-level violation metrics – full held-out split (1 620 images), operating threshold 0.35**

| Model | Hazard | Pos / Neg | TP | FP | FN | TN | Precision | Recall | Specificity [95% CI] | MCC [95% CI] | F1 | Always-yes F1 |
|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|---:|
| YOLOv9e | no_hard_hat | 1232 / 388 | 1193 | 44 | 39 | 344 | 0.964 | 0.968 | 0.887 [0.86–0.92] | 0.859 [0.83–0.89] | 0.966 | 0.864 |
| YOLOv9e | no_eye_protection | 996 / 624 | 953 | 41 | 43 | 583 | 0.959 | 0.957 | 0.934 [0.91–0.95] | 0.891 [0.87–0.91] | 0.958 | 0.761 |
| YOLOv9e | no_gloves | 1246 / 374 | 1192 | 43 | 54 | 331 | 0.965 | 0.957 | 0.885 [0.85–0.92] | 0.833 [0.80–0.86] | 0.961 | 0.870 |
| YOLOv9e | no_hi_vis_vest | 1443 / 177 | 1399 | 74 | 44 | 103 | 0.950 | 0.970 | 0.582 [0.51–0.65] | 0.599 [0.53–0.66] | 0.960 | 0.942 |
| YOLOv8s | no_hard_hat | 1232 / 388 | 1162 | 44 | 70 | 344 | 0.964 | 0.943 | 0.887 | 0.812 | 0.953 | 0.864 |
| YOLOv8s | no_eye_protection | 996 / 624 | 909 | 57 | 87 | 567 | 0.941 | 0.913 | 0.909 | 0.815 | 0.927 | 0.761 |
| YOLOv8s | no_gloves | 1246 / 374 | 1164 | 57 | 82 | 317 | 0.953 | 0.934 | 0.848 | 0.765 | 0.944 | 0.870 |
| YOLOv8s | no_hi_vis_vest | 1443 / 177 | 1368 | 79 | 75 | 98 | 0.945 | 0.948 | 0.554 | 0.507 | 0.947 | 0.942 |

**Fixed 300-image subset (all three models on identical images)**

| Model | Hazard | Pos / Neg | TP | FP | FN | TN | P | R | Spec | MCC | F1 | Always-yes F1 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| YOLOv9e | no_hard_hat | 237 / 63 | 232 | 7 | 5 | 56 | 0.971 | 0.979 | 0.889 | 0.878 | 0.975 | 0.883 |
| YOLOv9e | no_eye_protection | 195 / 105 | 187 | 7 | 8 | 98 | 0.964 | 0.959 | 0.933 | 0.890 | 0.961 | 0.788 |
| YOLOv9e | no_gloves | 238 / 62 | 232 | 8 | 6 | 54 | 0.967 | 0.975 | 0.871 | 0.856 | 0.971 | 0.885 |
| YOLOv9e | no_hi_vis_vest | 269 / 31 | 261 | 10 | 8 | 21 | 0.963 | 0.970 | 0.677 | 0.667 | 0.967 | 0.946 |
| YOLOv8s | no_hard_hat | 237 / 63 | 225 | 6 | 12 | 57 | 0.974 | 0.949 | 0.905 | 0.827 | 0.962 | 0.883 |
| YOLOv8s | no_eye_protection | 195 / 105 | 183 | 9 | 12 | 96 | 0.953 | 0.938 | 0.914 | 0.847 | 0.946 | 0.788 |
| YOLOv8s | no_gloves | 238 / 62 | 223 | 12 | 15 | 50 | 0.949 | 0.937 | 0.806 | 0.731 | 0.943 | 0.885 |
| YOLOv8s | no_hi_vis_vest | 269 / 31 | 258 | 12 | 11 | 19 | 0.956 | 0.959 | 0.613 | 0.580 | 0.957 | 0.946 |
| Qwen2.5-VL 7B (prompt v1) | no_hard_hat | 237 / 63 | 79 | 4 | 158 | 59 | 0.952 | 0.333 | 0.937 | 0.246 | 0.494 | 0.883 |
| Qwen2.5-VL 7B (prompt v1) | no_eye_protection | 195 / 105 | 71 | 21 | 124 | 84 | 0.772 | 0.364 | 0.800 | 0.170 | 0.495 | 0.788 |
| Qwen2.5-VL 7B (prompt v1) | no_gloves | 238 / 62 | 76 | 11 | 162 | 51 | 0.874 | 0.319 | 0.823 | 0.127 | 0.468 | 0.885 |
| Qwen2.5-VL 7B (prompt v1) | no_hi_vis_vest | 269 / 31 | 90 | 2 | 179 | 29 | 0.978 | 0.335 | 0.935 | 0.178 | 0.499 | 0.946 |

Macro MCC (subset): YOLOv9e 0.823, YOLOv8s 0.746, Qwen2.5-VL v1 0.180. The Qwen v1 F1 is far **below** the
always-yes baseline on every hazard.

**Why the vest check barely beats always-yes.** 89 % of test images are vest-positive, so always-yes already
reaches F1 0.942; F1 is dominated by the large positive class and can hardly move. Only 177 images are
negatives and only 45 test images contain a labelled vest at all (97 vest boxes). YOLOv9e raises 74 false
alarms on those 177 negatives (specificity 0.58). Breaking the 74 down: **47 are images whose ground truth has
no person box at all** (e.g. close-ups of hands, partial bodies) – the model detects a person, finds no vest and
flags it, while the label rule has no person to evaluate; 27 are images with labelled people, 14 of which have a
labelled vest the model missed or did not match to the torso. So the weakness is partly the model (rare class)
and partly the label definition (who counts as a "person"). MCC (0.60) and specificity expose this; F1 hides it.

**Object-level detection mAP is a different quantity** (box localisation over 17 classes, IoU 0.5) and is reported
separately below; it is not comparable to the image-level violation metrics above.

### 3.6 "Byte-identical after the formatting patch" claim – verified

Two temporary git worktrees (`ffa8792` = code `de90451` + results, and `b2f307b` = formatting patch) were each
used to run `prepare_sh17` and `compare --only-subset` on the same committed predictions:

- `summary.md` from both commits: **identical** (`cmp`), and identical to the committed `ffa8792:summary.md`.
- Ground-truth columns of the regenerated test manifest: hash `cc30023fad5d1b11` in both and at HEAD.
- Re-applying the current `rules.py` at conf 0.35 to the cached YOLO boxes reproduces the stored hazard codes
  for all 1 620 + 1 620 + 300 + 300 predictions (0 differences).

### 3.7 Superseded outputs removed

`git rm evaluation/results/summary.md summary.json fig_f1.png fig_pr.png` (commit `40ebc24`); still in history at
`ffa8792`.

### 3.8 Detection mAP vs the SH17 paper (object level; time-boxed 45 min, used ~26 min)

Documented protocol (authors' README, fetched 2026-11-17 via `gh api repos/ahmadmughees/SH17dataset/readme`):
`model.val(data="sh17.yaml", batch=1, imgsz=640, device="cuda:0")`, "ultralytics==8.0.38". The authors' table
reports **1 620 images / 15 358 instances** for the validation set – identical to our `val_files.txt` split.
Class order in their `sh17.yaml` and in both checkpoints equals `evaluation/sh17.py::SH17_NAMES`.

| Run | Software | Settings | YOLOv8s mAP50 / mAP50-95 | YOLOv9e mAP50 / mAP50-95 |
|---|---|---|---|---|
| Our evaluation (`--map`) | ultralytics 8.4.214, mps | imgsz 640, batch 8 | 0.549 / 0.346 | 0.636 / 0.421 |
| Same on CPU | 8.4.214, cpu | imgsz 640, batch 8 | 0.549 / 0.346 | – |
| Authors' batch size | 8.4.214, mps | imgsz 640, batch 1 | 0.548 / 0.346 | – |
| Larger input | 8.4.214, mps | imgsz 1280, batch 8 | 0.494 / 0.298 | – |
| Version that saved the weights | **8.2.38**, mps (isolated venv) | imgsz 640, batch 1 | 0.559 / 0.356 | 0.650 / 0.437 |
| Documented version | 8.0.38 | – | cannot load the checkpoints (`ultralytics.nn.modules.conv` missing) | – |
| **Paper / README** | 8.0.38 (stated), CUDA | imgsz 640, batch 1 | **0.637 / 0.417** | **0.709 / 0.487** |

Evidence gathered:
- The checkpoints were saved by ultralytics **8.2.38**, not 8.0.38 as the README states.
- Each checkpoint stores its final training-time validation metrics (`train_metrics`): YOLOv8s mAP50 0.6365,
  mAP50-95 0.4155; YOLOv9e 0.7088 / 0.4864 – i.e. the paper's numbers. That validation used the authors' local
  `safe_human.yaml`, whose image list we cannot see.
- Hardware (mps vs cpu), batch size and ultralytics version together explain at most ~1.4 points.

**Verdict: not reproduced.** Our best result is 7.8 (YOLOv8s) and 5.9 (YOLOv9e) mAP50 points below the paper on a
split with the same image and instance counts. The cause is **not established**; we only exclude device, batch
size, input size and library version as the main explanation. Scratch environments used:
`$TMPDIR/…/scratchpad/venv_ul8238` (not part of the project).

## Step 4 – Release gate

```bash
python -m evaluation.release_gate --run yolo_sh17_yolo9e
git diff shms/config/ai_release.json      # only "decided_at" changed
```

Thresholds (`evaluation/release_gate.json`): precision ≥ 0.80, recall ≥ 0.75, specificity ≥ 0.80, p95 latency
≤ 20 000 ms, on the full held-out split.

| Hazard | P | R | Specificity [95% CI] | Decision |
|---|---:|---:|---|---|
| no_hard_hat | 0.964 | 0.968 | 0.887 [0.86–0.92] | APPROVED |
| no_eye_protection | 0.959 | 0.957 | 0.934 [0.91–0.95] | APPROVED |
| no_gloves | 0.965 | 0.957 | 0.885 [0.85–0.92] | APPROVED |
| no_hi_vis_vest | 0.950 | 0.970 | 0.582 [0.51–0.65] | REJECTED (specificity) |

- The approved list is unchanged; only `decided_at` moved (commit `10ebae1`).
- Robustness of the decision: for every approved hazard the **lower** CI bound of every criterion is above its
  threshold, and the vest's **upper** specificity bound (0.65) is below 0.80, so no decision is borderline.
- `tests/test_release_gate.py` (4 tests) pass after the re-score; before it, the "shipped release matches
  shipped results" test failed (Step 1).
- ⚠ **Criteria provenance.** `release_gate.json → _why` and the README say the precision and recall targets
  "come from the proposal". The proposal (`../Site Hazard Management System (SHMS) Proposal.pdf`, §4) lists
  three success criteria: ≥ 80 % of AI classifications **accepted by the reporter without changes**; AI
  suggestion within **20 s**; new report on the dashboard within **5 minutes**. It contains no precision/recall
  targets. The 0.80/0.75 thresholds were therefore introduced later (by the author, before the evaluation was
  run in this repo); the specificity threshold after seeing results (Step 3.3). The `_why` text is a
  configuration file covered by AGENTS.md, so it was **not** edited; see Handover → decisions.

## Step 6 – Vision-language models

### 6.1 Prompt v1 – kept unchanged as a failed comparison

`evaluation/results/ollama_qwen2.5vl_7b_subset/` (run 2026-11-15, code `de90451`; re-scored only). On the 300-image
test subset: recall 0.32–0.36, MCC 0.13–0.25, F1 below the always-yes baseline for every hazard (Step 3.5).

Failure pattern: the answers are nearly all-or-nothing – **197 of 300 images got no hazard at all** (191 of them
contain at least one labelled violation) and 77 got all four. In the two raw answers inspected on 2026-11-15
(pexels-photo-7888728, pexels-photo-5953548) the model set `people_visible: false` and explained that the scene
(home office, pizza delivery) was not an industrial workplace, although one explanation itself listed missing
PPE. The explanation is not stored for empty answers, so this cannot be confirmed for all 197.

The low recall is therefore **not shown to be only a prompt problem**. Other plausible, untested causes:
- model size/capability (Ollama reports 8.3 B parameters, quantisation Q4_K_M – `ollama show qwen2.5vl:7b`);
- input downscaling to 1 024 px on the long side (`encode_image(max_side=1024)`): SH17 photos reach 8 192 px, and
  gloves, glasses and small heads far from the camera may become a few pixels;
- the image-level question format (one yes/no per hazard for the whole photo, plus an explicit "if no person is
  visible answer false" escape) versus the per-object definition used for the labels;
- the label definition itself (Step 3.4): many SH17 "violations" are people in settings where no PPE is required,
  which a model asked as a "safety inspector" may reasonably not call a violation.

### 6.2 Prompt v2 – separate, versioned experiment

Prompt v2 (`shms/detection/ollama_vlm.py → PROMPT_V2`, written by the author after seeing v1 fail on test images):
no refinery framing, "treat every visible person as if on an industrial site", per-person booleans
(head/face/hands/torso visible; hard hat, eye protection, all hands gloved, hi-vis/safety suit); hazards derived
in code like the YOLO rules. Not modified during this verification.

Dev split (100 training-split images, `--split dev`; `evaluation/results/ollama_qwen2.5vl_7b_promptv2_dev/`):

| Hazard | P | R | Spec | MCC | F1 | Always-yes F1 |
|---|---:|---:|---:|---:|---:|---:|
| no_hard_hat | 0.961 | 0.914 | 0.842 | 0.704 | 0.937 | 0.895 |
| no_eye_protection | 0.964 | 0.841 | 0.946 | 0.764 | 0.898 | 0.773 |
| no_gloves | 0.904 | 0.949 | 0.619 | 0.616 | 0.926 | 0.883 |
| no_hi_vis_vest | 0.930 | 0.879 | 0.333 | 0.175 | 0.904 | 0.953 |

Latency p50 5.8 s, p95 10.3 s, 0 errors. No prompt change was made after the dev run; v2 was then run **once** on
the test subset (6.3).

### 6.3 Prompt v2 – single run on the 300-image test subset

```bash
python -m evaluation.evaluate --root $R --detector ollama --prompt v2 --split dev     # 6.2
python -m evaluation.evaluate --root $R --detector ollama --prompt v2 --subset        # once
python -m evaluation.compare && python -m evaluation.compare --only-subset
```

`evaluation/results/ollama_qwen2.5vl_7b_promptv2_subset/` (commit `03f2b5b`), 300 images, 0 errors.

| Hazard | TP | FP | FN | TN | P | R | Spec [95% CI] | MCC [95% CI] | F1 | Always-yes F1 | YOLOv9e MCC (same images) |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|---:|---:|
| no_hard_hat | 229 | 5 | 8 | 58 | 0.979 | 0.966 | 0.921 [0.84–0.98] | 0.872 [0.79–0.93] | 0.972 | 0.883 | 0.878 |
| no_eye_protection | 152 | 6 | 43 | 99 | 0.962 | 0.779 | 0.943 [0.89–0.98] | 0.690 [0.62–0.77] | 0.861 | 0.788 | 0.890 |
| no_gloves | 234 | 17 | 4 | 45 | 0.932 | 0.983 | 0.726 [0.61–0.83] | 0.777 [0.69–0.86] | 0.957 | 0.885 | 0.856 |
| no_hi_vis_vest | 247 | 7 | 22 | 24 | 0.972 | 0.918 | 0.774 [0.62–0.91] | 0.585 [0.44–0.71] | 0.945 | 0.946 | 0.667 |

Macro MCC: v2 0.731 vs v1 0.180, YOLOv8s 0.746, YOLOv9e 0.823. Latency p50 5.6 s, p95 11.1 s (YOLOv9e 0.15 s).

Interpretation:
- v2 removes most of v1's failure: the change of prompt alone moved macro MCC from 0.18 to 0.73 on the same images.
  This supports – but does not prove – that the framing was the main cause of v1's low recall; model size and
  downscaling (6.1) were not varied.
- v2 roughly matches YOLOv9e for hard hat (overlapping CIs), and is clearly weaker for eye protection (recall 0.78)
  and gloves (specificity 0.73). Indicative gate check on the subset only (the gate is defined on the full split,
  which the VLM was not run on): hard hat and eye protection would pass; gloves (spec 0.73) and vest (spec 0.77) would
  fail. Latency p95 11.1 s is within the 20 s target but 60–70× slower than YOLOv9e (p50 5.6 s vs 0.09 s; p95 11.1 s vs 0.15 s).
- Caveats: prompt v2 was designed after looking at v1 failures on **test** images, so the test subset is not untouched
  for v2's design; it was then run once without changes. 300 images give wide CIs (e.g. vest specificity 0.62–0.91,
  31 negatives).
- Not done (optional, time): `qwen3-vl:8b`. No vision model is used or evaluated for spills or blocked walkways –
  there is no labelled test set for them.

## Step 7 – Label audit and scope

### 7.1 What the label audit does – and does not do

```bash
python -m evaluation.label_audit build --root $R --n 100     # done 2026-11-15 -> evaluation/data/label_audit.html (not in git)
# Hind: open the page, click Agree / Disagree for every image x hazard, "Download CSV"
#       -> save as evaluation/data/label_audit_results.csv
python -m evaluation.label_audit score                       # accuracy + 95% Wilson CI + Cohen's kappa per hazard
```

- 100 held-out images, drawn with seed 7 from the test manifest. For each image and hazard the page shows the
  label **derived** from SH17's boxes by `rules.py` (YES/NO); one domain expert (Hind) answers Agree/Disagree.
- It measures how often the dataset-derived labels agree with one expert (label accuracy, Wilson CI) and the
  agreement beyond chance (Cohen's kappa between derived labels and the expert's implied labels).
- It does **not** create new ground truth and does **not** satisfy an "at least 3 annotators" requirement for new
  annotations: it is one rater checking existing labels, so inter-annotator agreement among new annotators
  cannot be computed from it.
- Status (2026-11-17): **not yet done** – `label_audit_results.csv` does not exist. The audit must not be filled
  in by anyone other than the expert, and not by an AI.
- The page built on 2026-11-15 (older `label_audit.py`) was checked against the current code: identical 100
  images in identical order and identical derived labels, so it does not need rebuilding.

### 7.2 Draft scope-change note (for Hind's review – not final wording)

> **Scope change.** The proposal motivated SHMS with unsafe *conditions* in an alumina refinery – caustic spills on
> walkways, leaking steam or slurry flanges, missing grating or handrails – and planned to compare off-the-shelf
> models "on a set of labelled hazard images". No public, peer-reviewed labelled test set exists for those
> conditions, and building one credibly would require several annotators and an agreement study, which did not fit
> the project. The AI component was therefore scoped to hazards that *can* be measured: PPE violations, using the
> held-out split of the peer-reviewed SH17 dataset. Four PPE checks were evaluated – hard hat, eye/face protection,
> gloves and hi-vis vest. Three passed the release gate and are enabled in the app; the **hi-vis vest check was
> evaluated and rejected** (it flags too many compliant images: specificity 0.58). The workflow, risk matrix,
> routing, closure records and dashboard are delivered as proposed, but the hazard list
> (`shms/config/taxonomy.json`) now contains only the four PPE categories, so unsafe conditions cannot currently be
> reported even manually. Because the hazard-type list on the confirm page is limited to checks that are both
> required in the area and approved by the release gate (`Area.check_codes`), a missing hi-vis vest can currently
> not be reported either, not even manually. Detecting unsafe conditions is future work and depends on collecting a labelled
> dataset with at least three annotators. The proposal's own AI success criterion ("≥ 80 % of AI classifications
> accepted without changes") can only be measured in field use; the app records acceptance for that purpose,
> and the offline precision/recall/specificity evaluation was added as a measurable substitute.

The original proposal was not edited.

## Step 5 – Performance and model choice

### 5.1 What the load test measures (applies to both runs)

- Script: `evaluation/load_test.py`. Endpoint: `POST /api/detect` with header `X-User-Id: 1` and a multipart JPEG
  upload. Server side the request saves the photo to `uploads/detect_*.jpg` and runs the configured detector
  (`shms/web/api.py::detect`) – real upload, real disk write, real YOLO inference; no database write.
- Image: `data/samples/sh17_pexels-photo-7888728__no_hard_hat_no_eye_protection_no_gloves_no_hi_vis_vest.jpg`,
  1280 × 853 px, 162 KB (the same image for every request; YOLO resizes to 640 internally).
- Warm-up: one request before measuring (excluded). Then for each concurrency level (1, 4, 8 threads) 40
  requests in total, sent back-to-back by a thread pool.
- Timing boundary: **client side, end to end** – from just before `httpx.post` to the parsed response on the same
  machine (loopback): upload, multipart parsing, file write, inference, JSON response. Throughput = successful
  requests / wall time of the level.
- Server: one uvicorn worker process (no `--workers`), detector loaded once; requests are served from a thread
  pool, inference on the Apple GPU (mps).
- Limits: 40 requests per level is a short burst (< 1 s wall time per level for YOLOv8s), no think time, client
  and server on the same laptop, one fixed image (no cache effects in YOLO, but OS file cache is warm).

### 5.2 Earlier run (YOLOv8s, 2026-11-17, code `b2f307b`) – `evaluation/results/load_test_yolo_sh17_yolo8s.json`

| Users | Requests | Errors | Throughput (req/s) | p50 (ms) | p95 (ms) |
|---:|---:|---:|---:|---:|---:|
| 1 | 40 | 0 | 43.0 | 22 | 30 |
| 4 | 40 | 0 | 55.1 | 72 | 83 |
| 8 | 40 | 0 | 54.6 | 140 | 181 |

App started with `SHMS_DETECTOR=yolo SHMS_YOLO_DEVICE=mps` on port 8765 (port 8000 is occupied on this Mac by a
Docker container) and the default `models/sh17_yolo8s.pt` of that version.

### 5.3 New run with the default YOLOv9e (2026-11-17, code `10ebae1`) – `evaluation/results/load_test_yolo_sh17_yolo9e.json`

```bash
SHMS_DETECTOR=yolo SHMS_YOLO_DEVICE=mps SHMS_YOLO_WEIGHTS=models/sh17_yolo9e.pt uvicorn shms.asgi:app --port 8765 &
python -m evaluation.load_test --url http://127.0.0.1:8765 \
  --image data/samples/sh17_pexels-photo-7888728__no_hard_hat_no_eye_protection_no_gloves_no_hi_vis_vest.jpg \
  --users 1 4 8 --requests 40
```

(`SHMS_YOLO_WEIGHTS` set explicitly because real environment variables take precedence over `.env`; the response's
`model` field confirms `yolo:sh17_yolo9e`.) Server peak RSS during the run (sampled every 0.2 s with `ps`):
**1 380 MB**. 0 tracebacks in the server log.

| Users | Requests | Errors | Throughput (req/s) | p50 (ms) | p95 (ms) |
|---:|---:|---:|---:|---:|---:|
| 1 | 40 | 0 | 18.8 | 51 | 63 |
| 4 | 40 | 0 | 21.4 | 183 | 223 |
| 8 | 40 | 0 | 22.3 | 356 | 371 |

Throughput saturates at ~22 req/s from 4 users on (one process, one GPU); latency then grows linearly with
queueing. The YOLOv8s file was **not** re-run, to keep it as original evidence.

### 5.4 Model-inference latency (separate from API throughput)

| Measurement | YOLOv8s | YOLOv9e | Source |
|---|---|---|---|
| Per-image detector latency, 1 620 test images, p50 / p95 (steady state; includes reading the original SH17 photo – up to 8 192 px – resizing and inference) | 66 / 128 ms | 95 / 154 ms | `evaluation/results/yolo_sh17_yolo*/metrics.json → latency_steady` |
| Pure `model.predict` on one warm 1280 px image, 50 runs, p50 / p95 | 9 / 9 ms | 37 / 38 ms | standalone script (below) |
| API end-to-end, 1 user, p50 / p95 | 22 / 30 ms | 51 / 63 ms | load tests 5.2 / 5.3 |
| API throughput at 8 users | 54.6 req/s | 22.3 req/s | load tests |

Standalone measurement (`/usr/bin/time -l python -c "…YOLO(w).predict(img, device='mps') × 51…"`):

| | YOLOv8s | YOLOv9e |
|---|---:|---:|
| Peak RSS | 644 MB | 1 062 MB |
| macOS peak memory footprint (includes GPU/unified memory) | 606 MB | 2 304 MB |
| Weights file | 22.5 MB | 117.3 MB |
| Parameters | 11.1 M | 57.4 M |

All are far below the 20 s latency criterion.

### 5.5 Recommendation: YOLOv9e (with YOLOv8s as the low-resource fallback)

- **Accuracy:** YOLOv9e has higher MCC on every hazard (full split: hard hat 0.859 vs 0.812, eye 0.891 vs 0.815,
  gloves 0.833 vs 0.765, vest 0.599 vs 0.507) and equal or higher specificity on every hazard (gloves 0.885 vs
  0.848). Both models would pass the release gate for the same three hazards and fail it for the vest; YOLOv9e
  passes with larger margins.
- **Cost:** ~4× slower pure inference, ~2.5× lower API throughput, ~1.6× RSS, 5× file size. On the stated laptop
  this still means < 0.2 s per photo, which is irrelevant for a reporting workflow (one photo per report).
- **Reproducibility:** both use pinned, checksummed weights and deterministic inference; equal.
- **Caveat:** the choice was made after seeing test results (Step 3.3). The gap is consistent across all four
  hazards and both test sets (full and subset), which makes it unlikely to be a selection artefact, but it is not a
  pre-registered decision. YOLOv8s remains the better choice for CPU-only or memory-constrained machines.

## Step 8 – Reproducibility and hygiene

### 8.1 README commands checked

| Command / claim | How checked | Result |
|---|---|---|
| `git clone https://github.com/Hind2102/shms.git` | `gh repo view Hind2102/shms` | Repository exists (public) but is **empty** – nothing pushed. README now says "pending". |
| `python3 -m venv .venv` + `pip install -e ".[dev,yolo]" matplotlib` | fresh `git clone` of this branch into a scratch folder | ✅ with Python 3.12 (pip). ✗ with macOS system Python 3.9.6: pip fails with "File setup.py or setup.cfg not found … editable mode currently requires a setuptools-based build" – README now tells macOS users to use `python3.12`. |
| `pytest` in the fresh clone (no weights) | as above | 119 passed, 1 skipped ("SH17 weights not downloaded") |
| `ruff check . && ruff format --check .` | fresh clone and working copy | All checks passed; all files formatted |
| `python scripts/download_models.py --all` | working copy | "already present, checksum OK" (download path itself not re-run) |
| `uvicorn shms.asgi:app` | ports 8000/8001 are occupied on this Mac (Docker / another Python program), so `--port 8765` | ✅ app starts; README already mentions `--port 8765` |
| Evaluation commands (`prepare_sh17`, `evaluate … --rescore`, `compare`, `release_gate`) | Steps 3–4 | ✅ |
| `load_test` | Step 5; needs `--url` when not on port 8000 | ✅ (README now mentions `--url`) |
| `make eval-vlm` | `make -n` | previously ran an outdated single command; now runs exactly the three README commands |
| `docker compose up --build` / CI | – | see 8.4 |
| "~0.25 s per photo on CPU" (Prerequisites) | see 8.4 | |

README claims corrected (commit `49de103`): tested-on line; repository pending; conf 0.35 provenance; label audit
pending and single-rater; vest "42 % of people" → "42 % of photos without a vest violation (74/177)"; proposal's
own AI criteria added; load test p95 for both models; mAP paragraph ("not reproduced, cause unknown"); CI/Docker
"after the first push"; test count 120; reset by moving files aside instead of deleting; vest/unsafe conditions
cannot be reported.

### 8.2 Files git must not track

`git ls-files` and `git log --all --name-only` contain **no** `.env`, `kaggle.json`/token, `*.db`, `uploads/`,
`.venv/`, caches, `models/*.pt`, datasets or `backups/` – neither now nor in history. All are matched by
`.gitignore` (`git check-ignore -v` checked for each). Largest tracked files: the two full-split
`predictions.jsonl` (4.6 MB each).

### 8.3 Secret scan

Regex scan of every tracked text file at HEAD and of the full patch history (`git log --all -p`) for Kaggle
(`KGAT_…`, kaggle.json keys), GitHub (`gh*_`, `github_pat_`), AWS, OpenAI/Anthropic-style, Hugging Face,
Roboflow keys, private-key blocks and generic `api_key/secret/password/token = …` assignments: **0 hits**. Nothing
to rotate because of git. (The Kaggle token typed into the assistant chat on 2026-11-15 lives only in
`~/.kaggle/access_token`, mode 600; rotating it is optional hygiene.)

### 8.4 Docker image and CPU latency (2026-11-18)

- `docker build -t shms-verify:local .` → exit 0, image 2.32 GB.
- CI smoke test repeated locally on a port confirmed free (8790; a first attempt on 8766 was discarded because an
  unrelated local program already listened there): `/api/health` `{"status":"ok"}`, `/login` contains "Sign in",
  `/api/dashboard` contains `kpis`, `/metrics` contains `shms_hazards`; container log shows each request with 200;
  health status `healthy`; runs as user `app`; 0 tracebacks. Throw-away containers removed afterwards.
- Same image with `models/` mounted read-only (as in `docker-compose.yml`), YOLOv9e on CPU: 6 × `POST /api/detect`
  → first 8.3 s (model load), then 1.3–2.2 s; memory 1.38 GiB; 0 errors.
- `docker compose up` itself was not run: it publishes port 8000, which is occupied on this Mac. README now says how
  to change the mapping.
- Native CPU (M5 Pro), `build_detector(..., device="cpu")`, 30 calls on the sample photos: YOLOv8s p50 35 ms /
  p95 41 ms; YOLOv9e p50 200 ms / p95 216 ms. The README's former "~0.25 s on any laptop" was replaced by these
  measured values.
- Observation: `POST /api/detect` returns the raw detector output, including the unreleased `no_hi_vis_vest`
  suggestion; the report/confirm flow filters it out (8.5). Not changed (API design question, not a crash).
- GitHub Actions: **never run** – the repository is empty. CI status is unverified until the first push.

### 8.5 App walkthrough (photo → closure), YOLOv9e on mps, port 8765, `shms_demo.db`

Driven through the HTML forms with `curl` (cookie sessions):

1. `POST /login` as user 1 (Ahmed, reporter) → 303.
2. `POST /report` area 1 (BXH) with the sample photo → redirect to `/hazards/241/confirm`; AI `yolo:sh17_yolo9e`,
   2.5 s (first, cold call), suggestion *Worker without gloves*.
3. Confirm page offers exactly *hard hat, eye/face protection, gloves* – **no vest option** in BXH, although BXH
   requires vests (release gate).
4. `POST /hazards/241/confirm` (no_hard_hat, consequence 4) → status OPEN, risk C4 × L2 = 8 (Medium),
   `ai_accepted = 0` (reporter changed the AI suggestion), assigned to user 4 (Khalid, Area Owner).
5. As user 4: `POST /plan` → 303; `POST /close` with closing photo → status CLOSED, `closed_by_id = 4`,
   closure photo stored.
6. Audit trail (`hazard_events`): reported → confirmed → assigned → planned → closed.
7. `GET /areas/BXH` → 200, shows "AI checks reports here for: Hard hat, Eye / face protection, Gloves. Not
   AI-checked yet (did not pass the release gate on test data): Hi-vis vest."
8. `GET /monitoring` → 200, shows SLO panels (p95 target ≤ 20 s, error rate ≤ 2 %, acceptance rate).
9. 0 tracebacks in the server log.

Note: the closure text stored was cut at a `;` – reproduced with a raw socket capture: **curl** `-F` treats `;` as
a field separator and never sent the rest. Not an app bug.

### 8.6 Final checks (2026-11-18, HEAD before the last docs commit)

```bash
pytest                                  # 120 passed (YOLO tests included: weights present)
ruff check . && ruff format --check .   # All checks passed / 48 files already formatted
uvicorn shms.asgi:app --port 8765       # /login 200, /api/health 200, /metrics 200, 0 tracebacks (shms_demo.db via .env)
```

---

## Handover (2026-11-18)

### 1. Verified, and what remains uncertain

Verified (commands and files above):
- Same held-out test set throughout (manifest diff empty; ground-truth hash identical across three commits);
  dev split disjoint from test; 0 file overlaps and 0 dHash near-duplicates train↔test.
- Weights match their published SHA-256; provenance of every results folder.
- All earlier image-level numbers (P/R/F1, latency, mAP, sweeps) reproduce exactly from the cached predictions; the
  new specificity/MCC were recomputed independently. The "byte-identical after the formatting patch" claim holds.
- Release gate: hard hat, eye protection, gloves approved with margin; vest rejected with margin.
- Load tests (YOLOv8s earlier, YOLOv9e now), memory, CPU latency, Docker build + smoke test, end-to-end workflow in
  the app, /areas/BXH and /monitoring, 120 tests, ruff, clean secret scan, nothing sensitive tracked.

Uncertain / not established:
- **Detection mAP is not reproduced** (−6 to −8 points vs the paper); cause unknown.
- Label quality: the label audit has not been done, so how often the derived labels are wrong is unknown.
- Selection bias: YOLOv9e choice, the specificity threshold and prompt v2 were decided after seeing test results.
- Pre-training overlap of YOLO/Qwen with SH17 (Pexels) images is unknown.
- VLM results rest on 300 images (wide CIs) and one model; other causes of v1's failure were not varied.
- Field performance: SH17 is not refinery imagery; the proposal's acceptance criterion (≥ 80 %) can only be
  measured in use.
- CI has never run (repository empty).

### 2. What was fixed and how it was tested

No application code was changed – no demonstrated bug required it. Changes were limited to:
- `.gitignore`: `backups/` (checked with `git check-ignore`).
- `.env`: `SHMS_DATABASE_URL=sqlite:///shms_demo.db` (app start-up verified; previous file backed up).
- `README.md`: claims aligned with evidence (8.1, 8.4).
- `Makefile`: `eval-vlm` now runs the README's three commands (`make -n` checked).
- Re-scored `metrics.json`, new summaries/figures, v2 runs, YOLOv9e load test, `ai_release.json` timestamp.

Issues found but deliberately **not** changed (need your decision, see 5): outdated-schema message says "delete";
`release_gate.json → _why` says the P/R targets come from the proposal (they do not); vest cannot be reported even
manually; `/api/detect` returns the unreleased vest suggestion; the two new figures use different colours for the
same YOLO model.

### 3. Backups and preserved evidence

| What | Where |
|---|---|
| Original database (unchanged, still in place) | `shms.db` |
| Database backup (SHA-256 identical) | `backups/shms_2026-11-17.db` |
| `.env` before the change | `backups/env_before_2026-11-17.bak` |
| Results exactly as committed at `c19e9be` + checksums | `backups/evidence_results_c19e9be/`, `backups/evidence_results_c19e9be.sha256` |
| `evaluation/data` as at `c19e9be` | `backups/evidence_data_c19e9be/` |
| Superseded summary/figures | git history at `ffa8792` |
| All commits of this verification | branch `feature/verification` (not merged, not pushed) |

`backups/` is git-ignored: copy it somewhere safe if the laptop is the only copy.

### 4. Remaining tasks before Friday 20 November

| # | Task | Who | Effort | Depends on |
|---|---|---|---|---|
| 1 | Click the label audit (100 images × 4 labels), save `label_audit_results.csv` in `evaluation/data/` | Hind | 1–1.5 h | – |
| 2 | `python -m evaluation.label_audit score`, commit, update README/verification rows | agent | 10 min | 1 |
| 3 | Decide the five open issues in §2 (wording/design) | Hind | 15 min | – |
| 4 | Apply the decisions (text fixes ~15 min; making the vest reportable is a code change + test, ~1 h) | agent | 15 min – 1 h | 3 |
| 5 | Merge `feature/verification` into `master` | agent | 5 min | your OK |
| 6 | Push to GitHub, watch CI (tests on Ubuntu/macOS, Docker smoke test) | agent | 20–30 min | your OK to push; 5 |
| 7 | Write the report from this file; review the scope-change draft (7.2) | Hind | — | 1–3 |
| 8 | Optional: `qwen3-vl:8b` dev + subset run | agent | ~2 h compute | time |
| 9 | Optional: create a new Kaggle token (old one was typed into a chat) | Hind | 5 min | – |

### 5. Decisions or actions that need you

1. **Label audit** – only you can do it (it must not be filled in by anyone else or by an AI).
2. **`release_gate.json → _why`**: change "Precision and recall targets come from the proposal" to an accurate
   statement? (config file – needs your approval under AGENTS.md).
3. **Vest reporting**: keep "not reportable at all", or allow manual reporting of a missing vest where it is
   required while keeping the AI check off? (behaviour change).
4. **Schema-mismatch message**: say "move or back up" instead of "delete"? (wording in `shms/db.py`).
5. **Push / merge**: may I merge into `master` and push so CI runs, and is the repository meant to be public?
6. **Scope-change note** (7.2): review the wording before it goes into the report.

### 6. Candid assessment of submission readiness

The software is in good shape: workflow works end to end, 120 tests and lint pass, the Docker image builds and
passes the smoke test, nothing sensitive is in git. The evaluation is now honest and traceable: every number has a
command, a file and a commit, the test set is verified unchanged, and the weaknesses (vest, label definition,
selection bias, F1 vs always-yes) are stated rather than hidden.

It is **not yet submission-ready** for three reasons, all small but real: (1) the label audit is still empty, and
the README/report must not claim it until it is done; (2) nothing has been pushed, so the public repository and CI –
both referenced by the README – do not exist in practice yet; (3) two statements need your decision because they are
in configuration or behaviour (the "from the proposal" justification and vest reporting). The mAP gap to the paper is
a disclosed limitation, not a blocker. With roughly half a day of your time (audit + decisions + report) and an
hour of agent work after your go-ahead, the project can be submitted by Friday.

---

# Phase 0 – Safety net (2026-11-18)

### P0.1 Patches applied (branch `feature/verification`)

```bash
git am ../shms_fixes3.patch ../shms_proposal4.patch
```
- `f4c58eb` Correct release-gate provenance note; clearer wording for gated checks and outdated databases; readable
  model names and zoomed PR figure. (Resolves handover decisions 2 and 4; the `_why` text now states the proposal's
  own criteria.)
- `aa90777` Simulated reporter acceptance (`evaluation/acceptance.py`), user stories + data model
  (`docs/requirements.md`), no vest requirement in seeded areas (the synthesized refinery uses flame-resistant
  coveralls). (Resolves handover decision 3 by design: no area requires a vest.)

### P0.2 README
Structure lists `docs/requirements.md` and `docs/verification.md`; evaluation commands include
`python -m evaluation.acceptance --run yolo_sh17_yolo9e`; test count 121; seeded areas require coveralls, not vests.

### P0.3 Demo database
`shms_demo.db` renamed to `shms_demo.old.db` (`mv -n`, not deleted). Next start re-seeded a fresh `shms_demo.db`:
240 hazards, **0 areas with a vest check**; `/areas/BXH` lists "Flame-resistant coverall" and AI checks for hard hat,
eye/face protection, gloves only. (Status: implemented+tested.) Note: the walkthrough in 8.5 was done on the older
seed, where BXH still required a vest.

### P0.4 Checks and simulated acceptance

```bash
pytest                                   # 121 passed
ruff check . && ruff format --check .    # All checks passed / 50 files already formatted
python -m evaluation.acceptance --run yolo_sh17_yolo9e
python -m evaluation.acceptance --run yolo_sh17_yolo8s
python -m evaluation.acceptance --run ollama_qwen2.5vl_7b_promptv2_subset
python -m evaluation.compare && python -m evaluation.compare --only-subset
```

**Simulated** reporter acceptance (proposal criterion ≥ 80 %), `evaluation/results/acceptance_<run>.json`:

| Run | Images with ≥ 1 released violation | Accepted unchanged | 95 % Wilson CI | Wrong type | Nothing suggested |
|---|---:|---:|---|---:|---:|
| YOLOv9e, full split | 1 492 | 1 450 (97.2 %) | 96.2–97.9 % | 15 | 27 |
| YOLOv8s, full split | 1 492 | 1 416 (94.9 %) | 93.7–95.9 % | 22 | 54 |
| Qwen2.5-VL 7B prompt v2, subset | 284 | 277 (97.5 %) | 95.0–98.8 % | 3 | 4 |

Label: **simulated**, not field acceptance. Limits of the simulation (`evaluation/acceptance.py`): (1) an image counts
as accepted when the AI's top suggestion is *any* violation present – most images contain several, so this is
lenient; (2) images without a released violation are excluded, so false alarms on compliant workers do not lower
acceptance (they are captured by specificity instead); (3) a real reporter may also change a correct suggestion.
Real acceptance is recorded per report in the app (`ai_accepted`) and shown on `/monitoring`.

`compare`: summary tables unchanged; only `fig_pr_full.png` and `fig_pr_subset.png` changed (axes now zoomed to
0.3–1.0 – the report must mention that the axes do not start at 0).

### P0.5 Publication note
The pushed history contains the committer e-mail configured for this repository on all commits and, in six commit
messages written by the course-update patches, a `Claude-Session:` link (only openable by its owner). The secret scan
(8.3) found no credentials.

---

# Phase 1b (part 1) – Alembic migrations (branch `feature/migrations`, 2026-11-18)

Status: **implemented+tested**.

- `alembic.ini` (root) + `shms/migrations/` (inside the package, so the Docker image has them). The URL comes from
  `SHMS_DATABASE_URL`/`.env`. `alembic` added to `pyproject.toml` and the Dockerfile's dependency list.
- `0001_baseline`: the original schema (`de90451`), created only if tables are missing.
- `0002_course_upgrade`: `idem_key`, `uq_reporter_idem_key`, four CHECK constraints, three indexes (SQLite batch
  mode), each only if missing – so both an unstamped old database and an unstamped database from `b2f307b`–`aa90777`
  upgrade with the same command.
- `shms/db.py`: `schema_status()` (`empty`/`current`/`outdated`), `migrate_to_head(url)`; `create_all()` creates
  a new database and stamps it at head, and refuses an outdated one with "Back up the file, then run
  `alembic upgrade head`".
- Tests `tests/test_migrations.py` (4): old-schema fixture upgraded with identical counts and joins; outdated message;
  new DB at head; migrated schema == model schema (`alembic.autogenerate.compare_metadata` → no differences).
  TDD note: the two migration scripts were written before their tests; to show the tests can catch a broken
  migration, 0002 was mutated (no `idem_key`) → 2 tests failed; restored → 4 passed.
- Bug found and fixed during this task (caught by the existing `test_database_rejects_invalid_values`): stamping a
  new database through the migration environment left SQLite foreign-key enforcement switched off on the shared
  connection (`PRAGMA foreign_keys` cannot be changed inside a transaction). Fix: stamp directly with
  `MigrationContext.stamp`, and run migrations on a private engine that is disposed afterwards. Suite: 125 passed.

Verification on copies (originals untouched; backup SHA-256 `a3d05d76…` before and after):

```bash
cp backups/shms_2026-11-17.db $TMP/mig_old.db; cp shms_demo.old.db $TMP/mig_demo.db
SHMS_DATABASE_URL=sqlite:///$TMP/mig_old.db alembic upgrade head
```

| Copy of | Rows users/areas/hazards/events/notifications | Hazard+relationship hash | Events hash | FK violations after | Version after |
|---|---|---|---|---:|---|
| `backups/shms_2026-11-17.db` (pre-`b2f307b` schema) | 9 / 9 / 240 / 1 010 / 200 – identical | `a27eb9105fa4ac2a` = | `de70e25fcb9cdd8f` = | 0 | `0002_course_upgrade` |
| `shms_demo.old.db` (current schema, unstamped) | 9 / 9 / 241 / 1 017 / 196 – identical | `c145c8747adb93cf` = | `1057d4660c52a33b` = | 0 | `0002_course_upgrade` |

The hash covers, per hazard: id, status, area id and code, reporter id and name, assignee, closer, category, risk
score, closure action, number of events and of notifications. The app refuses the unmigrated copy with the new
message and starts on the migrated copy.

**Rollback path:** migrations are applied to a file that was copied first; to roll back, stop the app, put the copy
back and check out the code version that matches it (the old file needs code ≤ `aa90777`). `alembic downgrade` is
implemented for 0002 but restoring the copy is the documented path.

---

# Phase 1 – Safety workflow (branch `feature/workflow`, 2026-11-18)

Plan: `docs/superpowers/plans/2026-11-18-phase1-workflow-security.md`. All items below: **implemented+tested**.

### P1.1 State machine (`shms/services.py`)

| From | To | Action (event kind) | Who (server-side check) |
|---|---|---|---|
| draft | open | confirm → routed (`assigned`) | reporter or supervisor |
| draft | pending_verification | confirm "fixed on the spot" (`closed`) | reporter |
| open | planned | plan: text + action owner + deadline > now (`planned`) | Area Owner of the area, assignee, supervisor |
| open, planned | pending_verification | close with action (+ photo) (`closed`) | same as plan |
| pending_verification | closed | verify with note (`verified`) | supervisor or reporter, **not the closer** |
| pending_verification | open | reject, reason required (`rejected`) | supervisor or reporter, not the closer |
| closed | open | reopen, reason required (`reopened`); new target date, escalation reset | supervisor or reporter |

- One table `ALLOWED_TRANSITIONS`; the only status writer is `_move()`, which records `from_status`, `to_status`,
  actor, time and note on a `HazardEvent`. Managers are read-only (no action allowed).
- AI fields are never written after the draft (`test_ai_suggestion_is_preserved_through_the_lifecycle`).
- Dashboards: "open" = open + planned + pending; closure statistics count verified closures only.
- Migration `0003_workflow` (+ `0004_escalation`). Legacy closed rows keep `closed` with no verification and are
  labelled "Closed before the verification step existed" – nothing is invented. Upgrade of a copy of
  `backups/shms_2026-11-17.db` to `0004_escalation`: counts and relationship hashes identical, 0 FK violations.
- Requirement changes (old tests updated, named in commit `9491d30`): close → pending_verification instead of
  closed; fixed-on-the-spot → pending_verification; closed can be reopened.
- Seed: the synthetic supervisor verifies historic closures 0.5–3 days later (211 closed, 23 open, 6 pending in a
  fresh demo). This is **simulated** history.

### P1.2 Deadlines and escalation (`shms/escalate.py`, `shms/notify.py`)

- Target close date from the risk band (`config/risk_matrix.json`), unchanged. Plan deadline defaults to it.
- Project rule (not a regulation): level 1 when an open/planned hazard passes its target date → supervisors;
  level 2 at +7 days → managers; each once; pending/closed never escalate; reopen → new target date, level 0.
- Runs via `python -m shms.escalate` (schedulable) and on page loads, throttled to once a minute; failures are logged
  and never break a page.
- Notifications: in-app + **test mail backend** writing `.eml` files to `outbox/` (git-ignored, `SHMS_MAIL_OUTBOX`).
  No e-mail is sent; demo addresses use the reserved `shms.example` domain.

### P1.3 Manual reporting and honest wording

- When the AI finds nothing: "The AI found none of the checked items missing (…). This is not a confirmation that the
  scene is in order" + "Not checked by the AI here: <area PPE not covered by a released check>, and any hazard other
  than missing PPE." The former green "No missing PPE detected" box is gone. A test scans the visible page text for
  "safe", "no violation", "no missing PPE detected", "all clear", "compliant".
- When the AI fails: error shown, every released, required hazard type selectable.
- Audit note for new reports: "found none of the checked items missing" / "could not analyse the photo"
  (existing notes in databases unchanged).

### P1.4 Bugs found and fixed (each with a test that failed first)

| Bug | Test |
|---|---|
| `/hazards?status=<unknown>` → HTTP 500 (`ValueError`) | `test_register_ignores_unknown_status_filter` |
| Plan form with a deadline date → `NameError` (missing import) | `test_html_plan_with_deadline_date` |
| Owner queue would drop planned hazards | `test_queue_keeps_planned_hazards_and_supervisor_sees_pending` |

### P1.5 Checks

`pytest` 172 passed; `ruff check .` / `ruff format --check .` clean (local, 2026-11-18). New test files:
`test_workflow_v2.py` (24), `test_web_workflow.py` (11), `test_escalation.py` (9), `test_honest_wording.py` (3).
User stories US11–US15 added to `docs/requirements.md`.

Not done in Phase 1 (moved to Phase 1b): the API read endpoints (`GET /api/hazards`, `/api/hazards/{id}`,
`/api/dashboard`, `/api/monitoring`) currently need no sign-in; authorisation per object is not enforced on pages.

### P1.6 CI failure on PR #3 and fix (2026-11-18)

Run 44235508642: the four test jobs passed; the **docker** job failed. Container log: `PermissionError: [Errno 13]
Permission denied: '/app/outbox'` – seeding wrote alert e-mails to the default outbox, which the image's non-root
user cannot create, so the app crashed at start-up. Fix (`54fa73b`): outbox write errors are logged, never raised
(test `test_unwritable_outbox_never_blocks_a_report` failed first), and the image sets
`SHMS_MAIL_OUTBOX=/data/outbox`. Local Docker smoke run passed, then CI runs 44236463896 / 44236454587: all 5 jobs
green. PR #3 merged as `a2a90d4`.

Earlier (Phase 0), two runs showed "failure" because one macOS job was **cancelled** by GitHub ("The job was not
acquired by Runner of type hosted even after multiple attempts" – runner capacity); no test failed and the same
commit passed all jobs in its other run. Nothing was changed for that.

---

# Phase 1b (part 2) – Security (branch `feature/security`, 2026-11-18)

All items: **implemented+tested** (`pytest` 208 passed; `ruff` clean; local Docker smoke with the new CI steps passed).

| Requirement | Implementation | Tests |
|---|---|---|
| Hashed passwords (standard KDF) | `auth.hash_password`: scrypt n=2^14, r=8, p=1, 16-byte salt; constant-time compare | `test_password_hash_is_salted_scrypt_and_verifies`, `test_demo_users_have_hashed_passwords_not_plaintext` |
| Signed sessions, logout | cookie `shms_session` = uid.issued.HMAC-SHA256, 12 h; HttpOnly, SameSite=Lax, Secure on https; POST /logout | `test_login_with_correct_password_sets_a_signed_session`, `test_tampered_session_cookie_signs_the_user_out`, `test_old_unsigned_user_cookie_is_ignored`, `test_expired_session_is_rejected`, `test_logout_clears_the_session` |
| Generic login errors | same text and status (401) for unknown user and wrong password | `test_wrong_password_and_unknown_user_get_the_same_generic_message` |
| CSRF on all HTML forms | signed double-submit token (cookie + hidden field) checked by a router dependency on every POST, login included | `test_form_post_without_or_with_wrong_csrf_token_is_refused`, `test_login_form_also_needs_the_csrf_token`, `test_every_post_form_contains_the_csrf_field` |
| API: no anonymous header | `Authorization: Bearer <token>`; tokens hashed (SHA-256) in `api_tokens`; CLI `python -m shms.tokens create`; browser session not accepted on the API (so no CSRF exposure); `X-User-Id` only with `SHMS_DEMO_HEADER_AUTH=1` | `test_api_requires_a_token_in_normal_mode`, `test_api_accepts_a_valid_token_and_stores_only_its_hash`, `test_api_does_not_accept_the_browser_session_for_changes`, `test_demo_header_works_only_when_enabled`, `test_read_endpoints_and_metrics_need_sign_in` |
| Server-side authorisation per route/object | all pages need sign-in; `policy.can_view` on every hazard lookup (pages + API), 404 without revealing existence; actions via the state machine | `test_authz.py` (10 incl. parametrised) |
| Photos not public | `/uploads` static mount removed; `GET /photos/{name}`: sign-in, policy, name pattern `^[A-Za-z0-9_-]{1,80}\.jpg$` | `test_photos_are_not_public`, `test_other_reporter_cannot_open_a_draft_or_its_photo`, `test_photo_names_cannot_escape_the_upload_folder` |
| Uploads | ≤ 20 MB read limit; content must decode as JPEG/PNG/WebP (name/MIME not trusted); ≤ 40 MP; generated safe names; re-encoded JPEG | `test_uploads.py` (6) |
| Errors | central handler: generic HTML/JSON 500, details logged (`shms` logger) | `test_errors.py` (2) |
| Migrations | `0005_auth`: usernames from first names, no passwords for migrated users (set with `python -m shms.tokens set-password`), `api_tokens` table; schema = models test passes | `test_migrations.py` |

**Design decision deviating from the plan** (plan said "reporter sees own hazards only"): confirmed hazards are
visible to every signed-in user, because user story US7 requires operators to check an area's live hazards before
entering; only unconfirmed drafts are private. Recorded in `shms/policy.py`.

**Demo credentials:** usernames = first names, one documented demo password (`shms-demo-2026`, in the README) – not a
secret. The seed computes the hash once for all demo users (identical hashes; acceptable for a shared documented demo
password, not for real accounts).

**Test infrastructure:** the default test client (`tests/conftest.py::BrowserClient`) adds the CSRF field the way the
real form does; CSRF rejection is tested with a plain client. API tests use `X-User-Id` with
`demo_header_auth=True`, set only in the test settings fixture.

Other changes: `evaluation/load_test.py --token`; CI smoke test now checks 401 without a token and creates a token
inside the container; Docker keeps the generated secret in `/data/instance`; seeding synthetic history writes no
outbox e-mails (`test_seeding_the_demo_history_writes_no_mail`).

Status labels: sign-in, CSRF, tokens, authorisation, uploads, errors – implemented+tested. The demo passwords and
synthetic users – simulated. Single sign-on – planned (not implemented).

### P1b.S Security review of `feature/security` and fix (2026-11-18)

Method: security-review skill – one review pass over the whole branch diff, then an independent false-positive check of
each candidate; only findings with confidence ≥ 8/10 kept. Result: **one finding, MEDIUM, confidence 8/10**; nothing
HIGH. Checked and found sound: template auto-escaping (no `|safe`), CSRF coverage of every HTML POST, session/CSRF
signing and constant-time comparison, API token storage, policy checks on every hazard lookup, photo route name
pattern, upload validation, outbox file names, no secrets in API output.

**Finding – re-confirm bypass of the state machine** (`shms/services.py`, `confirm()`): it checked only who calls
(reporter or supervisor), never that the hazard was still a draft. Through `POST /hazards/{id}/confirm` or
`POST /api/hazards/{id}/confirm`, the hazard's own **reporter** could re-confirm an OPEN, PLANNED,
PENDING_VERIFICATION or CLOSED hazard and so: downgrade its risk (e.g. Extreme → Low, new due date), "close" it with
*fixed on the spot* without owner rights, move it out of overdue escalation, and send it back to OPEN without the
reason and checks of `reject()`/`reopen()`. Limits: reporter-only (supervisors already have these powers); every step
left a `confirmed` audit event; the final CLOSED state still required independent verification. Partly pre-existing
(the old table allowed only OPEN → CLOSED via this path); the new transitions of Phase 1 widened it.

**Audit of every other action** (point 3 of the instruction) found the same pattern – reliance on the shared
transition table only – in five more cases, all reachable by a supervisor:

| Action | Wrong state that was accepted | Why |
|---|---|---|
| `close()` | DRAFT | `draft → pending_verification` exists for "fixed on the spot" |
| `reject()` | DRAFT, CLOSED | `→ open` exists for confirm / reopen |
| `reopen()` | DRAFT, PENDING_VERIFICATION | `→ open` exists for confirm / reject (skips reject's "not the closer" rule) |

**Fix** (`services._require_state`): every action checks its own allowed from-states explicitly before anything else
– confirm {draft}, plan {open}, close {open, planned}, verify {pending}, reject {pending}, reopen {closed}; escalation
already selects only {open, planned}. The page route redirects a re-confirm to the hazard page with "This report has
already been confirmed…" before any upload is stored; the API returns 422. `WorkflowError` → 422 in both.

**Tests** (`tests/test_state_guards.py`, 40, all failed or were missing before the fix where a gap existed):
re-confirm of open/planned/pending/closed × reporter/supervisor × with/without "fixed on the spot" (16) leaves status,
category, risk fields, due date, closure and verification fields, escalation level and event count unchanged; API
(2) → 422 unchanged; page (2) → 303 with message, unchanged; every other action from every wrong state (19) →
`WorkflowError`, unchanged; escalation touches only open/planned (1). Suite: 248 passed; ruff clean.

---

# Phase 2 – Stronger evidence (branch `feature/evidence`, 2026-11-18)

### P2.2 Label-rule audit in code (`evaluation/label_rule_audit.py`)

```bash
python -m evaluation.label_rule_audit --root $R          # YOLOv9e full split, operating threshold 0.35
```

Output: `evaluation/results/label_rule_audit_yolo_sh17_yolo9e.json`; local gallery for the owner
`evaluation/data/label_rule_gallery.html` (git-ignored – SH17 images are CC BY-NC-SA). Status: **implemented+tested**
(5 unit tests); the classification is structural (from boxes), not a human judgement of the photos.

Every disagreement between model and derived label, by structural reason (FP = model says violation, label says no;
FN = the reverse):

| Hazard | Reasons (count) |
|---|---|
| `no_hard_hat` | FN: model found no head **33**; FP: no head box in the labels **27**; FP: PPE labelled, model missed it **16**; FN: model saw PPE that is not in the labels **6**; FP: labelled head below the rule's size limit **1** |
| `no_eye_protection` | FN: model found no face **35**; FP: PPE labelled, model missed it **23**; FP: no face box in the labels **16**; FN: model saw PPE that is not in the labels **8**; FP: labelled face below the rule's size limit **2** |
| `no_gloves` | FN: model found no hands **48**; FP: no hands box in the labels **36**; FN: model saw PPE that is not in the labels **6**; FP: PPE labelled, model missed it **4**; FP: labelled hands below the rule's size limit **3** |
| `no_hi_vis_vest` | FP: no person box in the labels **47**; FN: model found no person **31**; FP: PPE labelled, model missed it **24**; FN: model saw PPE that is not in the labels **13**; FP: labelled person below the rule's size limit **3** |

Reading: "no <part> box in the labels" (27 hard hat, 16 eye, 36 gloves, 47 vest false alarms) are photos in which the
model sees a head/face/hand/person that the SH17 annotation does not contain – either an unlabelled body part
(annotation gap: "no person box" ≠ "no person visible") or a model hallucination; which one can only be decided by
looking at the photos (gallery, for the owner). "PPE labelled, model missed it" and "model found no <part>" are model
errors (occlusion, small or unusual PPE). Scenes where PPE is not required (offices, kitchens, homes) are a property
of SH17 that the rule engine cannot see; it labels every bare head as a violation regardless of context.

**Stricter label variant – sensitivity analysis only** (each hazard scored only on photos in which the relevant
body part is labelled at or above the rule's size limit; released labels and results unchanged):

| Hazard | Released specificity | Released MCC | Images (part labelled) | Pos / Neg | Precision | Recall | Specificity [95% CI] | MCC [95% CI] |
|---|---:|---:|---:|---:|---:|---:|---|---|
| `no_hard_hat` | 0.887 | 0.859 | 1296 | 1232 / 64 | 0.987 | 0.968 | 0.750 [0.64–0.85] | 0.622 [0.53–0.71] |
| `no_eye_protection` | 0.934 | 0.891 | 1130 | 996 / 134 | 0.976 | 0.957 | 0.828 [0.77–0.89] | 0.740 [0.68–0.79] |
| `no_gloves` | 0.885 | 0.833 | 1257 | 1246 / 11 | 0.997 | 0.957 | 0.636 [0.33–0.89] | 0.257 [0.11–0.38] |
| `no_hi_vis_vest` | 0.582 | 0.599 | 1496 | 1443 / 53 | 0.983 | 0.970 | 0.547 [0.41–0.68] | 0.443 [0.33–0.55] |

**Finding:** a large share of the released specificity comes from "easy" negatives – photos with no labelled head,
face, hands or person, where neither the labels nor the model can produce a violation. On photos that actually test
recognition of PPE on a visible body part, specificity is lower: hard hat 0.750 (below the release gate's 0.80, CI
0.64–0.85, only 64 such negatives), eye protection 0.828 (above), gloves 0.636 on only **11** negatives (not
estimable with any confidence), vest 0.547. This does not change the released results; it qualifies them and is a
decision point for the owner (see Handover). The external validation (P2.1) has ~4 000 negatives that show heads with
hard hats and therefore tests exactly this.

### P2.3 Load test clarity – one table (existing measurements, no re-run)

Hardware: MacBook Pro, Apple M5 Pro, 24 GB, macOS 26.6.2; YOLO on `mps`. Image: the 1280 × 853 px sample photo
(`data/samples/sh17_pexels-photo-7888728__…jpg`), 162 KB. Server: one uvicorn worker on the same laptop (loopback).
Warm-up: one request (excluded) for API measurements; one prediction (excluded) for model-only measurements.

| Quantity | What is timed | YOLOv8s | YOLOv9e | Requests / errors | Source |
|---|---|---|---|---|---|
| Model-only latency, p50 / p95 | `model.predict` on the decoded sample image, 50 calls | 9 / 9 ms | 37 / 38 ms | 50 / 0 | standalone script (§5.4) |
| Detector latency on the test set, p50 / p95 | read original SH17 photo (up to 8 192 px) + resize + inference + rules, per image | 66 / 128 ms | 95 / 154 ms | 1 620 / 0 | `results/yolo_sh17_yolo*/metrics.json → latency_steady` |
| Upload-to-result latency, 1 user, p50 / p95 | client-side end to end: multipart upload, save, inference, JSON response | 22 / 30 ms | 51 / 63 ms | 40 / 0 | `load_test_*.json` level 1 |
| Upload-to-result latency, 8 users, p50 / p95 | same, 8 concurrent clients (queueing) | 140 / 181 ms | 356 / 371 ms | 40 / 0 | level 8 |
| API throughput, 1 / 4 / 8 users | successful requests ÷ wall time of the level | 43.0 / 55.1 / 54.6 req/s | 18.8 / 21.4 / 22.3 req/s | 40 per level / 0 | `load_test_*.json` |
| CPU only, detector p50 / p95 | `build_detector(device="cpu")` on the sample photos, 30 calls | 35 / 41 ms | 200 / 216 ms | 30 / 0 | §8.4 |

Notes: the upload-to-result latency at 1 user is lower than "detector latency on the test set" because the sample
photo is small (1280 px) while SH17 originals reach 8 192 px. 40 requests per level is a short burst. The YOLOv8s load
test was run at code `b2f307b` (before authentication); the YOLOv9e one at `10ebae1`; both used the demo header,
which now needs `SHMS_DEMO_HEADER_AUTH=1` or `--token` (`evaluation/load_test.py`). Not re-run: nothing in the
measured path (upload → detector) changed except the stricter upload check, whose cost was not measured separately.

### P2.4 Label audit (human task) – status and instructions

Status 2026-11-18: **not done** (`evaluation/data/label_audit_results.csv` absent). Ready for the owner:

1. Open `evaluation/data/label_audit.html` (local file, built 2026-11-15 with seed 7; verified identical to a rebuild
   with current code – §7.1). 100 images × 4 labels.
2. For each label click **Agree** if the YES/NO is right for the photo, **Disagree** otherwise; progress is saved in
   the browser.
3. **Download CSV** → save as `evaluation/data/label_audit_results.csv`; then
   `python -m evaluation.label_audit score` (accuracy, 95 % Wilson CI, Cohen's kappa) – to be run and recorded here.

Optional and separate: `evaluation/data/label_rule_gallery.html` shows examples of each disagreement category (green =
labels, red = model) to judge "no person box ≠ no person visible", occlusion and PPE-not-required scenes. It is not a
substitute for the audit and its impressions should not be reported as numbers.

### P2.1 External validation on untouched data – hard hat check (pre-registered, run once)

| Step | Evidence |
|---|---|
| Dataset chosen | Hard Hat Workers (Make ML), Hugging Face `Voxel51/hard-hat-detection`, **CC0**, 5 000 images (mostly 416 × 416 px), classes helmet / head (= head without hard hat) / person; not peer-reviewed; collection and annotation process undocumented |
| Plan committed **before** any image download or model run | `docs/external_validation_plan.md`, commit `22d9a6e` (2026-11-18 09:28 +04), pushed to GitHub. Only `samples.json` (labels) had been read |
| Script committed before the run | `evaluation/external_hardhat.py` + 3 tests, commit `1cc01a9` |
| Images downloaded | `uvx --from huggingface_hub hf download Voxel51/hard-hat-detection --repo-type dataset --include "data/*"` → 5 000 PNG, 1.2 GB, 0 missing; folder `~/Desktop/Final SEP/datasets/hardhat_workers` (outside git) |
| Run (once) | `python -m evaluation.external_hardhat --root …/hardhat_workers --sh17 …/sh17 --device mps` at code `023c947`; 0 errors; results commit `e151bea` |

Only `no_hard_hat` can be evaluated (no labels for eyes, gloves or vests). Leakage: **1** image is a dHash
near-duplicate (≤ 4 bits) of an SH17 image.

| Analysis | Pos / Neg | TP | FP | FN | TN | Precision [95% CI] | Recall [95% CI] | Specificity [95% CI] | MCC | F1 | Always-yes F1 |
|---|---|---:|---:|---:|---:|---|---|---|---:|---:|---:|
| **Primary** (rule engine on the labels) | 908 / 4 092 | 887 | 2 271 | 21 | 1 821 | **0.281** [0.27–0.30] | 0.977 [0.97–0.99] | **0.445** [0.43–0.46] | 0.337 | 0.436 | 0.307 |
| Sensitivity: any `head` box | 920 / 4 080 | 898 | 2 260 | 22 | 1 820 | 0.284 | 0.976 | 0.446 | 0.339 | 0.440 | 0.311 |
| Without the near-duplicate | 908 / 4 091 | 887 | 2 271 | 21 | 1 820 | 0.281 | 0.977 | 0.445 | 0.337 | 0.436 | 0.307 |

**Verdict (pre-registered thresholds P ≥ 0.80, R ≥ 0.75, Spec ≥ 0.80): FAIL** on precision and specificity. Recall
passes. The threshold sweep (report only) has specificity between 0.41 and 0.46 at every threshold from 0.10 to 0.70,
so no operating threshold would have passed.

Diagnostic (after the verdict; changes nothing): of the 2 271 false alarms, the model detected **no** hard hat in
876, fewer hard hats than labelled in 1 337, and all hard hats but judged a head uncovered by the rule's geometry in
58. On the 4 092 compliant images the labels contain 16 604 hard hats; the model detects 6 428 (≈ 39 %). The failure
is therefore mainly **hard-hat detection** on this data (small, low-resolution heads in 416 px photos), not the rule.
A plausible contributor – not tested – is that hard hats are rare in SH17 (154 helmet boxes vs 2 427 heads in its test
split).

Interpretation: the SH17 hold-out result (precision 0.964, specificity 0.887) does **not** transfer to this
independent dataset. Together with the stricter SH17 analysis (P2.2: specificity 0.750 on images with a labelled head),
the evidence says the released hard-hat check over-reports violations whenever many workers do wear hard hats and the
images are small. As pre-registered, the app's release decision is unchanged; this is a documented limitation and a
decision for the owner (Handover). Status labels: external validation – implemented+tested (run once); verdict – FAIL.

# Phase 3 – Interface and refinery overview (branch `feature/ui`, 2026-11-18)

Skills used: frontend-design (design plan reviewed against generic defaults before building). Status of each item:
**implemented+tested** unless stated.

| Requirement | Implementation | Evidence |
|---|---|---|
| Role-specific home pages | `/` → `services.role_home`: reporter (my reports, closures to check), Area Owner (my open hazards by target date, due within 3 days, waiting for verification), supervisor (verification queue, urgent High/Extreme, escalated), manager (site priorities, overdue, closure performance in 90 days with its denominator, weekly trend). Old dashboard moved to `/dashboard`. | `tests/test_home_and_map.py` (role data + one page test per role) |
| Interactive 2D overview | `/site`: SVG of the synthesized layout, zoom (buttons, wheel), pan (drag; a drag never opens an area), filters time window 30/90/180 days and risk level, overlays open risk / overdue / report volume; unknown filter values fall back to defaults | `test_plan_view_*`, overlay unit tests |
| Overlay honesty | each overlay prints "Calculation: …", the window and the site total with hazard count; shading relative to the highest area; areas with nothing recorded are hatched and labelled "No recorded hazards in this window" (never "safe"); report volume uses a neutral grey scale and says it "is not a measure of danger"; page labelled "Illustrative layout – not an actual site plan" | `test_areas_without_hazards_are_labelled_no_records_never_safe`, `test_report_volume_overlay_is_neutral_and_says_it_is_not_danger`, page text test (no "safe") |
| Risk matrix page | two sections: "From the ADOSH-SF guideline" (only the 5 × 5 consequence × likelihood structure with defined levels and level-dependent response – band wording and deadlines **not yet checked** against the official text: owner action) and "Defined by this project" (matrix, bands, target days, consequence wording, likelihood labelled "a project heuristic, not a validated likelihood") | `test_risk_matrix_page_separates_guidance_from_project_choices` |
| Look and responsiveness | palette from the subject (control-room slate, alumina off-white, bauxite red for actions, signal yellow for focus), DIN-style system font for headings and numbers, no web fonts (no external requests); visible keyboard focus; reduced motion respected | screenshots below |

Screenshots: Playwright 1.55 headless Chromium, signed in through the real login form, desktop 1366 px (full page)
and phone 390 px; script `docs/screenshots/shoot.py`. First pass: phone home pages for manager, supervisor and owner
were 10–47 px wider than the screen (work-list tables) and the plan view's zoom buttons covered an area on phones;
dark plan areas had low text contrast. After fixes: all 14 pages "fit" (page width = viewport), 0 server tracebacks.
Kept: `docs/screenshots/{desktop_manager_home,desktop_site_open_risk,desktop_matrix,phone_supervisor_home,phone_site_open_risk,phone_reporter_home}.png`.

Requirement change: `/` is now the role home page; `tests/test_errors.py` opens `/dashboard` (the route that calls
`services.dashboard`). Suite: 265 passed; ruff clean.

---

# Phase 4 – Experiment: unsafe conditions (branch `feature/conditions`, 2026-11-18)

Status: **experimental** throughout. Time used: ≈ 1.5 h of the 8 h box.

### P4.1 Candidates (verified)

Recorded in `docs/unsafe_conditions_plan.md` §2. Only one labelled candidate was found without an account:
`Jsohal174/warehouse-safety-hazard-dataset` (CC BY 4.0; 913 **synthetic** images: Blender renders made photorealistic
and with hazards injected by Google Gemini; overhead/drone view of a warehouse; whole-image labels). Model:
`qwen2.5vl:7b` (Apache 2.0, local). Real labelled spill / blocked-walkway photo datasets: none found on Hugging Face
with a usable licence; Roboflow Universe not searched (needs the owner's key). `qwen3-vl:8b`: not run.

### P4.2 Pre-registration and its amendments

| Commit | What | Before what |
|---|---|---|
| `aa3de90` (10:20) | plan: labels, dev rule (≤ 3 prompt versions on 60 train images), pass/fail, integration rule | any image download or model run |
| `5383b42` (10:25) | Addendum A: the dataset page's `train/test.jsonl` describe a different version (file names/counts do not match the images) → labels from `metadata.csv`; ambiguity sensitivity analysis from `accept_also` (14 ambiguous for spill, 2 for obstruction in test) | any model run |
| `fd5e4c7` | experiment code + 4 tests | any model run |
| `5f89fbf` | Addendum B: dev results, prompt `c2` frozen | the test run |

Dev split (60 train images, 20 per class): `c1` mean MCC 0.853 (spill 1.000; obstruction 0.706 – fallen boxes and
debris were called "clear walkway"); `c2` (asks for anything lying in the walkway, even if passable) 0.891 (spill
0.926, obstruction 0.857). `c3` not used. Caveat: train and test share base scenes (104 of 106 test source frames), so
dev tuning may transfer more easily to test than to new scenes.

### P4.3 Test result (prompt `c2`, run once, 186 images, 0 errors) – `evaluation/results/conditions_qwen2.5vl_7b_c2_test/`

| Hazard | Pos / Neg | TP | FP | FN | TN | Precision [95% CI] | Recall [95% CI] | Specificity [95% CI] | MCC | F1 | Always-yes F1 | Verdict |
|---|---|---:|---:|---:|---:|---|---|---|---:|---:|---:|---|
| Liquid on the floor | 44 / 142 | 41 | 1 | 3 | 141 | 0.976 [0.92–1.00] | 0.932 [0.85–1.00] | 0.993 [0.98–1.00] | 0.940 | 0.953 | 0.383 | PASS |
| Walkway obstructed | 48 / 138 | 38 | 8 | 10 | 130 | 0.826 [0.70–0.93] | 0.792 [0.67–0.90] | 0.942 [0.90–0.98] | 0.744 | 0.809 | 0.410 | PASS (lower CI bounds below the thresholds) |
| Sensitivity, ambiguous removed – liquid | 44 / 128 | 41 | 1 | 3 | 127 | 0.976 | 0.932 | 0.992 | 0.938 | 0.953 | – | PASS |
| Sensitivity, ambiguous removed – obstruction | 48 / 136 | 38 | 6 | 10 | 130 | 0.864 | 0.792 | 0.956 | 0.770 | 0.826 | – | PASS |

Latency (Apple M5 Pro, Ollama): p50 3.4 s, p95 4.0 s per image.

Limits (stated, not tested away): synthetic images generated by another AI model (Gemini) – a VLM may find them easier
than real photos; warehouse, not refinery; overhead camera, not a hand-held phone; labels from the generation intent with
visible noise (e.g. `spill/forklift_0066.jpg` described as "essentially safe"); shared base scenes between dev and
test; one model, one run; obstruction passes only on point estimates.

### P4.4 Integration (because both passed, as pre-registered) – experimental, off by default

- `SHMS_EXPERIMENTAL_CONDITIONS=1` (default `0`). Two categories in `shms/config/taxonomy.json` with
  `experimental: true`, `ai: false`: "Possible liquid on the floor", "Object possibly obstructing a walkway". They are
  never in `ai_codes()`/`enabled_codes()`, so the release gate cannot include them.
- With the flag on, the frozen prompt runs on the report photo (`conditions_vlm.observe`); results are stored as
  suggestions marked `experimental`, shown in a note "Experimental check (tested only on synthetic warehouse images, not
  on site photos) … Choose it below only if you can see it yourself", never pre-selected, never the AI's top suggestion;
  the model's free text is not shown (it could name a substance); a failing model gives no observation and never
  blocks a report. Reporters can choose the two types manually when the flag is on.
- Tests: `tests/test_experimental_conditions.py` (7) – flag off by default, model never called, categories hidden and
  refused; flag on: fixed wording, not pre-selected, model text hidden, failure non-blocking, PPE suggestion unchanged,
  experimental type confirmable. Requirement change: `test_taxonomy_contains_only_ai_detected_hazards_plus_flagged_experimental_ones`.
- Suite: 284 passed; ruff clean.

---

# Phase 5 – Freeze (branch `feature/freeze`, 2026-11-18)

| Check | Result |
|---|---|
| Full suite (local) | 284 passed; ruff check and format clean |
| CI | every phase PR merged only after GitHub Actions passed on all 5 jobs (Ubuntu/macOS × Python 3.11/3.12 + Docker build and smoke test); test step ≈ 1 min 53 s on Ubuntu (PR #7) – README now says "about 2 minutes" instead of "under a minute" |
| Fresh clone following the README | `git clone https://github.com/Hind2102/shms.git` at `d3a72c2` into a new folder; Python 3.12 venv; `pip install -e ".[dev,yolo]" matplotlib`; `python scripts/download_models.py --all` (real download: both "checksum OK"); `cp .env.example .env`; `pytest` → **284 passed** (YOLO tests ran); `ruff` clean; `uvicorn … --port 8765`; sign-in as `sara` / documented demo password through the form (CSRF) → home "Waiting for your verification"; `/site`, `/dashboard`, `/matrix`, `/hazards`, `/queue` → 200; 0 tracebacks |
| Docker | built and smoke-tested by CI on every PR (incl. token creation in the container and 401 without token); local run verified in Phase 1b |
| Git hygiene | no `.env`, Kaggle token, `*.db`, uploads, outbox, `instance/`, backups, weights, datasets or generated galleries tracked now or in history; regex secret scan over all history: 0 hits |
| README | brought in line with all phases (opening claim now states the external failure, repository live, 284 tests and real CI time, VLM v2 and simulated acceptance results, experimental feature, warehouse dataset licence, status table) |

## Final status table

| Status | Items |
|---|---|
| **Implemented + tested** | photo report with AI suggestion and manual fallback; 5 × 5 risk scoring; workflow with plan/close/verify/reject/reopen, four-eyes verification and from/to audit trail; overdue escalation; notifications; scrypt sign-in, signed sessions, CSRF, hashed API tokens, per-object authorisation, safe uploads, generic errors; Alembic migrations (old DB upgraded with identical rows); role home pages, plan view, dashboard, risk-matrix page; AI monitoring, `/metrics`; release gate; offline evaluation on SH17; pre-registered external validation; label-rule audit; Docker; CI |
| **Simulated** | synthesized people, areas, layout and history; simulated reporter acceptance; e-mail outbox (never sent); demo accounts with a documented password |
| **Experimental** | unsafe-condition check (liquid on floor, obstructed walkway) – synthetic test data, flag off by default; VLM as PPE detector |
| **Planned / not done** | label audit clicks (owner); ADOSH-SF band confirmation (owner); single sign-on; real refinery photos with ≥ 3 annotators; external validation of eye protection and gloves; licence for the project code |

## Handover (updated 2026-11-18)

**Verified:** every phase above, with commands, numbers and commits. **Uncertain:** detection mAP vs the SH17 paper
(not reproduced, cause unknown); field performance – the hard-hat check failed external validation (precision 0.281,
specificity 0.445); label quality until the audit is done; selection bias of decisions made after seeing test results
(YOLOv9e, specificity threshold, VLM prompt v2); synthetic-only evidence for the experimental check.

**Fixed (each with a failing test first):** re-confirm and wrong-state bypasses (security review, medium); foreign-key
switch leaking after database creation; Docker start-up crash (outbox permission); `/hazards?status=` 500; plan-form
`NameError`; owner queue dropping planned hazards; phone layout overflow and plan-view contrast.

**Backups and evidence:** `shms.db` untouched; `backups/shms_2026-11-17.db` (identical SHA-256); `backups/env_before_2026-11-17.bak`;
`backups/evidence_results_c19e9be/` (+ `.sha256`), `backups/evidence_data_c19e9be/`; `shms_demo.old.db`; tags `v1.0.0`
(fallback) and `v1.1.0` (this freeze).

**Remaining before 1 December (owner):** (1) label audit, 1–1.5 h, then `python -m evaluation.label_audit score`
(agent, 10 min); (2) confirm risk bands against the ADOSH-SF guideline, ~30 min; (3) decide the hard-hat release after
the external failure (recommended: keep as an "experimental suggestion" with the failure stated, or remove from the
release); (4) choose a code licence; (5) new Kaggle token (old one was typed into a chat); (6) say whether a supervisor
reviewed the synthesized layout. **Readiness:** software, tests, CI, Docker and documentation are submission-ready at
`v1.1.0`; the report must state the external-validation failure and the pending label audit.

---

# Owner decisions applied (branch `feature/hardhat-label-licence`, 2026-11-18)

1. **Hard hat stays enabled, labelled as unverified.** `shms/config/ai_release.json` gains a `notes` field (not read
   by the gate): `no_hard_hat.label` = "validated on SH17 only – failed external validation (Hard Hat Workers):
   unverified suggestion", with the evidence pointer. `taxonomy.release_note()` reads it; the confirm page (suggestion
   and drop-down), the area page and the hazard page show it; README results table and external-validation section
   say the same. Gate code, `release_gate.json` and all results unchanged: `python -m evaluation.release_gate --dry-run`
   gives the identical decision (3 approved, vest rejected); `test_shipped_release_matches_shipped_results` still
   passes. Caveat recorded in the file: re-running the gate rewrites `ai_release.json` and drops the note.
   Tests: `tests/test_release_notes.py` (4, failed first).
2. **Licence AGPL-3.0.** `LICENSE` = official text from https://www.gnu.org/licenses/agpl-3.0.txt (34 523 bytes,
   SHA-256 prefix `0d96a4ff68ad6d4b`); `pyproject.toml` `license = { text = "AGPL-3.0-only" }` + classifier; README
   table, licences table and status table updated.

Suite: 288 passed; ruff clean.

### Screenshot of the confirm page (2026-11-18)

`docs/screenshots/desktop_confirm.png` (1366 px, full page): signed in as `ahmed`, report in Digestion, photo
`data/samples/sh17_pexels-photo-7888728__…jpg` uploaded through the real form; app with `SHMS_DETECTOR=yolo`,
`models/sh17_yolo9e.pt` on `mps`, scratch database. Checked in the page: 5 detection boxes drawn, the hard-hat
suggestion carries "AI check validated on SH17 only – failed external validation (Hard Hat Workers): unverified
suggestion", model `yolo:sh17_yolo9e` named; 0 server tracebacks. Script: `docs/screenshots/shoot_confirm.py`.

# Phase 6 — Review and release work, 18 November 2026

**Review base:** 89e60ec; fallback tag resolves to e0a538cb7198e4426da66a946c77179744c865e8. Review findings, raw-count calculation, setup friction and rankings are recorded in review_phase6.md. Existing desktop_confirm.png predates Phase 6.

| Status | Check and command | Result |
|---|---|---|
| Implemented + tested | `.venv/bin/pytest`, `.venv/bin/ruff check .`, `.venv/bin/ruff format --check .` | Full baseline green, 88 Python files formatted |
| Implemented + tested | `uv pip install --python .venv/bin/python pytest-cov`, `pytest --cov=shms --cov=evaluation` | 288 passed, 6 warnings; 71% statement coverage; 110.62 s |
| Implemented + tested | Clean GitHub clone, CPython 3.12 venv, README pip install, download_models.py --all, copy .env.example | Dependencies and both checksums OK; inline comment breaks configured YOLO path |
| Planned | Human label-audit score | CSV absent; no score produced |

Resolved review findings in the environment example, README, architecture and course mapping. Moved the weights comment above its setting so the documented copy command selects the downloaded YOLOv9e file. The original results, split, gate, thresholds and model configurations were preserved.

Task 4: Extracted the original pytest-cov stdout table for the baseline measurement to `evaluation/results/phase6_baseline_coverage/statements.md` using its original line numbers; rendering against the changing working tree would give incorrect totals. No model or threshold was re-evaluated. No additional error-cause figure was generated: image-level error counts alone do not establish causes. Fresh-clone inference with the corrected example and included sample 7888728 used YOLOv9e and returned five boxes without error. Changed the grader reproduction command to use the gate's existing dry-run mode. Excluded private runtime directories from Docker build context and corrected an obsolete CLI reference in a migration docstring.

Phase 6 database checks ran on disposable SQLite copies only. Both upgrades to 0006_report_pin preserved prior rows and relationships, passed integrity_check and foreign_key_check, and left all 240 existing hazards per copy with null coordinates. Original demo SHA-256 5ca64d290d71af4312cd62005f9da1169a03834a25f12b9d47276d32d8d7b733, counts (users, areas, hazards, events, notifications) = (9, 9, 240, 1012, 196). Original 17 November backup SHA-256 a3d05d763c08cb653219d739aeb156e4dc13024b379dde01517c46da9dc842d1, counts (9, 9, 240, 1010, 200). Original hashes verified after migration.
