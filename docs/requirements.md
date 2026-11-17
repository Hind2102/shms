# Requirements: user stories and data model

The proposal committed to developing SHMS from user stories and a defined data model. This file records both
and links every story to where it is implemented and tested.

## User stories

| ID | As a … | I want to … | So that … | Implemented in | Verified by |
|---|---|---|---|---|---|
| US1 | field operator or contractor | report a hazard with a phone photo in a few taps | it is captured before someone is hurt | `/report`, `services.create_draft` | `test_api::test_full_workflow_and_dashboard_update`, `test_html_report_flow` |
| US2 | reporter | see what the AI found on my photo and confirm or correct it | the classification is fast but stays my decision | `/hazards/{id}/confirm`, AI evidence boxes | `test_html_report_flow`, `test_reporter_can_correct_ai` |
| US3 | reporter | choose a clearly defined consequence level while the system estimates likelihood | risk is scored consistently on the 5 × 5 matrix | `risk.py`, `config/risk_matrix.json`, `/matrix` | `test_risk.py` (all 25 cells), `test_likelihood_grows_with_similar_history` |
| US4 | reporter who already fixed the hazard | record the action taken and a closing photo | the fix is documented and can be reused elsewhere | confirm form "fixed on the spot" | `test_fixed_on_spot_closes_immediately_and_records_how` |
| US5 | Area Owner | receive open hazards for my areas, plan an action and close them with what was done | nothing is closed without a record of how | `/queue`, `/hazards/{id}` plan/close | `test_owner_closes_with_documented_action`, `test_only_owner_or_supervisor_can_close` |
| US6 | safety supervisor | be alerted to High and Extreme hazards and trace every action on them | serious hazards get attention at once | notifications, audit trail | `test_high_risk_alerts_supervisor_and_owner` |
| US7 | operator or visitor | check an area's live hazards and required PPE before entering | I know what to expect and wear | `/areas/{code}` | `test_html_pages_render` |
| US8 | manager | see where risk concentrates, how it trends and which hazards repeat | I can target resources and see if things improve | dashboard, heat map, repeat hotspots | `test_dashboard_counts_new_report_immediately`, `test_repeat_hotspots` |
| US9 | safety supervisor | know that the AI is only used where it was proven, and watch it in use | AI suggestions can be trusted | release gate, `/monitoring`, `/metrics` | `test_release_gate.py`, `test_monitoring_and_metrics` |
| US10 | reporter on poor site Wi-Fi | not create duplicates when I tap twice or the page retries | the register stays clean | idempotency keys | `test_idempotent_report_creation`, `test_html_double_submit_returns_same_draft` |

## Data model

```mermaid
erDiagram
    USER ||--o{ AREA : "owns (Area Owner)"
    USER ||--o{ HAZARD : "reports"
    USER ||--o{ HAZARD : "is assigned / closes"
    AREA ||--o{ HAZARD : "contains"
    HAZARD ||--o{ HAZARD_EVENT : "audit trail"
    USER ||--o{ HAZARD_EVENT : "acts"
    USER ||--o{ NOTIFICATION : "receives"
    HAZARD ||--o{ NOTIFICATION : "triggers"

    USER { int id PK; string name; enum role "reporter | area_owner | supervisor | manager" }
    AREA { int id PK; string code UK; string name; int owner_id FK; text required_ppe; text ai_checks; int x; int y; int w; int h }
    HAZARD {
        int id PK; int area_id FK; int reporter_id FK; enum status "draft | open | closed"
        string idem_key "unique per reporter"; datetime created_at; string photo_path
        string ai_model; text ai_suggestions; string ai_top_code; float ai_latency_ms; bool ai_accepted
        string category_code; int consequence "1-5"; int likelihood "1-5"; int risk_score "1-25"; string risk_level
        datetime due_at; int assignee_id FK; text planned_action
        datetime closed_at; int closed_by_id FK; text closure_action "required when closed"; string closure_photo_path
    }
    HAZARD_EVENT { int id PK; int hazard_id FK; int actor_id FK; string kind; text note; datetime at }
    NOTIFICATION { int id PK; int user_id FK; int hazard_id FK; text message; bool read; datetime created_at }
```

Integrity rules enforced by the database (`shms/models.py`): consequence and likelihood 1–5, risk score 1–25,
a closed hazard must have a closure action, foreign keys on every relation, one idempotency key per reporter,
and indexes on (area, category, created_at), status and created_at.
