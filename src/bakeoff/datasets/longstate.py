"""Long-State sweep: a JSON array of templated support tickets with one needle, Gold by
construction.

Every State is padded with filler tickets to a target token count (``tokens.count_tokens`` of
the compact JSON) and holds exactly one needle ticket at a controlled relative position. The
Questions depend only on the needle: which team handles it, and whether any ticket mentions a
data breach (filler never does). Everything is deterministic from the seed.
"""

from __future__ import annotations

import random
from datetime import date
from typing import Any

from bakeoff.datasets.case import Case, Reference
from bakeoff.datasets.family import FamilyManifest
from bakeoff.datasets.tokens import count_tokens, state_text
from bakeoff.systemone import ChoiceQuestion, Json, NoulQuestion

TARGETS: dict[str, int] = {
    "longstate-8k": 8_000,
    "longstate-16k": 16_000,
    "longstate-24k": 24_000,
    "longstate-32k": 32_000,
    "longstate-64k": 64_000,
    "longstate-128k": 128_000,
    "longstate-256k": 256_000,
}
POSITIONS = (0.1, 0.5, 0.9)
PER_POSITION = 2
SLACK = 0.005  # accepted distance from the target; the test tolerance is 5%
MAX_FIT_ROUNDS = 4
BREACH_PHRASE = "data breach"

TEAMS: dict[str, Json | None] = {
    "billing": "Charges, invoices, refunds, payment methods, subscription renewals",
    "technical": "Bugs, errors, outages, login failures, device and integration problems",
    "sales": "Pricing, plans, upgrades, quotes, trials, pre-purchase questions",
    "shipping": "Delivery status, lost or damaged packages, address changes, return logistics",
    "security": "Account compromise, suspicious logins, data breach notifications",
}
FILLER_TEAMS = ("billing", "technical", "sales", "shipping")
BREACH_QUESTION = "Does any ticket in this list mention a data breach?"

FIRST_NAMES = [
    "Priya",
    "Marcus",
    "Elena",
    "Tomas",
    "Aisha",
    "Jonas",
    "Mei",
    "Diego",
    "Hannah",
    "Kwame",
    "Sofia",
    "Liam",
    "Noor",
    "Ravi",
    "Ingrid",
    "Mateo",
    "Yuki",
    "Omar",
    "Chloe",
    "Sven",
]
LAST_NAMES = [
    "Raman",
    "Okafor",
    "Novak",
    "Lindqvist",
    "Haddad",
    "Petrov",
    "Tanaka",
    "Alvarez",
    "Becker",
    "Mensah",
    "Rossi",
    "Murphy",
    "Khan",
    "Iyer",
    "Larsen",
    "Castillo",
    "Sato",
    "Farah",
    "Dubois",
    "Berg",
]
PRODUCTS = [
    "Nimbus Router X2",
    "Atlas Hub",
    "Meridian Sensor Kit",
    "Orbit Camera",
    "Lumen Desk Lamp",
    "Vega Smart Plug",
    "Cirrus Thermostat",
    "Harbor Doorbell",
    "Strato Mesh Node",
    "Pico Tracker",
]
PLANS = ["Starter", "Team", "Business"]
CITIES = [
    "Austin",
    "Leeds",
    "Rotterdam",
    "Lyon",
    "Osaka",
    "Denver",
    "Porto",
    "Tallinn",
    "Calgary",
    "Adelaide",
    "Cork",
    "Malmo",
]
CLOSINGS = [
    "Thanks in advance.",
    "Let me know if you need more details.",
    "I have attached a screenshot.",
    "My account email is on file.",
    "Please reply as soon as you can.",
    "This is the second time I am writing about this.",
    "",
]

