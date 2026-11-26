# UX review – field use (v1.6.0, Phase 7)

**Users.** Field operators, contractors and visitors, Area Owners, supervisors and managers in an alumina refinery.
They often wear gloves, work in sunlight, use one hand and have little time.

**Method.**
- Reviewed v1.5.0 (`200185a`) on a fresh synthetic demo database.
- Every main page was opened per role at 390 px (phone) and 1366 px (desktop).
- Instruments:
  - [`docs/ux/page_audit.py`](ux/page_audit.py): screenshots, interactive elements under 48 × 48 px, phone text under
    16 px, horizontal overflow;
  - [`docs/ux/time_tasks.py`](ux/time_tasks.py): timing of three core tasks;
  - `docs/screenshots/audit_ui.py`: axe-core 4.10.3.
- Severity uses Nielsen's scale: 0 = not a problem, 1 = cosmetic, 2 = minor, 3 = major, 4 = catastrophe.

This review was committed **before** any v1.6.0 code change. The after-measurements are at the end.

## Task timing – before (v1.5.0)

| Task | View | Taps / clicks | Fields typed | Pages | Machine s | Estimated human s |
|---|---|---:|---:|---:|---:|---:|
| Report a hazard (from home) | phone | 7 | 0 | 3 | 0.2 | 16 |
| Check an area before entering | phone | 4 | 0 | 3 | 0.1 | 12 |
| Verify a closure (from home) | desktop | 2 | 1 | 2 | 0.1 | 14 |

**How the numbers are counted.**
- A native select or the photo picker counts as 2 taps (open, then choose).
- Estimated human seconds = 1.2 s per tap + 6 s per typed field + 2.5 s to read each new page + machine time.
  This is a keystroke-level estimate, **not a user study**.
- In the report task the mock AI pre-selects the hazard type and its default consequence. Without a suggestion the
  reporter needs about 3 more taps.

## Page audit – before

**Small tap targets.** Every page has 10–24 interactive elements under 48 × 48 px.
- The header navigation links are 32 px high.
- Others: the skip link, the sign-out button, table row links, the map's zoom and pan buttons (44 px), the report-pin
  coordinate fields and the "Show route" text link.

**Small text on phones.**
- Body text is 15 px.
- Tables, labels and notes are 13–14 px: 1,657 text blocks under 16 px on the hazard register alone.

**Overflow.**
- `/monitoring` is 23 px wider than a 390 px phone.
- On the supervisor phone home, wide tables are cut off inside their panels (the Status column is clipped).

**axe-core (v1.5.0):** 0 findings at both widths.

## Heuristic review (Nielsen's 10)

