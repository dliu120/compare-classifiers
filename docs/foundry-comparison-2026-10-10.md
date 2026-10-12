# Microsoft-Decision-1 Foundry comparison, 2026-10-10

## Executive summary

**On the 40 shared short-text Cases (80 Questions), Microsoft-Decision-1 scored 74/80
(92.5%) versus 75/80 (93.75%) for a fresh GPT-6 Luna own-build run through Copilot.**
Its measured short-text median was 0.27 s versus 3.86 s; estimated list-price cost was
$0.0171 versus $0.2634 per 1,000 requests. In this sample that is about 14.5x lower median
latency and 15.4x lower estimated cost, not a general performance or savings guarantee.

The one-question accuracy difference is not evidence of a reliable winner. Paired
question-row bootstrap difference (Foundry minus own build): -0.0125, 95% interval
[-0.0625, +0.0250]; McNemar wins/losses 1/2, p=1.0. Questions from one Case are correlated,
so these exploratory row-level statistics are not a production significance claim.

**Coverage is the larger trade-off:** Microsoft-Decision-1 is text-only and rejected this
dataset's 24k-and-larger States. On the full 119-question smoke set it scored 74/119
(62.2% overall, 92.5% answered-only), with 39 Non-answers. GPT-6 Luna answered all 119 and
scored 112/119 (94.1%). Do not compare answered-only quality as if supported inputs matched.

[Use the deployed API](foundry-api.md): `POST` to the resource's
`/providers/microsoft/v1/systemone` route with model alias `decision-1` and an authorized
Entra token. Authenticated Choice, Noul, and Score returned HTTP 200; no-token access
returned HTTP 401. Local/API-key authentication is disabled.

## Shared short-text results

BANKING77 contributes 20 Gold Questions; `routing-synthetic` contributes 60 Silver
Questions from 20 Cases. Every provider in this table answered the same 80 Questions.
Medians and costs deduplicate requests: 40 requests, not 80. ECE and Brier use the
harness-recomputed probabilities and answered Questions.

| Provider | Correct | Accuracy | Median s | p95 s | Estimated $ per 1k requests | ECE | Brier |
|---|---|---|---|---|---|---|---|
| Microsoft-Decision-1 (Foundry), Oct 10 | 74/80 | 0.925 | 0.27 | 0.40 | $0.0171 | 0.053 | 0.118 |
| GPT-6 Luna own build (Copilot, effort none), Oct 10 | 75/80 | 0.938 | 3.86 | 5.58 | $0.2634 | 0.050 | 0.100 |
| Jev 1.13.0, Oct 7 | 73/80 | 0.912 | 0.10 | 0.30 | $0.0329 | 0.070 | 0.129 |
| OpenAI Decisions GPT-6 Luna, Oct 8 | 73/80 | 0.912 | 0.14 | 0.41 | $0.0589 | 0.058 | 0.100 |
| Cloudflare Clef, Oct 8 | 78/80 | 0.975 | 0.53 | 0.78 | $0.2181 | 0.075 | 0.040 |
| Cloudflare Clef-flash, Oct 8 | 76/80 | 0.950 | 0.25 | 0.82 | $0.0818 | 0.094 | 0.100 |
| Liquid d1, Oct 8 | 76/80 | 0.950 | 0.22 | 0.44 | $0.0169 | 0.066 | 0.102 |
| GPT-6 Luna own build (OpenAI, effort none), Oct 8 | 74/80 | 0.925 | 4.68 | 8.77 | $0.2629 | 0.055 | 0.128 |

The Oct 7–8 rows are preserved historical measurements, not rerun services. The Oct 10
own build was rerun through the existing local aiproxy with two concurrent requests.
Foundry was paced at 30 requests/minute with one in flight. Final Foundry measurement
followed the own-build run after a latency-accounting correction; this is not a synchronized
load, cold-cache, or equal-concurrency test. All use the same canonical System One States,
Questions, and references; own-build wire prompts necessarily include its emulation schema.

## Full smoke coverage

Actual counts are **66 Cases and 119 question rows per provider**: routing 20/60, BANKING77
20/20, longstate-32k 6/12, and rendered-images 20/27 (Cases/Questions). The nominal
`--limit 20` is a cap, not a claim that every Family contains 20 Cases.

Right and Wrong count usable answers; Non-answers count Questions with no usable answer.
The three counts sum to Questions. Accuracy includes Non-answers in its denominator;
answered accuracy excludes them.

| Provider | Questions | Right | Wrong | Non-answers | Accuracy | Answered acc. | Median s, all sent requests | Overall cost |
|---|---|---|---|---|---|---|---|---|
| Microsoft-Decision-1 (Foundry) | 119 | 74 | 6 | 39 | 0.622 | 0.925 | 0.27 | unknown |
| GPT-6 Luna own build (Copilot, effort none) | 119 | 112 | 7 | 0 | 0.941 | 0.941 | 2.25 | $0.4850 per 1k requests |

- Foundry routing: 58/60. BANKING77: 16/20.
- Foundry longstate-32k: 12 Non-answers from 6 HTTP 422 context-limit responses.
- Foundry images: 27 `unsupported_modality` Non-answers from 20 Cases, rejected locally;
  no images were sent to the service and no inference charge was estimated for them.
