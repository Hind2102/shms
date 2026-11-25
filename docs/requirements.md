# Requirements: user stories and data model

The proposal committed to developing SHMS from user stories and a defined data model. This file records both
and links every story to where it is implemented and tested.

## User stories

| ID | As a … | I want to … | So that … | Implemented in | Verified by |
|---|---|---|---|---|---|
| US1 | field operator or contractor | report a hazard with a phone photo in a few taps | it is captured before someone is hurt | `/report`, `services.create_draft` | `test_api::test_full_workflow_and_dashboard_update`, `test_html_report_flow` |
| US2 | reporter | see what the AI found on my photo and confirm or correct it | the classification is fast but stays my decision | `/hazards/{id}/confirm`, AI evidence boxes | `test_html_report_flow`, `test_reporter_can_correct_ai` |
| US3 | reporter | choose a consequence level defined by ADOSH-SF Table 1 while the system estimates likelihood (Table 2; ADOSH-SF likelihood describes how likely harm is; SHMS estimates it from how often similar hazards were reported in the same area in the last 365 days – a project heuristic, not the guideline's definition.) | risk is scored consistently on the ADOSH-SF v4.0 5 × 5 matrix (Table 3) | `risk.py`, `config/risk_matrix.json`, `/matrix`, [source](risk_matrix_source.md) | `test_risk.py::test_every_matrix_cell_matches_the_guideline_table` (all 25 cells against the PDF grid), `test_unassigned_scores_take_the_band_of_their_cell_colour`, `test_likelihood_grows_with_similar_history` |
| US4 | reporter who already fixed the hazard | record the action taken and a closing photo | the fix is documented and can be reused elsewhere | confirm form "fixed on the spot" | `test_fixed_on_spot_records_how_and_awaits_verification` |
| US5 | Area Owner | receive open hazards for my areas, plan an action and close them with what was done | nothing is closed without a record of how | `/queue`, `/hazards/{id}` plan/close | `test_owner_closes_with_documented_action`, `test_only_owner_or_supervisor_can_close` |
| US6 | safety supervisor | be alerted to High and Extreme hazards and trace every action on them | serious hazards get attention at once | notifications, audit trail | `test_high_risk_alerts_supervisor_and_owner`, `test_high_band_alert_says_why` |
| US7 | operator or visitor | check an area's live hazards and required PPE before entering | I know what to expect and wear | `/areas/{code}` | `test_html_pages_render` |
| US8 | manager | see where risk concentrates, how it trends and which hazards repeat | I can target resources and see if things improve | dashboard, heat map, repeat hotspots | `test_dashboard_counts_new_report_immediately`, `test_repeat_hotspots` |
| US9 | safety supervisor | know that the AI is only used where it was proven, and watch it in use | reporters can see the limits of each suggestion | release gate, `/monitoring`, `/metrics` | `test_release_gate.py`, `test_monitoring_and_metrics` |
| US10 | reporter on poor site Wi-Fi | not create duplicates when I tap twice or the page retries | the register stays clean | idempotency keys | `test_idempotent_report_creation`, `test_html_double_submit_returns_same_draft` |
| US11 | safety supervisor or reporter | verify a closure independently, or reject it with a reason | a hazard is only closed when someone other than the closer has checked it | `services.verify/reject`, `/hazards/{id}/verify`, `/reject`, `/queue` "Awaiting verification" | `test_supervisor_verifies_closure`, `test_closer_cannot_verify_own_closure`, `test_reject_returns_to_open_with_reason`, `test_html_verify_and_reopen_flow` |
| US12 | Area Owner | plan an action with an owner and a deadline | everyone knows who does what by when | `services.plan_action`, plan form | `test_plan_moves_open_to_planned_with_owner_and_deadline`, `test_html_plan_with_deadline_date` |
| US13 | safety supervisor, manager | be told when a hazard is overdue, manager after a further week | overdue hazards are escalated, not forgotten | `shms/escalate.py`, `shms/notify.py` (test outbox) | `test_overdue_hazard_escalates_to_supervisors_and_writes_outbox_mail`, `test_second_level_after_seven_days_notifies_managers`, `test_opening_a_page_escalates_overdue_hazards` |
| US14 | supervisor or reporter | reopen a hazard that has come back, with a reason | recurrence is recorded on the same case | `services.reopen`, `/hazards/{id}/reopen` | `test_reopen_closed_hazard_requires_reason`, `test_reopen_sets_a_new_deadline_and_resets_escalation` |
| US15 | reporter | report manually when the AI finds nothing or fails, without being told the scene is safe | AI gaps never hide a hazard | confirm page wording, `Area.unchecked_ppe` | `test_ai_found_nothing_is_not_presented_as_safe`, `test_ai_failure_lets_reporter_choose_every_checked_type` |
| US16 | reporter, Area Owner, supervisor, manager | start on a page that shows what I have to act on | nobody has to search for their work | `/` → `services.role_home`, `home.html` | `test_each_role_gets_its_own_home_page`, `test_supervisor_home_lists_verifications_urgent_items_and_escalations`, `test_area_owner_home_lists_my_open_work_sorted_by_deadline`, `test_manager_home_has_closure_performance_with_its_denominator` |
| US17 | manager, supervisor | see where open risk, overdue work and reports concentrate on the site layout, with the calculation stated | priorities are visible without misreading report volume as danger | `/site` → `services.site_overview`, `site.html` | `test_open_risk_overlay_sums_active_risk_in_the_window_and_states_its_basis`, `test_areas_without_hazards_are_labelled_no_records_never_safe`, `test_report_volume_overlay_is_neutral_and_says_it_is_not_danger`, `test_plan_view_page_is_labelled_illustrative_and_explains_the_overlay` |
| US18 | Area Owner or reporter closing a hazard | state which level of the ADOSH-SF hierarchy of controls (Sec. 5.3.4(c)) the action uses | weak controls (PPE, the last resort) are visible and can be challenged | close form, fixed-on-the-spot form, `services._record_controls` | `test_close_requires_a_control_type_from_the_hierarchy`, `test_each_control_type_is_stored_and_written_to_the_audit_trail`, `test_close_form_shows_hierarchy_and_residual_and_refuses_without_them` |
| US19 | closer and verifier | record the residual consequence and see original vs residual risk (Appendix 2) | the verifier can judge whether the control reduced the risk enough | close form, verify form, `/queue` | `test_residual_risk_is_residual_consequence_times_likelihood`, `test_verifier_sees_original_and_residual_risk`, `test_fixed_on_the_spot_also_records_control_and_residual_risk` |
| US20 | safety supervisor | be alerted to any hazard with consequence 4 or 5 even when its score band is Low or Moderate, with the reason stated | low-likelihood, major-consequence risks get attention (ADOSH-SF Sec. 5(b)) | `risk.alert_reason`, notifications | `test_major_consequence_alerts_even_in_a_low_or_moderate_band`, `test_consequence_3_in_a_moderate_band_does_not_alert`, `test_alert_reason_for_every_cell` |
| US21 | manager | see the share of verified closures by control type in the last 90 days, with its denominator, and legacy closures as "not recorded" | I can see whether the site relies on PPE instead of higher controls | manager home, `services.closure_performance` | `test_manager_sees_closure_share_by_control_type_with_its_denominator`, `test_manager_home_panel_states_the_denominator`, `test_migration_never_invents_legacy_closure_values` |

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
        int id PK; int area_id FK; int reporter_id FK; enum status "draft | open | planned | pending_verification | closed"
        string idem_key "unique per reporter"; datetime created_at; string photo_path; int x "optional pin"; int y "optional pin"
        string ai_model; text ai_suggestions; string ai_top_code; float ai_latency_ms; bool ai_accepted
        string category_code; int consequence "1-5"; int likelihood "1-5"; int risk_score "1-25"; string risk_level
        datetime due_at; int assignee_id FK; text planned_action
        datetime closed_at; int closed_by_id FK; text closure_action "required when closed"; string closure_photo_path
        string control_type "elimination | substitution | engineering | procedural | ppe; NULL = not recorded (legacy)"
        int residual_consequence "1-5"; int residual_score; string residual_level
    }
    HAZARD_EVENT { int id PK; int hazard_id FK; int actor_id FK; string kind; text note; datetime at }
    NOTIFICATION { int id PK; int user_id FK; int hazard_id FK; text message; bool read; datetime created_at }
```

Integrity rules enforced by the database (`shms/models.py`): consequence and likelihood 1–5, risk score 1–25,
a closed hazard must have a closure action, control type from the hierarchy of controls, residual consequence 1–5,
foreign keys on every relation, one idempotency key per reporter,
and indexes on (area, category, created_at), status and created_at.

### Physical-condition reporting

A field worker can report liquid, blocked access, an open machine-panel cover, a floor opening, visible corrosion or another physical condition in any reporting area. The experimental inference flag affects only photo observations for liquid and walkway obstruction. A human chooses the category and consequence. Acceptance checks include flag-off confirmation, no model call when disabled, no automatic condition selection, fixed category wording and a desktop/phone spill closure walkthrough (tests/test_experimental_conditions.py and docs/screenshots/audit_ui.py).
