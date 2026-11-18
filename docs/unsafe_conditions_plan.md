# Experiment plan – unsafe conditions (floor spills, blocked walkways) with a local vision-language model

Status: **pre-registered.** Committed before any image of the dataset was downloaded and before any model was run on
it. Only the label files (`train.jsonl`, `test.jsonl`) were read, to write the counts below. Status of the whole
experiment: **experimental** – it is never part of the release gate unless it later passes on real labelled data.

## 1. Question

Can a local vision-language model (no paid API, no training) tell, from one photo, whether (a) liquid is spilled on
the floor and (b) an object obstructs a walkway/aisle – well enough to be offered as an *experimental suggestion* that
a person must confirm?

## 2. Candidates checked

| Candidate | Licence | What it is | Positives / negatives (test) | Domain relevance | Verdict |
|---|---|---|---|---|---|
| `Jsohal174/warehouse-safety-hazard-dataset` (Hugging Face, J. S. Sohal 2025) | CC BY 4.0 | **Synthetic**: Blender renders of a warehouse from an overhead/drone view, made photorealistic and with hazards injected by Google Gemini; whole-image labels spill / obstacle / forklift_violation / improper_stacking / safe; metadata incl. subtype, severity, quality flag | 186 test images: spill 43, obstacle 41, safe 52, forklift 28, stacking 22 | warehouse, not refinery; overhead camera, not a hand-held phone; labels come from the generation intent, not independent annotation | **used** (only labelled candidate found) |
| Other Hugging Face "spill" datasets (robot table cleanup, satellite oil spills, synthetic grey-scale oil shapes) | various | not floor spills in a plant from a person's viewpoint | – | none | not usable |
| Real labelled floor-spill / blocked-walkway photo datasets | – | none found on Hugging Face with a usable licence and labels; Roboflow Universe not searched (needs the owner's key) | – | – | gap; stated as a limitation |
| Model: `qwen2.5vl:7b` via Ollama (already installed) | Apache 2.0 | general VLM, 8.3 B parameters, Q4_K_M; training data not documented in detail | – | zero-shot; may have seen similar synthetic images – unknown | **used** |
| Model: `qwen3-vl:8b` | – | optional second model | – | – | only if time remains (not part of this plan's verdict) |

Hardware: MacBook Pro, Apple M5 Pro, 24 GB (Ollama on the Apple GPU).

## 3. Labels (decided now)

Multi-label ground truth per image, from the dataset's own metadata:

- `spill` = category is `spill`, **or** the subtype contains "spill + obstacle".
- `obstruction` = category is `obstacle`, **or** the subtype contains "spill + obstacle" or "with obstacle".
- All other images (safe, forklift_violation, improper_stacking) are negatives for both. Images flagged
  `quality: questionable` (3 in test) are kept in the primary analysis and dropped in a sensitivity analysis.

## 4. Prompt and model (tuning only on a dev split)

- Output schema (enforced by Ollama): `floor_liquid_visible`, `walkway_visible`, `walkway_obstructed`, `explanation`.
  Predicted `spill` = `floor_liquid_visible`; predicted `obstruction` = `walkway_visible AND walkway_obstructed` (no
  walkway in view → never "blocked walkway"). The model is never asked what the liquid is.
- **Dev split:** 60 images from the *train* split, drawn with seed 42: 20 spill, 20 obstacle, 20 safe. Caveat: train
  and test share base scenes (104 of 106 test source frames also occur in train), so dev tuning may transfer more
  easily to test than to new scenes.
- At most **three** prompt versions (`c1`, `c2`, `c3`) are tried on dev; the one with the highest mean MCC over the two
  hazards is frozen. Temperature 0, seed 42, images downscaled to 1024 px (as in the PPE evaluation).
- The frozen prompt is then run **once** on all 186 test images.

## 5. Metrics

Per hazard: positives/negatives, TP/FP/FN/TN, precision, recall, specificity, MCC, F1 with 95 % bootstrap CIs (1 000
resamples, seed 0), always-yes F1, latency p50/p95.

## 6. Pass / fail (decided now)

- Per hazard **pass** if precision ≥ 0.80, recall ≥ 0.75 and specificity ≥ 0.80 on the test split (same thresholds as
  the PPE release gate). Reported whatever the outcome.
- Because the data are synthetic, a pass does **not** release anything. If a hazard passes, it may be integrated as an
  **experimental, feature-flagged suggestion, off by default**, always requiring human confirmation, wording "possible
  liquid on the floor" / "object possibly obstructing a walkway", never naming a chemical. If it fails, it is reported
  and not integrated.

## 7. Outputs

`evaluation/results/conditions_qwen2.5vl_7b_<prompt>_dev/`, `…_test/` (predictions.jsonl, metrics.json);
`docs/verification.md` → Phase 4.
