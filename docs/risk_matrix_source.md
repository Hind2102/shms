# Risk matrix source: ADOSH-SF Technical Guideline "Process of Risk Management" v4.0

SHMS v1.4.0 aligns its risk matrix with this document. Everything below was read from the PDF itself.

| | |
|---|---|
| Title | ADOSH-SF Technical Guideline – Process of Risk Management |
| Framework | Abu Dhabi Occupational Safety and Health System Framework (ADOSH-SF), Abu Dhabi Public Health Centre (ADPHC) |
| Version / date | Version 4.0 – 15th July 2024 (page footer and amendment record, p. 15; cover: "July 2024") |
| URL | https://www.adphc.gov.ae/-/media/Project/ADPHC/ADPHC/PDF/OSHAD-SF/Technical-Guidelines/Process-of-Risk-Management--Eng.pdf |
| Downloaded | 25 Nov 2026, 484,797 bytes, 20 pages |
| SHA-256 | `f271e33d2bf74601390b1bed05c74a5483844ace5ff55b5a71740ebe9ce263d0` |
| Status | "The contents of this technical guide are not mandatory" (Sec. 1(a), p. 3) |

The PDF is not committed (third-party document); download it from the URL and check the hash.

## Table 1 – Hazard Consequence (Sec. 5.3.1, p. 9)

"Area impacted" rows; the table "is not linked to categorization of ADOSH-SF Serious Incidents" (5.3.1(b)); the
definitions "have been adopted from HB 203:2000" (5.3(l), p. 8).

| Score | Name | Human Health and Safety (SHMS main definition) | Production Loss (guidance) | Total Cost of Impacts or Incident Event (guidance) |
|---|---|---|---|---|
| 1 | Insignificant | Minor injuries, which may require self-administered first aid. Injured personnel can continue to perform normal duties. | Incident event without causing production loss. | Financial loss (compensation, fines, cost to repair, plant damage) of less than AED5,000. |
| 2 | Minor | Injuries requiring on-site treatment by medical practitioner. Personnel unable to continue to perform duties. | Production loss or delay up to one week. | Financial loss (…) of AED5,000 - AED50,000. |
| 3 | Moderate | Serious injuries requiring off-site medical treatment by medical practitioner or immediate evacuation to hospital. Potential long-term or permanently disabling effects. | Production loss or delay of one week to one month. | Financial loss (…) of AED50,000 - AED500,000 |
| 4 | Major | Single fatality. | Production loss or delay for over one month. | Financial loss (…) of AED500,000 - AED10M. |
| 5 | Catastrophic | Multiple fatalities. | Loss of licence to operate or ability to produce indefinitely. | Severe financial penalties or legal liabilities. Financial loss (…) of greater than AED10M. |

## Table 2 – Likelihood (Sec. 5.3.2, p. 10)

| Probability | Descriptor | Likely Frequency |
|---|---|---|
| 5 | Frequent | Occurs frequently |
| 4 | Often | Occurs several times per year |
| 3 | Likely | Has occurred more than once |
| 2 | Possible | Has occurred |
| 1 | Rare | Never occurred |

Table 3 labels level 5 "Frequent/ Almost Certain"; SHMS uses "Frequent / Almost certain".

**Project interpretation (not in the guideline):** SHMS sets likelihood from confirmed hazards of the same type in
the same area in the previous 365 days: 0 → 1, 1 → 2, 2 → 3, 3–5 → 4, ≥ 6 → 5. The guideline allows estimates from
"past records" (5.3(f)(i)) but defines no counts.

## Table 3 – Risk Rating (Sec. 5.3.3, p. 10)

Risk = Consequence Score × Likelihood of Occurrence (5.3(d), p. 7). The coloured grid was rendered from the PDF and
read cell by cell; the fill colours in the PDF are green `#99CC00`, yellow `#FFFF00`, orange `#FFCC00`, red `#FF0000`.

| Likelihood \ Consequence | Insignificant (1) | Minor (2) | Moderate (3) | Major (4) | Catastrophic (5) |
|---|---|---|---|---|---|
| Rare (1) | 1 green | 2 green | 3 green | 4 yellow | 5 yellow |
| Possible (2) | 2 green | 4 yellow | 6 yellow | 8 orange | 10 orange |
| Likely (3) | 3 green | 6 yellow | 9 orange | 12 orange | 15 red |
| Often (4) | 4 yellow | 8 orange | 12 orange | 16 red | 20 red |
| Frequent/ Almost Certain (5) | 5 yellow | 10 orange | 15 red | 20 red | 25 red |

| Printed range | Rating | Action (verbatim) |
|---|---|---|
| 15 - 25 | Extreme Risk | Activity or industry should not proceed in current form. |
| 8 - 12 | High Risk | Activity or industry should be modified to include remedial planning and action and be subject to detailed OSH assessment. |
| 4 - 6 | Moderate Risk | Activity or industry can operate subject to management and /or modification. |
| 1 - 3 | Low Risk | No immediate action required, unless escalation of risk is possible. |

**Scores outside the printed ranges, taken from the cell colours:** 5 → Moderate (yellow), 9 → High (orange),
10 → High (orange), 16 → Extreme (red). The colours are consistent with a pure score rule (every cell with the same
score has the same colour). SHMS stores the bands as Low 1–3, Moderate 4–7, High 8–14, Extreme 15–25 so that 1–25 is
covered without gaps; 7, 11, 13 and 14 cannot occur as products of two levels.

## Other sections used

| Section | Page | Text | Used for |
|---|---|---|---|
| 5(b) | 5 | "Particular attention shall also be given to risks that may have very low likelihood of an occurrence but may result in major consequences." | High-consequence alert: consequence ≥ 4 alerts supervisors in any band (threshold 4 = "Major" is the project's reading) |
| 5.3.4(a) | 11 | "For hazard(s) with low risk, actions may not be required." | – (SHMS still routes Low hazards; project choice) |
| 5.3.4(c) | 11 | "(i) elimination of the hazard (where possible); (ii) substitution (eg. use a less hazardous substances ); (iii) engineering / isolation - for plant and equipment (e.g. exhaust ventilation); (iv) procedural (e.g. via improving work methods, housekeeping); and (v) personal protective equipment (PPE) – it is the last resort if the above measures are not practicable." | Control type chosen at closure |
| 5.3.4(f) | 11 | action plan addressing "… time frame for completing the actions …" | The guideline requires a time frame but sets none → SHMS target days are **project-defined** (Low 30, Moderate 14, High 7, Extreme 1) |
| Appendix 2 | 17 | Example Risk Assessment Form with columns "Existing Control Measures", "Additional Controls Required", "Residual Risk" | Residual consequence and residual risk at closure |

## Where this differed from the task description

1. The high-consequence rule is in **Sec. 5(b)** (p. 5, "Five Steps of Risk Assessment"), not Sec. 5.1(b);
   Sec. 5.1(b) is about generating a comprehensive list of sources of risk.
2. Table 2 names level 5 only "Frequent"; "Frequent/ Almost Certain" appears in Table 3.
3. Everything else in the task matched the PDF: Table 1 names, Table 2 frequencies, the printed band ranges and
   action texts, the colours of 5/9/10/16 (Moderate/High/High/Extreme), the hierarchy of controls in 5.3.4(c),
   residual risk in Appendix 2, and the absence of close-out time frames.
