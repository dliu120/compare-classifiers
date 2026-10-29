# Liquid D1.1 comparison, 2026-10-28

D1.1 was evaluated against the previously recorded D1 on the published smoke and input-length
families. The requests used the same Case and Question identifiers for both models. The run
completed October 28 Pacific time (October 29 UTC).

## Model and pricing

Liquid's [decision-model documentation](https://docs.liquid.ai/lfm/models/decision-models)
describes D1.1 as a hosted decision model for text and images. Its
[D1 API guide](https://docs.liquid.ai/lfm/models/d1) uses model ID `d1.1` with the same System One endpoint.
Liquid documents input-token billing, but its [pricing page](https://www.liquid.ai/pricing)
does not list a separate D1.1 rate. Successful D1.1 responses in this run included a
vendor-reported `usage.cost`; their values are included as returned, not estimated from the
older D1 or D1 Ultra rates and not independently verified against an invoice. These responses
imply about $0.02/MTok, the same as the current listed legacy D1 input rate, but that is not a
separately published D1.1 price. The D1 smoke result's stored $0.32/1,000 estimate used the
prior $0.04/MTok D1 rate. Liquid's current page lists legacy D1 at $0.02/MTok, which would be
about $0.16/1,000 requests for the same reported input-token usage.

A live D1.1 request at the 64k target returned HTTP 422 with this limit: **65,536 tokens or
250,000 bytes of text per prompt**. This limit was observed in the API response; it was not
listed in the current model documentation.

## Smoke comparison

Both arms used 66 requests over four Families: 20 BANKING77 Cases, 20 synthetic routing Cases,
six 32k long-state Cases, and 20 rendered-image Cases. These contain 119 scored Questions. All
D1.1 requests returned HTTP 200; it had no Non-answers.

| Family | Questions | D1 right | D1.1 right | D1 median s | D1.1 median s |
|---|---:|---:|---:|---:|---:|
| BANKING77 | 20 | 19 | 16 | 0.21 | 0.16 |
| Routing synthetic | 60 | 57 | 56 | 0.22 | 0.17 |
| Long-state 32k | 12 | 12 | 12 | 1.58 | 1.41 |
| Rendered images | 27 | 27 | 27 | 0.29 | 0.20 |
| **Pooled** | **119** | **115** | **111** | **0.25** | **0.17** |

On paired Questions, both models were right on 110, D1 alone was right on five, D1.1 alone was
right on one, and both were wrong on three. D1.1's pooled API-reported cost was about $0.08 per
1,000 requests. D1's previously recorded estimate is $0.32 and is historical, not a current-rate
estimate. Liquid's public response example documents token counts but not `usage.cost`; the
numeric field is present in all 66 successful D1.1 smoke responses and 24 successful sweep
responses. Treat these amounts as vendor-reported, not independently billed totals. The harness
budget reserves $0 for unknown-price calls and may have concurrent requests in flight after
crossing its configured amount; it is not a hard spend cap for unpriced providers.

## Input-length sweep

Six deterministic Cases and 12 Questions were evaluated at each target. Each D1.1 request at
64k or above returned HTTP 422; these are limit rejections, not wrong answers by the model.

| State target | D1 right / Questions | D1.1 right / Questions | D1.1 HTTP 200 requests | D1.1 HTTP 422 requests |
|---|---:|---:|---:|---:|
| 8k | 12/12 | 12/12 | 6/6 | 0/6 |
| 16k | 10/12 | 12/12 | 6/6 | 0/6 |
| 24k | 11/12 | 12/12 | 6/6 | 0/6 |
| 32k | 12/12 | 12/12 | 6/6 | 0/6 |
| 64k | 0/12 | 0/12 | 0/6 | 6/6 |
| 128k | 0/12 | 0/12 | 0/6 | 6/6 |
| 256k | 0/12 | 0/12 | 0/6 | 6/6 |

The 8k–32k results are a single pass on synthetic ticket lists with one decisive ticket. They
do not establish general performance on arbitrary long documents. The 64k and larger inputs
exceed the API's observed token-or-byte limit. The sweep's pooled D1.1 cost is unknown because
the 18 rejected requests returned no reported cost; its 24 successful requests reported a total
of $0.01246.

## Artifacts and reproduction

- [Smoke report](../runs/report.md) and [input-length sweep report](../runs/input-cap-sweep/report.md).
- The sweep report's pooled D1.1 cost is `unknown` because 18 limit-rejected requests returned no cost; the 24 successful requests reported $0.01246 total.
- [Smoke SQLite results](../runs/bakeoff.sqlite) and [sweep SQLite results](../runs/input-cap-sweep/bakeoff.sqlite).
- [Smoke raw captures](../runs/raw/liquid-d1-1__banking77.jsonl.gz) and [sweep raw captures](../runs/input-cap-sweep/raw/liquid-d1-1__longstate-8k.jsonl.gz). The adjacent D1.1 captures use the same naming pattern.
- [Liquid Console D1.1 decision models](https://console.liquid.ai/docs/getting-started/d1.1#decision-models), [public model documentation](https://docs.liquid.ai/lfm/models/d1), and [pricing](https://www.liquid.ai/pricing).

To reproduce the smoke arm, configure `LIQUID_API_KEY` and run:

```sh
uv run bakeoff run -p liquid/d1.1 \
  -f routing-synthetic -f banking77 -f longstate-32k -f rendered-images \
  --limit 20 --runs-dir runs
```

To reproduce the full input-length arm, first generate the deterministic `longstate-*` Families
with `uv run bakeoff gen smoke --limit 20`, then run:

```sh
uv run bakeoff run -p liquid/d1.1 \
  -f longstate-8k -f longstate-16k -f longstate-24k -f longstate-32k \
  -f longstate-64k -f longstate-128k -f longstate-256k \
  --runs-dir runs/input-cap-sweep
```
