# Phase 6 independent submission review

Review base `89e60ec`, after fallback `v1.1.1` (`e0a538c`). Historical verification entries and preregistrations are dated records. Preserve them when later results supersede earlier claims.

## Evidence and discrepancies (line numbers at review base)

- README:19,57 attributes the label audit to the author and lists committed audit results. Only manifests and split statistics are tracked in evaluation/data. Human audit CSV absent. README:382 correctly says pending.
- README:230,383 gives 284 tests. The baseline suite collected 288.
- README:381 cites a functional dashboard-update test for a five-second bound. Immediate visibility on the following request is tested; elapsed time is not asserted.
- README:409 generalises a limited dataset search to a claim about all real datasets. The unsafe-condition study used synthetic warehouse images. Its preregistration describes candidate searches and limitations.
- README:420 says SH17 images are not redistributed. Three named sample images are tracked in data/samples; the full corpus is external.
- docs/architecture.md:59 omits planned and pending verification. Lines 80–83 still describe four available PPE checks. The vest gate rejects the fourth. Two synthetic-data condition checks require an explicit feature flag.
- docs/course_mapping.md:5 says dependencies are pinned. pyproject.toml uses minimum versions. Line 10 describes an older release as the submission.
- shms/templates/report.html:6 advertises a vest check which the release gate disables.
- .env.example:7 (weights setting) appends prose to the weight filename. shms/settings.py:25 preserves the comment. On a fresh clone, the configured filename after copying the example did not match either downloaded file. This can silently turn the demonstration into detector-error/manual fallback.

## Evaluation

Independent join of the 1,620 SH17 test manifest entries to YOLOv9e prediction records by image for `no_hard_hat`: TP 1193, FP 44, FN 39, TN 344. Precision 1193/1237 = 0.964, recall 1193/1232 = 0.968, specificity 344/388 = 0.887. Always-positive F1 = 2464/2852 = 0.864. These agree with summary_full.md. The bootstrap resamples paired image labels/predictions with a fixed seed. Its percentile intervals describe image-level sampling variation and do not address shared scenes, rule validity, dataset shift or post hoc selection. The F1 implementation returns undefined for TP=0, FP>0, FN>0 although count-based F1 is zero. No change to released numbers is warranted by that edge case.

The SH17 numbers measure agreement with geometric rules applied to annotated objects. The specificity gate was introduced after viewing results. The external hard-hat test (887 TP, 2271 FP, 21 FN, 1821 TN) gives 0.281 precision and 0.445 specificity. The always-positive baseline and the much lower specificity under the stricter body-part analysis belong beside the positive results. External generalisation for the other released checks is unknown. The warehouse condition labels come from generation metadata; shared scenes weaken independence. The two experiments answer the lecturer's precision/recall question within their stated domains. A single expert reviewing derived labels cannot establish agreement among three independent annotators. No human result is available. The 97.2% acceptance figure is a simulation; the load run measures requests to the service.

## Implementation and setup

A modular monolith with separate policy, detection and scoring modules suits this workflow. The highest-risk regression from adding a second map is disagreement among drawn geometry, route decisions and persisted coordinates. Share one coordinate definition. Keep full operational risk separate from optional display filters and apply object-level authorisation before exposing individual reports. The existing flow uses a session for pages and API tokens for automated callers. Existing tests cover policy and invalid transitions. The map lacks keyboard panning, accessible point selection and routing tests. Optional provider, evaluation CLI and browser paths deserve direct checks. Unit coverage alone cannot establish accessibility or a successful real-model demonstration.

Fresh GitHub clone succeeded. System python3 is 3.9.6 and python3.12 is absent from PATH. Using the installed uv-managed CPython 3.12 by full path, venv creation, editable installation of `.[dev,yolo]` plus matplotlib, both model downloads and both checksum checks succeeded. The copied .env exposed the filename bug above. No human audit results were present to score.

## Priority (grade benefit, implementation risk, effort)

1. Resolve evidence/setup contradictions: high benefit, low risk, under one hour.
2. Deliver one accessible illustrative process map with truthful overlays and before-entry details: high benefit, moderate risk, cap ten hours including migrations, coordinate validation and routing.
3. Verify real UI at phone and desktop sizes, contrast and keyboard operation: high benefit, low risk, four-hour cap.
4. Preserve the released evaluations; use software coverage and measured setup as new evidence. External failure figures are already available. A new model study would add risk without resolving the human tasks.

Baseline pytest-cov statement coverage across shms and evaluation: 2,154/3,043 statements (71%), 288 passed in 110.62 s. Lowest modules (statements, missed, coverage):
    evaluation/compare.py                               125    125     0%
    evaluation/label_audit.py                            67     67     0%
    evaluation/load_test.py                              55     55     0%
    evaluation/prepare_sh17.py                          104    104     0%
    shms/asgi.py                                          2      2     0%
    evaluation/evaluate.py                              150    125    17%
    evaluation/label_rule_audit.py                       99     63    36%
    evaluation/conditions.py                             81     51    37%
