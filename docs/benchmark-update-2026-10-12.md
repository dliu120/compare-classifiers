# CLEF resumption and large-context sweep

Run on 2026-10-12 UTC (October 11 Pacific). This update fills the missing CLEF 8k–24k
cells and tests 512k, 768k, and 900k States. It does not rerun the smoke comparison or
the earlier 32k–256k sweep. Historical measurements and report snapshots are retained.

## CLEF: missing short-input cells

Six deterministic Cases per length, two Questions each; needles near 10%, 50%, and 90%.
All 36 new requests returned HTTP 200 on their first attempt, with no Non-answers.

| Provider | State target | Right / Questions | Wrong | Median s | Estimated $ / 1k requests |
|---|---|---|---|---|---|
| Clef | 8k | 12/12 | 0 | 1.45 | 2.2174 |
| Clef | 16k | 12/12 | 0 | 2.15 | 4.3700 |
| Clef | 24k | 12/12 | 0 | 3.14 | 6.5127 |
| Clef-flash | 8k | 12/12 | 0 | 2.34 | 0.8315 |
| Clef-flash | 16k | 12/12 | 0 | 4.03 | 1.6387 |
| Clef-flash | 24k | 9/12 | 3 | 5.48 | 2.1600 |

Clef-flash's three misses were at the late needle position:
`longstate-24k-p90-0` chose the wrong team and missed the data breach;
`longstate-24k-p90-1` chose the wrong team.
Known list-price estimate: **$0.10638246**, counted once per request.

The [updated sweep report](../runs/input-cap-sweep/report.md) now covers 84 Questions
for each CLEF variant: Clef 72 right, zero wrong usable answers, 12 historical
Non-answers at 256k; Clef-flash 69 right, three wrong usable answers, and those same
12 historical Non-answers. These pooled rows mix dates, so they are not fresh full sweeps.

## Large-context extension

The same seed-0 ticket generator produced six Cases at each new length. Each Case asks
which team should handle a named ticket and whether any ticket mentions a data breach.
Both references are assigned by construction; filler tickets never mention a breach.

| Nominal State target | Actual State tokens (`o200k_base`) | Luna Copilot reported input tokens on HTTP 200 |
|---|---|---|
| 512k | 512,004–512,067 | 512,462–512,524 |
| 768k | 768,006–768,062 | 768,463–768,522 |
| 900k | 900,004–900,041 | none; all rejected |

Own-build specs use `effort=none`, `mode=probabilities`, and `samples=1`, with neither
`max_in` nor `cap` set. Raw request metadata records `truncated=false`: the harness did
not cut the State to make it fit. Questions and system/schema overhead are additional
to State-only token counts. Vendor tokenizers may differ.

### Acceptance and accuracy are separate

All rows below have six attempted requests and 12 scored Questions.
Wrong counts usable but incorrect answers, separately from Non-answers.

| Provider / Route | State target | HTTP 200 | Right | Wrong | Non-answers | Outcome |
|---|---|---|---|---|---|---|
| Luna own build, Copilot | 512k | 6/6 | 12 | 0 | 0 | answered |
| Luna own build, Copilot | 768k | 6/6 | 10 | 2 | 0 | answered, two retrieval misses |
| Luna own build, Copilot | 900k | 0/6 | 0 | 0 | 12 | proxy 502, upstream 400 prompt limit |
| Clef | 512k | 0/6 | 0 | 0 | 12 | HTTP 413 |
| Clef | 768k | 0/6 | 0 | 0 | 12 | HTTP 413 |
| Clef | 900k | 0/6 | 0 | 0 | 12 | HTTP 413 |
| Clef-flash | 512k | 0/6 | 0 | 0 | 12 | HTTP 413 |
| Clef-flash | 768k | 0/6 | 0 | 0 | 12 | HTTP 413 |
| Clef-flash | 900k | 0/6 | 0 | 0 | 12 | HTTP 413 |
| OpenAI Decisions, Luna | 512k | 0/6 | 0 | 0 | 12 | HTTP 401, authentication-blocked |
| OpenAI Decisions, Luna | 768k | 0/6 | 0 | 0 | 12 | HTTP 401, authentication-blocked |
| OpenAI Decisions, Luna | 900k | 0/6 | 0 | 0 | 12 | HTTP 401, authentication-blocked |
| Luna own build, OpenAI direct | 512k | 0/6 | 0 | 0 | 12 | HTTP 401, authentication-blocked |
| Luna own build, OpenAI direct | 768k | 0/6 | 0 | 0 | 12 | HTTP 401, authentication-blocked |
| Luna own build, OpenAI direct | 900k | 0/6 | 0 | 0 | 12 | HTTP 401, authentication-blocked |

