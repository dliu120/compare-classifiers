from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import bakeoff.providers
from bakeoff import cli, runner
from bakeoff.config import Settings
from bakeoff.datasets.case import Case, Reference, family_dir, write_cases
from bakeoff.http import elide_images
from bakeoff.metrics import ResultRow
from bakeoff.providers import parse_spec
from bakeoff.providers.base import Provider, ProviderResult
from bakeoff.store import Store
from bakeoff.systemone import (
    Answer,
    ChoiceAnswer,
    ChoiceQuestion,
    NoulAnswer,
    NoulQuestion,
    Question,
    ScoreAnswer,
    ScoreQuestion,
    SystemOneRequest,
    SystemOneResponse,
    Usage,
)
from tests.conftest import TINY_PNG

OPTIONS = ["billing", "technical", "sales"]
TOP_PROBABILITY = 0.7
SECRET = "ts-secret-key-value-0123456789"


class FakeProvider(Provider):
    """Answers from the State text: the Option named in the State wins with probability 0.7.

    ``yield_first`` makes each call suspend once, as a real HTTP call does, so concurrency
    actually interleaves; ``rate_limit_case`` names the Case that comes back rate limited;
    ``leak`` raises with the loaded Jev key in the message.
    """

    supports_images = True

    def __init__(
        self,
        spec: str = "fake",
        *,
        cost: float | None = 0.01,
        max_in: int | None = None,
        fail: bool = False,
        concurrency: int = 1,
        yield_first: bool = False,
        rate_limit_case: str | None = None,
        leak: str | None = None,
    ) -> None:
        self.id = spec
        self.model = "fake-model"
        self.max_input_tokens = max_in
        self.concurrency = concurrency
        self.cost = cost
        self.fail = fail
        self.yield_first = yield_first
        self.rate_limit_case = rate_limit_case
        self.leak = leak
        self.calls = 0
        self.requests: list[SystemOneRequest] = []

    def estimate_cost_usd(self, approx_tokens: int | None) -> float:
        return self.cost or 0.0

    async def _call(self, request: SystemOneRequest) -> ProviderResult:
        self.calls += 1
        self.requests.append(request)
        STARTS.append(self.id)
        if self.yield_first:
            await asyncio.sleep(0)
        if self.fail:
            raise RuntimeError("scripted failure")
        if self.leak:
            raise RuntimeError(f"vendor said: invalid key {self.leak}")
        state = request.state if isinstance(request.state, str) else json.dumps(request.state)
        if self.rate_limit_case is not None and self.rate_limit_case in state:
            return self.non_answer(
                request, "rate_limited", "HTTP 429", latency_s=0.01, http_status=429, attempts=4
            )
        answers = {
            question_id: fake_answer(question, state)
            for question_id, question in request.questions.items()
        }
        return ProviderResult(
            provider_id=self.id,
            response=SystemOneResponse(
                model=self.model, answers=answers, usage=Usage(input_tokens=100, output_tokens=3)
            ),
            http_status=200,
            latency_s=0.01,
            request_raw=elide_images(request.model_dump(mode="json")),
            response_raw={"ok": True},
            cost_usd=self.cost,
        )


def fake_answer(question: Question, state: str) -> Answer:
    match question:
        case ChoiceQuestion():
            options = list(question.criteria)
            chosen = next((option for option in options if option in state), options[0])
            rest = (1.0 - TOP_PROBABILITY) / (len(options) - 1)
            probabilities = {
                option: TOP_PROBABILITY if option == chosen else rest for option in options
            }
            return ChoiceAnswer(choice=chosen, probabilities=probabilities)
        case NoulQuestion():
            return NoulAnswer(noul=0.9 if "ASAP" in state else 0.1)
        case ScoreQuestion():
            levels = len(question.criteria)
            probabilities = {
                str(index): 0.8 if index == 1 else 0.2 / (levels - 1) for index in range(levels)
            }
            return ScoreAnswer(score=1.0, probabilities=probabilities)
    raise TypeError(type(question).__name__)


BUILT: list[FakeProvider] = []
STARTS: list[str] = []  # provider ids in the order their calls started


