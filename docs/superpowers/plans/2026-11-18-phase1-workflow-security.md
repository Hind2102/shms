# Phase 1 + 1b: Safety Workflow, Security and Migrations – Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.
> Execution chosen by the owner's standing instruction ("work autonomously"): **native**, one branch-level review.

**Goal:** Turn the 3-state demo workflow into a verifiable safety workflow (plan → close → verify / reject / reopen,
deadlines, escalation) and make the app safe to expose (real sign-in, CSRF, per-object authorisation, safe uploads,
Alembic migrations that upgrade the old database).

**Architecture:** Keep the existing layering (`services.py` = state machine + rules, `web/` = thin routes). Add
three focused modules: `shms/auth.py` (passwords, sessions, CSRF, API tokens), `shms/policy.py` (who may see/do
what), `shms/notify.py` (in-app + file-outbox mail). Migrations live in `migrations/` (Alembic).

**Tech Stack:** FastAPI, SQLAlchemy 2, SQLite, Jinja2; stdlib `hashlib.scrypt`, `hmac`, `secrets`; new dependency
`alembic` only.

**Spec:** owner's prompt of 2026-11-18, sections PHASE 1 and PHASE 1b (quoted in `docs/verification.md` → Phase 1).

## Global Constraints

- Never delete a database; schema changes only through Alembic migrations.
- Original AI suggestion fields (`ai_model`, `ai_suggestions`, `ai_top_code`, `ai_latency_ms`, `ai_error`) are
  never modified after the draft is created.
- Every status change = one rule in `ALLOWED_TRANSITIONS` + a permission check + one `HazardEvent` with
  `from_status`, `to_status`, actor, time and note.
- A check that is not AI-checked (not released or not required) must never be shown as "safe"/"no violation".
- Demo passwords are documented in the README and are not secrets; no real secret is committed.
- `X-User-Id` header auth only when `SHMS_DEMO_HEADER_AUTH=1`.
- No new infrastructure; one new dependency (`alembic`).
- Each branch: `pytest` + `ruff check .` + `ruff format --check .` green before PR.

## State machine (decided here)

| From | To | Action | Who |
|---|---|---|---|
| DRAFT | OPEN | confirm (routes to Area Owner) | reporter (or supervisor) |
| DRAFT | PENDING_VERIFICATION | confirm with "fixed on the spot" | reporter |
| OPEN | PLANNED | plan action (text + owner + deadline ≤ due date allowed to exceed only with note) | owner/assignee/supervisor |
| OPEN, PLANNED | PENDING_VERIFICATION | close with action (+ photo) | owner/assignee/supervisor |
| PENDING_VERIFICATION | CLOSED | verify with note | supervisor, or the reporter – never the person who closed it |
| PENDING_VERIFICATION | OPEN | reject with mandatory reason | supervisor or reporter |
| CLOSED | OPEN | reopen with mandatory reason | supervisor or reporter |

"Active" = OPEN, PLANNED, PENDING_VERIFICATION. Dashboard "open" counts use active; "closed" counts use CLOSED.
Escalation: level 1 when an active hazard (OPEN/PLANNED) passes `due_at` → notify supervisors; level 2 at
`due_at + 7 days` → notify managers. Project rule, documented as such.

## Review Focus

1. Old `shms.db` (pre-`b2f307b` schema) upgraded with `alembic upgrade head` keeps every row and relationship.
2. A reporter cannot open another reporter's hazard, photo or `/hazards/{id}` by guessing ids (403/404).
3. A form POST without a valid CSRF token is refused even with a valid session.
4. A file renamed `.jpg` that is not an image, a > 20 MB upload and a decompression bomb are refused.
5. When the AI returns nothing or fails, the page says the AI found nothing *for the checked items* and never "safe".

---

### Task 1: Alembic baseline and old-schema upgrade (branch `feature/migrations`)

**Files:** Create `alembic.ini`, `migrations/env.py`, `migrations/versions/0001_baseline.py`,
`migrations/versions/0002_course_upgrade.py`; modify `shms/db.py` (replace refusal), `pyproject.toml` (alembic,
package data); test `tests/test_migrations.py`.

**Interfaces:** Produces `shms.db.schema_status(engine) -> str` (`"empty" | "current" | "outdated"`),
`shms.db.migrate_to_head(url: str) -> None`.

- [ ] Test `test_upgrade_old_schema_preserves_rows`: copy a fixture DB built with the `de90451` schema (generated in
  the test from SQL DDL captured from `backups/shms_2026-11-17.db`), run `migrate_to_head`, assert per-table row
  counts equal and `hazards.area_id/reporter_id`, `hazard_events.hazard_id` joins unchanged, `idem_key` column present.
- [ ] Test `test_outdated_db_message_says_alembic`: `SchemaMismatch` message contains `alembic upgrade head`.
- [ ] Test `test_fresh_db_is_stamped_head`: empty URL → `create_all` + stamp; `alembic current` = head.
- [ ] 0001 creates the original tables only if absent; 0002 adds `idem_key`, unique constraint, check constraints
  and indexes in `batch_alter_table` (SQLite), only if absent – so unstamped old and current DBs both upgrade.