FILLER_TEMPLATES: dict[str, list[tuple[str, str]]] = {
    "billing": [
        (
            "Duplicate charge on my card",
            (
                "My statement shows two charges of {amount} for order {order} on {date}. I only "
                "placed "
                "one order and would like the extra charge refunded."
            ),
        ),
        (
            "Invoice {invoice} is wrong",
            (
                "Invoice {invoice} lists {n} seats but we only have {m}. Can you correct it and "
                "send a "
                "new copy to our accounts team?"
            ),
        ),
        (
            "Cancel auto-renewal",
            (
                "Please turn off automatic renewal on my {plan} plan before it renews on {date}. "
                "I want "
                "to decide manually each year."
            ),
        ),
        (
            "Refund still pending",
            (
                "I returned my {product} {days} days ago and the refund of {amount} has not "
                "appeared on "
                "my card yet."
            ),
        ),
    ],
    "technical": [
        (
            "{product} will not stay connected",
            (
                "My {product} drops off the network every evening and the app shows error "
                "E{code}. I "
                "have already restarted it twice."
            ),
        ),
        (
            "Login loop on the web app",
            (
                "Since {date} the web app sends me back to the login page right after I sign in. "
                "Clearing cookies did not help."
            ),
        ),
        (
            "API returns 500 errors",
            (
                "Calls to the /v2/devices endpoint started returning 500 errors around {time} "
                "today. "
                "Our integration retries but nothing goes through."
            ),
        ),
        (
            "Firmware {version} broke scheduling",
            (
                "After updating my {product} to firmware {version} the schedules I set no longer "
                "run, "
                "and the app offers no way to roll back."
            ),
        ),
    ],
    "sales": [
        (
            "Quote for {n} units",
            (
                "We are planning to deploy {n} {product} units across {m} sites and need a volume "
                "quote "
                "and lead times."
            ),
        ),
        (
            "Which plan includes SSO?",
            (
                "Does the {plan} plan include single sign-on and audit logs, or is that only on "
                "the "
                "enterprise tier? We are comparing options for next quarter."
            ),
        ),
        (
            "Extend our trial",
            (
                "Our team's trial ends on {date} and we need two more weeks to finish the "
                "evaluation "
                "before purchasing."
            ),
        ),
        (
            "Education discount",
            (
                "I teach at a community college in {city} and would like to know whether you offer "
                "academic pricing for the {product}."
            ),
        ),
    ],
    "shipping": [
        (
            "Order {order} not delivered",
            (
                "Tracking for order {order} says delivered on {date} but nothing arrived at my "
                "address "
                "in {city}. Could you check with the carrier?"
            ),
        ),
        (
            "Package arrived damaged",
            (
                "The box for order {order} arrived crushed and the {product} inside has a cracked "
                "housing. I would like a replacement."
            ),
        ),
        (
            "Change shipping address",
            (
                "Order {order} has not shipped yet. Please change the delivery address to our new "
                "office in {city}."
            ),
        ),
        (
            "Where is my replacement?",
            (
                "The replacement {product} promised {days} days ago still shows as processing. "
                "When "
                "will it ship?"
            ),
        ),
    ],
}

NEEDLE_TEMPLATES: dict[str, tuple[str, str]] = {
    "billing": (
        "Charged twice for invoice {invoice}",
        (
            "I was charged twice for invoice {invoice} on {date}: two identical payments of "
            "{amount}. Please refund the duplicate charge to my card and confirm when it is done."
        ),
    ),
    "technical": (
        "{product} reboots constantly after update",
        (
            "Since the {version} firmware update my {product} reboots every few minutes and error "
            "E{code} shows in the app. Nothing in the troubleshooting guide fixes it."
        ),
    ),
    "sales": (
        "Volume quote before our budget meeting",
        (
            "We are evaluating the {product} for {n} offices and need a volume quote plus the "
            "{plan} versus enterprise plan comparison before our budget meeting on {date}."
        ),
    ),
    "shipping": (
        "Order {order} marked delivered but missing",
        (
            "Order {order} shows delivered on {date} but nothing arrived at my address in {city}. "
            "The carrier tracking ends at a facility hundreds of miles away."
        ),
    ),
    "security": (
        "Was my account affected by the data breach?",
        (
            "I received an email saying my personal data was exposed in your recent data breach. "
            "I want to know which of my details were affected and whether I must reset my password."
        ),
    ),
}


