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

from . import area_profiles, auth, notify, services, taxonomy
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
LAB_CHECKS = "no_eye_protection,no_gloves"  # a laboratory does not require a hard hat
# Reporting zones of the approved concept map (v1.5.0): code, owner index, required PPE shown at the entrance.
# Names and geometry come from the map (shms/site_layout.py). PPE lists are project assumptions, not verified site
# requirements. This refinery uses coveralls, not hi-vis vests, so no area requires a vest (the vest check was also
# rejected by the release gate). AI checks are the released PPE checks only (REQUIRED ∩ release gate).
# The first nine keep their v1.4 order (and ids); the six new zones follow, as migration 0009 adds them.
ZONE_OWNER = [  # v1.4 order first (ids), then the v1.5 zones, then LAB (v1.7.0, migration 0011)
    ("BXH", 3),
    ("GRD", 3),
    ("DIG", 3),
    ("CLR", 4),
    ("FLT", 4),
    ("PRC", 5),
    ("CAL", 5),
    ("TNK", 6),
    ("PWR", 6),
    ("EVP", 5),
    ("HYD", 5),
    ("ALS", 5),
    ("LIM", 6),
    ("WKS", 6),
    ("WTR", 6),
    ("LAB", 6),
]
# v1.7.0: required PPE per zone from the area profiles (project assumptions, shms/config/area_profiles.json).
ZONE_PPE = [(code, owner, ", ".join(area_profiles.get(code)["required_ppe"])) for code, owner in ZONE_OWNER]