def build(spec: str, settings: Settings) -> Provider:
    """Registry hook: ``fake[?cost=<float>|none&max_in=<int>&fail=1&concurrency=<int>&...]``."""
    _, _, options = parse_spec(spec)
    cost_option = options.get("cost", "0.01")
    provider = FakeProvider(
        spec,
        cost=None if cost_option == "none" else float(cost_option),
        max_in=int(options["max_in"]) if "max_in" in options else None,
        fail=options.get("fail") == "1",
        concurrency=int(options.get("concurrency", "1")),
        yield_first=options.get("yield") == "1",
        rate_limit_case=options.get("rate_limit_case"),
        leak=getattr(settings, options.get("credential", "typesafe_api_key"))
        if options.get("leak") == "1"
        else None,
    )
    BUILT.append(provider)
    return provider


def write_toy_family(data_root: Path, name: str = "toy", *, approx_tokens: int = 50) -> list[Case]:
    """Four Choice Cases; the last one names a different Option than its reference (wrong)."""
    cases = []
    for index in range(4):
        wanted = OPTIONS[index % 3]
        said = OPTIONS[(index + 1) % 3] if index == 3 else wanted
        cases.append(
            Case(
                id=f"c{index}",
                family=name,
                track="text",
                state=f"ticket {index} about {said}",
                questions={
                    "department": ChoiceQuestion(
                        instructions="Which team?", criteria=dict.fromkeys(OPTIONS)
                    )
                },
                reference={"department": Reference(kind="gold", choice=wanted)},
                approx_tokens=approx_tokens,
            )
        )
    write_family_files(data_root, name, "text", cases)
    return cases


def write_family_files(data_root: Path, name: str, track: str, cases: list[Case]) -> Path:
    directory = family_dir(data_root, name)
    write_cases(cases, directory / "cases.jsonl")
    meta = {
        "name": name, "track": track, "source": "tests", "license": "none",
        "reference_kind": "gold", "generated_by": "tests", "created": "2026-10-06",
    }  # fmt: skip
    (directory / "family.json").write_text(json.dumps(meta), encoding="utf-8")
    return directory


def write_image_family(data_root: Path, name: str = "pics", *, missing: bool = False) -> list[Case]:
    """A text Case and an image Case whose PNG is conftest's tiny image (absent if ``missing``)."""
    png = base64.b64decode(TINY_PNG.split(",", 1)[1])
    sha = hashlib.sha256(png).hexdigest()
    directory = family_dir(data_root, name)
    if not missing:
        (directory / "images").mkdir(parents=True, exist_ok=True)
        (directory / "images" / f"{sha}.png").write_bytes(png)
    question = {
        "department": ChoiceQuestion(instructions="Which team?", criteria=dict.fromkeys(OPTIONS))
    }
    cases = [
        Case(
            id="text-only", family=name, track="text", state="ticket about billing",
            questions=question, reference={"department": Reference(kind="gold", choice="billing")},
        ),
        Case(
            id="with-image", family=name, track="image", state="screenshot about sales",
            image_path=f"images/{sha}.png", image_sha256=sha,
            questions=question, reference={"department": Reference(kind="gold", choice="sales")},
        ),
    ]  # fmt: skip
    write_family_files(data_root, name, "image", cases)
    return cases


@pytest.fixture
def fake_registry(monkeypatch: pytest.MonkeyPatch) -> list[FakeProvider]:
    monkeypatch.setitem(bakeoff.providers.MODULES, "fake", "tests.test_runner")
    BUILT.clear()
    STARTS.clear()
    return BUILT


@pytest.fixture
def toy(tmp_path: Path) -> Settings:
    data = tmp_path / "data"
    write_toy_family(data)
    return Settings(data_dir=data, runs_dir=tmp_path / "runs", budget_usd=5.0)


