"""Synthesized refinery layout, users and hazard history (deterministic, seed 42).

v1.4.1: 150 reports over 6 months with per-area frequencies (PROFILE), realistic consequences
(CONSEQUENCE_WEIGHTS) and mixed closure controls (CONTROLS), so that the ADOSH-SF v4.0 bands come out roughly
Low 40 %, Moderate 35 %, High 24 %, Extreme 1 % (tests/test_seed_realism.py).
v1.5.0: 15 zones of the approved concept map and 210 reports (Low 39.5 %, Moderate 35.2 %, High 21.0 %,
Extreme 4.3 %).

Real refinery records and site maps are confidential, so the demo uses a
synthesized layout that follows the Bayer process flow and a generated
history that runs through the same service functions as live reports.
Run:  python -m shms.seed  (or `make seed`)
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import auth, notify, services, taxonomy
from .models import Area, Hazard, Role, Status, User, utcnow

DEMO_PASSWORD = "shms-demo-2026"  # documented demo password for the synthesized users – not a secret

USERS = [
    ("Ahmed (Operator)", Role.REPORTER),
    ("Fatima (Operator)", Role.REPORTER),
    ("Ravi (Contractor)", Role.REPORTER),
    ("Khalid (Area Owner - Digestion side)", Role.AREA_OWNER),
    ("Mariam (Area Owner - Clarification side)", Role.AREA_OWNER),
    ("Omar (Area Owner - Precipitation side)", Role.AREA_OWNER),
    ("Noura (Area Owner - Utilities side)", Role.AREA_OWNER),
    ("Sara (Safety Supervisor)", Role.SUPERVISOR),
    ("Yousef (Refinery Manager)", Role.MANAGER),
]

BASE_PPE = "Hard hat, Safety glasses, Gloves, Safety boots, Flame-resistant coverall"
REQUIRED = "no_hard_hat,no_eye_protection,no_gloves"
# Reporting zones of the approved concept map (v1.5.0): code, owner index, required PPE shown at the entrance.
# Names and geometry come from the map (shms/site_layout.py). PPE lists are project assumptions, not verified site
# requirements. This refinery uses coveralls, not hi-vis vests, so no area requires a vest (the vest check was also
# rejected by the release gate). AI checks are the released PPE checks only (REQUIRED ∩ release gate).
# The first nine keep their v1.4 order (and ids); the six new zones follow, as migration 0009 adds them.
ZONE_PPE = [
    ("BXH", 3, f"{BASE_PPE}, Dust mask, Hearing protection"),
    ("GRD", 3, f"{BASE_PPE}, Hearing protection"),
    ("DIG", 3, f"{BASE_PPE}, Face shield over glasses (caustic), Chemical gloves"),
    ("CLR", 4, f"{BASE_PPE}, Face shield over glasses (caustic), Chemical gloves"),
    ("FLT", 4, f"{BASE_PPE}, Face shield over glasses (caustic), Chemical gloves"),
    ("PRC", 5, f"{BASE_PPE}, Chemical gloves"),
    ("CAL", 5, f"{BASE_PPE}, Heat-resistant gloves, Dust mask"),
    ("TNK", 6, f"{BASE_PPE}, Face shield (caustic transfers), Chemical suit"),
    ("PWR", 6, f"{BASE_PPE}, Hearing protection, Arc-rated clothing (switchrooms)"),
    ("EVP", 5, "Hard hat, Face shield, Chemical gloves"),
    ("HYD", 5, "Hard hat, Face shield, Chemical gloves"),
    ("ALS", 5, "Hard hat, Safety glasses, Gloves, Dust mask"),
    ("LIM", 6, "Hard hat, Goggles, Gloves, Dust mask"),
    ("WKS", 6, "Hard hat, Safety glasses, Gloves, Hearing protection"),
    ("WTR", 6, "Hard hat, Safety glasses, Life jacket (near open water)"),
]


def _area_rows():
    from .site_layout import REPORTING

    for code, owner, ppe in ZONE_PPE:
        z = REPORTING[code]
        yield code, z.name, owner, ppe, REQUIRED, z.x, z.y, z.w, z.h


AREAS = list(_area_rows())  # code, name, owner index, required PPE, AI checks, x, y, w, h (map bounding box)

# ---------------------------------------------------------------- synthesized history (v1.4.1)
# Expected findings per area over the 6-month history, by hazard type. Caustic areas (digestion, clarification,
# filtration, tank farm) have more eye/face and glove findings; bauxite handling and grinding more hard-hat findings
# (mobile plant, conveyors, overhead work); calcination hot-work gloves; the powerhouse more open panels.
# Repeats of one type in one area are kept low, as on a site that acts on its findings.
PPE_FINDINGS = ("no_hard_hat", "no_eye_protection", "no_gloves")
CAUSTIC = {"DIG", "CLR", "FLT", "TNK", "EVP"}
PROFILE: dict[str, dict[str, float]] = {
    "BXH": {
        "no_hard_hat": 3,
        "no_eye_protection": 1,
        "no_gloves": 1,
        "walkway_obstruction": 1.5,
        "surface_corrosion": 1,
        "open_panel": 0.7,
        "other_condition": 0.7,
    },
    "GRD": {
        "no_hard_hat": 2.5,
        "no_eye_protection": 1,
        "no_gloves": 1,
        "open_panel": 1,
        "floor_liquid": 1,
        "walkway_obstruction": 0.8,
        "surface_corrosion": 0.6,
    },
    "DIG": {
        "no_hard_hat": 1,
        "no_eye_protection": 3,
        "no_gloves": 2.5,
        "floor_liquid": 2,
        "surface_corrosion": 1,
        "floor_opening": 0.6,
        "other_condition": 0.6,
    },
    "CLR": {
        "no_hard_hat": 1,
        "no_eye_protection": 2.5,
        "no_gloves": 2,
        "floor_liquid": 1.5,
        "floor_opening": 0.7,
        "surface_corrosion": 1,
        "walkway_obstruction": 0.6,
    },
    "FLT": {
        "no_hard_hat": 1,
        "no_eye_protection": 2.5,
        "no_gloves": 2,
        "floor_liquid": 1.5,
        "walkway_obstruction": 1,
        "surface_corrosion": 0.8,
    },
    "PRC": {
        "no_hard_hat": 1.5,
        "no_eye_protection": 1.5,
        "no_gloves": 1.5,
        "walkway_obstruction": 1,
        "floor_opening": 0.7,
        "surface_corrosion": 0.8,
        "floor_liquid": 0.7,
    },
    "CAL": {
        "no_hard_hat": 1.5,
        "no_eye_protection": 1,
        "no_gloves": 2,
        "surface_corrosion": 1,
        "other_condition": 1,
        "walkway_obstruction": 0.7,
    },
    "TNK": {
        "no_hard_hat": 0.7,
        "no_eye_protection": 2,
        "no_gloves": 1.5,
        "surface_corrosion": 1.5,
        "floor_liquid": 1,
        "open_panel": 0.5,
    },
    "PWR": {
        "no_hard_hat": 1,
        "no_eye_protection": 0.7,
        "no_gloves": 0.7,
        "open_panel": 1.5,
        "other_condition": 1,
        "surface_corrosion": 0.6,
    },
    # New zones of the v1.5.0 concept map (project assumptions about typical findings)
    "EVP": {
        "no_eye_protection": 2,
        "no_gloves": 1.5,
        "no_hard_hat": 0.7,
        "floor_liquid": 1.2,
        "surface_corrosion": 0.8,
    },
    "HYD": {
        "no_gloves": 1.5,
        "no_eye_protection": 1.2,
        "no_hard_hat": 0.8,
        "floor_liquid": 1,
        "walkway_obstruction": 0.7,
    },
    "ALS": {
        "no_hard_hat": 1.5,
        "no_eye_protection": 1,
        "no_gloves": 0.7,
        "walkway_obstruction": 0.8,
        "other_condition": 0.6,
    },
    "LIM": {
        "no_eye_protection": 1.5,
        "no_gloves": 1,
        "no_hard_hat": 1,
        "walkway_obstruction": 0.6,
        "surface_corrosion": 0.5,
    },
    "WKS": {"no_hard_hat": 1.2, "no_eye_protection": 1.2, "no_gloves": 1, "walkway_obstruction": 1, "open_panel": 0.7},
    "WTR": {"no_hard_hat": 0.8, "floor_opening": 0.6, "other_condition": 0.8, "walkway_obstruction": 0.5},
}
# Consequence (ADOSH-SF Table 1) as weights for C1..C5. Most missing-PPE findings are C2-C3; C4 only where the
# context makes it credible (no face shield at a caustic sampling point or during line breaking; an uncovered opening
# at height). The description says which context applies.
CONSEQUENCE_WEIGHTS: dict[str, tuple[float, ...]] = {
    "no_hard_hat": (0, 55, 45, 0, 0),
    "no_eye_protection": (0, 60, 40, 0, 0),
    "no_gloves": (5, 60, 35, 0, 0),
    "floor_liquid": (10, 65, 25, 0, 0),
    "walkway_obstruction": (25, 65, 10, 0, 0),
    "open_panel": (0, 45, 55, 0, 0),
    "floor_opening": (0, 20, 60, 20, 0),
    "surface_corrosion": (55, 40, 5, 0, 0),
    "other_condition": (20, 65, 15, 0, 0),
}
CAUSTIC_C4 = {"no_eye_protection": 0.12, "no_gloves": 0.04}  # share of caustic-area findings that are C4
C4_CONTEXT = {
    "no_eye_protection": "No face shield at a caustic sampling point during line breaking.",
    "no_gloves": "Bare hands on a caustic sample valve.",
    "floor_opening": "Grating removed at a raised platform edge.",
}
# Closure controls: (control type, weight, how far the residual consequence drops, action text). Residual consequence
# is never higher than the original. Elimination and substitution are rare.
CONTROLS: dict[str, list[tuple[str, float, int, str]]] = {
    "ppe_finding": [
        ("procedural", 40, 1, "Toolbox talk held with the crew; task permit re-checked for the required PPE."),
        ("ppe", 33, 1, "PPE issued / replaced from the area store; worker briefed."),
        ("engineering", 22, 1, "PPE station installed at the area entrance; sign plus barrier at the access point."),
        ("substitution", 2, 2, "Sampling moved to a closed sampler so the task no longer needs open handling."),
        ("elimination", 2, 2, "Manual sampling at this point discontinued (online analyser in use)."),
    ],
    "condition": [
        ("procedural", 40, 1, "Housekeeping round added to the shift checklist; area cleaned and re-inspected."),
        ("engineering", 45, 1, "Barrier and signage placed; drip tray / guard / cover fitted by maintenance."),
        ("elimination", 5, 2, "Source removed: leaking fitting replaced / redundant item taken out of the walkway."),
        ("substitution", 3, 2, "Coated grating substituted for the corroded section."),
        ("ppe", 3, 0, "Interim PPE issued until the repair is made."),
    ],
}
N_HISTORY = 210  # v1.5.0: 15 reporting zones (was 150 for 9 zones in v1.4.1)


def _consequence(rng: random.Random, area_code: str, cat: str) -> tuple[int, str]:
    if area_code in CAUSTIC and rng.random() < CAUSTIC_C4.get(cat, 0):
        return 4, C4_CONTEXT[cat]
    c = rng.choices((1, 2, 3, 4, 5), CONSEQUENCE_WEIGHTS[cat])[0]
    return c, C4_CONTEXT.get(cat, "") if c == 4 else ""


def _control(rng: random.Random, cat: str, consequence: int) -> tuple[str, int, str]:
    options = CONTROLS["ppe_finding" if cat in PPE_FINDINGS else "condition"]
    code, _, drop, text = rng.choices(options, [o[1] for o in options])[0]
    return code, max(1, consequence - drop), text


def _synthetic_ai(rng: random.Random, area: Area, true_code: str, age: timedelta):
    """Synthetic AI result for demo history (last 60 days only, as if the AI went live then): mostly right,
    sometimes another PPE item, sometimes nothing detected. Clearly demo data, not an evaluation."""
    from .detection.base import DetectorResult, Suggestion

    if age.days > 60:
        return None
    r = rng.random()
    if r < 0.84:
        code = true_code
    elif r < 0.93:
        code = rng.choice([c for c in area.check_codes if c != true_code] or [true_code])
    else:
        return DetectorResult("yolo:sh17_yolo9e", [], rng.uniform(250, 900))
    return DetectorResult("yolo:sh17_yolo9e", [Suggestion(code, rng.uniform(0.45, 0.95))], rng.uniform(250, 900))


def seed(db: Session, n_history: int = N_HISTORY, now: datetime | None = None, rng_seed: int = 42) -> None:
    if db.scalar(select(User).limit(1)) is not None:
        return  # already seeded
    rng = random.Random(rng_seed)
    now = now or utcnow()

    # Demo addresses use the reserved .example domain: the test outbox can never deliver real mail.
    # Every demo user signs in with their first name and DEMO_PASSWORD (documented in the README; not a secret).
    pw = auth.hash_password(DEMO_PASSWORD)
    users = [
        User(
            name=n,
            role=r,
            email=f"{n.split()[0].lower()}@shms.example",
            username=n.split()[0].lower(),
            password_hash=pw,
        )
        for n, r in USERS
    ]
    db.add_all(users)
    db.flush()
    areas = [
        Area(
            code=c,
            name=nm,
            owner_id=users[o].id,
            required_ppe=ppe,
            ai_checks=checks,
            x=x,
            y=y,
            w=w,
            h=h,
        )
        for c, nm, o, ppe, checks, x, y, w, h in AREAS
    ]
    db.add_all(areas)
    db.flush()

    reporters = [u for u in users if u.role == Role.REPORTER]
    supervisor = next(u for u in users if u.role == Role.SUPERVISOR)
    times = sorted(now - timedelta(days=rng.uniform(0, 180), hours=rng.uniform(0, 12)) for _ in range(n_history))

    with notify.no_mail():  # synthetic history: in-app notifications only, no outbox e-mails
        _history(db, rng, areas, reporters, supervisor, times, now)
    db.commit()


def _history(db, rng, areas, reporters, supervisor, times, now) -> None:
    cells = [(a, cat, w) for a in areas for cat, w in PROFILE[a.code].items()]
    for t in times:
        area, cat, _ = rng.choices(cells, [w for *_, w in cells])[0]
        reporter = rng.choice(reporters)
        ai = _synthetic_ai(rng, area, cat, now - t) if cat in PPE_FINDINGS else None  # AI checks PPE only
        h = services.create_draft(db, reporter, area, None, ai, at=t)
        cons, context = _consequence(rng, area.code, cat)
        control, residual, action = _control(rng, cat, cons)
        on_spot = rng.random() < 0.25 and cons <= 3
        services.confirm(
            db,
            h,
            reporter,
            services.Confirmation(
                category_code=cat,
                consequence=cons,
                description=f"Synthetic report: {taxonomy.get(cat).name.lower()}. {context}".strip(),
                fixed_on_spot=on_spot,
                closure_action=action if on_spot else "",
                control_type=control if on_spot else None,
                residual_consequence=residual if on_spot else None,
            ),
            at=t,
        )
        close_at = t if on_spot else None
        if not on_spot:
            # Older hazards are mostly closed; recent ones are more likely still open.
            age = (now - t).days
            if rng.random() < min(0.97, 0.35 + age / 60):
                close_at = min(now, t + timedelta(days=rng.uniform(0.2, 1.6) * (h.due_at - t).days + 0.1))
                services.close(
                    db, h, area.owner, action, at=close_at, control_type=control, residual_consequence=residual
                )
        if close_at is not None:
            # The safety supervisor verifies closures a few days later; recent ones are still waiting.
            verify_at = close_at + timedelta(days=rng.uniform(0.5, 3))
            if verify_at < now:
                services.verify(db, h, supervisor, "Checked on site (synthetic)", at=verify_at)


def main() -> None:
    from .db import create_all, init_engine, new_session
    from .settings import get_settings

    init_engine(get_settings().database_url)
    create_all()
    with new_session() as db:
        seed(db)
        n = db.query(Hazard).filter(Hazard.status != Status.DRAFT).count()
        print(f"Seeded database {get_settings().database_url} with {n} synthetic hazards.")


if __name__ == "__main__":
    main()