- [ ] Verify on a COPY of `backups/shms_2026-11-17.db`: counts/joins before = after; record in verification.md.
- [ ] Commit, PR, CI, merge.

### Task 2: Workflow states, events with from/to, verify/reject/reopen (branch `feature/workflow`)

**Files:** Modify `shms/models.py` (Status values, `HazardEvent.from_status/to_status`, `Hazard.action_owner_id`,
`action_due_at`, `verified_at`, `verified_by_id`, `escalation_level`), `shms/services.py`, templates
`hazard.html`; migration `0003_workflow.py`; tests `tests/test_workflow.py` (+ new tests).

**Interfaces:** Produces `services.plan_action(db, h, actor, text, owner_id: int, due: datetime)`,
`services.close(...) -> PENDING_VERIFICATION`, `services.verify(db, h, actor, note: str)`,
`services.reject(db, h, actor, reason: str)`, `services.reopen(db, h, actor, reason: str)`,
`services.ACTIVE: frozenset[Status]`.

- [ ] Tests: one per row of the state-machine table (allowed), one per illegal move, one per forbidden actor;
  `test_closer_cannot_verify_own_closure`; `test_reopen_requires_reason`; `test_events_record_from_and_to`;
  `test_ai_fields_unchanged_after_confirm_and_close`.
- [ ] Existing tests that assert "close → CLOSED" or "fixed on the spot closes immediately" are updated to
  PENDING_VERIFICATION, with the requirement change named in the commit message.
- [ ] Dashboard/area/register queries use `ACTIVE`; closure performance uses verified CLOSED.

### Task 3: Deadlines, escalation, notifications and test outbox (same branch)

**Files:** Create `shms/notify.py`, `shms/escalate.py` (CLI `python -m shms.escalate`); modify `services.py`,
`settings.py` (`mail_outbox` = `outbox/`, git-ignored), `models.User.email`; migration `0004_escalation.py`;
tests `tests/test_escalation.py`.

**Interfaces:** `notify.send(db, users: list[User], hazard: Hazard, subject: str, body: str) -> None` (writes a
`Notification` per user and one `.eml` per user to the outbox); `escalate.run(db, now: datetime) -> list[tuple[int, int]]`
(hazard id, new level).

- [ ] Tests: overdue OPEN → level 1 + supervisors notified + outbox file; 7 days later → level 2 + managers;
  running twice does not notify twice; PENDING_VERIFICATION/CLOSED never escalate; page load triggers at most one
  run per minute.

### Task 4: Manual reporting and honest "not checked" wording (same branch)

- [ ] Tests: AI error → all area check codes selectable; AI found nothing → page says "The AI found no missing
  <checked items>" and lists items *not AI-checked*, and the words "safe" / "no violation" / "No missing PPE
  detected" do not appear.

### Task 5: Sign-in, sessions, CSRF, API tokens (branch `feature/security`)

**Files:** Create `shms/auth.py`, `shms/tokens.py` (CLI); modify `models.User.password_hash`, new `ApiToken` model,
`web/deps.py`, `web/pages.py` login/logout, every `<form method="post">` template, `settings.py`
(`secret_key` from `SHMS_SECRET_KEY` or a git-ignored `instance/secret_key` file, `demo_header_auth`), seed demo
passwords; migration `0005_auth.py`; tests `tests/test_auth.py`.

**Interfaces:** `auth.hash_password(pw) -> str` (scrypt n=2**14, r=8, p=1, 16-byte salt),
`auth.check_password(pw, stored) -> bool` (constant-time), `auth.sign_session(uid) -> str`,
`auth.read_session(cookie) -> int | None` (HMAC-SHA256, 12 h expiry), `auth.csrf_token(session) -> str`,
`tokens.create(db, user, label) -> str` (stores SHA-256 only).

- [ ] Tests: wrong password and unknown user give the same message; tampered cookie → signed out; POST without /
  with wrong CSRF → 403; logout clears session; API without token → 401; API with token → 200; `X-User-Id` ignored
  unless `SHMS_DEMO_HEADER_AUTH=1`; token stored hashed.

### Task 6: Per-object authorisation, safe uploads, error handling (same branch)

**Files:** Create `shms/policy.py`; modify `web/pages.py`, `web/api.py`, `web/deps.py` (`save_photo`),
`main.py` (500 handler; replace `/uploads` static mount with an authorised `GET /photos/{name}`); tests
`tests/test_authz.py`, `tests/test_uploads.py`.

**Interfaces:** `policy.can_view(user, h) -> bool`, `policy.can_act(user, h) -> bool`,
`policy.visible_hazards(db, user) -> Select`.

- [ ] Tests (per role): reporter sees own hazards only; area owner own areas; supervisor/manager all; manager
  cannot plan/close/verify; photo route enforces `can_view`; non-image `.jpg` → 422; > 20 MB → 413 without reading
  everything into memory; > 40 MP → 422; filename `../../x.jpg` stored as safe name; unhandled exception → generic
  500 page, traceback only in the log.