def _area_rows():
    from .site_layout import REPORTING

    for code, owner, ppe in ZONE_PPE:
        z = REPORTING[code]
        checks = LAB_CHECKS if code == "LAB" else REQUIRED
        yield code, z.name, owner, ppe, checks, z.x, z.y, z.w, z.h


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
# v1.6.0: closure action texts that match the hazard type and the control (the control is still drawn from CONTROLS,
# so the random sequence and the v1.4.1 distribution are unchanged). PPE findings close with PPE issued, a briefing or a
# PPE station; physical conditions with a barrier, cover, housekeeping or repair.
ACTION_TEXT: dict[str, dict[str, str]] = {
    "no_hard_hat": {
        "procedural": "Toolbox talk on head protection; task permit re-checked for hard hats.",
        "ppe": "Hard hat issued from the area store; worker briefed.",
        "engineering": "Hard-hat station installed at the area entrance with a mandatory-PPE sign.",
        "substitution": "Overhead work re-planned to ground level, removing the head-strike exposure.",
        "elimination": "Overhead lifting over the walkway stopped; the task was re-routed.",
    },
    "no_eye_protection": {
        "procedural": "Briefing on eye and face protection at caustic points; permit re-checked.",
        "ppe": "Safety glasses and face shield issued; worker briefed.",
        "engineering": "Face-shield station fitted at the sampling point, with sign and barrier.",
        "substitution": "Sampling moved to a closed sampler so the task no longer needs open handling.",
        "elimination": "Manual sampling at this point discontinued (online analyser in use).",
    },
    "no_gloves": {
        "procedural": "Toolbox talk on glove selection; task permit re-checked.",
        "ppe": "Chemical gloves issued / replaced; worker briefed.",
        "engineering": "Glove dispenser installed at the area entrance.",
        "substitution": "Closed sampler fitted so the valve is no longer handled by hand.",
        "elimination": "Manual valve operation replaced by remote actuation.",
    },
    "floor_liquid": {
        "procedural": "Spill cleaned up; housekeeping round added to the shift checklist.",
        "engineering": "Drip tray fitted under the leaking flange; area barriered until dry.",
        "elimination": "Leaking fitting replaced by maintenance.",
        "substitution": "Hose connection replaced with a dry-break coupling.",
        "ppe": "Interim: slip-resistant overshoes issued until the leak is repaired.",
    },
    "walkway_obstruction": {
        "procedural": "Materials moved to the laydown area; housekeeping check added.",
        "engineering": "Walkway re-marked and a barrier fitted to keep it clear.",
        "elimination": "Redundant equipment removed from the walkway.",
        "substitution": "Temporary hoses re-routed overhead instead of across the walkway.",
        "ppe": "Interim: crew briefed and safety footwear checked until the item is moved.",
    },
    "open_panel": {
        "procedural": "Panel closed and isolation checked; added to the inspection round.",
        "engineering": "Panel cover refitted and guard bolted in place.",
        "elimination": "Redundant panel opening blanked off.",
        "substitution": "Hinged cover replaced with an interlocked cover.",
        "ppe": "Interim: arc-rated gloves required at the panel until the cover is refitted.",
    },
    "floor_opening": {
        "procedural": "Opening barricaded; permit and handover notes re-checked.",
        "engineering": "Grating replaced and secured; toe board fitted.",
        "elimination": "Opening permanently closed with a steel plate.",
        "substitution": "Removable grating replaced with bolted grating.",
        "ppe": "Interim: fall-arrest harness required at the opening until repaired.",
    },
    "surface_corrosion": {
        "procedural": "Corrosion check added to the maintenance inspection round.",
        "engineering": "Corroded section repaired and coated.",
        "elimination": "Corroded redundant bracket removed.",
        "substitution": "Coated grating substituted for the corroded section.",
        "ppe": "Interim: gloves required for handling until the repair is made.",
    },
    "other_condition": {
        "procedural": "Condition reported to maintenance; housekeeping check added.",
        "engineering": "Barrier and signage placed; repair completed by maintenance.",
        "elimination": "Source of the condition removed.",
        "substitution": "Material replaced with a less hazardous alternative.",
        "ppe": "Interim PPE issued until the repair is made.",
    },
}
# v1.7.0: closure texts for the area-profile hazard types (manual categories), one per control used below.
ACTION_TEXT.update(
    {
        "steam_leak": {
            "engineering": "Leaking steam joint isolated and repaired by maintenance; barrier kept until re-tested.",
            "procedural": "Steam leak tagged and added to the shutdown work list; barrier and warning sign placed.",
        },
        "excessive_noise": {
            "engineering": "Silencer fitted to the vacuum-pump exhaust; noise level re-measured below the limit.",
            "ppe": "Hearing protection issued from the area store; crew briefed on the hearing-protection zone.",
        },
        "hot_surface": {
            "engineering": "Insulation and a guard fitted over the hot pipe section.",
            "procedural": "Hot-surface warning signs added; the task was re-planned to avoid contact.",
        },
        "caustic_leak": {
            "engineering": "Leaking flange repaired and a splash guard fitted; spill neutralised and cleaned up.",
            "procedural": "Line isolated and tagged for repair; area barriered and spill cleaned up.",
        },
        "dust_release": {
            "engineering": "Dust-extraction hood repaired and the conveyor skirt rubber replaced.",
            "procedural": "Spillage removed with the vacuum truck; dust check added to the housekeeping round.",
        },
        "work_at_height": {
            "engineering": "Handrail and toe-board reinstated on the platform edge.",
            "procedural": "Work stopped until a permit and a harness anchor point were in place.",
        },
        "confined_space": {
            "procedural": "Entry stopped; permit, gas test and standby person arranged before re-entry.",
            "engineering": "Manway locked closed and a confined-space sign fitted.",
        },
        "electrical_hazard": {
            "engineering": "Damaged cable replaced and the panel cover refitted by an electrician.",
            "procedural": "Equipment isolated, locked out and tagged until the electrician's repair.",
        },
    }
)
PROFILE_CONSEQUENCE = {  # weights for consequence 1..5 (project assumption; at most 4, as in the main history)
    "steam_leak": (0, 5, 50, 45, 0),
    "excessive_noise": (0, 10, 55, 35, 0),
    "hot_surface": (0, 10, 55, 35, 0),
    "caustic_leak": (0, 5, 50, 45, 0),
    "dust_release": (0, 10, 55, 35, 0),
    "work_at_height": (0, 5, 50, 45, 0),
    "confined_space": (0, 5, 50, 45, 0),
    "electrical_hazard": (0, 5, 50, 45, 0),
}
PROFILE_CONTEXT = {  # what was seen, so every synthetic report states its context
    "steam_leak": "Steam plume from a flange on the heater line; area not yet barriered.",
    "excessive_noise": "Pump enclosure door left open; noise clearly above normal.",
    "hot_surface": "Insulation missing on a hot pipe section next to the walkway.",
    "caustic_leak": "Caustic dripping from a valve gland onto the platform.",
    "dust_release": "Dust cloud at the conveyor transfer point; extraction not working.",
    "work_at_height": "Platform handrail removed for maintenance and not reinstated.",
    "confined_space": "Tank manway open with no permit board or standby person.",
    "electrical_hazard": "Damaged cable insulation on a portable pump in a wet area.",
}
CONTROL_DROP = {"engineering": 1, "procedural": 1, "ppe": 0, "elimination": 2}
N_PROFILE_HISTORY = 48  # v1.7.0: extra synthetic reports of the area-profile hazard types (separate random stream)
PIN_SHARE = 0.7  # v1.7.0: share of synthetic reports with a map pin (separate random stream)

