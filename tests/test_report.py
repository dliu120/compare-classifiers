from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from bakeoff.metrics import ResultRow
from bakeoff.report import (
    build_report,
    display_name,
    provider_cells,
    render_pareto_svg,
    sweep_target_tokens,
    write_pareto_svg,
)
from bakeoff.runner import run_id_for
from bakeoff.store import Store

CHEAP = "jev"
UNPRICED = "ownbuild/openai/gpt-6-luna?effort=low&cap=512"
FAMILIES = ["toy", "longstate-4k", "longstate-16k"]


def _row(run_id: str, case_id: str, *, correct: bool, cost: float | None) -> ResultRow:
    probabilities = {"a": 0.8, "b": 0.2} if correct else {"a": 0.3, "b": 0.7}
    return ResultRow(
        run_id=run_id,
        case_id=case_id,
        question_id="q",
        rep=0,
        qtype="choice",
        n_options=2,
        reference_json={"kind": "gold", "choice": "a"},
        answer_json={
            "type": "choice",
            "choice": "a" if correct else "b",
            "probabilities": probabilities,
        },
        correct=correct,
        prob_ref=probabilities["a"],
        prob_pred=max(probabilities.values()),
        confidence=0.6,
        latency_s=0.5,
        input_tokens=120,
        cost_usd=cost,
        http_status=200,
        over_limit=case_id == "c3",
        created_at="2026-10-06T00:00:00+00:00",
    )


def seed(runs_dir: Path) -> None:
    """Every Family reuses the case ids c0..c3; the cheap Provider's cost per Case grows with
    the Family (0.0001, 0.0002, 0.0003), so pooled aggregates can be told from one Family's."""
    patterns = {
        CHEAP: (0.0001, [True, True, False, True]),
        UNPRICED: (None, [True, False, False, True]),
    }
    with Store(runs_dir) as store:
        for provider_id, (cost, pattern) in patterns.items():
            for position, family in enumerate(FAMILIES, start=1):
                run_id = run_id_for(provider_id, family)
                store.begin_run(run_id, provider_id, family, {"model": "m"})
                store.write_rows(
                    [
                        _row(run_id, f"c{index}", correct=correct, cost=cost and cost * position)
                        for index, correct in enumerate(pattern)
                    ]
                )
                store.finish_run(run_id)


def test_build_report_has_family_overall_pairwise_and_sweep_tables(tmp_path: Path) -> None:
    seed(tmp_path)
    markdown = build_report(tmp_path)
    for family in FAMILIES:
        assert f"## {family}" in markdown
    assert "## Overall" in markdown and "## Sweeps" in markdown
    assert "| jev-1.13.0 | n/a | n/a | 4 | 3 | 1 | 0 | 0.750 |" in markdown
    assert "| gpt-6-luna (openai, out ≤512) | low | no cap | 4 | 2 | 2 | 0 | 0.500 |" in markdown
    assert "unknown" in markdown  # the unpriced Provider's cost column
    assert "$0.1000" in markdown  # 0.0001 per Case in toy -> $0.10 per 1k
    overall = markdown.split("## Overall")[1].split("## Sweeps")[0]
    assert "| jev-1.13.0 | n/a | n/a | 12 | 9 | 3 | 0 | 0.750 |" in overall  # three Families pooled
    assert "$0.2000" in overall  # mean of 0.0001, 0.0002, 0.0003 over 12 requests, not 4
    assert "| 4,000 tok | 16,000 tok |" in markdown
    assert "0.750*" in markdown  # c3 is over the input limit
    assert "against the most accurate Run, jev-1.13.0," in markdown and "McNemar" in markdown
    assert "## Runs" in markdown and f"`{UNPRICED}`" in markdown


