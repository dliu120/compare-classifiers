"""Markdown report and Pareto chart (hand-written SVG) from a runs directory."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from bakeoff.metrics import ResultRow, RunMetrics, aggregate
from bakeoff.providers import parse_spec
from bakeoff.stats import mcnemar, paired_bootstrap_diff
from bakeoff.store import RunRecord, Store, has_store, now_iso

SWEEP_PREFIX = "longstate-"
MIN_RUNS_FOR_PAIRWISE = 2

# One accent per Provider family, plus a marker shape so identity never rests on hue alone.
# Validated with the dataviz palette checker: lightness band passes on light and dark
# surfaces; six hues cannot clear the all-pairs CVD gate, so labels carry identity.
ACCENTS: dict[str, tuple[str, str]] = {
    "jev": ("#2a78d6", "circle"),
    "cloudflare": ("#199e70", "triangle"),
    "liquid": ("#c98500", "diamond"),
    "openai-decisions": ("#d55181", "plus"),
    "foundry": ("#d88a3a", "square"),
    "ownbuild": ("#9085e9", "cross"),
}
FALLBACK_ACCENT = ("#898781", "circle")
INK = "#898781"  # muted ink: legible on light and dark backgrounds

NA = "n/a"
NO_CAP = "no cap"
EFFORT_ORDER = ["none", "low", "medium", "high", "xhigh", "max"]
OWNBUILD_DEFAULTS = {"mode": "probabilities", "samples": "1"}
VENDOR_MODELS = {"jev": "jev-1.13.0"}  # families whose spec names no model
VENDOR_SUFFIX = {
    "cloudflare": "Cloudflare",
    "liquid": "Liquid",
    "openai-decisions": "OpenAI Decisions",
    "foundry": "Microsoft Foundry",
}

ID_HEADERS = ["Provider", "Effort", "Input cap"]
MAIN_HEADERS = [
    *ID_HEADERS, "Cases", "Right", "Wrong", "Non-answers", "Accuracy", "Answered acc.",
    "Non-answer rate", "Median s", "$ per 1k", "Over cap",
]  # fmt: skip
DETAIL_HEADERS = [*ID_HEADERS, "Chance-corrected", "Macro-F1", "ECE", "Brier", "p95 s"]

LEGEND = [
    "**How to read this report**",
    "",
    (
        "- **Provider**: the model that answered. Own build rows name the route in parentheses, "
        "plus any output cap or sampling; the exact spec of every row is in the Runs section."
    ),
    (
        "- **Effort**: the reasoning effort set on the own build. Decision APIs have no such "
        "setting, so they show n/a."
    ),
    (
        "- **Input cap**: the input-token limit set on the own build, or `no cap`. Decision APIs "
        "show n/a; their fixed limits show up as Over cap."
    ),
    "- **Cases**: question rows scored; a Case can carry several Questions.",
    "- **Right**: count of Questions answered correctly.",
    "- **Wrong**: count of Questions answered incorrectly, excluding Non-answers.",
    "- **Accuracy**: share of rows answered correctly. A Non-answer counts as wrong.",
    (
        "- **Answered acc.**: accuracy over the rows that produced an Answer, so a Provider "
        "that could not take an input is not penalised for it here."
    ),
    (
        "- **Non-answers**: count of Questions with no usable answer: refused, truncated, errored, "
        "or rejected because the input was over the vendor's limit."
    ),
    "- **Right + Wrong + Non-answers** equals Cases; these are question counts, not requests.",
    "- **Non-answer rate**: share of scored Questions with no usable answer.",
    "- **Median s**: seconds per request; half the requests were faster.",
    (
        "- **$ per 1k**: dollars per 1,000 requests, from vendor-reported costs when available "
        "or estimated from the stored rate and usage; later price changes do not recalculate "
        "stored rows. `unknown` when any request has no reported or estimated cost."
    ),
    (
        "- **Over cap**: share of Cases longer than the Provider's input limit. In the sweep table "
        "the same thing is marked with `*`."
    ),
    (
        "- **Details tables**: chance-corrected accuracy (0 is guessing, 1 is perfect), macro-F1 "
        "(accuracy balanced across classes), ECE and Brier (calibration, lower is better, 0 is "
        "perfect), and p95 latency (19 of 20 requests were faster)."
    ),
    "",
]


def provider_cells(provider_id: str) -> tuple[str, str, str]:
    """(model, effort, input cap) for a Provider id; unknown ids get (id, n/a, n/a)."""
    try:
        family, parts, params = parse_spec(provider_id)
    except ValueError:
        return provider_id, NA, NA
    if family == "ownbuild":
        route = parts[0] if parts else "?"
        model = parts[1] if len(parts) > 1 else "?"
        notes = [route]
        if "cap" in params:
            notes.append(f"out ≤{params['cap']}")
        for key in ("mode", "samples", "via"):
            if key in params and params[key] != OWNBUILD_DEFAULTS.get(key):
                notes.append(f"{key} {params[key]}")
        return (
            f"{model} ({', '.join(notes)})",
            params.get("effort", "default"),
            params.get("max_in", NO_CAP),
        )
    model = parts[0] if parts else VENDOR_MODELS.get(family, family)
    suffix = VENDOR_SUFFIX.get(family)
    return (f"{model} ({suffix})" if suffix else model), NA, NA


def display_name(provider_id: str) -> str:
    """One-line label: the cells that are not n/a, joined with middle dots."""
    model, effort, cap = provider_cells(provider_id)
    bits = [model]
    if effort != NA:
        bits.append(f"effort {effort}")
    if cap != NA:
        bits.append(f"in ≤{cap}" if cap != NO_CAP else NO_CAP)
    return " · ".join(bits)


def _sort_key(provider_id: str) -> tuple[str, int, int]:
    model, effort, cap = provider_cells(provider_id)
    effort_rank = EFFORT_ORDER.index(effort) if effort in EFFORT_ORDER else len(EFFORT_ORDER)
    return model, effort_rank, int(cap) if cap.isdigit() else 10**12


@dataclass
class RunView:
    record: RunRecord
    rows: list[ResultRow]
    metrics: RunMetrics

    @property
    def family(self) -> str:
        return self.record.family

    @property
    def provider_id(self) -> str:
        return self.record.provider_id


def load_runs(runs_dir: Path) -> list[RunView]:
    if not has_store(runs_dir):
        return []
    with Store(runs_dir) as store:
        views = []
        for record in store.runs():
            rows = store.rows(record.run_id)
            views.append(RunView(record, rows, aggregate(rows)))
    return views


def build_report(runs_dir: Path) -> str:
    views = load_runs(runs_dir)
    lines = ["# Bakeoff report", "", f"_{len(views)} runs in `{runs_dir}`, built {now_iso()}_", ""]
    if not views:
        lines.append("No runs found.")
        return "\n".join(lines) + "\n"
    lines += LEGEND
    for family in sorted({view.family for view in views}):
        members = [view for view in views if view.family == family]
        lines += [f"## {family}", "", *_metrics_tables(members), ""]
        lines += _pairwise(members)
    lines += ["## Overall", "", *_overall_tables(views), ""]
    lines += _sweeps(views)
    lines += _runs_appendix(views)
    return "\n".join(lines).rstrip() + "\n"


def _metrics_tables(views: list[RunView]) -> list[str]:
    ordered = sorted(views, key=lambda view: _sort_key(view.provider_id))
    return _main_and_details([(view.provider_id, view.metrics) for view in ordered])


def _overall_tables(views: list[RunView]) -> list[str]:
    """Rows of every Family pooled per Provider."""
    labelled = []
    for provider_id in sorted({view.provider_id for view in views}, key=_sort_key):
        pooled = [row for view in views if view.provider_id == provider_id for row in view.rows]
        labelled.append((provider_id, aggregate(pooled)))
    return _main_and_details(labelled)


def _main_and_details(labelled: list[tuple[str, RunMetrics]]) -> list[str]:
    main = _table(MAIN_HEADERS, [_main_row(pid, m) for pid, m in labelled])
    details = _table(DETAIL_HEADERS, [_details_row(pid, m) for pid, m in labelled])
    return [main, "", "Details:", "", details]


def _main_row(provider_id: str, m: RunMetrics) -> list[str]:
    return [
        *provider_cells(provider_id), str(m.n), str(m.n_correct),
        str(m.n_answered - m.n_correct), str(m.n - m.n_answered),
        _num(m.accuracy), _num(m.accuracy_answered),
        _num(m.non_answer_rate),
        _num(m.latency_p50, 2), _money(m.cost_per_1k), _num(m.over_limit_rate),
    ]  # fmt: skip


def _details_row(provider_id: str, m: RunMetrics) -> list[str]:
    return [
        *provider_cells(provider_id), _num(m.chance_corrected), _num(m.macro_f1), _num(m.ece),
        _num(m.brier), _num(m.latency_p95, 2),
    ]  # fmt: skip


def _runs_appendix(views: list[RunView]) -> list[str]:
    """Every row label with the exact Provider spec behind it."""
    ids = sorted({view.provider_id for view in views}, key=_sort_key)
    lines = ["## Runs", "", "Row labels above and the exact spec each one stands for:", ""]
    lines += [f"- **{display_name(pid)}**: `{pid}`" for pid in ids]
    return lines + [""]


def _pairwise(views: list[RunView]) -> list[str]:
    """Each Run against the most accurate Run of the Family, on shared (case, question, rep)."""
    scored = [view for view in views if view.metrics.accuracy is not None]
    if len(scored) < MIN_RUNS_FOR_PAIRWISE:
        return []
    best = max(scored, key=lambda view: view.metrics.accuracy or 0.0)
    best_correct = _correct_by_key(best)
    rows = []
    for view in scored:
        if view is best:
            continue
        correct = _correct_by_key(view)
        if not set(correct) & set(best_correct):
            continue
        diff, low, high = paired_bootstrap_diff(correct, best_correct)
        only_a, only_b, p_value = mcnemar(correct, best_correct)
        rows.append(
            [
                *provider_cells(view.provider_id),
                f"{diff:+.3f}",
                f"[{low:+.3f}, {high:+.3f}]",
                f"{only_a}/{only_b}",
                _num(p_value),
            ]
        )
    if not rows:
        return []
    headers = [*ID_HEADERS, "Accuracy diff", "95% interval", "Wins/losses", "McNemar p"]
    return [
        (
            f"Each row against the most accurate Run, {display_name(best.provider_id)}, on the "
            "same Cases (a negative diff means it did worse):"
        ),
        "", _table(headers, rows), "",
    ]  # fmt: skip


def _correct_by_key(view: RunView) -> dict[str, bool]:
    return {f"{row.case_id}|{row.question_id}|{row.rep}": row.correct for row in view.rows}


def sweep_target_tokens(family: str) -> int | None:
    """``longstate-8k`` -> 8000, ``longstate-32000`` -> 32000; None when not a sweep Family."""
    if not family.startswith(SWEEP_PREFIX):
        return None
    match = re.search(r"(\d+)(k?)", family[len(SWEEP_PREFIX) :], re.IGNORECASE)
    if match is None:
        return None
    return int(match.group(1)) * (1000 if match.group(2) else 1)


def _sweeps(views: list[RunView]) -> list[str]:
    sweeps = [(sweep_target_tokens(view.family), view) for view in views]
    sweeps = [(target, view) for target, view in sweeps if target is not None]
    if not sweeps:
        return []
    targets = sorted({target for target, _ in sweeps})
    headers = [*ID_HEADERS, *[f"{target:,} tok" for target in targets]]
    rows = []
    for provider_id in sorted({view.provider_id for _, view in sweeps}, key=_sort_key):
        cells = [*provider_cells(provider_id)]
        for target in targets:
            match = [v for t, v in sweeps if t == target and v.provider_id == provider_id]
            cells.append(_sweep_cell(match[0].metrics) if match else "")
        rows.append(cells)
    return [
        "## Sweeps", "",
        (
            "Accuracy by State length (`longstate-*` Families); `*` marks Runs with Cases "
            "over the Provider's documented input limit."
        ), "",
        _table(headers, rows), "",
    ]  # fmt: skip


def _sweep_cell(metrics: RunMetrics) -> str:
    flag = "*" if (metrics.over_limit_rate or 0.0) > 0.0 else ""
    return _num(metrics.accuracy) + flag


def _table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def _num(value: float | None, digits: int = 3) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def _money(value: float | None) -> str:
    return "unknown" if value is None else f"${value:.4f}"


# --- Pareto SVG ---------------------------------------------------------------------------

WIDTH = 800
PLOT_LEFT, PLOT_RIGHT, PLOT_TOP, PLOT_BOTTOM = 72, 776, 56, 336
FREE_X = PLOT_LEFT + 16  # where zero-cost Runs sit, left of the log scale
LOG_LEFT = PLOT_LEFT + 48
FONT = "font-family=\"system-ui, -apple-system, 'Segoe UI', sans-serif\""


@dataclass
class _Point:
    label: str
    family: str
    cost: float | None
    y_value: float


def write_pareto_svg(runs_dir: Path, path: Path) -> None:
    """Chance-corrected accuracy (y) against cost per 1k Cases (x, log scale), one point per Run."""
    points = [
        _Point(
            f"{display_name(view.provider_id)} · {view.family}",
            parse_spec(view.provider_id)[0],
            view.metrics.cost_per_1k,
            view.metrics.chance_corrected or 0.0,
        )
        for view in load_runs(runs_dir)
        if view.metrics.n > 0
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_pareto_svg(points), encoding="utf-8")


def render_pareto_svg(points: list[_Point]) -> str:
    plotted = [point for point in points if point.cost is not None]
    unknown = [point for point in points if point.cost is None]
    families = sorted({point.family for point in points})
    height = PLOT_BOTTOM + 64 + 18 * len(families) + (18 * (len(unknown) + 1) if unknown else 0)
    x_scale = _log_scale([point.cost for point in plotted if point.cost])
    y_low = min(0.0, math.floor(min((p.y_value for p in plotted), default=0.0) * 4) / 4)
    body = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" '
            f'viewBox="0 0 {WIDTH} {height}" {FONT} font-size="12">'
        ),
        "<title>Chance-corrected accuracy against cost per 1k Cases</title>",
        (
            f'<text x="{PLOT_LEFT}" y="28" fill="{INK}" font-size="15" font-weight="600">'
            "Chance-corrected accuracy vs cost per 1k Cases (log x)</text>"
        ),
        *_axes(x_scale, y_low, any(point.cost == 0 for point in plotted)),
        *_marks(plotted, x_scale, y_low),
        *_legend(families, PLOT_BOTTOM + 48),
        *_unknown_list(unknown, PLOT_BOTTOM + 48 + 18 * len(families) + 6),
        "</svg>",
    ]
    return "\n".join(body) + "\n"


def _log_scale(costs: list[float]) -> tuple[float, float]:
    """Decade bounds (log10) that enclose every positive cost, at least one decade wide."""
    if not costs:
        return -2.0, 0.0
    low = math.floor(math.log10(min(costs)))
    high = math.ceil(math.log10(max(costs)))
    return float(low), float(max(high, low + 1))


def _x(cost: float, scale: tuple[float, float]) -> float:
    if cost <= 0:
        return FREE_X
    low, high = scale
    return LOG_LEFT + (math.log10(cost) - low) / (high - low) * (PLOT_RIGHT - LOG_LEFT)


def _y(value: float, y_low: float) -> float:
    return PLOT_BOTTOM - (value - y_low) / (1.0 - y_low) * (PLOT_BOTTOM - PLOT_TOP)


def _axes(scale: tuple[float, float], y_low: float, has_free: bool) -> list[str]:
    out = [
        _line(PLOT_LEFT, PLOT_BOTTOM, PLOT_RIGHT, PLOT_BOTTOM, 1.0),
        _line(PLOT_LEFT, PLOT_TOP, PLOT_LEFT, PLOT_BOTTOM, 1.0),
    ]
    tick = y_low
    while tick <= 1.0 + 1e-9:
        y = _y(tick, y_low)
        out.append(_line(PLOT_LEFT, y, PLOT_RIGHT, y, 0.25))
        out.append(
            f'<text x="{PLOT_LEFT - 8}" y="{y + 4:.1f}" fill="{INK}" text-anchor="end">'
            f"{tick:.2f}</text>"
        )
        tick += 0.25
    low, high = scale
    for exponent in range(int(low), int(high) + 1):
        x = _x(10.0**exponent, scale)
        out.append(_line(x, PLOT_TOP, x, PLOT_BOTTOM, 0.25))
        out.append(
            f'<text x="{x:.1f}" y="{PLOT_BOTTOM + 18}" fill="{INK}" text-anchor="middle">'
            f"{_money_tick(10.0**exponent)}</text>"
        )
    if has_free:
        out.append(
            f'<text x="{FREE_X}" y="{PLOT_BOTTOM + 18}" fill="{INK}" text-anchor="middle">'
            "free</text>"
        )
    out.append(
        f'<text x="{(PLOT_LEFT + PLOT_RIGHT) / 2:.0f}" y="{PLOT_BOTTOM + 38}" fill="{INK}" '
        'text-anchor="middle">cost per 1k Cases (USD, log scale)</text>'
    )
    out.append(
        f'<text transform="translate(18 {(PLOT_TOP + PLOT_BOTTOM) / 2:.0f}) rotate(-90)" '
        f'fill="{INK}" text-anchor="middle">chance-corrected accuracy</text>'
    )
    return out


def _line(x1: float, y1: float, x2: float, y2: float, opacity: float) -> str:
    return (
        f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{INK}" '
        f'stroke-width="1" opacity="{opacity}"/>'
    )


def _money_tick(value: float) -> str:
    return f"${value:g}"


LABEL_HEIGHT = 13.0
LABEL_CHAR_WIDTH = 6.5  # rough width of one 11px character, for collision checks


def _marks(points: list[_Point], scale: tuple[float, float], y_low: float) -> list[str]:
    """Marks first, then labels placed so they overlap neither a mark nor an earlier label."""
    ordered = sorted(points, key=lambda point: (point.cost or 0.0, -point.y_value))
    positions = [(_x(point.cost or 0.0, scale), _y(point.y_value, y_low)) for point in ordered]
    placed = [(x - 7.0, x + 7.0, y) for x, y in positions]  # (left, right, y) boxes to avoid
    out = []
    for point, (x, y) in zip(ordered, positions, strict=True):
        color, shape = ACCENTS.get(point.family, FALLBACK_ACCENT)
        out.append(_shape(shape, x, y, color))
        text = _shorten(point.label)
        width = LABEL_CHAR_WIDTH * len(text)
        anchor, left = ("start", x + 8) if x + 8 + width <= WIDTH - 8 else ("end", x - 8 - width)
        label_y = _free_label_y(placed, left, left + width, y - 8)
        placed.append((left, left + width, label_y))
        text_x = left if anchor == "start" else left + width
        out.append(
            f'<text x="{text_x:.1f}" y="{label_y:.1f}" fill="{INK}" font-size="11" '
            f'text-anchor="{anchor}">{escape(text)}</text>'
        )
    return out


def _free_label_y(
    placed: list[tuple[float, float, float]], left: float, right: float, y: float
) -> float:
    """Push a label down until it no longer overlaps any label placed before it."""
    while any(
        other_left < right and other_right > left and abs(other_y - y) < LABEL_HEIGHT
        for other_left, other_right, other_y in placed
    ):
        y += LABEL_HEIGHT
    return y


def _shape(shape: str, x: float, y: float, color: str) -> str:
    r = 5.0
    match shape:
        case "square":
            return (
                f'<rect x="{x - r:.1f}" y="{y - r:.1f}" width="{2 * r}" height="{2 * r}" '
                f'fill="{color}"/>'
            )
        case "triangle":
            corners = [(x, y - r - 1), (x - r - 1, y + r), (x + r + 1, y + r)]
            return _polygon(corners, color)
        case "diamond":
            corners = [(x, y - r - 1), (x + r + 1, y), (x, y + r + 1), (x - r - 1, y)]
            return _polygon(corners, color)
        case "plus":
            return (
                f'<path d="M{x - r - 1:.1f} {y:.1f} H{x + r + 1:.1f} M{x:.1f} {y - r - 1:.1f} '
                f'V{y + r + 1:.1f}" stroke="{color}" stroke-width="3"/>'
            )
        case "cross":
            return (
                f'<path d="M{x - r:.1f} {y - r:.1f} L{x + r:.1f} {y + r:.1f} M{x - r:.1f} '
                f'{y + r:.1f} L{x + r:.1f} {y - r:.1f}" stroke="{color}" stroke-width="3"/>'
            )
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{color}"/>'


def _polygon(corners: list[tuple[float, float]], color: str) -> str:
    points = " ".join(f"{px:.1f},{py:.1f}" for px, py in corners)
    return f'<polygon points="{points}" fill="{color}"/>'


def _legend(families: list[str], top: int) -> list[str]:
    out = []
    for index, family in enumerate(families):
        color, shape = ACCENTS.get(family, FALLBACK_ACCENT)
        y = top + 18 * index
        out.append(_shape(shape, PLOT_LEFT + 6, y - 4, color))
        out.append(f'<text x="{PLOT_LEFT + 20}" y="{y}" fill="{INK}">{escape(family)}</text>')
    return out


def _unknown_list(points: list[_Point], top: int) -> list[str]:
    if not points:
        return []
    heading = f'<text x="{PLOT_LEFT}" y="{top}" fill="{INK}" font-weight="600">'
    out = [heading + "Unknown cost, not plotted:</text>"]
    for index, point in enumerate(points, start=1):
        out.append(
            f'<text x="{PLOT_LEFT + 12}" y="{top + 18 * index}" fill="{INK}">'
            f"{escape(_shorten(point.label, 80))} (chance-corrected {point.y_value:.3f})</text>"
        )
    return out


def _shorten(text: str, limit: int = 56) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"
