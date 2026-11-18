# External validation plan – hard hat check on an independent dataset

Status: **pre-registered**. Committed before any image of this dataset was downloaded or any model was run on it.
Only the annotation file (`samples.json`) was read, to state the counts below. Nothing in the model, threshold,
rule engine or release gate may be changed after this commit because of the external results.

## 1. Question

Does the released `no_hard_hat` check (YOLOv9e, SH17 weights, confidence 0.35, `shms/detection/rules.py`) keep its
performance on photos that come from a different source than SH17 and that the model never saw?

## 2. Dataset

| Item | Value |
|---|---|
| Name | Hard Hat Workers (Make ML), as published on Hugging Face: `Voxel51/hard-hat-detection` (mirror of Kaggle `andrewmvd/hard-hat-detection`) |
| URL | https://huggingface.co/datasets/Voxel51/hard-hat-detection |
| Licence | CC0 1.0 (public domain dedication), as stated on the dataset card |
| Access | public download, no account |
| Annotation file | `samples.json`, SHA-256 prefix `da9777e7dfede390`, downloaded 2026-11-18 09:27 (+04) |
| Size | 5 000 images, mostly 416 × 416 px (PNG); boxes: helmet 18 966, head 5 785, person 751 |
| Classes | `helmet` (hard hat on a head), `head` (head **without** a hard hat), `person` (sparse: 158 images) |
| Provenance limits | not peer-reviewed; who collected the photos, from where, and how they were annotated is not documented (Make ML did not publish a datasheet); single annotator or agreement unknown |
| Independence from SH17 | different publisher, different annotation scheme, different image size. Possible overlap of source photos (both may contain web images) is **checked** (section 5) |

## 3. Label mapping (only hard hat can be evaluated)

- The dataset labels heads and hard hats only; it has no labels for eyes/face protection, gloves or vests, and people
  are labelled in only 3 % of images. **Only `no_hard_hat` is evaluated.** The other released checks (eye protection,
  gloves) have no external validation; this is stated as a limitation.
- Ground truth (primary): the dataset's boxes are mapped `head → head`, `helmet → helmet` and passed through the
  **same rule engine** used for SH17 (`hazards_from_boxes`, default `RuleConfig`). Image positive = rule finds
  `no_hard_hat`.
- Ground truth (pre-registered sensitivity analysis): image positive = at least one `head` box, no size threshold.
- From the annotation file: 920 / 5 000 images (18.4 %) contain at least one `head` box; 4 080 contain none. This is
  far below SH17's 76 % prevalence, so specificity is measured on many more negatives (4 080 vs 388).

## 4. Model and procedure (fixed)

- Model: `models/sh17_yolo9e.pt` (SHA-256 `5ac6ac23…4f33f39d`), the released default; device `mps`.
- Operating threshold: 0.35 (unchanged). Boxes kept at ≥ 0.10 for the sweep, exactly as in `evaluation/evaluate.py`.
- Predicted label: `no_hard_hat` from `hazards_from_boxes` on the model's boxes at 0.35.
- Images: **all 5 000**, original files, no resizing by us (YOLO resizes internally to 640).
- Run **once**: `python -m evaluation.external_hardhat --root <dataset folder>` writes
  `evaluation/results/external_hardhat_yolo_sh17_yolo9e/` (predictions.jsonl, metrics.json). No re-runs except to
  resume an interrupted run (cached predictions).

## 5. Leakage check (before scoring)

dHash (64-bit) of every image compared with every SH17 image (train + test lists), Hamming distance ≤ 4 bits – the
same check as `prepare_sh17.py`. Report the number of near-duplicates. Primary analysis: all images. Pre-registered
secondary analysis: excluding near-duplicates.

## 6. Metrics

Per the SH17 evaluation: positives / negatives, prevalence, confusion matrix (TP/FP/FN/TN), precision, recall,
specificity, MCC, F1, each with 95 % percentile bootstrap CIs (1 000 resamples, seed 0), and the always-yes F1.
Also the threshold sweep (reported, **not** used to change anything).

## 7. What counts as pass / fail (decided now)

- **Pass** if, on the primary analysis, the point estimates meet the release-gate thresholds already used for SH17:
  precision ≥ 0.80, recall ≥ 0.75, specificity ≥ 0.80. **Fail** otherwise. CIs are reported next to the verdict.
- The verdict is reported whatever it is. A fail does **not** silently change the app: the SH17-based release
  decision stays as committed, the external result is documented as a limitation, and any change to the release is a
  separate, explicit decision by the project owner.
- Expected weaknesses stated in advance: the images are small (416 px), so heads are small; SH17's rule thresholds
  (minimum head area 0.04 % of the image) were set on larger photos; the dataset's annotation quality is unknown.

## 8. What will be reported

`docs/verification.md` → Phase 2: the commands, all numbers above, the leakage count, the verdict and its limits,
with the commit of this plan as the reference point.
