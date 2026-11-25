"""Synthesized refinery layout, users and hazard history (deterministic, seed 42).

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
# code, name, owner index, extra PPE shown at the entrance, AI checks, x, y, w, h, relative hazard weight
# This refinery uses coveralls, not hi-vis vests, so no area requires a vest (the vest check was also
# rejected by the release gate). Every area requires hard hat, eye protection and gloves.
AREAS = [
    ("BXH", "Bauxite Handling", 3, "Dust mask, Hearing protection", REQUIRED, 20, 40, 200, 230, 1.0),
    ("GRD", "Grinding & Desilication", 3, "Hearing protection", REQUIRED, 240, 40, 180, 230, 1.0),
    ("DIG", "Digestion", 3, "Face shield over glasses (caustic), Chemical gloves", REQUIRED, 440, 40, 200, 230, 2.2),
    (
        "CLR",
        "Clarification (Red Mud)",
        4,
        "Face shield over glasses (caustic), Chemical gloves",
        REQUIRED,
        660,
        40,
        150,
        230,
        1.4,
    ),
    (
        "FLT",
        "Security Filtration",
        4,
        "Face shield over glasses (caustic), Chemical gloves",
        REQUIRED,
        830,
        40,
        150,
        230,
        1.8,
    ),
    ("PRC", "Precipitation", 5, "Chemical gloves", REQUIRED, 660, 300, 320, 250, 1.2),
    ("CAL", "Calcination", 5, "Heat-resistant gloves, Dust mask", REQUIRED, 380, 300, 260, 250, 1.3),
    (
        "TNK",
        "Caustic Tank Farm",
        6,
        "Face shield (caustic transfers), Chemical suit",
        REQUIRED,
        240,
        300,
        120,
        250,
        0.9,
    ),
    (
        "PWR",
        "Powerhouse & Utilities",
        6,
        "Hearing protection, Arc-rated clothing (switchrooms)",
        REQUIRED,
        20,
        300,
        200,
        250,
        0.7,
    ),
]

CATEGORY_WEIGHTS = {"no_hard_hat": 6, "no_eye_protection": 9, "no_gloves": 8, "no_hi_vis_vest": 5}

ACTIONS = {
    "no_hard_hat": "Work stopped; worker briefed and hard hat issued. Toolbox talk held with the crew.",
    "no_eye_protection": "Task paused; safety glasses and face shield issued. Eye-wash station location reconfirmed.",
    "no_gloves": "Task paused; chemical gloves issued and task risk assessment reviewed.",
    "no_hi_vis_vest": "Worker briefed; hi-vis vest issued from the area PPE station.",
}
# Synthetic closures issue PPE, so their control type is PPE (the last level of the ADOSH-SF hierarchy). The residual
# consequence is a fixed synthetic choice (two levels lower, at least 1) – demo data, not an assessment.
SYNTHETIC_CONTROL = "ppe"


def _residual(consequence: int) -> int:
    return max(1, consequence - 2)


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


def seed(db: Session, n_history: int = 240, now: datetime | None = None, rng_seed: int = 42) -> None:
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
            required_ppe=f"{BASE_PPE}, {extra}",
            ai_checks=checks,
            x=x,
            y=y,
            w=w,
            h=h,
        )
        for c, nm, o, extra, checks, x, y, w, h, _ in AREAS
    ]
    db.add_all(areas)
    db.flush()

    reporters = [u for u in users if u.role == Role.REPORTER]
    supervisor = next(u for u in users if u.role == Role.SUPERVISOR)
    area_w = [a[-1] for a in AREAS]
    times = sorted(now - timedelta(days=rng.uniform(0, 180), hours=rng.uniform(0, 12)) for _ in range(n_history))

    with notify.no_mail():  # synthetic history: in-app notifications only, no outbox e-mails
        _history(db, rng, areas, area_w, reporters, supervisor, times, now)
    db.commit()


def _history(db, rng, areas, area_w, reporters, supervisor, times, now) -> None:
    for t in times:
        area = rng.choices(areas, area_w)[0]
        cats = area.check_codes
        cat = rng.choices(cats, [CATEGORY_WEIGHTS[c] for c in cats])[0]
        reporter = rng.choice(reporters)
        h = services.create_draft(db, reporter, area, None, _synthetic_ai(rng, area, cat, now - t), at=t)
        cons = max(1, min(5, taxonomy.get(cat).default_consequence + rng.choice([-1, 0, 0, 0, 1])))
        on_spot = rng.random() < 0.25 and cons <= 3
        services.confirm(
            db,
            h,
            reporter,
            services.Confirmation(
                category_code=cat,
                consequence=cons,
                description=f"Synthetic report: {taxonomy.get(cat).name.lower()}.",
                fixed_on_spot=on_spot,
                closure_action=ACTIONS[cat] if on_spot else "",
                control_type=SYNTHETIC_CONTROL if on_spot else None,
                residual_consequence=_residual(cons) if on_spot else None,
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
                    db,
                    h,
                    area.owner,
                    ACTIONS[cat],
                    at=close_at,
                    control_type=SYNTHETIC_CONTROL,
                    residual_consequence=_residual(cons),
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
