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
