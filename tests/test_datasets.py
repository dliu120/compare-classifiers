from __future__ import annotations

import io
import json
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image, PngImagePlugin

from bakeoff.datasets import images, longstate, public, rendered, smoke, synthetic, tokens
from bakeoff.datasets.case import load_family
from bakeoff.datasets.family import FamilyManifest, read_manifest, write_family, write_manifest
from tests.tokenizer import needs_tokenizer

# --- tokens -------------------------------------------------------------------------------------


@needs_tokenizer
def test_count_tokens_and_state_text():
    assert tokens.count_tokens("") == 0
    assert tokens.count_tokens("hello world") == 2
    assert tokens.count_tokens("<|endoftext|> is plain text here") > 0
    assert tokens.state_text("as is") == "as is"
    assert tokens.state_text({"b": [1, 2], "a": "x"}) == '{"b":[1,2],"a":"x"}'
    assert tokens.state_text(["é"]) == '["é"]'


@needs_tokenizer
def test_truncate_state_keeps_the_head():
    text = " ".join(f"word{i}" for i in range(200))
    head, cut = tokens.truncate_state(text, 25)
    assert cut is True
    assert text.startswith(head)
    assert 0 < tokens.count_tokens(head) <= 25
    same, cut = tokens.truncate_state(text, 10_000)
    assert cut is False and same is text
    structured = [{"id": i, "body": "some ticket text"} for i in range(50)]
    head, cut = tokens.truncate_state(structured, 20)
    assert cut is True and isinstance(head, str)
    assert tokens.state_text(structured).startswith(head)


# --- images -------------------------------------------------------------------------------------


def _png_with_metadata() -> bytes:
    image = Image.new("RGBA", (300, 200), (255, 0, 0, 255))
    image.putpixel((0, 0), (0, 0, 255, 0))  # one transparent pixel composites onto white
    info = PngImagePlugin.PngInfo()
    info.add_text("Comment", "secret comment")
    info.add_text("Author", "someone")
    exif = Image.Exif()
    exif[0x010F] = "ACME camera"
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", pnginfo=info, exif=exif, icc_profile=b"\x00" * 128)
    return buffer.getvalue()


def test_canonicalize_is_deterministic_and_strips_metadata(tmp_path: Path):
    source = _png_with_metadata()
    with Image.open(io.BytesIO(source)) as original:
        assert original.info.get("Comment") == "secret comment"
        assert "exif" in original.info and "icc_profile" in original.info
    data, sha = images.canonicalize(source)
    again, sha_again = images.canonicalize(source)
    path = tmp_path / "in.png"
    path.write_bytes(source)
    from_path, sha_path = images.canonicalize(path)
    assert data == again == from_path and sha == sha_again == sha_path
    assert len(sha) == 64
    with Image.open(io.BytesIO(data)) as canonical:
        assert canonical.mode == "RGB" and canonical.size == (300, 200)
        assert canonical.format == "PNG"
        assert not {"exif", "icc_profile", "Comment", "Author"} & set(canonical.info)
        assert canonical.getpixel((0, 0)) == (255, 255, 255)
        assert canonical.getpixel((10, 10)) == (255, 0, 0)
    assert b"secret comment" not in data and b"ACME" not in data


def test_canonicalize_caps_longest_side_and_keeps_aspect():
    buffer = io.BytesIO()
    Image.new("RGB", (3000, 1000), (0, 128, 0)).save(buffer, format="PNG")
    data, _ = images.canonicalize(buffer.getvalue())
    with Image.open(io.BytesIO(data)) as canonical:
        assert canonical.size == (1440, 480)
    buffer = io.BytesIO()
    Image.new("L", (100, 1440), 7).save(buffer, format="PNG")
    data, _ = images.canonicalize(buffer.getvalue())
    with Image.open(io.BytesIO(data)) as canonical:
        assert canonical.size == (100, 1440) and canonical.mode == "RGB"


