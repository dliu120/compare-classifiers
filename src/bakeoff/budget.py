"""BudgetGuard: the spending cap the runner consults before every request."""

from __future__ import annotations

from bakeoff import pricing
from bakeoff.systemone import Usage


class BudgetGuard:
    """Tracks spend against a cap in USD.

    ``already_spent`` seeds the counter with what earlier invocations recorded, so a resumed
    bakeoff stays under the same cap. A request is admitted by ``reserve`` with an estimate of
    its cost, which counts toward the cap while the request is in flight, so concurrent
    requests cannot all slip under the cap together. ``settle`` replaces the estimate with the
    real cost; a request whose cost stays unknown keeps its estimate (never zero) and is
    counted in ``unknown_costs`` so reports can say how much spend is unpriced.
    """

    def __init__(self, limit_usd: float, already_spent: float = 0.0) -> None:
        self.limit_usd = limit_usd
        self.spent_usd = already_spent  # known spend, every invocation
        self.session_usd = 0.0  # known spend by this process only
        self.estimated_usd = 0.0  # estimates standing in for unknown costs
        self.reserved_usd = 0.0  # estimates of requests in flight
        self.unknown_costs = 0
        self.stopped = False  # set the first time ``reserve`` refuses a request

    @property
    def committed_usd(self) -> float:
        return self.spent_usd + self.estimated_usd + self.reserved_usd

    def reserve(self, estimate_usd: float) -> bool:
        """Admit a request expected to cost ``estimate_usd``; False once the cap is reached."""
        if self.committed_usd >= self.limit_usd:
            self.stopped = True
            return False
        self.reserved_usd += estimate_usd
        return True

    def settle(self, estimate_usd: float, cost_usd: float | None) -> None:
        """Release the reservation and record what the request cost."""
        self.reserved_usd -= estimate_usd
        if cost_usd is None:
            self.unknown_costs += 1
            self.estimated_usd += estimate_usd
            return
        self.spent_usd += cost_usd
        self.session_usd += cost_usd


def estimate_cost_usd(
    price_key: str | None, input_tokens: int | None, output_tokens: int = 0, calls: int = 1
) -> float:
    """What a request may cost before it is sent, for ``calls`` calls of ``input_tokens`` in
    and up to ``output_tokens`` out at the listed price. Zero when the price is unknown."""
    usage = Usage(input_tokens=input_tokens or 0, output_tokens=output_tokens)
    cost = pricing.cost_usd(price_key, usage)
    return calls * cost if cost is not None else 0.0