- Overall Foundry cost stays **unknown** because six rejected requests reported no usage.
  Its $0.0171 short-text estimate must not be presented as a full-smoke cost.
- Median includes actual HTTP rejections, not just successful decisions. Pacing waits
  were excluded from both successful and failed request latency; no-token and retry
  branches are covered by focused tests, not a production traffic test.

## Input-length sweep

Six deterministic Cases per length, two Gold-by-construction Questions each, seed 0,
needle at 10%, 50%, or 90%. Regenerated States were checked against historical raw inputs
before sending. Input sizes are `o200k_base` State counts, not Foundry's full-prompt tokenizer.

| State target | Correct / Questions | HTTP result | Median s | Estimated $ per 1k requests |
|---|---|---|---|---|
| 8k | 12/12 | 200 | 0.54 | $0.3845 |
| 16k | 12/12 | 200 | 0.67 | $0.7659 |
| 24k | 0/12 | 422 | 0.54 | unknown |
| 32k | 0/12 | 422 | 0.55 | unknown |
| 64k | 0/12 | 422 | 0.84 | unknown |
| 128k | 0/12 | 422 | 0.39 | unknown |
| 256k | 0/12 | 422 | 0.48 | unknown |

All 24k, 32k, and 64k responses said the per-Question prompt exceeded the 32,768-token
context including the decision token. At 128k and 256k the request-level validator instead
reported a 64,000-token State-plus-Questions limit. No response from these rejected inputs
contained a usable Answer. The 8k and 16k States produced 24/24 correct Answers.
The tested usable range is therefore between 16k and 24k of **these proxy-counted States**;
it is not a new universal model limit. The report's `Over cap` column can still show zero
at 24k/32k because it compares the proxy State count to the documented full-prompt limit.

Against the preserved sweep, Jev also answered 8k/16k and rejected 24k+. OpenAI Decisions
answered all seven lengths; Liquid d1 answered 8k–32k with some errors and rejected 64k+.
Cloudflare's 8k–24k cells remain unrun. See the updated
[full sweep table](../runs/input-cap-sweep/report.md#sweeps).

## Repeatability and limits

Three same-input Foundry short-text passes scored **73/80, 73/80, and 74/80**. On
`routing-synthetic-010/is_urgent`, the first two probabilities were just above 0.5, while
the final pass was 0.4688. That crossed the Noul scoring threshold and changed correctness.
The published main and comparison tables use the final corrected-latency pass, not the
best selected Question from each pass. The prior-pass witness is retained in
[`runs/foundry-repeatability.json`](../runs/foundry-repeatability.json). This is a concrete
variation observation, not proof of its cause or a broad model-stability rate.

Other limitations:
- Smoke-scale and partly synthetic/Silver data; BANKING77 has only 20 Questions here.
- No current credential was configured for the other hosted providers; their archived
  results are explicitly historical. Only GPT-6 Luna own build was freshly rerun.
- Network latency is from this Mac to Azure and Copilot, not server-only inference time.
- Foundry observed model name, endpoint, deployment, SKU, and allocation are time-bound.
  ARM reported Preview with an inference-deprecation date while the public catalog listed
  GA; neither proves a production support guarantee.
- Prices are $0.042/M input for Foundry and existing harness list prices for others,
  including reported caching where available. Output is free for Foundry despite nonzero
  output usage. These are not Azure invoices or controlled cache/cost comparisons.
- The final published Foundry smoke and sweep have $0.000684894 and $0.006902658 known
  estimated spend, respectively; 36 rejected requests have unknown usage/cost. These are
  retained-run costs, not total session cost: repeat passes and probes also made calls.
- The Entra token must be renewed after expiry. No automatic renewal or production
  load/availability test is claimed. No production decision workflow was deployed.

## Evidence and reproduction

- [Generic deployment setup, authentication, and usage example](foundry-api.md).
- [Sanitized three-type live smoke](../runs/foundry-live-smoke.json).
  Deployment inventory and account identifiers are intentionally excluded.
- [Full fresh-comparison report](../runs/foundry-comparison/report.md),
  [machine-readable summary](../runs/foundry-comparison/summary.json), and
  [exact input manifest](../runs/foundry-comparison/input-manifest.json).
- Updated combined [smoke report](../runs/report.md) and
  [input-cap sweep report](../runs/input-cap-sweep/report.md).
- SQLite scored rows and compressed raw requests/responses are retained beside each report.
  Historical non-Foundry rows and run metadata were checked unchanged against the base.
- `uv run pytest -q`, `uv run ruff check .`, and targeted formatting checks cover the
  adapter, credential handling, pacing/latency, errors, resource lifetime, and report labels.

Repeat with a new runs directory after setting the Foundry variables in the API guide:

```sh
uv run bakeoff run -p foundry -p 'ownbuild/copilot/gpt-6-luna?effort=none' \
  -f routing-synthetic -f banking77 -f longstate-32k -f rendered-images \
  --limit 20 --budget 2 --runs-dir runs/my-fresh-comparison
uv run bakeoff report --runs-dir runs/my-fresh-comparison
```
