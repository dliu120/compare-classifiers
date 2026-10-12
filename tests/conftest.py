from __future__ import annotations

import pytest

from bakeoff.config import Settings
from bakeoff.systemone import ChoiceQuestion, NoulQuestion, ScoreQuestion, SystemOneRequest

STATE = (
    "Hi, I've been trying to connect my Stripe account for 3 days and the integration keeps "
    "failing. I'm losing sales. Please help ASAP."
)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        typesafe_api_key="ts-test",
        openai_api_key="sk-test",
        cloudflare_account_id="acct",
        cloudflare_auth_token="cf-test",
        liquid_api_key="liquid_test",
        aiproxy_base_url="http://127.0.0.1:17688/v1",
    )


@pytest.fixture
def sample_request() -> SystemOneRequest:
    return SystemOneRequest(
        model="test",
        state=STATE,
        questions={
            "department": ChoiceQuestion(
                instructions="Which team should handle this?",
                criteria={
                    "billing": "Payment or subscription issues",
                    "technical": "Bugs or integration problems",
                    "sales": "Pricing or account questions",
                },
            ),
            "frustration": ScoreQuestion(
                instructions="How frustrated does the customer appear?",
                criteria=["Calm, just stating facts", "Frustrated but civil", "Very angry"],
            ),
            "is_urgent": NoulQuestion(instructions="Does this message convey urgency?"),
        },
    )


TINY_PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


@pytest.fixture
def image_request(sample_request: SystemOneRequest) -> SystemOneRequest:
    return sample_request.model_copy(update={"images": [TINY_PNG]})
