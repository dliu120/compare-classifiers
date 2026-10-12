"""``bakeoff`` command line: probe, run, report, serve, gen smoke."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from bakeoff import runner
from bakeoff.config import Settings, load_settings
from bakeoff.providers import make_provider, parse_spec
from bakeoff.providers.base import Provider, ProviderResult
from bakeoff.report import build_report, write_pareto_svg
from bakeoff.systemone import (
    Answer,
    ChoiceAnswer,
    ChoiceQuestion,
    NonAnswer,
    NoulAnswer,
    NoulQuestion,
    ScoreAnswer,
    ScoreQuestion,
    SystemOneRequest,
)

app = typer.Typer(name="bakeoff", help="Decision API bakeoff.", no_args_is_help=True)
gen_app = typer.Typer(help="Generate Families.", no_args_is_help=True)
app.add_typer(gen_app, name="gen")

DEFAULT_PROBE_SPECS = [
    "jev",
    "cloudflare/clef-flash",
    "liquid/d1",
    "openai-decisions",
    "foundry",
    "ownbuild/openai/gpt-6-luna?effort=none",  # the reference Route (docs/adr/0002)
    "ownbuild/copilot/gpt-6-luna?effort=none",
]
KEYED_FAMILIES = {"jev", "cloudflare", "liquid", "openai-decisions", "foundry"}
DEFAULT_SERVE_SPEC = "ownbuild/openai/gpt-6-luna"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}

# The Stripe sample from tests/conftest.py, copied rather than imported.
PROBE_STATE = (
    "Hi, I've been trying to connect my Stripe account for 3 days and the integration keeps "
    "failing. I'm losing sales. Please help ASAP."
)


def probe_request(model: str) -> SystemOneRequest:
    return SystemOneRequest(
        model=model,
        state=PROBE_STATE,
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


ProviderOption = Annotated[
    list[str] | None, typer.Option("--provider", "-p", help="Provider spec; repeatable.")
]


@app.command()
def probe(provider: ProviderOption = None) -> None:
    """Send the Stripe sample request to every configured Provider and tabulate the replies."""
    settings = load_settings()
    specs = list(dict.fromkeys([*DEFAULT_PROBE_SPECS, *(provider or [])]))
    asyncio.run(_probe(specs, settings))


async def _probe(specs: list[str], settings: Settings) -> None:
    table = Table("provider", "status", "latency", "answer", "cost", title="probe")
    rows = await asyncio.gather(*(_probe_one(spec, settings) for spec in specs))
    for row in rows:
        table.add_row(*row)
    Console().print(table)


async def _probe_one(spec: str, settings: Settings) -> list[str]:
    family = parse_spec(spec)[0]
    if family in KEYED_FAMILIES and not settings.has(family):
        return [spec, "skipped", "", f"no credentials for {family}", ""]
    try:
        provider: Provider = make_provider(spec, settings)
    except Exception as exc:  # noqa: BLE001 - a Provider that cannot be built is a probe result
        return [spec, "skipped", "", f"cannot build: {type(exc).__name__}: {exc}", ""]
    started = time.perf_counter()
    try:
        result = await provider.evaluate(probe_request(provider.model))
    finally:
        await provider.aclose()
    latency = result.latency_s or (time.perf_counter() - started)
    return [
        provider.id,
        str(result.http_status) if result.http_status is not None else "-",
        f"{latency:.2f}s",
        describe_result(result),
        "unknown" if result.cost_usd is None else f"${result.cost_usd:.6f}",
    ]


def describe_result(result: ProviderResult) -> str:
    if result.response is None:
        return f"non-answer: {result.error}"
    return "; ".join(
        f"{question_id}: {describe_answer(answer)}"
        for question_id, answer in result.response.answers.items()
    )


def describe_answer(answer: Answer) -> str:
    match answer:
        case NonAnswer():
            return f"non-answer ({answer.cause})"
        case NoulAnswer():
            return f"{answer.noul:.2f}"
        case ChoiceAnswer():
            return f"{answer.choice} ({answer.probabilities.get(answer.choice, 0.0):.2f})"
        case ScoreAnswer():
            return f"{answer.score:.2f}"
    return repr(answer)


@app.command()
def run(
    provider: Annotated[
        list[str], typer.Option("--provider", "-p", help="Provider spec; repeatable.")
    ],
    family: Annotated[list[str], typer.Option("--family", "-f", help="Family name; repeatable.")],
    limit: Annotated[int | None, typer.Option(help="Cases per Family.")] = None,
    reps: Annotated[int, typer.Option(help="Repetitions per Case.")] = 1,
    runs_dir: Annotated[Path | None, typer.Option(help="Where results go.")] = None,
    budget: Annotated[float | None, typer.Option(help="Spending cap in USD.")] = None,
) -> None:
    """Evaluate Providers over Families; resumable, stops at the budget."""
    settings = load_settings()
    if budget is not None:
        settings = settings.model_copy(update={"budget_usd": budget})
    summary = runner.run(provider, family, settings, limit=limit, reps=reps, runs_dir=runs_dir)
    typer.echo(summary.model_dump_json(indent=2))
    if summary.stopped_for_budget:
        typer.echo("stopped for budget; rerun with a higher --budget to resume", err=True)


@app.command()
def report(
    runs_dir: Annotated[Path | None, typer.Option(help="Where results are.")] = None,
) -> None:
    """Write report.md and pareto.svg into the runs directory and print the markdown."""
    settings = load_settings()
    target = runs_dir if runs_dir is not None else settings.runs_dir
    markdown = build_report(target)
    target.mkdir(parents=True, exist_ok=True)
    (target / "report.md").write_text(markdown, encoding="utf-8")
    write_pareto_svg(target, target / "pareto.svg")
    typer.echo(markdown)


@app.command()
def serve(
    spec: Annotated[str, typer.Option(help="Own build spec to serve.")] = DEFAULT_SERVE_SPEC,
    host: Annotated[str, typer.Option()] = "127.0.0.1",
    port: Annotated[int, typer.Option()] = 8787,
    allow_remote: Annotated[
        bool, typer.Option(help="Bind to a non-loopback host: the endpoint has no auth or cap.")
    ] = False,
) -> None:
    """Serve the Own build as a System One endpoint (POST /v1/systemone, GET /v1/models)."""
    import uvicorn

    from bakeoff.ownbuild.server import create_app

    if host not in LOOPBACK_HOSTS and not allow_remote:
        raise typer.BadParameter(
            f"{host!r} is reachable from other machines and the endpoint spends your API key "
            "with no authentication or budget; pass --allow-remote to bind to it anyway",
            param_hint="--host",
        )
    uvicorn.run(create_app(spec, load_settings()), host=host, port=port)


@gen_app.command("smoke")
def gen_smoke(
    limit: Annotated[int | None, typer.Option(help="Cases per Family.")] = None,
) -> None:
    """Build the smoke Families under <data_dir>/smoke."""
    from bakeoff.datasets.smoke import build_smoke

    settings = load_settings()
    names = build_smoke(settings.data_dir / "smoke", settings, limit=limit)
    typer.echo("\n".join(names) if names else "no families written")