def test_canonicalize_falls_back_to_jpeg_when_png_exceeds_3mib():
    noise = np.random.default_rng(0).integers(0, 256, (1440, 1440, 3), dtype=np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(noise).save(buffer, format="PNG")
    data, _ = images.canonicalize(buffer.getvalue())
    assert images.mime_type(data) == "image/jpeg"
    assert len(data) < images.PNG_BYTE_LIMIT
    assert images.data_url(data).startswith("data:image/jpeg;base64,")


def test_write_image_and_data_url(tmp_path: Path):
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (1, 2, 3)).save(buffer, format="PNG")
    data, sha = images.canonicalize(buffer.getvalue())
    relative = images.write_image(tmp_path, data, sha)
    assert relative == f"images/{sha}.png"
    assert (tmp_path / relative).read_bytes() == data
    assert images.data_url(data).startswith("data:image/png;base64,")
    with pytest.raises(ValueError):
        images.mime_type(b"not an image")


# --- family manifest ----------------------------------------------------------------------------


def test_manifest_round_trip(tmp_path: Path):
    manifest = FamilyManifest(
        name="demo",
        track="text",
        source="unit test",
        license="cc-by-4.0",
        reference_kind="gold",
        generated_by="tests",
        created=date(2026, 10, 6),
        notes=None,
    )
    write_manifest(manifest, tmp_path)
    raw = json.loads((tmp_path / "family.json").read_text())
    assert raw["created"] == "2026-10-06" and raw["reference_kind"] == "gold"
    assert set(raw) == {
        "name",
        "track",
        "source",
        "license",
        "reference_kind",
        "generated_by",
        "created",
        "notes",
    }
    assert read_manifest(tmp_path) == manifest


@needs_tokenizer
def test_write_family_rejects_foreign_cases(tmp_path: Path):
    manifest = FamilyManifest(
        name="demo",
        track="text",
        source="unit test",
        license="x",
        reference_kind="gold",
        created=date(2026, 10, 6),
    )
    cases = longstate.build_longstate_cases(
        600, family="other", positions=(0.5,), per_position=1, seed=1
    )
    with pytest.raises(ValueError):
        write_family(tmp_path, manifest, cases)


# --- longstate ----------------------------------------------------------------------------------


@needs_tokenizer
@pytest.mark.parametrize("target", [4_000, 32_000])
def test_longstate_hits_targets_and_needle_gold(target: int):
    cases = longstate.build_longstate_cases(target, family="longstate-test", seed=7)
    assert len(cases) == 6
    assert sorted(case.meta["position"] for case in cases) == [0.1, 0.1, 0.5, 0.5, 0.9, 0.9]
    assert sum(case.reference["mentions_breach"].noul for case in cases) == 3
    assert len({case.id for case in cases}) == 6
    for case in cases:
        assert case.approx_tokens == tokens.count_tokens(tokens.state_text(case.state))
        assert abs(case.approx_tokens - target) / target <= 0.05
        assert isinstance(case.state, list) and case.meta["ticket_count"] == len(case.state)
        needle_id = case.meta["needle_id"]
        hits = [i for i, ticket in enumerate(case.state) if ticket["id"] == needle_id]
        assert hits == [case.meta["needle_index"]]
        assert abs(hits[0] / (len(case.state) - 1) - case.meta["position"]) < 0.02
        assert needle_id in case.questions["team"].instructions
        needle = case.state[hits[0]]
        breach = case.reference["mentions_breach"].noul
        assert ("data breach" in needle["body"]) is breach
        others = [t for i, t in enumerate(case.state) if i != hits[0]]
        assert not any("breach" in json.dumps(t).lower() for t in others)
        team = case.reference["team"].choice
        assert team in case.questions["team"].criteria and team == case.meta["team"]
        assert (team == "security") is breach
        assert len({t["id"] for t in case.state}) == len(case.state)


