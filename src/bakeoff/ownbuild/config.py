"""One Variant of the Own build: Route, model, reasoning effort, output cap, input cap, mode and
sample count, parsed from a spec and printed back as the normalized spec that is its id."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bakeoff import pricing
from bakeoff.providers import parse_spec

Route = Literal["openai", "copilot"]
Effort = Literal["none", "low", "medium", "high", "xhigh", "max"]
Mode = Literal["probabilities", "discrete", "logprobs"]

FAMILY = "ownbuild"
DEFAULT_MODEL = "gpt-6-luna"
COPILOT_PREFIX = "github-copilot/"
QUERY_KEYS = ("effort", "cap", "max_in", "mode", "samples")  # the order a spec prints them in


class OwnBuildConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    route: Route
    model: str = DEFAULT_MODEL
    effort: Effort | None = None  # None omits the reasoning field
    cap: int | None = Field(default=None, ge=1)  # max_output_tokens; None omits it
    max_in: int | None = Field(default=None, ge=1)  # input token cap applied to the State
    mode: Mode = "probabilities"
    samples: int = Field(default=1, ge=1)  # k >= 2 averages k independent calls

    @model_validator(mode="after")
    def _logprobs_need_openai_without_reasoning(self) -> OwnBuildConfig:
        if self.mode == "logprobs" and (self.route != "openai" or self.effort != "none"):
            raise ValueError("mode=logprobs is only valid on route openai with effort none")
        return self

    @property
    def discrete(self) -> bool:
        return self.mode != "probabilities"

    @property
    def spec(self) -> str:
        """Normalized spec: every set field as a query key, in ``QUERY_KEYS`` order."""
        pairs = [(key, getattr(self, key)) for key in QUERY_KEYS]
        query = "&".join(f"{key}={value}" for key, value in pairs if value is not None)
        return f"{FAMILY}/{self.route}/{self.model}?{query}"

    @classmethod
    def from_spec(cls, spec: str) -> tuple[OwnBuildConfig, dict[str, str]]:
        """Parse ``ownbuild/<route>/<model>?...``; also returns the query keys it did not use."""
        family, path, query = parse_spec(spec)
        if family != FAMILY or not path:
            raise ValueError(f"expected {FAMILY}/<route>/<model>[?...], got {spec!r}")
        fields: dict[str, Any] = {"route": path[0]}
        if len(path) > 1:
            fields["model"] = "/".join(path[1:])
        for key in QUERY_KEYS:
            value = query.pop(key, "")
            if value != "":
                fields[key] = value
        return cls(**fields), query


def wire_model_id(config: OwnBuildConfig) -> str:
    """The model id on the wire: aiproxy wants the ``github-copilot/`` prefix, OpenAI the bare
    id."""
    if config.route == "copilot" and not config.model.startswith(COPILOT_PREFIX):
        return COPILOT_PREFIX + config.model
    return config.model


def price_key_for(model: str) -> str | None:
    """The pricing key of a model id, or None when ``bakeoff.pricing`` does not list it: a model
    is never billed at another model's rate. Both Routes carry the same list price."""
    key = model.removeprefix(COPILOT_PREFIX)
    return key if key in pricing.PRICES else None