def test_run_writes_rows_and_raw_capture(fake_registry: list[FakeProvider], toy: Settings) -> None:
    summary = runner.run(["fake"], ["toy"], toy)
    assert summary.run_ids == ["fake__toy"]
    assert (summary.cases_done, summary.non_answers) == (4, 0)
    assert summary.cost_usd == pytest.approx(0.04)
    assert not summary.stopped_for_budget and summary.rate_limited == []
    assert fake_registry[0].calls == 4
    with Store(toy.runs_dir) as store:
        rows = store.rows("fake__toy")
        records = store.runs()
    assert len(rows) == 4
    assert sum(row.correct for row in rows) == 3
    assert all(row.prob_pred == pytest.approx(TOP_PROBABILITY) for row in rows)
    assert records[0].provider_id == "fake" and records[0].finished_at is not None
    lines = (toy.runs_dir / "raw" / "fake__toy.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4
    record = json.loads(lines[0])
    assert record["request_raw"]["questions"] and record["response_raw"] == {"ok": True}
    assert "headers" not in json.dumps(record).lower()


def test_run_resumes_without_duplicates(fake_registry: list[FakeProvider], toy: Settings) -> None:
    runner.run(["fake"], ["toy"], toy)
    summary = runner.run(["fake"], ["toy"], toy)
    assert fake_registry[1].calls == 0
    assert summary.cases_done == 0 and summary.cost_usd == 0.0
    with Store(toy.runs_dir) as store:
        assert len(store.rows("fake__toy")) == 4
        assert len(store.runs()) == 1


def test_run_with_reps_and_limit(fake_registry: list[FakeProvider], toy: Settings) -> None:
    summary = runner.run(["fake"], ["toy"], toy, limit=2, reps=2)
    assert summary.cases_done == 4
    with Store(toy.runs_dir) as store:
        rows = store.rows("fake__toy")
    assert {(row.case_id, row.rep) for row in rows} == {("c0", 0), ("c0", 1), ("c1", 0), ("c1", 1)}


def test_same_provider_twice_plans_one_run(
    fake_registry: list[FakeProvider], toy: Settings
) -> None:
    summary = runner.run(["fake", "fake"], ["toy"], toy)
    assert summary.run_ids == ["fake__toy"]
    assert summary.cases_done == 4 and summary.cost_usd == pytest.approx(0.04)
    assert fake_registry[0].calls == 4 and fake_registry[1].calls == 0
    lines = (toy.runs_dir / "raw" / "fake__toy.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4


def test_run_stops_for_budget_and_resumes_later(
    fake_registry: list[FakeProvider], toy: Settings
) -> None:
    tiny = toy.model_copy(update={"budget_usd": 0.015})
    summary = runner.run(["fake"], ["toy"], tiny)
    assert summary.stopped_for_budget
    assert summary.cases_done == 2
    assert summary.cost_usd == pytest.approx(0.02)
    later = runner.run(["fake"], ["toy"], toy)
    assert later.cases_done == 2 and not later.stopped_for_budget
    with Store(toy.runs_dir) as store:
        assert len(store.rows("fake__toy")) == 4
        assert store.total_cost_usd() == pytest.approx(0.04)


def test_budget_holds_under_concurrency(fake_registry: list[FakeProvider], toy: Settings) -> None:
    """Requests in flight count against the cap, so a wave of concurrent calls cannot all pass
    the check while nothing has been recorded yet."""
    tiny = toy.model_copy(update={"budget_usd": 0.5})
    summary = runner.run(["fake?cost=1.0&concurrency=4&yield=1"], ["toy"], tiny)
    assert summary.stopped_for_budget
    assert summary.cases_done == 1 and fake_registry[0].calls == 1
    assert summary.cost_usd == pytest.approx(1.0)


def test_run_flags_over_limit(fake_registry: list[FakeProvider], toy: Settings) -> None:
    spec = "fake?max_in=10"
    runner.run([spec], ["toy"], toy)
    with Store(toy.runs_dir) as store:
        rows = store.rows(runner.run_id_for(spec, "toy"))
    assert rows and all(row.over_limit for row in rows)


def test_run_flags_reported_input_limit_rejection(toy: Settings) -> None:
    case = write_toy_family(toy.data_dir)[0]
    provider = FakeProvider()
    result = ProviderResult(
        provider_id=provider.id,
        latency_s=0.1,
        http_status=422,
        error="HTTP 422: prompt is over the model's input limit",
    )

    rows = runner.build_rows("fake__toy", case, 0, provider, result)

    assert rows and all(row.over_limit for row in rows)


def test_run_does_not_flag_unrelated_http_422_as_over_limit(toy: Settings) -> None:
    case = write_toy_family(toy.data_dir)[0]
    provider = FakeProvider()
    result = ProviderResult(
        provider_id=provider.id,
        latency_s=0.1,
        http_status=422,
        error="HTTP 422: invalid model name",
    )

    rows = runner.build_rows("fake__toy", case, 0, provider, result)

    assert rows and not any(row.over_limit for row in rows)


def test_run_counts_non_answers_and_unknown_costs(
    fake_registry: list[FakeProvider], toy: Settings
) -> None:
    summary = runner.run(["fake?fail=1&cost=none"], ["toy"], toy, limit=2)
    assert (summary.cases_done, summary.non_answers) == (2, 2)
    assert summary.unknown_costs == 2 and summary.cost_usd == 0.0
    with Store(toy.runs_dir) as store:
        rows = store.rows(runner.run_id_for("fake?fail=1&cost=none", "toy"))
    assert {row.non_answer_cause for row in rows} == {"error"}
    assert not any(row.correct for row in rows)


def test_rate_limited_provider_stops_and_resumes_later(
    fake_registry: list[FakeProvider], toy: Settings
) -> None:
    spec = "fake?rate_limit_case=ticket 0"
    summary = runner.run([spec], ["toy"], toy)
    assert summary.rate_limited == [spec]
    assert summary.cases_done == 1 and summary.non_answers == 1
    assert fake_registry[0].calls == 1  # the remaining Cases were not attempted
    later = runner.run([spec], ["toy"], toy)
    assert later.cases_done == 3 and later.rate_limited == []  # c0 is done; the rest resume
    with Store(toy.runs_dir) as store:
        rows = store.rows(runner.run_id_for(spec, "toy"))
    assert len(rows) == 4
    assert [row.non_answer_cause for row in rows].count("rate_limited") == 1


def test_image_family_round_trip(fake_registry: list[FakeProvider], tmp_path: Path) -> None:
    data = tmp_path / "data"
    write_image_family(data)
    settings = Settings(data_dir=data, runs_dir=tmp_path / "runs")
    summary = runner.run(["fake"], ["pics"], settings)
    assert (summary.cases_done, summary.non_answers) == (2, 0)
    sent = {request.images[0] if request.images else None for request in fake_registry[0].requests}
    assert sent == {None, TINY_PNG}
    raw = (settings.runs_dir / "raw" / "fake__pics.jsonl").read_text(encoding="utf-8")
    assert "$image" in raw and TINY_PNG.split(",", 1)[1] not in raw
    with Store(settings.runs_dir) as store:
        rows = {row.case_id: row for row in store.rows("fake__pics")}
    assert rows["with-image"].correct and rows["text-only"].correct


def test_unreadable_case_is_a_row_not_a_crash(
    fake_registry: list[FakeProvider], tmp_path: Path
) -> None:
    data = tmp_path / "data"
    write_image_family(data, missing=True)
    settings = Settings(data_dir=data, runs_dir=tmp_path / "runs")
    summary = runner.run(["fake"], ["pics"], settings)
    assert (summary.cases_done, summary.non_answers) == (2, 1)
    assert summary.unknown_costs == 0 and summary.cost_usd == pytest.approx(0.01)
    with Store(settings.runs_dir) as store:
        rows = {row.case_id: row for row in store.rows("fake__pics")}
    broken = rows["with-image"]
    assert broken.non_answer_cause == "error"
    assert "FileNotFoundError" in broken.answer_json["detail"]
    assert broken.cost_usd == 0.0 and broken.latency_s == 0.0 and broken.http_status is None
    assert rows["text-only"].correct
    raw_path = settings.runs_dir / "raw" / "fake__pics.jsonl"
    lines = raw_path.read_text(encoding="utf-8").splitlines()
    records = {record["case_id"]: record for record in map(json.loads, lines)}
    assert set(records) == {"text-only", "with-image"}
    assert records["with-image"]["cost_usd"] == 0.0 and records["with-image"]["request_raw"] is None


def test_a_failing_evaluation_surfaces_after_the_others_recorded(
    fake_registry: list[FakeProvider], toy: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Requests in flight were already sent (and billed): a crash in one evaluation must not
    cancel the rest before their rows are written."""
    original = Store.write_raw

    def write_raw(self: Store, run_id: str, record: dict) -> None:
        if record["case_id"] == "c1":
            raise OSError("disk full")
        original(self, run_id, record)

    monkeypatch.setattr(Store, "write_raw", write_raw)
    with pytest.raises(OSError, match="disk full"):
        runner.run(["fake?concurrency=4&yield=1"], ["toy"], toy)
    with Store(toy.runs_dir) as store:
        done = store.completed(runner.run_id_for("fake?concurrency=4&yield=1", "toy"))
    assert done == {("c0", 0), ("c2", 0), ("c3", 0)}


def test_providers_take_turns_at_the_global_slots(
    fake_registry: list[FakeProvider], toy: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner, "GLOBAL_CONCURRENCY", 1)
    runner.run(["fake?tag=a&yield=1", "fake?tag=b&yield=1"], ["toy"], toy)
    assert len(STARTS) == 8
    first_b = STARTS.index("fake?tag=b&yield=1")
    last_a = len(STARTS) - 1 - STARTS[::-1].index("fake?tag=a&yield=1")
    assert first_b < last_a  # the second Provider did not wait for the first to finish


@pytest.mark.parametrize("credential", ["typesafe_api_key", "foundry_access_token"])
def test_loaded_credentials_never_reach_the_store(
    fake_registry: list[FakeProvider], toy: Settings, credential: str
) -> None:
    keyed = toy.model_copy(update={credential: SECRET})
    spec = f"fake?leak=1&cost=none&credential={credential}"
    runner.run([spec], ["toy"], keyed, limit=1)
    raw = (toy.runs_dir / "raw").glob("*.jsonl")
    text = "".join(path.read_text(encoding="utf-8") for path in raw)
    assert SECRET not in text and "invalid key ***" in text
    with Store(toy.runs_dir) as store:
        rows = store.rows(runner.run_id_for(spec, "toy"))
    assert rows and SECRET not in json.dumps(rows[0].answer_json)
    assert "***" in rows[0].answer_json["detail"]


def test_store_inserts_are_idempotent(tmp_path: Path) -> None:
    rows = [
        ResultRow(
            run_id="r", case_id="c0", question_id="q", rep=0, qtype="noul", n_options=2,
            reference_json={"kind": "gold", "noul": True},
            answer_json={"type": "noul", "noul": 0.9}, correct=True, prob_ref=0.9, prob_pred=0.9,
            latency_s=0.1, created_at="2026-10-06T00:00:00+00:00",
        )
    ]  # fmt: skip
    with Store(tmp_path) as store:
        store.begin_run("r", "fake", "toy", {})
        store.write_rows(rows)
        store.write_rows(rows)
        store.begin_run("r", "fake", "toy", {"again": True})
        assert len(store.rows("r")) == 1
        assert len(store.runs()) == 1 and store.runs()[0].config == {"again": True}
        assert store.completed("r") == {("c0", 0)}
        assert store.conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_run_id_slug() -> None:
    assert runner.run_id_for("ownbuild/copilot/gpt-6-luna?effort=low&cap=512", "toy") == (
        "ownbuild-copilot-gpt-6-luna-effort-low-cap-512__toy"
    )
    assert runner.run_id_for("liquid/d1:free", "x") == "liquid-d1-free__x"


def test_default_data_root_prefers_smoke(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    assert runner.default_data_root(settings) == tmp_path
    (tmp_path / "smoke").mkdir()
    assert runner.default_data_root(settings) == tmp_path / "smoke"


def test_cli_run_then_report(
    fake_registry: list[FakeProvider], toy: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "load_settings", lambda: toy)
    cli_runner = CliRunner()
    result = cli_runner.invoke(
        cli.app, ["run", "--provider", "fake", "--family", "toy", "--limit", "3"]
    )
    assert result.exit_code == 0, result.output
    assert '"cases_done": 3' in result.output
    result = cli_runner.invoke(cli.app, ["report", "--runs-dir", str(toy.runs_dir)])
    assert result.exit_code == 0, result.output
    assert "## toy" in result.output and "| fake |" in result.output
    assert (toy.runs_dir / "report.md").is_file()
    assert (toy.runs_dir / "pareto.svg").read_text(encoding="utf-8").startswith("<svg")


def test_cli_probe_skips_unkeyed_and_probes_fake(
    fake_registry: list[FakeProvider], toy: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "load_settings", lambda: toy)  # no credentials at all
    monkeypatch.setattr(cli, "DEFAULT_PROBE_SPECS", ["jev", "cloudflare/clef-flash"])
    result = CliRunner().invoke(cli.app, ["probe", "--provider", "fake"])
    assert result.exit_code == 0, result.output
    assert "no credentials" in result.output
    assert "fake" in result.output and "200" in result.output
    assert "sales" in result.output  # the Stripe sample mentions sales
    assert len(fake_registry) == 1 and fake_registry[0].calls == 1


def test_cli_serve_refuses_a_remote_host_unless_told_to(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "load_settings", lambda: Settings())
    result = CliRunner().invoke(cli.app, ["serve", "--host", "0.0.0.0"])
    assert result.exit_code != 0
    assert "--allow-remote" in result.output
    assert "ownbuild/openai/gpt-6-luna?effort=none" in cli.DEFAULT_PROBE_SPECS
