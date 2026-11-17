# SHMS – Verification log

Purpose: every number and claim the final report may use, with the command that produced it, the file it lives
in, and what remains uncertain. Earlier reported numbers are treated as claims and re-checked here.

Branch: `feature/verification` (created from `main` at `c19e9be`). Nothing pushed.

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
