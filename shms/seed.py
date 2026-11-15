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

from . import services, taxonomy
from .models import Area, Hazard, Role, Status, User, utcnow

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

BASE_PPE = "Hard hat, Safety glasses, Hi-vis vest, Safety boots, Gloves"
# code, name, owner index, extra PPE, x, y, w, h, relative hazard weight
AREAS = [
    ("BXH", "Bauxite Handling", 3, "Dust mask, Hearing protection", 20, 40, 200, 230, 1.0),
    ("GRD", "Grinding & Desilication", 3, "Hearing protection", 240, 40, 180, 230, 1.0),
    ("DIG", "Digestion", 3, "Face shield (caustic), Chemical gloves", 440, 40, 200, 230, 2.2),
    ("CLR", "Clarification (Red Mud)", 4, "Face shield (caustic), Chemical gloves", 660, 40, 150, 230, 1.4),
    ("FLT", "Security Filtration", 4, "Face shield (caustic), Chemical gloves", 830, 40, 150, 230, 1.8),
    ("PRC", "Precipitation", 5, "Chemical gloves", 660, 300, 320, 250, 1.2),
    ("CAL", "Calcination", 5, "Heat-resistant gloves, Dust mask", 380, 300, 260, 250, 1.3),
    ("TNK", "Caustic Tank Farm", 6, "Face shield (caustic), Chemical suit for transfers", 240, 300, 120, 250, 0.9),
    ("PWR", "Powerhouse & Utilities", 6, "Hearing protection, Arc-rated clothing (switchrooms)", 20, 300, 200, 250, 0.7),
]

CATEGORY_WEIGHTS = {
    "caustic_spill": 18, "steam_leak": 10, "slip_trip": 16, "no_hard_hat": 6, "no_hi_vis_vest": 5,
    "no_gloves": 8, "other_ppe": 6, "fall_from_height": 7, "electrical": 5, "machine_guarding": 5,
    "unsafe_behaviour": 6, "fire": 3, "other": 5,
}

ACTIONS = {
    "caustic_spill": "Isolated line, neutralised and washed down spill; flange gasket replaced by maintenance.",
    "steam_leak": "Barricaded area; leaking steam trap isolated and replaced under permit.",
    "slip_trip": "Housekeeping completed; hoses re-routed to hose rack.",
    "no_hard_hat": "Worker stopped and briefed; hard hat issued. Toolbox talk held with crew.",
    "no_hi_vis_vest": "Worker briefed; hi-vis vest issued from area PPE station.",
    "no_gloves": "Task paused; chemical gloves issued and task risk assessment reviewed.",
    "other_ppe": "Face shield issued; PPE requirement sign re-posted at area entry.",
    "fall_from_height": "Area barricaded; missing grating replaced and handrail repaired.",
    "electrical": "Panel isolated (LOTO); damaged cable replaced by electrician.",
    "machine_guarding": "Equipment stopped; guard re-installed and checked before restart.",
    "unsafe_behaviour": "Activity stopped; supervisor coaching conversation recorded.",
    "fire": "Combustibles removed; extinguisher access cleared.",
    "other": "Corrective action completed by area team.",
}


def seed(db: Session, n_history: int = 240, now: datetime | None = None, rng_seed: int = 42) -> None:
    if db.scalar(select(User).limit(1)) is not None:
        return  # already seeded
    rng = random.Random(rng_seed)
    now = now or utcnow()

    users = [User(name=n, role=r) for n, r in USERS]
    db.add_all(users)
    db.flush()
    areas = [Area(code=c, name=nm, owner_id=users[o].id, required_ppe=f"{BASE_PPE}, {extra}",
                  x=x, y=y, w=w, h=h) for c, nm, o, extra, x, y, w, h, _ in AREAS]
    db.add_all(areas)
    db.flush()

    reporters = [u for u in users if u.role == Role.REPORTER]
    area_w = [a[-1] for a in AREAS]
    cats, cat_w = list(CATEGORY_WEIGHTS), list(CATEGORY_WEIGHTS.values())
    times = sorted(now - timedelta(days=rng.uniform(0, 180), hours=rng.uniform(0, 12)) for _ in range(n_history))

    for t in times:
        area = rng.choices(areas, area_w)[0]
        cat = rng.choices(cats, cat_w)[0]
        reporter = rng.choice(reporters)
        h = services.create_draft(db, reporter, area, None, None, at=t)
        cons = max(1, min(5, taxonomy.get(cat).default_consequence + rng.choice([-1, 0, 0, 0, 1])))
        on_spot = rng.random() < 0.25 and cons <= 3
        services.confirm(db, h, reporter, services.Confirmation(
            category_code=cat, consequence=cons, description=f"Synthetic report: {taxonomy.get(cat).name.lower()}.",
            fixed_on_spot=on_spot, closure_action=ACTIONS[cat] if on_spot else ""), at=t)
        if not on_spot:
            # Older hazards are mostly closed; recent ones are more likely still open.
            age = (now - t).days
            if rng.random() < min(0.97, 0.35 + age / 60):
                close_at = min(now, t + timedelta(days=rng.uniform(0.2, 1.6) * (h.due_at - t).days + 0.1))
                services.close(db, h, area.owner, ACTIONS[cat], at=close_at)
    db.commit()


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