@needs_tokenizer
def test_longstate_is_deterministic_and_seed_sensitive():
    first = longstate.build_longstate_cases(3_000, family="f", positions=(0.5,), seed=3)
    second = longstate.build_longstate_cases(3_000, family="f", positions=(0.5,), seed=3)
    third = longstate.build_longstate_cases(3_000, family="f", positions=(0.5,), seed=4)
    assert [c.model_dump() for c in first] == [c.model_dump() for c in second]
    assert first[0].state != third[0].state
    assert set(longstate.TARGETS) == {
        "longstate-8k",
        "longstate-16k",
        "longstate-24k",
        "longstate-32k",
        "longstate-64k",
        "longstate-128k",
        "longstate-256k",
    }
    manifest = longstate.manifest("longstate-32k", date(2026, 10, 6))
    assert manifest.reference_kind == "gold" and "32000" in manifest.notes


# --- rendered -----------------------------------------------------------------------------------


@needs_tokenizer
def test_rendered_gold_consistency_and_determinism(tmp_path: Path):
    first_dir, second_dir = tmp_path / "a", tmp_path / "b"
    cases = rendered.build_rendered_cases(first_dir, count=9, seed=5)
    again = rendered.build_rendered_cases(second_dir, count=9, seed=5)
    assert [c.model_dump() for c in cases] == [c.model_dump() for c in again]
    assert [case.meta["kind"] for case in cases] == list(rendered.KINDS) * 3
    for case in cases:
        assert case.track == "image" and case.image_path.startswith("images/")
        path = first_dir / case.image_path
        assert path.is_file()
        data = path.read_bytes()
        assert images.canonicalize(data)[1] == case.image_sha256
        assert set(case.questions) == set(case.reference)
        match case.meta["kind"]:
            case "receipt":
                assert case.reference["above_1000"].noul is (case.meta["total"] > 1000)
                assert not 900 <= case.meta["total"] <= 1100
                assert case.reference["currency"].choice == case.meta["currency"]
                assert case.meta["currency"] in case.questions["currency"].criteria
            case "ui":
                highlighted = case.reference["highlighted"].choice
                assert highlighted == case.meta["highlighted"]
                assert highlighted in case.questions["highlighted"].criteria
                assert set(case.questions["highlighted"].criteria) == set(case.meta["buttons"])
            case "color":
                dominant = case.reference["color"].choice
                with Image.open(path) as image:
                    counts = {rgb: n for n, rgb in image.getcolors(maxcolors=4096)}
                share = counts.get(rendered.PALETTE[dominant], 0) / (image.width * image.height)
                assert share >= 0.6
                if case.meta["secondary"]:
                    assert counts[rendered.PALETTE[case.meta["secondary"]]] > 0
    assert len({case.image_sha256 for case in cases}) == 9
    assert rendered.manifest(date(2026, 10, 6)).track == "image"


# --- synthetic ----------------------------------------------------------------------------------

AUTHORED: list[dict[str, Any]] = [
    {
        "state": "Order 1234 never arrived and tracking is stuck.",
        "department": "shipping",
        "is_urgent": True,
        "frustration": "frustrated",
    },
    {
        "state": "Why was I charged $49 twice this month?",
        "department": "billing",
        "is_urgent": False,
        "frustration": "calm",
    },
    {
        "state": "The app crashes with error E42 when I open settings.",
        "department": "technical",
        "is_urgent": False,
        "frustration": "calm",
    },
    {
        "state": "Do you offer a discount for 30 seats on the Team plan?",
        "department": "sales",
        "is_urgent": False,
        "frustration": "calm",
    },
    {
        "state": "I want to speak to someone about your careers page.",
        "department": "other",
        "is_urgent": False,
        "frustration": "calm",
    },
    {
        "state": "My package came crushed and the hub inside is broken!",
        "department": "shipping",
        "is_urgent": True,
        "frustration": "angry",
    },
    {
        "state": "Please cancel my renewal before Friday.",
        "department": "billing",
        "is_urgent": True,
        "frustration": "calm",
    },
    {
        "state": "SSO login loops back to the sign-in page since yesterday.",
        "department": "technical",
        "is_urgent": True,
        "frustration": "frustrated",
    },
    {
        "state": "Can I get a quote for the Business plan for 12 people?",
        "department": "sales",
        "is_urgent": False,
        "frustration": "calm",
    },
    {
        "state": "order 5678 NEVER arrived, and tracking is stuck!!!",
        "department": "shipping",
        "is_urgent": True,
        "frustration": "angry",
    },  # near-duplicate of the first ticket
]


