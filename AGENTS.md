# Instructions for coding agents (Claude Code, Cursor, Codex …)

This repository is a graded course project. Agents may help, but a human reviews and owns every change.

## Before you change anything
- Read `README.md` and `docs/architecture.md`.
- Run `pytest` and `ruff check .` first; both must be green before and after your change.

## Rules
- **Do not change behaviour silently.** The following files define the evaluated system; change them only when
  asked, and explain the change: `shms/services.py`, `shms/risk.py`, `shms/detection/rules.py`,
  `shms/config/*.json`, `evaluation/metrics.py`.
- **Never edit or delete tests to make them pass.** Fix the code, or explain why the test is wrong.
- **Never edit files in `evaluation/results/` or `evaluation/data/` by hand.** They are produced by the
  evaluation scripts and must match a re-run.
- **No secrets in git**: no `.env`, `kaggle.json`, API keys or tokens. Use `.env.example` for new settings.
- Work on a branch (`feature/<name>`), commit in small steps with clear messages, and open a pull request.
  `main` must always pass CI.
- New behaviour needs a test in `tests/`. Keep functions small and typed; follow `ruff format`.

## Useful commands
```bash
source .venv/bin/activate
pytest                      # all tests (no GPU or model needed)
ruff check . && ruff format --check .
uvicorn shms.asgi:app --reload
```
