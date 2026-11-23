# External floor-liquid evaluation protocol

**Decision before inference.** Test the existing Qwen2.5-VL 7B Ollama model with frozen prompt c2, seed 42 and the existing 1024-pixel encoding. The question includes wet patches. Both publisher labels (water and wet surface) therefore indicate positive evidence. Neither class provides dry controls. An empty or missing label is unknown. No precision, specificity, gate promotion or refinery claim follows from this study.

Use Patil and Bhutad, *Dataset of Stagnant Water and Wet Surface with Annotations*, Mendeley Data v4, DOI [10.17632/y6zyrnxbfm.4](https://data.mendeley.com/datasets/y6zyrnxbfm/4), CC BY 4.0. The newer 330,169,869-byte archive has SHA-256 427e336858a996ee967abdbfc94c5582b96f496ed85d3261632183d47dd39f40. Keep original data outside Git. The authors describe the indoor series as top-view water photos. Restrict to their labelled indoor series for the floor-photo test. Outdoor water may be on unpaved ground. Keep raw originals and augmented copies out of the denominator.

Inventory the archive and validate image/annotation pairing. Use the original annotated indoor photos, remove exact image duplicates, select up to 32 by ascending SHA-256 of the image bytes, and exclude near-duplicates (64-bit difference hash at Hamming distance ≤ 4 from an already selected photo). Retain source filenames and hashes for reproducibility. This is a bounded external challenge, not a random sample of refinery reports. Similarity filtering does not establish independent locations.

Record model identity, every selected prediction or error, the positive detection count and denominator, and a descriptive Wilson interval. Count inference errors as missed detections and report them separately. A failed request before evaluation starts is an infrastructure failure. Never use these images to change the prompt or thresholds. The all-positive baseline has recall 1 by construction. Meaningful false-alarm testing requires labelled dry examples from comparable scenes. No new human annotations are assumed.

## Reproduction and outcome

From the README environment, start local Ollama and pull qwen2.5vl:7b. Download the December archive (the other two are different files). Use a new output path.

```sh
curl -fL https://data.mendeley.com/public-files/datasets/y6zyrnxbfm/files/b1892735-9b83-4519-9088-1c50d982b14a/file_downloaded -o /tmp/shms-water-v4.zip
python -m evaluation.external_floor_liquid /tmp/shms-water-v4.zip /tmp/shms-water-reproduction.json
```

All five annotated indoor images qualified. All were labelled water. The model flagged zero, with zero request errors. Recall was 0/5 (descriptive Wilson 95% interval 0–43.4%). All five missed cases, model digest and source hashes are in [the run output](../evaluation/results/external_floor_liquid_v4/summary.json). Specificity and precision remain unknown. This small external check cannot estimate performance on dry floors or at the refinery. The pre-inference plan was committed in e74aa34.
