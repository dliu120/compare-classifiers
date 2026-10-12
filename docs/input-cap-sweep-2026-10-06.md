# Input-cap sweep, 2026-10-06 to 2026-10-08

## Executive summary

**For this long-input retrieval benchmark, gpt-6-luna (OpenAI Decisions) was the fastest
configuration that answered every question correctly across all seven lengths.** The own
build at a 256k input cap matched its accuracy on both Routes, with lower estimated
list-price cost but higher median latency. This is a result for this sweep, not a general
best-classifier claim.

The three configurations tied at **84/84 correct, with no Non-answers**, on the same
8k–256k sweep (42 requests, two Questions per request):

| Provider | Input cap | Median s | Estimated $ per 1k requests |
|---|---|---|---|
| gpt-6-luna (OpenAI Decisions) | n/a | 0.66 | $7.5807 |
| gpt-6-luna (copilot) | 256000 | 2.27 | $6.2783 |
| gpt-6-luna (openai) | 256000 | 2.36 | $6.3596 |

Both own-build rows use reasoning effort `none`. Their medians measure requests that
returned correct answers; this is a comparison within the fully correct, full-sweep subset.
See [Overall](#overall) for every configuration and [Sweeps](#sweeps) for accuracy by length.

- **Fast rejection is not fast classification.** jev-1.13.0 had the lowest pooled median
  (0.22 s), but 71.4% Non-answers and 28.6% accuracy: it rejected every tested length from
  24k upward. d1 (Liquid)'s 0.68 s pooled median likewise includes rejections; it had 53.6%
  accuracy and 42.9% Non-answers. These are not successful-only latency figures.
- **Smaller input caps trade evidence for cost.** The lowest known full-sweep cost was
  gpt-6-luna (copilot) at 32k: $1.9199 per 1k requests, but only 84.5% accuracy. Its 64k cap
  reached 91.7% at $2.9113. The own build keeps only the State's head, so a lower cap can
  remove the decisive ticket; cheaper does not mean equivalent quality.
- **Cloudflare has incomplete coverage.** clef (Cloudflare) and clef-flash (Cloudflare)
  each scored 36/36 at 32k–128k, then returned HTTP 413 for all 256k requests. Their overall
  rows cover only 48 Questions, not 84; the unrun 8k–24k cells are missing evidence, not
  failures. Do not rank those pooled results as if coverage were equal.

**Interpretation limits.** These are deterministic, templated synthetic tickets with
[references assigned by construction](../src/bakeoff/datasets/longstate.py), not human
production examples or the separate model-generated `routing-synthetic` Family. Six Cases
per length and two related Questions per Case give narrow evidence: template, class mix,
and input-length selection can affect rankings. The sweep weights lengths equally, which
need not match production traffic. Sizes use the harness's `o200k_base` tokenizer, not
necessarily a vendor's tokenizer; slight size overshoots explain the diagonal cap markers.

Costs are [estimates from reported usage and the harness's list prices](../src/bakeoff/pricing.py),
including reported cached-input discounts—not invoices, guaranteed savings, or a controlled
cold-cache comparison. Unknown costs are not zero. Before choosing a Provider or cap,
validate the tradeoff on representative inputs and their actual length distribution.

## Setup and per-vendor observations

Accuracy by State length over the `longstate-*` Families at 8k, 16k, 24k, 32k, 64k, 128k,
and 256k tokens (6 Cases per length, 2 Questions each: which team handles the needle ticket,
and whether any ticket mentions a data breach; needle at 10%, 50%, or 90% of the State).
Providers: Jev, Liquid d1, Cloudflare Clef and Clef-flash, OpenAI Decisions, and the own
build on both Routes (GPT-6 Luna, reasoning effort none, no output cap) at input caps of
32k, 64k, 128k, and 256k. The own build keeps the head of the State when it exceeds its cap,
so a needle past the cap is cut.

What each vendor did. Jev answered 8k and 16k perfectly and rejected 24k and above with HTTP
400 `max_tokens_exceeded`, so its usable limit sits between 16k and 24k of our tokens despite
the documented 32k. Liquid d1 missed two needles at 16k and one at 24k, then rejected 64k and
above with HTTP 422 naming a 65,536-token or 250 KB per-question limit. Cloudflare Clef and
Clef-flash answered 32k to 128k perfectly while reporting about 143k input tokens at 128k,
despite a documented 65,536 window, slowed to 20 to 60 seconds per request there, and were
rejected at 256k with HTTP 413; their 8k to 24k cells are empty because the account's free
daily allowance of 10,000 neurons was used up before those rows could run. OpenAI Decisions
answered every length correctly in about a second. The own build was perfect whenever its cap
covered the State. The generated Families overshoot their nominal size by a few dozen tokens,
so the own build's diagonal cells carry a `*` for that trim. Spend: $0.64 for the own build
via Copilot, $0.94 for OpenAI Decisions and the OpenAI direct Route together, $0.52 for Clef,
Clef-flash and d1 at 32k to 256k, and $0.16 for the 8k to 24k rows.

# Bakeoff report

_85 runs in `runs/input-cap-sweep`, built 2026-10-08T15:39:28+00:00_

**How to read this report**

- **Provider**: the model that answered. Own build rows name the route in parentheses, plus any output cap or sampling; the exact spec of every row is in the Runs section.
- **Effort**: the reasoning effort set on the own build. Decision APIs have no such setting, so they show n/a.
- **Input cap**: the input-token limit set on the own build, or `no cap`. Decision APIs show n/a; their fixed limits show up as Over cap.
- **Cases**: question rows scored; a Case can carry several Questions.
- **Accuracy**: share of rows answered correctly. A Non-answer counts as wrong.
- **Answered acc.**: accuracy over the rows that produced an Answer, so a Provider that could not take an input is not penalised for it here.
- **Non-answers**: share of rows with no usable answer: refused, truncated, errored, or rejected because the input was over the vendor's limit.
- **Median s**: seconds per request; half the requests were faster.
- **$ per 1k**: dollars per 1,000 requests at list prices, from the token counts each vendor reported; `unknown` when the vendor reported no usage.
- **Over cap**: share of Cases longer than the Provider's input limit. In the sweep table the same thing is marked with `*`.
- **Details tables**: chance-corrected accuracy (0 is guessing, 1 is perfect), macro-F1 (accuracy balanced across classes), ECE and Brier (calibration, lower is better, 0 is perfect), and p95 latency (19 of 20 requests were faster).

## longstate-128k

| Provider | Effort | Input cap | Cases | Accuracy | Answered acc. | Non-answers | Median s | $ per 1k | Over cap |
|---|---|---|---|---|---|---|---|---|---|
| clef (Cloudflare) | n/a | n/a | 12 | 1.000 | 1.000 | 0.000 | 60.54 | $34.3823 | 1.000 |
| clef-flash (Cloudflare) | n/a | n/a | 12 | 1.000 | 1.000 | 0.000 | 30.02 | $12.8934 | 1.000 |
| d1 (Liquid) | n/a | n/a | 12 | 0.000 | - | 1.000 | 0.21 | unknown | 1.000 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | 12 | 1.000 | 1.000 | 0.000 | 0.58 | $12.8391 | 0.000 |
| gpt-6-luna (copilot) | none | 32000 | 12 | 0.667 | 0.667 | 0.000 | 2.37 | $3.2737 | 1.000 |
| gpt-6-luna (copilot) | none | 64000 | 12 | 0.833 | 0.833 | 0.000 | 2.17 | $6.4748 | 1.000 |
| gpt-6-luna (copilot) | none | 128000 | 12 | 1.000 | 1.000 | 0.000 | 4.23 | $12.8747 | 1.000 |
| gpt-6-luna (copilot) | none | 256000 | 12 | 1.000 | 1.000 | 0.000 | 2.70 | $12.8781 | 0.000 |
| gpt-6-luna (openai) | none | 32000 | 12 | 0.500 | 0.500 | 0.000 | 4.09 | $3.2750 | 1.000 |
| gpt-6-luna (openai) | none | 64000 | 12 | 0.750 | 0.750 | 0.000 | 3.43 | $6.4737 | 1.000 |
| gpt-6-luna (openai) | none | 128000 | 12 | 1.000 | 1.000 | 0.000 | 5.78 | $12.8727 | 1.000 |
| gpt-6-luna (openai) | none | 256000 | 12 | 1.000 | 1.000 | 0.000 | 5.85 | $12.8759 | 0.000 |
| jev-1.13.0 | n/a | n/a | 12 | 0.000 | - | 1.000 | 0.14 | unknown | 1.000 |

Details:

| Provider | Effort | Input cap | Chance-corrected | Macro-F1 | ECE | Brier | p95 s |
|---|---|---|---|---|---|---|---|
| clef (Cloudflare) | n/a | n/a | 1.000 | 1.000 | 0.015 | 0.001 | 74.12 |
| clef-flash (Cloudflare) | n/a | n/a | 1.000 | 1.000 | 0.040 | 0.004 | 30.56 |
| d1 (Liquid) | n/a | n/a | -0.538 | 0.000 | - | - | 0.46 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | 1.000 | 1.000 | 0.003 | 0.000 | 0.70 |
| gpt-6-luna (copilot) | none | 32000 | 0.487 | 0.675 | 0.299 | 0.587 | 2.85 |
| gpt-6-luna (copilot) | none | 64000 | 0.744 | 0.910 | 0.138 | 0.293 | 2.41 |
| gpt-6-luna (copilot) | none | 128000 | 1.000 | 1.000 | 0.018 | 0.001 | 5.32 |
| gpt-6-luna (copilot) | none | 256000 | 1.000 | 1.000 | 0.014 | 0.001 | 8.28 |
| gpt-6-luna (openai) | none | 32000 | 0.231 | 0.403 | 0.417 | 0.872 | 6.66 |
| gpt-6-luna (openai) | none | 64000 | 0.615 | 0.687 | 0.171 | 0.392 | 7.11 |
| gpt-6-luna (openai) | none | 128000 | 1.000 | 1.000 | 0.011 | 0.000 | 8.38 |
| gpt-6-luna (openai) | none | 256000 | 1.000 | 1.000 | 0.004 | 0.000 | 8.28 |
| jev-1.13.0 | n/a | n/a | -0.538 | 0.000 | - | - | 0.16 |

Each row against the most accurate Run, clef (Cloudflare), on the same Cases (a negative diff means it did worse):

| Provider | Effort | Input cap | Accuracy diff | 95% interval | Wins/losses | McNemar p |
|---|---|---|---|---|---|---|
| clef-flash (Cloudflare) | n/a | n/a | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| jev-1.13.0 | n/a | n/a | -1.000 | [-1.000, -1.000] | 0/12 | 0.000 |
| d1 (Liquid) | n/a | n/a | -1.000 | [-1.000, -1.000] | 0/12 | 0.000 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (copilot) | none | 128000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (copilot) | none | 256000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (copilot) | none | 32000 | -0.333 | [-0.583, -0.083] | 0/4 | 0.125 |
| gpt-6-luna (copilot) | none | 64000 | -0.167 | [-0.417, +0.000] | 0/2 | 0.500 |
| gpt-6-luna (openai) | none | 128000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (openai) | none | 256000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (openai) | none | 32000 | -0.500 | [-0.750, -0.250] | 0/6 | 0.031 |
| gpt-6-luna (openai) | none | 64000 | -0.250 | [-0.500, +0.000] | 0/3 | 0.250 |

## longstate-16k

| Provider | Effort | Input cap | Cases | Accuracy | Answered acc. | Non-answers | Median s | $ per 1k | Over cap |
|---|---|---|---|---|---|---|---|---|---|
| d1 (Liquid) | n/a | n/a | 12 | 0.833 | 0.833 | 0.000 | 0.73 | $1.6612 | 0.000 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | 12 | 1.000 | 1.000 | 0.000 | 0.21 | $1.6389 | 0.000 |
| gpt-6-luna (copilot) | none | 32000 | 12 | 1.000 | 1.000 | 0.000 | 1.88 | $0.1923 | 0.000 |
| gpt-6-luna (copilot) | none | 64000 | 12 | 1.000 | 1.000 | 0.000 | 1.81 | $0.4407 | 0.000 |
| gpt-6-luna (copilot) | none | 128000 | 12 | 1.000 | 1.000 | 0.000 | 1.81 | $0.9350 | 0.000 |
| gpt-6-luna (copilot) | none | 256000 | 12 | 1.000 | 1.000 | 0.000 | 1.78 | $0.6885 | 0.000 |
| gpt-6-luna (openai) | none | 32000 | 12 | 1.000 | 1.000 | 0.000 | 1.68 | $1.1814 | 0.000 |
| gpt-6-luna (openai) | none | 64000 | 12 | 1.000 | 1.000 | 0.000 | 1.75 | $0.6880 | 0.000 |
| gpt-6-luna (openai) | none | 128000 | 12 | 1.000 | 1.000 | 0.000 | 2.06 | $0.1914 | 0.000 |
| gpt-6-luna (openai) | none | 256000 | 12 | 1.000 | 1.000 | 0.000 | 1.85 | $0.1934 | 0.000 |
| jev-1.13.0 | n/a | n/a | 12 | 1.000 | 1.000 | 0.000 | 0.26 | $0.9915 | 0.000 |

Details:

| Provider | Effort | Input cap | Chance-corrected | Macro-F1 | ECE | Brier | p95 s |
|---|---|---|---|---|---|---|---|
| d1 (Liquid) | n/a | n/a | 0.744 | 0.833 | 0.150 | 0.280 | 0.93 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | 1.000 | 1.000 | 0.000 | 0.000 | 0.76 |
| gpt-6-luna (copilot) | none | 32000 | 1.000 | 1.000 | 0.006 | 0.000 | 3.36 |
| gpt-6-luna (copilot) | none | 64000 | 1.000 | 1.000 | 0.009 | 0.000 | 3.39 |
| gpt-6-luna (copilot) | none | 128000 | 1.000 | 1.000 | 0.011 | 0.000 | 2.01 |
| gpt-6-luna (copilot) | none | 256000 | 1.000 | 1.000 | 0.011 | 0.000 | 3.25 |
| gpt-6-luna (openai) | none | 32000 | 1.000 | 1.000 | 0.008 | 0.000 | 2.51 |
| gpt-6-luna (openai) | none | 64000 | 1.000 | 1.000 | 0.007 | 0.000 | 2.32 |
| gpt-6-luna (openai) | none | 128000 | 1.000 | 1.000 | 0.008 | 0.000 | 2.39 |
| gpt-6-luna (openai) | none | 256000 | 1.000 | 1.000 | 0.008 | 0.000 | 2.19 |
| jev-1.13.0 | n/a | n/a | 1.000 | 1.000 | 0.005 | 0.000 | 0.69 |

Each row against the most accurate Run, jev-1.13.0, on the same Cases (a negative diff means it did worse):

| Provider | Effort | Input cap | Accuracy diff | 95% interval | Wins/losses | McNemar p |
|---|---|---|---|---|---|---|
| d1 (Liquid) | n/a | n/a | -0.167 | [-0.417, +0.000] | 0/2 | 0.500 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (copilot) | none | 128000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (copilot) | none | 256000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (copilot) | none | 32000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (copilot) | none | 64000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (openai) | none | 128000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (openai) | none | 256000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (openai) | none | 32000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (openai) | none | 64000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |

## longstate-24k

| Provider | Effort | Input cap | Cases | Accuracy | Answered acc. | Non-answers | Median s | $ per 1k | Over cap |
|---|---|---|---|---|---|---|---|---|---|
| d1 (Liquid) | n/a | n/a | 12 | 0.917 | 0.917 | 0.000 | 1.08 | $2.4840 | 0.000 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | 12 | 1.000 | 1.000 | 0.000 | 0.19 | $2.4376 | 0.000 |
| gpt-6-luna (copilot) | none | 32000 | 12 | 1.000 | 1.000 | 0.000 | 1.88 | $0.2728 | 0.000 |
| gpt-6-luna (copilot) | none | 64000 | 12 | 1.000 | 1.000 | 0.000 | 1.93 | $0.2730 | 0.000 |
| gpt-6-luna (copilot) | none | 128000 | 12 | 1.000 | 1.000 | 0.000 | 2.06 | $2.4772 | 0.000 |
| gpt-6-luna (copilot) | none | 256000 | 12 | 1.000 | 1.000 | 0.000 | 2.25 | $0.2736 | 0.000 |
| gpt-6-luna (openai) | none | 32000 | 12 | 1.000 | 1.000 | 0.000 | 1.63 | $2.1090 | 0.000 |
| gpt-6-luna (openai) | none | 64000 | 12 | 1.000 | 1.000 | 0.000 | 1.49 | $1.0087 | 0.000 |
| gpt-6-luna (openai) | none | 128000 | 12 | 1.000 | 1.000 | 0.000 | 1.54 | $0.6399 | 0.000 |
| gpt-6-luna (openai) | none | 256000 | 12 | 1.000 | 1.000 | 0.000 | 1.62 | $0.2738 | 0.000 |
| jev-1.13.0 | n/a | n/a | 12 | 0.000 | - | 1.000 | 0.07 | unknown | 0.000 |

Details:

| Provider | Effort | Input cap | Chance-corrected | Macro-F1 | ECE | Brier | p95 s |
|---|---|---|---|---|---|---|---|
| d1 (Liquid) | n/a | n/a | 0.872 | 0.911 | 0.121 | 0.186 | 1.15 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | 1.000 | 1.000 | 0.000 | 0.000 | 0.23 |
| gpt-6-luna (copilot) | none | 32000 | 1.000 | 1.000 | 0.005 | 0.000 | 2.39 |
| gpt-6-luna (copilot) | none | 64000 | 1.000 | 1.000 | 0.011 | 0.000 | 2.20 |
| gpt-6-luna (copilot) | none | 128000 | 1.000 | 1.000 | 0.008 | 0.000 | 2.61 |
| gpt-6-luna (copilot) | none | 256000 | 1.000 | 1.000 | 0.008 | 0.000 | 3.12 |
| gpt-6-luna (openai) | none | 32000 | 1.000 | 1.000 | 0.010 | 0.000 | 2.63 |
| gpt-6-luna (openai) | none | 64000 | 1.000 | 1.000 | 0.011 | 0.000 | 1.81 |
| gpt-6-luna (openai) | none | 128000 | 1.000 | 1.000 | 0.006 | 0.000 | 2.20 |
| gpt-6-luna (openai) | none | 256000 | 1.000 | 1.000 | 0.010 | 0.000 | 1.78 |
| jev-1.13.0 | n/a | n/a | -0.538 | 0.000 | - | - | 0.08 |

Each row against the most accurate Run, gpt-6-luna (OpenAI Decisions), on the same Cases (a negative diff means it did worse):

| Provider | Effort | Input cap | Accuracy diff | 95% interval | Wins/losses | McNemar p |
|---|---|---|---|---|---|---|
| jev-1.13.0 | n/a | n/a | -1.000 | [-1.000, -1.000] | 0/12 | 0.000 |
| d1 (Liquid) | n/a | n/a | -0.083 | [-0.250, +0.000] | 0/1 | 1.000 |
| gpt-6-luna (copilot) | none | 128000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (copilot) | none | 256000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (copilot) | none | 32000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (copilot) | none | 64000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (openai) | none | 128000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (openai) | none | 256000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (openai) | none | 32000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (openai) | none | 64000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |

## longstate-256k

| Provider | Effort | Input cap | Cases | Accuracy | Answered acc. | Non-answers | Median s | $ per 1k | Over cap |
|---|---|---|---|---|---|---|---|---|---|
| clef (Cloudflare) | n/a | n/a | 12 | 0.000 | - | 1.000 | 0.14 | unknown | 1.000 |
| clef-flash (Cloudflare) | n/a | n/a | 12 | 0.000 | - | 1.000 | 0.21 | unknown | 1.000 |
| d1 (Liquid) | n/a | n/a | 12 | 0.000 | - | 1.000 | 0.22 | unknown | 1.000 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | 12 | 1.000 | 1.000 | 0.000 | 1.29 | $25.6373 | 0.000 |
| gpt-6-luna (copilot) | none | 32000 | 12 | 0.667 | 0.667 | 0.000 | 2.68 | $2.7870 | 1.000 |
| gpt-6-luna (copilot) | none | 64000 | 12 | 0.583 | 0.583 | 0.000 | 2.71 | $5.5078 | 1.000 |
| gpt-6-luna (copilot) | none | 128000 | 12 | 0.583 | 0.583 | 0.000 | 2.70 | $12.8744 | 1.000 |
| gpt-6-luna (copilot) | none | 256000 | 12 | 1.000 | 1.000 | 0.000 | 3.61 | $25.6735 | 1.000 |
| gpt-6-luna (openai) | none | 32000 | 12 | 0.583 | 0.583 | 0.000 | 2.63 | $2.7869 | 1.000 |
| gpt-6-luna (openai) | none | 64000 | 12 | 0.583 | 0.583 | 0.000 | 5.63 | $5.5069 | 1.000 |
| gpt-6-luna (openai) | none | 128000 | 12 | 0.583 | 0.583 | 0.000 | 4.93 | $12.8747 | 1.000 |
| gpt-6-luna (openai) | none | 256000 | 12 | 1.000 | 1.000 | 0.000 | 3.42 | $25.6748 | 1.000 |
| jev-1.13.0 | n/a | n/a | 12 | 0.000 | - | 1.000 | 0.22 | unknown | 1.000 |

Details:

| Provider | Effort | Input cap | Chance-corrected | Macro-F1 | ECE | Brier | p95 s |
|---|---|---|---|---|---|---|---|
| clef (Cloudflare) | n/a | n/a | -0.538 | 0.000 | - | - | 0.19 |
| clef-flash (Cloudflare) | n/a | n/a | -0.538 | 0.000 | - | - | 0.25 |
| d1 (Liquid) | n/a | n/a | -0.538 | 0.000 | - | - | 0.64 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | 1.000 | 1.000 | 0.034 | 0.018 | 1.66 |
| gpt-6-luna (copilot) | none | 32000 | 0.487 | 0.564 | 0.273 | 0.555 | 2.79 |
| gpt-6-luna (copilot) | none | 64000 | 0.359 | 0.514 | 0.318 | 0.685 | 3.06 |
| gpt-6-luna (copilot) | none | 128000 | 0.359 | 0.486 | 0.276 | 0.619 | 2.89 |
| gpt-6-luna (copilot) | none | 256000 | 1.000 | 1.000 | 0.014 | 0.001 | 4.15 |
| gpt-6-luna (openai) | none | 32000 | 0.359 | 0.514 | 0.339 | 0.703 | 7.12 |
| gpt-6-luna (openai) | none | 64000 | 0.359 | 0.553 | 0.387 | 0.778 | 9.66 |
| gpt-6-luna (openai) | none | 128000 | 0.359 | 0.514 | 0.338 | 0.713 | 8.73 |
| gpt-6-luna (openai) | none | 256000 | 1.000 | 1.000 | 0.019 | 0.001 | 9.90 |
| jev-1.13.0 | n/a | n/a | -0.538 | 0.000 | - | - | 0.38 |

Each row against the most accurate Run, gpt-6-luna (OpenAI Decisions), on the same Cases (a negative diff means it did worse):

| Provider | Effort | Input cap | Accuracy diff | 95% interval | Wins/losses | McNemar p |
|---|---|---|---|---|---|---|
| clef (Cloudflare) | n/a | n/a | -1.000 | [-1.000, -1.000] | 0/12 | 0.000 |
| clef-flash (Cloudflare) | n/a | n/a | -1.000 | [-1.000, -1.000] | 0/12 | 0.000 |
| jev-1.13.0 | n/a | n/a | -1.000 | [-1.000, -1.000] | 0/12 | 0.000 |
| d1 (Liquid) | n/a | n/a | -1.000 | [-1.000, -1.000] | 0/12 | 0.000 |
| gpt-6-luna (copilot) | none | 128000 | -0.417 | [-0.667, -0.167] | 0/5 | 0.062 |
| gpt-6-luna (copilot) | none | 256000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (copilot) | none | 32000 | -0.333 | [-0.583, -0.083] | 0/4 | 0.125 |
| gpt-6-luna (copilot) | none | 64000 | -0.417 | [-0.667, -0.167] | 0/5 | 0.062 |
| gpt-6-luna (openai) | none | 128000 | -0.417 | [-0.667, -0.167] | 0/5 | 0.062 |
| gpt-6-luna (openai) | none | 256000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (openai) | none | 32000 | -0.417 | [-0.667, -0.167] | 0/5 | 0.062 |
| gpt-6-luna (openai) | none | 64000 | -0.417 | [-0.667, -0.167] | 0/5 | 0.062 |

## longstate-32k

| Provider | Effort | Input cap | Cases | Accuracy | Answered acc. | Non-answers | Median s | $ per 1k | Over cap |
|---|---|---|---|---|---|---|---|---|---|
| clef (Cloudflare) | n/a | n/a | 12 | 1.000 | 1.000 | 0.000 | 7.09 | $8.6538 | 0.000 |
| clef-flash (Cloudflare) | n/a | n/a | 12 | 1.000 | 1.000 | 0.000 | 2.47 | $3.2452 | 0.000 |
| d1 (Liquid) | n/a | n/a | 12 | 1.000 | 1.000 | 0.000 | 1.88 | $3.3110 | 0.000 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | 12 | 1.000 | 1.000 | 0.000 | 0.94 | $3.2382 | 0.000 |
| gpt-6-luna (copilot) | none | 32000 | 12 | 1.000 | 1.000 | 0.000 | 2.25 | $3.2744 | 1.000 |
| gpt-6-luna (copilot) | none | 64000 | 12 | 1.000 | 1.000 | 0.000 | 2.13 | $0.8417 | 0.000 |
| gpt-6-luna (copilot) | none | 128000 | 12 | 1.000 | 1.000 | 0.000 | 2.29 | $0.8395 | 0.000 |
| gpt-6-luna (copilot) | none | 256000 | 12 | 1.000 | 1.000 | 0.000 | 2.33 | $2.3022 | 0.000 |
| gpt-6-luna (openai) | none | 32000 | 12 | 1.000 | 1.000 | 0.000 | 2.92 | $3.2748 | 1.000 |
| gpt-6-luna (openai) | none | 64000 | 12 | 1.000 | 1.000 | 0.000 | 2.97 | $2.3035 | 0.000 |
| gpt-6-luna (openai) | none | 128000 | 12 | 1.000 | 1.000 | 0.000 | 3.38 | $0.8413 | 0.000 |
| gpt-6-luna (openai) | none | 256000 | 12 | 1.000 | 1.000 | 0.000 | 2.74 | $0.8417 | 0.000 |
| jev-1.13.0 | n/a | n/a | 12 | 0.000 | - | 1.000 | 0.24 | unknown | 1.000 |

Details:

| Provider | Effort | Input cap | Chance-corrected | Macro-F1 | ECE | Brier | p95 s |
|---|---|---|---|---|---|---|---|
| clef (Cloudflare) | n/a | n/a | 1.000 | 1.000 | 0.012 | 0.000 | 15.89 |
| clef-flash (Cloudflare) | n/a | n/a | 1.000 | 1.000 | 0.029 | 0.002 | 2.95 |
| d1 (Liquid) | n/a | n/a | 1.000 | 1.000 | 0.010 | 0.000 | 3.28 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | 1.000 | 1.000 | 0.000 | 0.000 | 1.29 |
| gpt-6-luna (copilot) | none | 32000 | 1.000 | 1.000 | 0.016 | 0.001 | 3.16 |
| gpt-6-luna (copilot) | none | 64000 | 1.000 | 1.000 | 0.016 | 0.001 | 3.38 |
| gpt-6-luna (copilot) | none | 128000 | 1.000 | 1.000 | 0.006 | 0.000 | 2.39 |
| gpt-6-luna (copilot) | none | 256000 | 1.000 | 1.000 | 0.010 | 0.000 | 2.86 |
| gpt-6-luna (openai) | none | 32000 | 1.000 | 1.000 | 0.014 | 0.001 | 4.53 |
| gpt-6-luna (openai) | none | 64000 | 1.000 | 1.000 | 0.015 | 0.001 | 4.13 |
| gpt-6-luna (openai) | none | 128000 | 1.000 | 1.000 | 0.016 | 0.001 | 4.38 |
| gpt-6-luna (openai) | none | 256000 | 1.000 | 1.000 | 0.011 | 0.000 | 8.59 |
| jev-1.13.0 | n/a | n/a | -0.538 | 0.000 | - | - | 0.38 |

Each row against the most accurate Run, clef (Cloudflare), on the same Cases (a negative diff means it did worse):

| Provider | Effort | Input cap | Accuracy diff | 95% interval | Wins/losses | McNemar p |
|---|---|---|---|---|---|---|
| clef-flash (Cloudflare) | n/a | n/a | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| jev-1.13.0 | n/a | n/a | -1.000 | [-1.000, -1.000] | 0/12 | 0.000 |
| d1 (Liquid) | n/a | n/a | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (copilot) | none | 128000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (copilot) | none | 256000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (copilot) | none | 32000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (copilot) | none | 64000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (openai) | none | 128000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (openai) | none | 256000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (openai) | none | 32000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (openai) | none | 64000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |

## longstate-64k

| Provider | Effort | Input cap | Cases | Accuracy | Answered acc. | Non-answers | Median s | $ per 1k | Over cap |
|---|---|---|---|---|---|---|---|---|---|
| clef (Cloudflare) | n/a | n/a | 12 | 1.000 | 1.000 | 0.000 | 16.35 | $17.2271 | 0.000 |
| clef-flash (Cloudflare) | n/a | n/a | 12 | 1.000 | 1.000 | 0.000 | 19.76 | $6.4602 | 0.000 |
| d1 (Liquid) | n/a | n/a | 12 | 0.000 | - | 1.000 | 0.17 | unknown | 1.000 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | 12 | 1.000 | 1.000 | 0.000 | 0.33 | $6.4393 | 0.000 |
| gpt-6-luna (copilot) | none | 32000 | 12 | 0.583 | 0.583 | 0.000 | 2.16 | $3.2747 | 1.000 |
| gpt-6-luna (copilot) | none | 64000 | 12 | 1.000 | 1.000 | 0.000 | 2.22 | $6.4750 | 1.000 |
| gpt-6-luna (copilot) | none | 128000 | 12 | 1.000 | 1.000 | 0.000 | 2.34 | $5.5109 | 0.000 |
| gpt-6-luna (copilot) | none | 256000 | 12 | 1.000 | 1.000 | 0.000 | 2.23 | $1.6397 | 0.000 |
| gpt-6-luna (openai) | none | 32000 | 12 | 0.583 | 0.583 | 0.000 | 3.15 | $3.2746 | 1.000 |
| gpt-6-luna (openai) | none | 64000 | 12 | 1.000 | 1.000 | 0.000 | 2.90 | $6.4749 | 1.000 |
| gpt-6-luna (openai) | none | 128000 | 12 | 1.000 | 1.000 | 0.000 | 3.82 | $4.5447 | 0.000 |
| gpt-6-luna (openai) | none | 256000 | 12 | 1.000 | 1.000 | 0.000 | 3.18 | $4.5440 | 0.000 |
| jev-1.13.0 | n/a | n/a | 12 | 0.000 | - | 1.000 | 0.12 | unknown | 1.000 |

Details:

| Provider | Effort | Input cap | Chance-corrected | Macro-F1 | ECE | Brier | p95 s |
|---|---|---|---|---|---|---|---|
| clef (Cloudflare) | n/a | n/a | 1.000 | 1.000 | 0.012 | 0.000 | 30.64 |
| clef-flash (Cloudflare) | n/a | n/a | 1.000 | 1.000 | 0.033 | 0.003 | 20.61 |
| d1 (Liquid) | n/a | n/a | -0.538 | 0.000 | - | - | 0.32 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | 1.000 | 1.000 | 0.001 | 0.000 | 1.04 |
| gpt-6-luna (copilot) | none | 32000 | 0.359 | 0.542 | 0.271 | 0.616 | 2.84 |
| gpt-6-luna (copilot) | none | 64000 | 1.000 | 1.000 | 0.018 | 0.001 | 2.59 |
| gpt-6-luna (copilot) | none | 128000 | 1.000 | 1.000 | 0.013 | 0.001 | 2.44 |
| gpt-6-luna (copilot) | none | 256000 | 1.000 | 1.000 | 0.011 | 0.001 | 2.28 |
| gpt-6-luna (openai) | none | 32000 | 0.359 | 0.553 | 0.318 | 0.673 | 3.92 |
| gpt-6-luna (openai) | none | 64000 | 1.000 | 1.000 | 0.015 | 0.001 | 3.54 |
| gpt-6-luna (openai) | none | 128000 | 1.000 | 1.000 | 0.016 | 0.001 | 7.30 |
| gpt-6-luna (openai) | none | 256000 | 1.000 | 1.000 | 0.016 | 0.001 | 9.08 |
| jev-1.13.0 | n/a | n/a | -0.538 | 0.000 | - | - | 0.33 |

Each row against the most accurate Run, clef (Cloudflare), on the same Cases (a negative diff means it did worse):

| Provider | Effort | Input cap | Accuracy diff | 95% interval | Wins/losses | McNemar p |
|---|---|---|---|---|---|---|
| clef-flash (Cloudflare) | n/a | n/a | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| jev-1.13.0 | n/a | n/a | -1.000 | [-1.000, -1.000] | 0/12 | 0.000 |
| d1 (Liquid) | n/a | n/a | -1.000 | [-1.000, -1.000] | 0/12 | 0.000 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (copilot) | none | 128000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (copilot) | none | 256000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (copilot) | none | 32000 | -0.417 | [-0.667, -0.167] | 0/5 | 0.062 |
| gpt-6-luna (copilot) | none | 64000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (openai) | none | 128000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (openai) | none | 256000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (openai) | none | 32000 | -0.417 | [-0.667, -0.167] | 0/5 | 0.062 |
| gpt-6-luna (openai) | none | 64000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |

## longstate-8k

| Provider | Effort | Input cap | Cases | Accuracy | Answered acc. | Non-answers | Median s | $ per 1k | Over cap |
|---|---|---|---|---|---|---|---|---|---|
| d1 (Liquid) | n/a | n/a | 12 | 1.000 | 1.000 | 0.000 | 1.02 | $0.8303 | 0.000 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | 12 | 1.000 | 1.000 | 0.000 | 0.72 | $0.8342 | 0.000 |
| gpt-6-luna (copilot) | none | 32000 | 12 | 1.000 | 1.000 | 0.000 | 1.89 | $0.3646 | 0.000 |
| gpt-6-luna (copilot) | none | 64000 | 12 | 1.000 | 1.000 | 0.000 | 1.69 | $0.3663 | 0.000 |
| gpt-6-luna (copilot) | none | 128000 | 12 | 1.000 | 1.000 | 0.000 | 1.74 | $0.1131 | 0.000 |
| gpt-6-luna (copilot) | none | 256000 | 12 | 1.000 | 1.000 | 0.000 | 1.81 | $0.4922 | 0.000 |
| gpt-6-luna (openai) | none | 32000 | 12 | 1.000 | 1.000 | 0.000 | 2.10 | $0.4930 | 0.000 |
| gpt-6-luna (openai) | none | 64000 | 12 | 1.000 | 1.000 | 0.000 | 2.12 | $0.6202 | 0.000 |
| gpt-6-luna (openai) | none | 128000 | 12 | 1.000 | 1.000 | 0.000 | 1.68 | $0.1135 | 0.000 |
| gpt-6-luna (openai) | none | 256000 | 12 | 1.000 | 1.000 | 0.000 | 1.75 | $0.1138 | 0.000 |
| jev-1.13.0 | n/a | n/a | 12 | 1.000 | 1.000 | 0.000 | 0.67 | $0.5030 | 0.000 |

Details:

| Provider | Effort | Input cap | Chance-corrected | Macro-F1 | ECE | Brier | p95 s |
|---|---|---|---|---|---|---|---|
| d1 (Liquid) | n/a | n/a | 1.000 | 1.000 | 0.003 | 0.000 | 1.06 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | 1.000 | 1.000 | 0.000 | 0.000 | 0.85 |
| gpt-6-luna (copilot) | none | 32000 | 1.000 | 1.000 | 0.004 | 0.000 | 2.36 |
| gpt-6-luna (copilot) | none | 64000 | 1.000 | 1.000 | 0.010 | 0.000 | 2.49 |
| gpt-6-luna (copilot) | none | 128000 | 1.000 | 1.000 | 0.007 | 0.000 | 1.82 |
| gpt-6-luna (copilot) | none | 256000 | 1.000 | 1.000 | 0.007 | 0.000 | 2.44 |
| gpt-6-luna (openai) | none | 32000 | 1.000 | 1.000 | 0.012 | 0.001 | 2.76 |
| gpt-6-luna (openai) | none | 64000 | 1.000 | 1.000 | 0.007 | 0.000 | 2.75 |
| gpt-6-luna (openai) | none | 128000 | 1.000 | 1.000 | 0.012 | 0.000 | 2.11 |
| gpt-6-luna (openai) | none | 256000 | 1.000 | 1.000 | 0.012 | 0.001 | 2.24 |
| jev-1.13.0 | n/a | n/a | 1.000 | 1.000 | 0.006 | 0.000 | 0.70 |

Each row against the most accurate Run, jev-1.13.0, on the same Cases (a negative diff means it did worse):

| Provider | Effort | Input cap | Accuracy diff | 95% interval | Wins/losses | McNemar p |
|---|---|---|---|---|---|---|
| d1 (Liquid) | n/a | n/a | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (copilot) | none | 128000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (copilot) | none | 256000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (copilot) | none | 32000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (copilot) | none | 64000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (openai) | none | 128000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (openai) | none | 256000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (openai) | none | 32000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (openai) | none | 64000 | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |

## Overall

| Provider | Effort | Input cap | Cases | Accuracy | Answered acc. | Non-answers | Median s | $ per 1k | Over cap |
|---|---|---|---|---|---|---|---|---|---|
| clef (Cloudflare) | n/a | n/a | 48 | 0.750 | 1.000 | 0.250 | 15.85 | unknown | 0.500 |
| clef-flash (Cloudflare) | n/a | n/a | 48 | 0.750 | 1.000 | 0.250 | 4.16 | unknown | 0.500 |
| d1 (Liquid) | n/a | n/a | 84 | 0.536 | 0.938 | 0.429 | 0.68 | unknown | 0.429 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | 84 | 1.000 | 1.000 | 0.000 | 0.66 | $7.5807 | 0.000 |
| gpt-6-luna (copilot) | none | 32000 | 84 | 0.845 | 0.845 | 0.000 | 2.16 | $1.9199 | 0.571 |
| gpt-6-luna (copilot) | none | 64000 | 84 | 0.917 | 0.917 | 0.000 | 2.15 | $2.9113 | 0.429 |
| gpt-6-luna (copilot) | none | 128000 | 84 | 0.940 | 0.940 | 0.000 | 2.19 | $5.0892 | 0.286 |
| gpt-6-luna (copilot) | none | 256000 | 84 | 1.000 | 1.000 | 0.000 | 2.27 | $6.2783 | 0.143 |
| gpt-6-luna (openai) | none | 32000 | 84 | 0.810 | 0.810 | 0.000 | 2.54 | $2.3421 | 0.571 |
| gpt-6-luna (openai) | none | 64000 | 84 | 0.905 | 0.905 | 0.000 | 2.46 | $3.2966 | 0.429 |
| gpt-6-luna (openai) | none | 128000 | 84 | 0.940 | 0.940 | 0.000 | 2.39 | $4.5826 | 0.286 |
| gpt-6-luna (openai) | none | 256000 | 84 | 1.000 | 1.000 | 0.000 | 2.36 | $6.3596 | 0.143 |
| jev-1.13.0 | n/a | n/a | 84 | 0.286 | 1.000 | 0.714 | 0.22 | unknown | 0.571 |

Details:

| Provider | Effort | Input cap | Chance-corrected | Macro-F1 | ECE | Brier | p95 s |
|---|---|---|---|---|---|---|---|
| clef (Cloudflare) | n/a | n/a | 0.615 | 0.857 | 0.013 | 0.000 | 61.65 |
| clef-flash (Cloudflare) | n/a | n/a | 0.615 | 0.857 | 0.034 | 0.003 | 30.32 |
| d1 (Liquid) | n/a | n/a | 0.286 | 0.680 | 0.056 | 0.117 | 2.34 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | 1.000 | 1.000 | 0.005 | 0.003 | 1.40 |
| gpt-6-luna (copilot) | none | 32000 | 0.762 | 0.853 | 0.116 | 0.251 | 3.03 |
| gpt-6-luna (copilot) | none | 64000 | 0.872 | 0.928 | 0.056 | 0.140 | 3.12 |
| gpt-6-luna (copilot) | none | 128000 | 0.908 | 0.931 | 0.030 | 0.089 | 4.98 |
| gpt-6-luna (copilot) | none | 256000 | 1.000 | 1.000 | 0.011 | 0.000 | 3.97 |
| gpt-6-luna (openai) | none | 32000 | 0.707 | 0.811 | 0.147 | 0.321 | 4.73 |
| gpt-6-luna (openai) | none | 64000 | 0.853 | 0.909 | 0.072 | 0.167 | 7.82 |
| gpt-6-luna (openai) | none | 128000 | 0.908 | 0.941 | 0.038 | 0.102 | 8.32 |
| gpt-6-luna (openai) | none | 256000 | 1.000 | 1.000 | 0.011 | 0.000 | 10.03 |
| jev-1.13.0 | n/a | n/a | -0.099 | 0.444 | 0.005 | 0.000 | 0.69 |

## Sweeps

Accuracy by State length (`longstate-*` Families); `*` marks Runs with Cases over the Provider's documented input limit.

| Provider | Effort | Input cap | 8,000 tok | 16,000 tok | 24,000 tok | 32,000 tok | 64,000 tok | 128,000 tok | 256,000 tok |
|---|---|---|---|---|---|---|---|---|---|
| clef (Cloudflare) | n/a | n/a |  |  |  | 1.000 | 1.000 | 1.000* | 0.000* |
| clef-flash (Cloudflare) | n/a | n/a |  |  |  | 1.000 | 1.000 | 1.000* | 0.000* |
| d1 (Liquid) | n/a | n/a | 1.000 | 0.833 | 0.917 | 1.000 | 0.000* | 0.000* | 0.000* |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| gpt-6-luna (copilot) | none | 32000 | 1.000 | 1.000 | 1.000 | 1.000* | 0.583* | 0.667* | 0.667* |
| gpt-6-luna (copilot) | none | 64000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000* | 0.833* | 0.583* |
| gpt-6-luna (copilot) | none | 128000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000* | 0.583* |
| gpt-6-luna (copilot) | none | 256000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000* |
| gpt-6-luna (openai) | none | 32000 | 1.000 | 1.000 | 1.000 | 1.000* | 0.583* | 0.500* | 0.583* |
| gpt-6-luna (openai) | none | 64000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000* | 0.750* | 0.583* |
| gpt-6-luna (openai) | none | 128000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000* | 0.583* |
| gpt-6-luna (openai) | none | 256000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000* |
| jev-1.13.0 | n/a | n/a | 1.000 | 1.000 | 0.000 | 0.000* | 0.000* | 0.000* | 0.000* |

## Runs

Row labels above and the exact spec each one stands for:

- **clef (Cloudflare)**: `cloudflare/clef`
- **clef-flash (Cloudflare)**: `cloudflare/clef-flash`
- **d1 (Liquid)**: `liquid/d1`
- **gpt-6-luna (OpenAI Decisions)**: `openai-decisions/gpt-6-luna`
- **gpt-6-luna (copilot) · effort none · in ≤32000**: `ownbuild/copilot/gpt-6-luna?effort=none&max_in=32000&mode=probabilities&samples=1`
- **gpt-6-luna (copilot) · effort none · in ≤64000**: `ownbuild/copilot/gpt-6-luna?effort=none&max_in=64000&mode=probabilities&samples=1`
- **gpt-6-luna (copilot) · effort none · in ≤128000**: `ownbuild/copilot/gpt-6-luna?effort=none&max_in=128000&mode=probabilities&samples=1`
- **gpt-6-luna (copilot) · effort none · in ≤256000**: `ownbuild/copilot/gpt-6-luna?effort=none&max_in=256000&mode=probabilities&samples=1`
- **gpt-6-luna (openai) · effort none · in ≤32000**: `ownbuild/openai/gpt-6-luna?effort=none&max_in=32000&mode=probabilities&samples=1`
- **gpt-6-luna (openai) · effort none · in ≤64000**: `ownbuild/openai/gpt-6-luna?effort=none&max_in=64000&mode=probabilities&samples=1`
- **gpt-6-luna (openai) · effort none · in ≤128000**: `ownbuild/openai/gpt-6-luna?effort=none&max_in=128000&mode=probabilities&samples=1`
- **gpt-6-luna (openai) · effort none · in ≤256000**: `ownbuild/openai/gpt-6-luna?effort=none&max_in=256000&mode=probabilities&samples=1`
- **jev-1.13.0**: `jev`