N_HISTORY = 210  # v1.5.0: 15 reporting zones (was 150 for 9 zones in v1.4.1)


def _consequence(rng: random.Random, area_code: str, cat: str) -> tuple[int, str]:
    if area_code in CAUSTIC and rng.random() < CAUSTIC_C4.get(cat, 0):
        return 4, C4_CONTEXT[cat]
    c = rng.choices((1, 2, 3, 4, 5), CONSEQUENCE_WEIGHTS[cat])[0]
    return c, C4_CONTEXT.get(cat, "") if c == 4 else ""


def _control(rng: random.Random, cat: str, consequence: int) -> tuple[str, int, str]:
    options = CONTROLS["ppe_finding" if cat in PPE_FINDINGS else "condition"]
    code, _, drop, _generic = rng.choices(options, [o[1] for o in options])[0]
    return code, max(1, consequence - drop), ACTION_TEXT[cat][code]


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
        # v1.7.0 additions use their own random streams, so the v1.4.1/v1.5 history above is unchanged.
        _profile_history(db, random.Random(rng_seed + 1), areas, reporters, supervisor, now)
    _place_pins(db, random.Random(rng_seed + 2))
    db.commit()


def _history(db, rng, areas, reporters, supervisor, times, now) -> None:
    cells = [(a, cat, w) for a in areas if a.code in PROFILE for cat, w in PROFILE[a.code].items()]
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


def _profile_history(db, rng, areas, reporters, supervisor, now) -> None:
    """Reports of the area-profile hazard types (steam leak, noise, …) in every zone, LAB included."""
    for _ in range(N_PROFILE_HISTORY):
        area = rng.choice(areas)
        # The area's two main profile hazards: repeats in one area are what raise likelihood on a real site.
        cats = [c for c in area_profiles.get(area.code)["typical_hazards"] if c in PROFILE_CONSEQUENCE][:2]
        if not cats:
            continue
        cat = rng.choice(cats)
        t = now - timedelta(days=rng.uniform(0, 180), hours=rng.uniform(0, 12))
        h = services.create_draft(db, rng.choice(reporters), area, None, None, at=t)
        cons = rng.choices((1, 2, 3, 4, 5), PROFILE_CONSEQUENCE[cat])[0]
        control = rng.choice(sorted(ACTION_TEXT[cat]))
        residual = max(1, cons - CONTROL_DROP[control])
        services.confirm(
            db,
            h,
            h.reporter,
            services.Confirmation(
                category_code=cat,
                consequence=cons,
                description=f"Synthetic report: {taxonomy.get(cat).name.lower()}. {PROFILE_CONTEXT[cat]}",
            ),
            at=t,
        )
        if rng.random() < min(0.95, 0.3 + (now - t).days / 60):
            close_at = min(now, t + timedelta(days=rng.uniform(0.2, 1.5) * max(1, (h.due_at - t).days)))
            services.close(
                db,
                h,
                area.owner,
                ACTION_TEXT[cat][control],
                at=close_at,
                control_type=control,
                residual_consequence=residual,
            )
            verify_at = close_at + timedelta(days=rng.uniform(0.5, 3))
            if verify_at < now:
                services.verify(db, h, supervisor, "Checked on site (synthetic)", at=verify_at)


def _place_pins(db, rng) -> None:
    """Give most synthetic reports a map pin at a random point inside their zone (reporters tap the exact spot)."""
    from .site_layout import REPORTING

    for h in db.scalars(select(Hazard).where(Hazard.x.is_(None)).order_by(Hazard.id)):
        z = REPORTING.get(h.area.code)
        if z is None or rng.random() >= PIN_SHARE:
            continue
        for _ in range(50):
            x, y = rng.randint(z.x + 8, z.x + z.w - 8), rng.randint(z.y + 8, z.y + z.h - 8)
            if z.contains(x, y):
                h.x, h.y = x, y
                break


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