def build_longstate_cases(
    target_tokens: int,
    *,
    family: str,
    positions: tuple[float, ...] = POSITIONS,
    per_position: int = PER_POSITION,
    seed: int = 0,
) -> list[Case]:
    """``per_position`` Cases per position: even ones mention a breach (security), odd ones rotate
    through the other teams so no two Cases at one position share a team."""
    rng = random.Random(seed)
    cases = []
    for p_index, position in enumerate(positions):
        for k in range(per_position):
            if k % 2 == 0:
                team = "security"
            else:
                team = FILLER_TEAMS[(p_index + k // 2) % len(FILLER_TEAMS)]
            cases.append(_build_case(rng, family, target_tokens, position, k, team))
    return cases


def manifest(family: str, created: date, *, seed: int = 0) -> FamilyManifest:
    return FamilyManifest(
        name=family,
        track="text",
        source=f"bakeoff.datasets.longstate (programmatic, seed {seed})",
        license="synthetic; generated by this project, no third-party content",
        reference_kind="gold",
        generated_by="bakeoff.datasets.longstate.build_longstate_cases",
        created=created,
        notes=f"Target {TARGETS.get(family, '?')} o200k_base tokens of compact JSON; one needle "
        f"ticket per Case at relative positions {POSITIONS}.",
    )


def _build_case(
    rng: random.Random, family: str, target: int, position: float, k: int, team: str
) -> Case:
    ids: set[str] = set()
    needle = _needle_ticket(rng, ids, team)
    state, index, total = _pad(rng, ids, needle, position, target)
    needle_id = needle["id"]
    return Case(
        id=f"{family}-p{round(position * 100):02d}-{k}",
        family=family,
        track="text",
        state=state,
        questions={
            "team": ChoiceQuestion(
                instructions=f"Which team should handle ticket {needle_id}?", criteria=dict(TEAMS)
            ),
            "mentions_breach": NoulQuestion(instructions=BREACH_QUESTION),
        },
        reference={
            "team": Reference(kind="gold", choice=team, source="by construction"),
            "mentions_breach": Reference(
                kind="gold", noul=team == "security", source="by construction"
            ),
        },
        meta={
            "target_tokens": target,
            "position": position,
            "needle_id": needle_id,
            "needle_index": index,
            "ticket_count": len(state),
            "mentions_breach": team == "security",
            "team": team,
        },
        approx_tokens=total,
    )


def _pad(
    rng: random.Random, ids: set[str], needle: dict[str, Any], position: float, target: int
) -> tuple[list[dict[str, Any]], int, int]:
    """Filler tickets around the needle until the compact JSON measures ``target`` tokens.

    Per-ticket counts overestimate the whole (``},{"`` merges at ticket boundaries), so the sum
    is corrected by the measured ratio and the state re-measured, a few rounds at most.
    """
    fillers: list[dict[str, Any]] = []
    estimate = 2 + _ticket_tokens(needle)
    ratio = 1.0
    for _ in range(MAX_FIT_ROUNDS):
        while estimate * ratio < target:
            ticket = _filler_ticket(rng, ids)
            fillers.append(ticket)
            estimate += _ticket_tokens(ticket)
        index = round(position * len(fillers))
        state = fillers[:index] + [needle] + fillers[index:]
        total = count_tokens(state_text(state))
        if abs(total - target) <= target * SLACK or not fillers:
            return state, index, total
        ratio = total / estimate
        while estimate * ratio > target and fillers:
            estimate -= _ticket_tokens(fillers.pop())
    index = round(position * len(fillers))
    state = fillers[:index] + [needle] + fillers[index:]
    return state, index, count_tokens(state_text(state))


def _ticket_tokens(ticket: dict[str, Any]) -> int:
    return count_tokens(state_text(ticket)) + 1  # plus the separating comma


def _needle_ticket(rng: random.Random, ids: set[str], team: str) -> dict[str, Any]:
    subject, body = NEEDLE_TEMPLATES[team]
    return _ticket(rng, ids, subject, body, closing="")


def _filler_ticket(rng: random.Random, ids: set[str]) -> dict[str, Any]:
    team = rng.choice(FILLER_TEAMS)
    subject, body = rng.choice(FILLER_TEMPLATES[team])
    return _ticket(rng, ids, subject, body, closing=rng.choice(CLOSINGS))


def _ticket(
    rng: random.Random, ids: set[str], subject: str, body: str, *, closing: str
) -> dict[str, Any]:
    values = _values(rng)
    text = body.format_map(values)
    if closing:
        text = f"{text} {closing}"
    return {
        "id": _new_id(rng, ids),
        "opened": values["date"],
        "customer": f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
        "subject": subject.format_map(values),
        "body": text,
    }


def _values(rng: random.Random) -> dict[str, Any]:
    return {
        "amount": f"{rng.randint(10, 900)}.{rng.randint(0, 99):02d} USD",
        "order": f"#{rng.randint(100_000, 999_999)}",
        "invoice": f"INV-{rng.randint(1000, 9999)}",
        "date": f"2026-{rng.randint(1, 9):02d}-{rng.randint(1, 28):02d}",
        "days": rng.randint(3, 30),
        "n": rng.randint(12, 400),
        "m": rng.randint(2, 11),
        "product": rng.choice(PRODUCTS),
        "plan": rng.choice(PLANS),
        "code": rng.randint(100, 999),
        "time": f"{rng.randint(0, 23):02d}:{rng.choice(('00', '15', '30', '45'))}",
        "version": f"{rng.randint(2, 5)}.{rng.randint(0, 9)}.{rng.randint(0, 9)}",
        "city": rng.choice(CITIES),
    }


def _new_id(rng: random.Random, ids: set[str]) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        candidate = "TK-" + "".join(rng.choice(alphabet) for _ in range(6))
        if candidate not in ids:
            ids.add(candidate)
            return candidate
