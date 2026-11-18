# Baseline statement coverage

Commit 89e60ec. Captured during the original test run.

```text
Name                                              Stmts   Miss  Cover
---------------------------------------------------------------------
evaluation/__init__.py                                0      0   100%
evaluation/acceptance.py                             50     21    58%
evaluation/compare.py                               125    125     0%
evaluation/conditions.py                             81     51    37%
evaluation/evaluate.py                              150    125    17%
evaluation/external_hardhat.py                      106     58    45%
evaluation/label_audit.py                            67     67     0%
evaluation/label_rule_audit.py                       99     63    36%
evaluation/load_test.py                              55     55     0%
evaluation/metrics.py                                77      9    88%
evaluation/prepare_sh17.py                          104    104     0%
evaluation/release_gate.py                           44     17    61%
evaluation/robustness.py                             56     33    41%
evaluation/sh17.py                                   69      6    91%
shms/__init__.py                                      0      0   100%
shms/asgi.py                                          2      2     0%
shms/auth.py                                         68      6    91%
shms/db.py                                           73      0   100%
shms/detection/__init__.py                           22      7    68%
shms/detection/base.py                               53      1    98%
shms/detection/conditions_vlm.py                     30      0   100%
shms/detection/mock.py                               18      0   100%
shms/detection/ollama_vlm.py                         59      0   100%
shms/detection/rules.py                              67      1    99%
shms/detection/yolo.py                               27      1    96%
shms/escalate.py                                     51      9    82%
shms/main.py                                         66     16    76%
shms/migrations/__init__.py                           0      0   100%
shms/migrations/env.py                               22      5    77%
shms/migrations/versions/0001_baseline.py            23      2    91%
shms/migrations/versions/0002_course_upgrade.py      35      7    80%
shms/migrations/versions/0003_workflow.py            33     10    70%
shms/migrations/versions/0004_escalation.py          17      4    76%
shms/migrations/versions/0005_auth.py                28      5    82%
shms/migrations/versions/__init__.py                  0      0   100%
shms/models.py                                      132      0   100%
shms/notify.py                                       39      0   100%
shms/policy.py                                       10      1    90%
shms/risk.py                                         59      1    98%
shms/seed.py                                         75     10    87%
shms/services.py                                    346      7    98%
shms/settings.py                                     46      1    98%
shms/taxonomy.py                                     48      6    88%
shms/tokens.py                                       45     25    44%
shms/web/__init__.py                                  0      0   100%
shms/web/api.py                                     116      3    97%
shms/web/deps.py                                     56      0   100%
shms/web/pages.py                                   238     22    91%
shms/web/telemetry.py                                56      3    95%
---------------------------------------------------------------------
TOTAL                                              3043    889    71%
```
