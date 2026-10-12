"""Run Providers over Families: one Run per (Provider, Family), resumable and budget-capped."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn

from bakeoff import budget
from bakeoff.budget import BudgetGuard
from bakeoff.config import Settings
from bakeoff.datasets.case import Case, family_dir, load_family
from bakeoff.metrics import ResultRow, options_count, score_answer
from bakeoff.providers import make_provider
from bakeoff.providers.base import Provider, ProviderResult
from bakeoff.store import Store, now_iso
from bakeoff.systemone import Answer, NonAnswer, SystemOneRequest, SystemOneResponse, Usage

GLOBAL_CONCURRENCY = 32


class RunSummary(BaseModel):
    run_ids: list[str]
    cases_done: int  # (Case, rep) evaluations completed by this invocation
    non_answers: int  # Question rows that are Non-answers, this invocation
    cost_usd: float  # known spend, this invocation
    unknown_costs: int = 0  # requests whose cost is unknown, this invocation
    stopped_for_budget: bool
    rate_limited: list[str] = []  # Providers that stopped after a rate-limited request


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def run_id_for(provider_id: str, family: str) -> str:
    return f"{slug(provider_id)}__{family}"


def default_data_root(settings: Settings) -> Path:
    """``<data_dir>/smoke`` when it exists, else ``<data_dir>``."""
    smoke = settings.data_dir / "smoke"
    return smoke if smoke.is_dir() else settings.data_dir


def secrets_of(settings: Settings) -> list[str]:
    """The credential values loaded, so persisted captures can be scrubbed of them."""
    values = [
        settings.typesafe_api_key,
        settings.openai_api_key,
        settings.cloudflare_auth_token,
        settings.liquid_api_key,
        settings.foundry_access_token,
    ]
    return [value for value in values if value]


def is_over_limit(case: Case, provider: Provider) -> bool:
    return (
        case.approx_tokens is not None
        and provider.max_input_tokens is not None
        and case.approx_tokens > provider.max_input_tokens
    )


def build_rows(
    run_id: str, case: Case, rep: int, provider: Provider, result: ProviderResult
) -> list[ResultRow]:
    """Score every Question of one Case evaluation. Missing answers become Non-answers."""
    response = result.response
    usage = response.usage if response is not None else Usage()
    created_at = now_iso()
    over_limit = is_over_limit(case, provider)
    rows = []
    for question_id, question in case.questions.items():
        answer = _answer_for(question_id, result)
        scored = score_answer(question, case.reference[question_id], answer)
        rows.append(
            ResultRow(
                run_id=run_id,
                case_id=case.id,
                question_id=question_id,
                rep=rep,
                qtype=question.type,
                n_options=options_count(question),
                reference_json=case.reference[question_id].model_dump(mode="json"),
                answer_json=answer.model_dump(mode="json"),
                non_answer_cause=scored.non_answer_cause,
                correct=scored.correct,
                prob_ref=scored.prob_ref,
                prob_pred=scored.prob_pred,
                confidence=scored.confidence,
                latency_s=result.latency_s,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                reasoning_tokens=usage.reasoning_tokens,
                cached_tokens=usage.cached_tokens,
                cost_usd=result.cost_usd,
                http_status=result.http_status,
                attempts=result.attempts,
                over_limit=over_limit,
                created_at=created_at,
            )
        )
    return rows


def _answer_for(question_id: str, result: ProviderResult) -> Answer:
    if result.response is None:
        return NonAnswer(cause="error", detail=result.error or "no response")
    answer = result.response.answers.get(question_id)
    if answer is None:
        return NonAnswer(cause="invalid_output", detail=f"no answer for question {question_id!r}")
    return answer


@dataclass
class _Throttle:
    """Shared by every Run of one Provider: set once a request came back rate limited."""

    rate_limited: bool = False


@dataclass
class _Plan:
    """One Run: a Provider over the Cases of one Family, minus what the store already holds."""

    provider: Provider
    semaphore: asyncio.Semaphore
    throttle: _Throttle
    family: str
    family_dir: Path
    run_id: str
    cases: list[Case]
    reps: int
    pending: list[tuple[Case, int]]  # (Case, rep) pairs not yet in the store


@dataclass
class _Tally:
    cases_done: int = 0
    non_answers: int = 0
    by_run: dict[str, tuple[int, int]] = field(default_factory=dict)  # run_id -> (cases, non)


@dataclass
class _Context:
    store: Store
    guard: BudgetGuard
    progress: Progress
    tally: _Tally
    global_semaphore: asyncio.Semaphore


def run(
    providers: list[str],
    families: list[str],
    settings: Settings,
    *,
    limit: int | None = None,
    reps: int = 1,
    runs_dir: Path | None = None,
    data_root: Path | None = None,
) -> RunSummary:
    """Synchronous entry point; see ``run_async`` for callers that already own an event loop."""
    return asyncio.run(
        run_async(
            providers,
            families,
            settings,
            limit=limit,
            reps=reps,
            runs_dir=runs_dir,
            data_root=data_root,
        )
    )


async def run_async(
    providers: list[str],
    families: list[str],
    settings: Settings,
    *,
    limit: int | None = None,
    reps: int = 1,
    runs_dir: Path | None = None,
    data_root: Path | None = None,
) -> RunSummary:
    runs_dir = runs_dir if runs_dir is not None else settings.runs_dir
    data_root = data_root if data_root is not None else default_data_root(settings)
    console = Console(stderr=True)
    store = Store(runs_dir, redact=secrets_of(settings))
    built: list[Provider] = []
    try:
        for spec in providers:
            built.append(make_provider(spec, settings))
        guard = BudgetGuard(settings.budget_usd, store.total_cost_usd())
        plans = _plan(_unique(built), families, data_root, store, limit=limit, reps=reps)
        tally = _Tally()
        progress = Progress(
            TextColumn("{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
        )
        context = _Context(store, guard, progress, tally, asyncio.Semaphore(GLOBAL_CONCURRENCY))
        with progress:
            await _execute(plans, context)
        for plan in plans:
            store.finish_run(plan.run_id)
        _print_summary(console, plans, context)
    finally:
        for provider in built:
            await provider.aclose()
        store.close()
    return RunSummary(
        run_ids=[plan.run_id for plan in plans],
        cases_done=tally.cases_done,
        non_answers=tally.non_answers,
        cost_usd=guard.session_usd,
        unknown_costs=guard.unknown_costs,
        stopped_for_budget=guard.stopped,
        rate_limited=_rate_limited_ids(plans),
    )


def _unique(providers: list[Provider]) -> list[Provider]:
    """One Provider per id: specs that normalize to the same id would plan the same Run twice."""
    by_id: dict[str, Provider] = {}
    for provider in providers:
        by_id.setdefault(provider.id, provider)
    return list(by_id.values())


def _plan(
    providers: list[Provider],
    families: list[str],
    data_root: Path,
    store: Store,
    *,
    limit: int | None,
    reps: int,
) -> list[_Plan]:
    semaphores = {provider.id: asyncio.Semaphore(provider.concurrency) for provider in providers}
    throttles = {provider.id: _Throttle() for provider in providers}
    cases_by_family = {family: load_family(data_root, family)[:limit] for family in families}
    plans = []
    for provider in providers:
        for family, cases in cases_by_family.items():
            run_id = run_id_for(provider.id, family)
            store.begin_run(run_id, provider.id, family, _config(provider, limit, reps))
            done = store.completed(run_id)
            pending = [
                (case, rep) for case in cases for rep in range(reps) if (case.id, rep) not in done
            ]
            plans.append(
                _Plan(
                    provider=provider,
                    semaphore=semaphores[provider.id],
                    throttle=throttles[provider.id],
                    family=family,
                    family_dir=family_dir(data_root, family),
                    run_id=run_id,
                    cases=cases,
                    reps=reps,
                    pending=pending,
                )
            )
    return plans


def _config(provider: Provider, limit: int | None, reps: int) -> dict[str, object]:
    return {
        "provider_id": provider.id,
        "model": provider.model,
        "limit": limit,
        "reps": reps,
        "max_input_tokens": provider.max_input_tokens,
        "concurrency": provider.concurrency,
        "price_key": provider.price_key,
    }


async def _execute(plans: list[_Plan], context: _Context) -> None:
    """Evaluate every pending (Case, rep). A failure in one evaluation surfaces only after the
    others have finished and recorded their results, since their requests were already sent."""
    evaluations = []
    for plan in plans:
        total = len(plan.cases) * plan.reps
        task = context.progress.add_task(
            plan.run_id, total=total, completed=total - len(plan.pending)
        )
        for case, rep in plan.pending:
            evaluations.append(_evaluate(plan, case, rep, task, context))
    outcomes = await asyncio.gather(*evaluations, return_exceptions=True)
    failures = [outcome for outcome in outcomes if isinstance(outcome, BaseException)]
    if failures:
        raise failures[0]


async def _evaluate(plan: _Plan, case: Case, rep: int, task: int, context: _Context) -> None:
    estimate = _estimate(plan.provider, case)
    # The Provider's own slot first, so a slow Provider's queue never fills the global slots.
    async with plan.semaphore, context.global_semaphore:
        if plan.throttle.rate_limited or not context.guard.reserve(estimate):
            return
        request, result = await _ask(plan, case)
    context.guard.settle(estimate, result.cost_usd)
    if _is_rate_limited(result):
        plan.throttle.rate_limited = True
    rows = build_rows(plan.run_id, case, rep, plan.provider, result)
    context.store.write_raw(plan.run_id, _raw_record(plan, case, rep, request, result))
    context.store.write_rows(rows)
    _count(context.tally, plan.run_id, rows)
    context.progress.advance(task)


def _estimate(provider: Provider, case: Case) -> float:
    """The cost reserved before a request is sent: the Case's token count at the input rate,
    which is the whole bill for a decision API. A Provider that also pays for output (the Own
    build) defines ``estimate_cost_usd(approx_tokens)`` and is asked instead."""
    estimator = getattr(provider, "estimate_cost_usd", None)
    if estimator is not None:
        return estimator(case.approx_tokens)
    return budget.estimate_cost_usd(provider.price_key, case.approx_tokens)


async def _ask(plan: _Plan, case: Case) -> tuple[SystemOneRequest | None, ProviderResult]:
    try:
        request = case.to_request(plan.provider.model, plan.family_dir)
    except Exception as exc:  # noqa: BLE001 - a Case that cannot be sent is a row, not a crash
        return None, _unsendable(plan.provider, case, exc)
    result = await plan.provider.evaluate(request)
    if result.cost_usd is None and _never_sent(result):
        result.cost_usd = 0.0
    return request, result


def _unsendable(provider: Provider, case: Case, exc: Exception) -> ProviderResult:
    """Error Non-answers for a Case whose request could not be built (a missing image file)."""
    detail = f"{type(exc).__name__}: {exc}"
    answers = {qid: NonAnswer(cause="error", detail=detail) for qid in case.questions}
    return ProviderResult(
        provider_id=provider.id,
        response=SystemOneResponse(model=provider.model, answers=answers),
        latency_s=0.0,
        error=detail,
        cost_usd=0.0,
    )


def _never_sent(result: ProviderResult) -> bool:
    """True when the Provider declined the request without a call (a text-only Provider given
    an image): such a request cost nothing."""
    answers = result.response.answers.values() if result.response is not None else []
    return bool(answers) and all(
        isinstance(answer, NonAnswer) and answer.cause == "unsupported_modality"
        for answer in answers
    )


def _is_rate_limited(result: ProviderResult) -> bool:
    answers = result.response.answers.values() if result.response is not None else []
    return any(isinstance(a, NonAnswer) and a.cause == "rate_limited" for a in answers)


def _rate_limited_ids(plans: list[_Plan]) -> list[str]:
    ids = [plan.provider.id for plan in plans if plan.throttle.rate_limited]
    return list(dict.fromkeys(ids))


def _raw_record(
    plan: _Plan, case: Case, rep: int, request: SystemOneRequest | None, result: ProviderResult
) -> dict[str, object]:
    request_raw = result.request_raw
    if request_raw is None and request is not None:
        request_raw = request.model_dump(mode="json")
    return {
        "run_id": plan.run_id,
        "provider_id": plan.provider.id,
        "case_id": case.id,
        "rep": rep,
        "created_at": now_iso(),
        "http_status": result.http_status,
        "latency_s": result.latency_s,
        "attempts": result.attempts,
        "error": result.error,
        "cost_usd": result.cost_usd,
        "request_raw": request_raw,
        "response_raw": result.response_raw,
    }


def _count(tally: _Tally, run_id: str, rows: list[ResultRow]) -> None:
    non_answers = sum(row.non_answer_cause is not None for row in rows)
    tally.cases_done += 1
    tally.non_answers += non_answers
    cases, missing = tally.by_run.get(run_id, (0, 0))
    tally.by_run[run_id] = (cases + 1, missing + non_answers)


def _print_summary(console: Console, plans: list[_Plan], context: _Context) -> None:
    for plan in plans:
        cases, non_answers = context.tally.by_run.get(plan.run_id, (0, 0))
        skipped = len(plan.pending) - cases
        line = f"{plan.run_id}: {cases} cases, {non_answers} non-answers"
        if skipped:
            line += f", {skipped} not attempted"
        if plan.throttle.rate_limited:
            line += "; stopped: rate limited"
        console.print(line)
    guard = context.guard
    line = f"spent ${guard.session_usd:.4f} this run (${guard.spent_usd:.4f} total"
    line += f" of ${guard.limit_usd:.2f} budget)"
    if guard.unknown_costs:
        line += (
            f", {guard.unknown_costs} requests with unknown cost"
            f" (estimated ${guard.estimated_usd:.4f})"
        )
    if guard.stopped:
        line += "; stopped for budget"
    console.print(line)