def _fake_generator(disagree_on: set[int], fail_batches: set[int] = frozenset()):
    calls: list[dict[str, Any]] = []
    batches = {"count": 0}

    async def generate(body: dict[str, Any]) -> dict[str, Any]:
        calls.append(body)
        assert body["text"]["format"]["type"] == "json_schema"
        if body["model"] == synthetic.AUTHOR_MODEL:
            batch = batches["count"]
            batches["count"] += 1
            if batch in fail_batches:
                raise ValueError("model returned prose")
            return {"cases": AUTHORED}
        assert body["model"] == synthetic.JUDGE_MODEL
        prompt = body["input"][0]["content"][0]["text"]
        assert all(item["state"] in prompt for item in AUTHORED)
        answers = []
        for index, item in enumerate(AUTHORED, start=1):
            department = "other" if index in disagree_on else item["department"]
            answers.append(
                {
                    "index": index,
                    "department": department,
                    "is_urgent": False,
                    "frustration": "calm",
                }
            )
        return {"answers": answers}

    return generate, calls


@needs_tokenizer
async def test_synthetic_keeps_only_agreed_distinct_cases():
    generate, calls = _fake_generator(disagree_on={2, 6})
    result = await synthetic.generate_routing_cases(generate, target=40, max_batches=1)
    assert result.batches == 1 and result.failures == 0 and result.authored == 10
    assert result.disagreed == 2 and result.duplicates == 1 and result.unjudged == 0
    assert len(result.cases) == 7
    assert [body["model"] for body in calls] == [synthetic.AUTHOR_MODEL, synthetic.JUDGE_MODEL]
    first = result.cases[0]
    assert first.family == synthetic.FAMILY and first.id == "routing-synthetic-000"
    assert set(first.questions) == {"department", "is_urgent", "frustration"}
    assert first.reference["department"].choice == "shipping"
    assert first.reference["department"].kind == "silver"
    assert synthetic.AUTHOR_MODEL in first.reference["department"].source
    assert synthetic.JUDGE_MODEL in first.reference["department"].source
    assert first.reference["is_urgent"].noul is True
    assert first.reference["frustration"].score == 1
    judge = {"department": "shipping", "is_urgent": False, "frustration": "calm"}
    assert first.meta["judge"] == judge
    assert first.approx_tokens == tokens.count_tokens(first.state)
    states = [case.state for case in result.cases]
    assert not any("charged $49" in state or "crushed" in state for state in states)
    assert states[0] == AUTHORED[0]["state"] and AUTHORED[-1]["state"] not in states


@needs_tokenizer
async def test_synthetic_stops_at_target_and_survives_failed_batches():
    generate, _ = _fake_generator(disagree_on=set(), fail_batches={1})
    result = await synthetic.generate_routing_cases(generate, target=5, max_batches=3)
    assert len(result.cases) == 5 and result.batches == 1
    generate, _ = _fake_generator(disagree_on=set(), fail_batches={0})
    result = await synthetic.generate_routing_cases(generate, target=5, max_batches=3)
    assert result.failures == 1 and result.batches == 1 and result.cases == []
    generate, _ = _fake_generator(disagree_on=set(), fail_batches={1})
    result = await synthetic.generate_routing_cases(generate, target=12, max_batches=3)
    assert result.failures == 1 and result.batches == 3
    assert len(result.cases) == 9  # 9 distinct in the first batch; the third repeats them all
    assert result.duplicates == 1 + 10