| # | Heuristic | Page / role / width | Problem | Sev. | Fix in v1.6.0 |
|---|---|---|---|---:|---|
| 1 | Visibility of system status | Supervisor home, phone and desktop | Nothing shows what happened *this shift*: the lists are all-time and long (9 closures to verify, 10 urgent, 10 escalated). | 3 | "Since start of shift" counts (reported, alerts, closures verified, still waiting) using a project shift setting (day 06:00–18:00 / night 18:00–06:00). |
| 1 | Visibility of system status | Area Owner home | The owner's list is all their work by deadline. What happened in "my area today" is not visible first. | 2 | "My areas today" card first: new reports today, overdue and due today, per owned area. |
| 1 | Visibility of system status | Report, step 1, phone | The submit button reads "Analyse and continue" and the step count is in prose. Users don't see that two steps remain. | 2 | Step indicator "1 Photo · 2 Area · 3 Confirm" and a fixed bottom action bar. |
| 2 | Match with the real world | Check before entering, all roles | Required PPE is a comma-separated text list ("Hard hat, Safety glasses, …"). Field staff recognise mandatory-PPE signs faster than text. | 3 | PPE as our own blue-circle pictograms with text labels (not ISO 7010 artwork). |
| 2 | Match with the real world | Seeded data | Closure texts sometimes don't match the hazard, e.g. a PPE finding "closed" with "Barrier and signage placed; drip tray…". This undermines trust in the demo. | 2 | Seed closure texts per hazard type and control (PPE findings → PPE issued / briefing / PPE station; conditions → barrier / cover / housekeeping / repair). |
| 3 | User control and freedom | Report, step 1 | Changing the area clears the pin without warning; there is no visible way back from the confirm page. | 1 | Keep the pin when the new area contains it; add a "Back" secondary action on the confirm page. |
| 4 | Consistency and standards | All pages | Buttons come in several styles (`.btn`, `.btn.secondary`, `.btn.big`, unstyled `button` in map controls, text links used as actions). The spacing scale is ad hoc. | 2 | One button hierarchy (primary / secondary / danger), one card pattern and a 4-step spacing scale (8/16/24/32). |
| 4 | Consistency and standards | Risk badges | Badges show the word, but colour does most of the work. Yellow (Moderate) and amber (High) are hard to tell apart in sunlight. | 3 | Badges keep the word and add a distinct shape icon per level: ○ Low, ◆ Moderate, ▲ High, ■ Extreme (outlined, black). |
| 5 | Error prevention | Report pin | Typing X/Y coordinates is error-prone with gloves. | 1 | Tapping the map stays primary; the coordinate fields move into a collapsed "Enter coordinates" section. |
| 6 | Recognition rather than recall | Report, step 1, phone | The reporter must find their area in a list of 15 every time. | 3 | Area pre-selected from the last area used (this device), or from the photo's GPS when it is inside a zone. Photo comes first. |
| 6 | Recognition rather than recall | Confirm page | Consequence levels are radio rows with long guideline text. The level is hard to pick quickly. | 2 | Large labelled cards with the Table 1 name and short health-and-safety text, the full text one tap away. |
| 7 | Flexibility and efficiency | Every phone page | Reporting needs the header link (32 px, 2nd row of a 4-row header) or the home button. | 3 | A big "Report a hazard" button fixed at the bottom of every phone page. |
| 7 | Flexibility and efficiency | Control room | There is no large-screen view; the dashboard is built for reading at a desk. | 2 | `/board`: read-only large-screen page with the map (open-risk overlay), Extreme/High list and overdue count. Refreshes every 60 s, dark option, sign-in required. |
| 8 | Aesthetic and minimalist design | Site plan, phone | The map is only 370 px wide and its own title strip repeats the page heading. The zone card is far below the map (after filters, key and calculation). The pin list is always expanded. | 3 | Map at full content width; the title strip is hidden inside the app (the "Concept layout only" note stays); the area card and route come straight under the map on phones; the pin list collapses ("Show open hazard pins (n)"). |
| 8 | Aesthetic and minimalist design | Header, phone | Navigation wraps onto 4 lines and takes 140 px of screen before any content. | 3 | Compact header on phones: logo, Home, Alerts and a "Menu" disclosure for the rest. |
| 8 | Aesthetic and minimalist design | Supervisor and reporter homes, phone | Seven-column tables don't fit; the Status column is clipped. | 3 | Stacked list rows on phones (hazard and badge on the first line, area, status and date on the second). |
| 9 | Help users recognise, diagnose and recover from errors | Route refusal | Good: it names the flagged zones and the next step (contact the Area Owner). | 0 | – |
| 10 | Help and documentation | Site plan | The help text sits under the map, after the key. | 1 | Short help next to the map controls; the full explanation stays below. |
| – | Accessibility / field use | All, phone | Body 15 px, tables 13–14 px, tap targets 32–44 px. | 3 | Body ≥ 16 px on phones; all controls ≥ 48 × 48 px; no hover-only controls. |
| – | Accessibility / field use | `/monitoring`, phone | 23 px horizontal overflow. | 2 | Wrap the KPI grid; scroll wide tables inside their card. |
| – | Honesty | Empty states | The overlays and heat map already avoid "safe". Some empty lists say "None." or "Nothing open. Well done." | 1 | "No recorded hazards in this window" style messages, never "safe"; a test checks every page. |

Heuristics with no problem found (severity 0): error messages on the report and closure forms are specific; the
state machine refuses illegal steps and says why.

## After (v1.6.0)

The after-measurements are added at the end of this file, below this line, by the verification step.