Copilot's 900k errors name an **872,000-token prompt limit**, for example:
`prompt token count of 900376 exceeds the limit of 872000`.
This establishes a rejection on that Route, not incorrect model reasoning.
The official [Luna model page](https://developers.openai.com/api/docs/models/gpt-6-luna)
lists a 922,000-token maximum input for OpenAI; authentication failures prevent testing
that limit here. HTTP 401 rows are retained for audit, but must not rank model quality.

Cloudflare's rejection errors name context limits of 65,536 for Clef and 24,576 for
Clef-flash. This differs from the earlier documented 65,536 for both. The errors and
historical results are observations, not proof of silent truncation or a changed model.

### Needle-position breakdown: Luna through Copilot

Each cell is Right / Questions: two Cases and four Questions per position.

| State target | Near 10% | Near 50% | Near 90% |
|---|---|---|---|
| 512k | 4/4 | 4/4 | 4/4 |
| 768k | 4/4 | 3/4 | 3/4 |
| 900k | 0/4, all Non-answers | 0/4, all Non-answers | 0/4, all Non-answers |

At 768k, `longstate-768k-p50-0` selected sales for a security ticket;
`longstate-768k-p90-0` selected shipping for a security ticket. Both were confident
wrong choices (selected-option probabilities 0.96 and 0.92). All six breach Questions
were correct. This is evidence of retrieval errors in this pass, not an exact quality
breakpoint between 512k and 768k.

### Latency and estimated cost

| Copilot State target | Median s | p95 s | Known estimated total | Estimated $ / 1k requests |
|---|---|---|---|---|
| 512k | 5.36 | 12.82 | $0.6152111 | 102.5352 |
| 768k | 9.30 | 16.57 | $0.9224408 | 153.7401 |
| 900k | 3.39 (rejections) | 4.94 | unknown | unknown |

The [full report](../runs/long-context-2026-10-12/report.md) retains calibration,
all failure rows, and request latency. Rejection latency is not successful retrieval
latency. Costs use reported usage and Standard list prices, not invoices or measured
cash spending. The [pricing page](https://developers.openai.com/api/docs/pricing) and
[Decisions guide](https://developers.openai.com/api/docs/guides/decisions#pricing-and-availability)
apply long-context multipliers above 272k: Luna input $0.20/M, cached input $0.02/M,
output $0.75/M; Decisions input $0.20/M and no output charge.
Copilot estimates retain the harness's same-list-rate convention; they are not a
verified Copilot invoice.

Known estimated cost for both parts of this update is **$1.64403436**. The 78
large-context failures reported no usage, so their costs stay unknown. The Cloudflare
pass initially stopped after 30 requests at its estimate budget; the resumption sent
the remaining six, without rerunning recorded failures. The Luna pass used a $10
estimate budget; the Cloudflare resumption used $5. No billing plan was changed.

## Evidence and reproduction

- [Input manifest](../runs/long-context-2026-10-12/input-manifest.json): actual token
  counts, State SHA-256 hashes, needle IDs/indices, Questions, and references.
- [SQLite results](../runs/long-context-2026-10-12/bakeoff.sqlite) and
  [raw gzip JSONL captures](../runs/long-context-2026-10-12/raw): request/response
  records for 90 large-context requests. HTTP 401 credential identifiers were removed
  from error text before archiving; status and authentication-failure meaning remain.
  Public archives also omit provider request IDs and unrelated account/provider metadata.
- [Run summaries](../runs/long-context-2026-10-12/run-summary.json): invocation
  counts, known cost, unknown-cost counts, and budget-stop/resumption receipts.

For direct Decisions and Cloudflare HTTP failures, the existing harness records the
canonical System One request rather than the adapter's exact wire body. The own-build
captures include the Responses wire body. HTTP status and returned error are observed
in both cases; canonical-input captures do not prove the exact failed wire serialization.

Generate only the three extended Families without replacing the existing smoke data:

```sh
uv run python - <<'PY'
from datetime import date
from pathlib import Path
from bakeoff.datasets.family import FamilyManifest, write_family
from bakeoff.datasets.longstate import build_longstate_cases

for target in (512_000, 768_000, 900_000):
    name = f"longstate-{target // 1000}k"
    cases = build_longstate_cases(target, family=name, seed=0)
    manifest = FamilyManifest(
        name=name, track="text",
        source="bakeoff.datasets.longstate (programmatic, seed 0)",
        license="synthetic; generated by this project, no third-party content",
        reference_kind="gold",
        generated_by="bakeoff.datasets.longstate.build_longstate_cases",
        created=date(2026, 10, 12),
    )
    write_family(Path("data/smoke"), manifest, cases)
PY
```

Use a **new results directory** for a fresh measurement; recorded Non-answers are also
skipped by resume. The first command runs the Route that was usable in this session;
the others require working credentials and have their own budget directories.

```sh
uv run bakeoff run -p 'ownbuild/copilot/gpt-6-luna?effort=none' \
  -f longstate-512k -f longstate-768k -f longstate-900k \
  --limit 6 --runs-dir runs/long-context-copilot-fresh --budget 5
uv run bakeoff run -p openai-decisions -p 'ownbuild/openai/gpt-6-luna?effort=none' \
  -f longstate-512k -f longstate-768k -f longstate-900k \
  --limit 6 --runs-dir runs/long-context-openai-fresh --budget 6
uv run bakeoff run -p cloudflare/clef -p cloudflare/clef-flash \
  -f longstate-512k -f longstate-768k -f longstate-900k \
  --limit 6 --runs-dir runs/long-context-clef-fresh --budget 5
uv run bakeoff report --runs-dir runs/long-context-copilot-fresh
```

## Interpretation limits

Six deterministic Cases per length, two related Questions each, one seed, one pass,
templated synthetic tickets, and a limited class mix. Needle position is a ticket-list
fraction, not an exact tokenizer-specific offset. HTTP acceptance does not establish
that a service attended to every input token. These tests measure named-ticket
retrieval and breach detection, not multi-step reasoning over arbitrary documents.
Routes were not controlled for cache state, load, or deployment version; do not infer
general speed or quality rankings from these measurements.