@pytest.mark.parametrize(
    ("outcomes", "counts", "accuracy", "answered_accuracy"),
    [
        (["right", "right"], (2, 0, 0), "1.000", "1.000"),
        (["wrong", "wrong"], (0, 2, 0), "0.000", "0.000"),
        (["non_answer", "non_answer"], (0, 0, 2), "0.000", "-"),
        (["right", "wrong", "non_answer"], (1, 1, 1), "0.333", "0.500"),
        ([], (0, 0, 0), "-", "-"),
    ],
)
def test_report_counts_answers_without_counting_non_answers_as_wrong(
    tmp_path: Path,
    outcomes: list[str],
    counts: tuple[int, int, int],
    accuracy: str,
    answered_accuracy: str,
) -> None:
    with Store(tmp_path) as store:
        for family in ["first", "second"]:
            run_id = run_id_for(CHEAP, family)
            store.begin_run(run_id, CHEAP, family, {"model": "m"})
            rows = []
            for index, outcome in enumerate(outcomes):
                row = _row(run_id, f"c{index}", correct=outcome == "right", cost=0.0001)
                if outcome == "non_answer":
                    row = row.model_copy(
                        update={
                            "non_answer_cause": "unsupported_modality",
                            "answer_json": {
                                "type": "non_answer",
                                "cause": "unsupported_modality",
                            },
                            "prob_ref": None,
                            "prob_pred": None,
                            "confidence": None,
                            "http_status": None,
                            "latency_s": 0.0,
                            "cost_usd": 0.0,
                        }
                    )
                rows.append(row)
            store.write_rows(rows)
            store.finish_run(run_id)

    markdown = build_report(tmp_path)
    assert "| Cases | Right | Wrong | Non-answers | Accuracy | Answered acc. |" in markdown
    for section, multiplier in [("first", 1), ("second", 1), ("Overall", 2)]:
        block = markdown.split(f"## {section}\n")[1].split("## ")[0]
        line = next(line for line in block.splitlines() if line.startswith("| jev-1.13.0 |"))
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        total, right, wrong, non_answers = map(int, cells[3:7])
        assert (right, wrong, non_answers) == tuple(count * multiplier for count in counts)
        assert total == right + wrong + non_answers == len(outcomes) * multiplier
        assert cells[7:9] == [accuracy, answered_accuracy]


def test_write_pareto_svg_plots_priced_runs_and_lists_the_rest(tmp_path: Path) -> None:
    seed(tmp_path)
    target = tmp_path / "out" / "pareto.svg"
    write_pareto_svg(tmp_path, target)
    svg = target.read_text(encoding="utf-8")
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert "jev-1.13.0 · toy" in svg
    assert "Unknown cost, not plotted" in svg and "out ≤512" in svg
    assert "$0.1" in svg  # a decade tick on the log axis
    root = ET.fromstring(svg)  # well-formed XML
    assert root.tag.endswith("svg")


def test_report_on_empty_runs_dir_creates_nothing(tmp_path: Path) -> None:
    assert "No runs found" in build_report(tmp_path)
    write_pareto_svg(tmp_path, tmp_path / "pareto.svg")
    assert (tmp_path / "pareto.svg").is_file()
    assert not (tmp_path / "bakeoff.sqlite").exists()


def test_render_handles_free_runs() -> None:
    from bakeoff.report import _Point

    svg = render_pareto_svg([_Point("liquid/d1:free · toy", "liquid", 0.0, 0.4)])
    assert ">free<" in svg
    ET.fromstring(svg)


def test_sweep_target_tokens() -> None:
    assert sweep_target_tokens("longstate-8k") == 8000
    assert sweep_target_tokens("longstate-32000") == 32000
    assert sweep_target_tokens("longstate-4K") == 4000
    assert sweep_target_tokens("toy") is None
    assert sweep_target_tokens("longstate-") is None


def test_provider_cells_split_model_effort_and_input_cap() -> None:
    assert provider_cells("jev") == ("jev-1.13.0", "n/a", "n/a")
    assert provider_cells("cloudflare/clef-flash") == ("clef-flash (Cloudflare)", "n/a", "n/a")
    assert provider_cells("openai-decisions/gpt-6-luna") == (
        "gpt-6-luna (OpenAI Decisions)",
        "n/a",
        "n/a",
    )
    assert provider_cells("foundry/decision-1") == (
        "decision-1 (Microsoft Foundry)",
        "n/a",
        "n/a",
    )
    spec = "ownbuild/copilot/gpt-6-luna?effort=none&max_in=128000&mode=probabilities&samples=1"
    assert provider_cells(spec) == ("gpt-6-luna (copilot)", "none", "128000")
    assert provider_cells("ownbuild/openai/gpt-6-luna?cap=512&samples=3") == (
        "gpt-6-luna (openai, out ≤512, samples 3)",
        "default",
        "no cap",
    )
    assert provider_cells("not-a-provider") == ("not-a-provider", "n/a", "n/a")
    assert display_name(spec) == "gpt-6-luna (copilot) · effort none · in ≤128000"
    assert display_name("jev") == "jev-1.13.0"