def test_synthetic_parsing_helpers():
    fenced = '```json\n{"cases": []}\n```'
    assert synthetic.parse_json_object(fenced) == {"cases": []}
    assert synthetic.parse_json_object('Sure! {"a": 1} hope this helps') == {"a": 1}
    with pytest.raises(ValueError):
        synthetic.parse_json_object("no json here")
    with pytest.raises(TypeError):
        synthetic.parse_json_object("[1, 2]")
    response = {
        "status": "completed",
        "output": [
            {"type": "reasoning"},
            {"type": "message", "content": [{"type": "output_text", "text": '{"x": 1}'}]},
        ],
    }
    assert synthetic.output_text(response) == '{"x": 1}'
    with pytest.raises(ValueError):
        synthetic.output_text({"status": "incomplete", "incomplete_details": {"reason": "max"}})
    with pytest.raises(ValueError):
        synthetic.output_text(
            {"output": [{"type": "message", "content": [{"type": "refusal", "refusal": "no"}]}]}
        )
    assert synthetic.normalize_state("Order #1234 NEVER arrived!!") == "order never arrived"
    manifest = synthetic.manifest(date(2026, 10, 6))
    assert synthetic.AUTHOR_MODEL in manifest.generated_by
    assert synthetic.JUDGE_MODEL in manifest.generated_by
    assert manifest.reference_kind == "silver"


def test_synthetic_request_bodies_follow_the_responses_api():
    body = synthetic.author_request(0, 5, 10)
    assert body["model"] == synthetic.AUTHOR_MODEL
    assert body["input"][0]["role"] == "user"
    assert body["input"][0]["content"][0]["type"] == "input_text"
    assert body["text"]["format"]["strict"] is True
    assert body["text"]["format"]["schema"]["properties"]["cases"]["items"]["required"] == [
        "state",
        "department",
        "is_urgent",
        "frustration",
    ]
    prompt = body["input"][0]["content"][0]["text"]
    assert "exactly 10 tickets" in prompt and "exactly 2 tickets for each department" in prompt
    judge = synthetic.judge_request(["one", "two"])
    assert judge["model"] == synthetic.JUDGE_MODEL
    assert "1. one\n2. two" in judge["input"][0]["content"][0]["text"]


# --- public loaders (offline fake) --------------------------------------------------------------

BANK_LABELS = ["activate_my_card", "card_arrival", "reverted_card_payment?"]
CLINC_LABELS = ["weather", "oos", "transfer"]


def _fake_fetch(spec: public.PublicDataset, cache: Path) -> public.Table:
    assert cache.name == "_cache"
    if spec is public.BANKING77:
        rows = [{"text": f"bank query {i}", "label": BANK_LABELS[i % 3]} for i in range(12)]
        return public.Table(rows, {"label": BANK_LABELS})
    if spec is public.CLINC150:
        rows = [{"text": f"clinc query {i}", "intent": CLINC_LABELS[i % 3]} for i in range(12)]
        return public.Table(rows, {"intent": CLINC_LABELS})
    assert spec is public.WHEN2CALL
    tool = json.dumps({"name": "get_weather", "parameters": {"city": "string"}})
    rows = [
        {
            "uuid": f"u{i}",
            "source": "BFCL",
            "source_id": f"s{i}",
            "target_tool": None,
            "question": f"question {i}",
            "tools": [tool, "not json"],
            "correct_answer": ["tool_call", "request_for_info", "cannot_answer"][i % 3],
        }
        for i in range(12)
    ]
    return public.Table(rows)


@needs_tokenizer
def test_public_loaders_with_fake_fetch(tmp_path: Path):
    bank = public.load_banking77(tmp_path, 5, 1, fetch=_fake_fetch)
    assert len(bank) == 5 and [c.id for c in bank] == sorted(c.id for c in bank)
    assert bank == public.load_banking77(tmp_path, 5, 1, fetch=_fake_fetch)
    assert bank != public.load_banking77(tmp_path, 5, 2, fetch=_fake_fetch)
    assert len(public.load_banking77(tmp_path, None, 0, fetch=_fake_fetch)) == 12
    case = bank[0]
    assert case.family == "banking77" and case.track == "text"
    question = case.questions["intent"]
    assert list(question.criteria) == BANK_LABELS and set(question.criteria.values()) == {None}
    assert case.reference["intent"].kind == "gold"
    assert case.reference["intent"].choice == BANK_LABELS[case.meta["source_index"] % 3]
    assert case.approx_tokens == tokens.count_tokens(case.state)

    clinc = public.load_clinc150(tmp_path, 4, 0, fetch=_fake_fetch)
    assert len(clinc) == 4
    criteria = clinc[0].questions["intent"].criteria
    assert criteria["oos"] and criteria["weather"] is None

    w2c = public.load_when2call(tmp_path, 3, 0, fetch=_fake_fetch)
    assert len(w2c) == 3
    case = w2c[0]
    assert set(case.state) == {"question", "tools"}
    assert case.state["tools"][0] == {"name": "get_weather", "parameters": {"city": "string"}}
    assert case.state["tools"][1] == "not json"
    assert set(case.questions["response_type"].criteria) == {
        "direct",
        "tool_call",
        "request_for_info",
        "cannot_answer",
    }
    assert case.reference["response_type"].kind == "silver"
    assert case.meta["uuid"].startswith("u")

    manifest = public.manifest("banking77", date(2026, 10, 6))
    assert manifest.license == "cc-by-4.0" and "legacy-datasets/banking77" in manifest.source
    assert public.manifest("when2call", date(2026, 10, 6)).reference_kind == "silver"
    assert public.manifest("clinc150", date(2026, 10, 6)).license == "cc-by-3.0"
    directory = write_family(tmp_path, manifest, bank)
    assert load_family(tmp_path, "banking77") == bank
    assert read_manifest(directory).name == "banking77"


@needs_tokenizer
def test_public_loader_rejects_label_outside_options(tmp_path: Path):
    def bad_fetch(spec: public.PublicDataset, cache: Path) -> public.Table:
        return public.Table([{"text": "x", "label": "unknown"}], {"label": BANK_LABELS})

    with pytest.raises(ValueError):
        public.load_banking77(tmp_path, None, 0, fetch=bad_fetch)


# --- smoke --------------------------------------------------------------------------------------


@needs_tokenizer
def test_build_smoke_offline_with_fakes(tmp_path: Path, settings):
    generate, _ = _fake_generator(disagree_on=set())
    written = smoke.build_smoke(
        tmp_path,
        settings,
        limit=2,
        created=date(2026, 10, 6),
        fetch=_fake_fetch,
        generate=generate,
    )
    assert written == [
        "banking77",
        "when2call",
        "clinc150",
        "routing-synthetic",
        "longstate-8k",
        "longstate-16k",
        "longstate-24k",
        "longstate-32k",
        "longstate-64k",
        "longstate-128k",
        "longstate-256k",
        "rendered-images",
    ]
    assert (tmp_path / ".gitignore").read_text().splitlines() == ["_cache/", "longstate-*/"]
    for family in written:
        cases = load_family(tmp_path, family)
        manifest = read_manifest(tmp_path / family)
        assert manifest.name == family and manifest.created == date(2026, 10, 6)
        assert 1 <= len(cases) <= 2, family
        assert all(case.family == family for case in cases)
    assert len(load_family(tmp_path, "longstate-256k")) == 2  # 1 per position, capped at limit
    assert load_family(tmp_path, "longstate-256k")[0].approx_tokens > 240_000
    assert (tmp_path / "rendered-images" / "images").is_dir()


@needs_tokenizer
def test_build_smoke_skips_a_public_family_that_fails(tmp_path: Path, settings):
    def flaky_fetch(spec: public.PublicDataset, cache: Path) -> public.Table:
        if spec is public.WHEN2CALL:
            raise ConnectionError("hub unreachable")
        return _fake_fetch(spec, cache)

    async def no_generator(body: dict[str, Any]) -> dict[str, Any]:
        raise ConnectionError("aiproxy down")

    written = smoke.build_smoke(
        tmp_path,
        settings,
        limit=1,
        created=date(2026, 10, 6),
        fetch=flaky_fetch,
        generate=no_generator,
    )
    assert "when2call" not in written and "routing-synthetic" not in written
    assert "banking77" in written and "rendered-images" in written
    assert not (tmp_path / "when2call").exists()
