# Bakeoff report

_15 runs in `runs/long-context-2026-10-12`, built 2026-10-12T04:19:09+00:00_

**How to read this report**

- **Provider**: the model that answered. Own build rows name the route in parentheses, plus any output cap or sampling; the exact spec of every row is in the Runs section.
- **Effort**: the reasoning effort set on the own build. Decision APIs have no such setting, so they show n/a.
- **Input cap**: the input-token limit set on the own build, or `no cap`. Decision APIs show n/a; their fixed limits show up as Over cap.
- **Cases**: question rows scored; a Case can carry several Questions.
- **Right**: count of Questions answered correctly.
- **Wrong**: count of Questions answered incorrectly, excluding Non-answers.
- **Accuracy**: share of rows answered correctly. A Non-answer counts as wrong.
- **Answered acc.**: accuracy over the rows that produced an Answer, so a Provider that could not take an input is not penalised for it here.
- **Non-answers**: count of Questions with no usable answer: refused, truncated, errored, or rejected because the input was over the vendor's limit.
- **Right + Wrong + Non-answers** equals Cases; these are question counts, not requests.
- **Non-answer rate**: share of scored Questions with no usable answer.
- **Median s**: seconds per request; half the requests were faster.
- **$ per 1k**: dollars per 1,000 requests at list prices, from the token counts each vendor reported; `unknown` when the vendor reported no usage.
- **Over cap**: share of Cases longer than the Provider's input limit. In the sweep table the same thing is marked with `*`.
- **Details tables**: chance-corrected accuracy (0 is guessing, 1 is perfect), macro-F1 (accuracy balanced across classes), ECE and Brier (calibration, lower is better, 0 is perfect), and p95 latency (19 of 20 requests were faster).

## longstate-512k

| Provider | Effort | Input cap | Cases | Right | Wrong | Non-answers | Accuracy | Answered acc. | Non-answer rate | Median s | $ per 1k | Over cap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| clef (Cloudflare) | n/a | n/a | 12 | 0 | 0 | 12 | 0.000 | - | 1.000 | 0.89 | unknown | 1.000 |
| clef-flash (Cloudflare) | n/a | n/a | 12 | 0 | 0 | 12 | 0.000 | - | 1.000 | 0.72 | unknown | 1.000 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | 12 | 0 | 0 | 12 | 0.000 | - | 1.000 | 0.82 | unknown | 0.000 |
| gpt-6-luna (copilot) | none | no cap | 12 | 12 | 0 | 0 | 1.000 | 1.000 | 0.000 | 5.36 | $102.5352 | 0.000 |
| gpt-6-luna (openai) | none | no cap | 12 | 0 | 0 | 12 | 0.000 | - | 1.000 | 1.15 | unknown | 0.000 |

Details:

| Provider | Effort | Input cap | Chance-corrected | Macro-F1 | ECE | Brier | p95 s |
|---|---|---|---|---|---|---|---|
| clef (Cloudflare) | n/a | n/a | -0.538 | 0.000 | - | - | 1.13 |
| clef-flash (Cloudflare) | n/a | n/a | -0.538 | 0.000 | - | - | 0.86 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | -0.538 | 0.000 | - | - | 0.93 |
| gpt-6-luna (copilot) | none | no cap | 1.000 | 1.000 | 0.004 | 0.000 | 12.82 |
| gpt-6-luna (openai) | none | no cap | -0.538 | 0.000 | - | - | 1.28 |

Each row against the most accurate Run, gpt-6-luna (copilot) · effort none · no cap, on the same Cases (a negative diff means it did worse):

| Provider | Effort | Input cap | Accuracy diff | 95% interval | Wins/losses | McNemar p |
|---|---|---|---|---|---|---|
| clef (Cloudflare) | n/a | n/a | -1.000 | [-1.000, -1.000] | 0/12 | 0.000 |
| clef-flash (Cloudflare) | n/a | n/a | -1.000 | [-1.000, -1.000] | 0/12 | 0.000 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | -1.000 | [-1.000, -1.000] | 0/12 | 0.000 |
| gpt-6-luna (openai) | none | no cap | -1.000 | [-1.000, -1.000] | 0/12 | 0.000 |

## longstate-768k

| Provider | Effort | Input cap | Cases | Right | Wrong | Non-answers | Accuracy | Answered acc. | Non-answer rate | Median s | $ per 1k | Over cap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| clef (Cloudflare) | n/a | n/a | 12 | 0 | 0 | 12 | 0.000 | - | 1.000 | 0.91 | unknown | 1.000 |
| clef-flash (Cloudflare) | n/a | n/a | 12 | 0 | 0 | 12 | 0.000 | - | 1.000 | 0.58 | unknown | 1.000 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | 12 | 0 | 0 | 12 | 0.000 | - | 1.000 | 0.93 | unknown | 0.000 |
| gpt-6-luna (copilot) | none | no cap | 12 | 10 | 2 | 0 | 0.833 | 0.833 | 0.000 | 9.30 | $153.7401 | 0.000 |
| gpt-6-luna (openai) | none | no cap | 12 | 0 | 0 | 12 | 0.000 | - | 1.000 | 1.17 | unknown | 0.000 |

Details:

| Provider | Effort | Input cap | Chance-corrected | Macro-F1 | ECE | Brier | p95 s |
|---|---|---|---|---|---|---|---|
| clef (Cloudflare) | n/a | n/a | -0.538 | 0.000 | - | - | 1.68 |
| clef-flash (Cloudflare) | n/a | n/a | -0.538 | 0.000 | - | - | 0.92 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | -0.538 | 0.000 | - | - | 1.51 |
| gpt-6-luna (copilot) | none | no cap | 0.744 | 0.861 | 0.151 | 0.309 | 16.57 |
| gpt-6-luna (openai) | none | no cap | -0.538 | 0.000 | - | - | 1.46 |

Each row against the most accurate Run, gpt-6-luna (copilot) · effort none · no cap, on the same Cases (a negative diff means it did worse):

| Provider | Effort | Input cap | Accuracy diff | 95% interval | Wins/losses | McNemar p |
|---|---|---|---|---|---|---|
| clef (Cloudflare) | n/a | n/a | -0.833 | [-1.000, -0.583] | 0/10 | 0.002 |
| clef-flash (Cloudflare) | n/a | n/a | -0.833 | [-1.000, -0.583] | 0/10 | 0.002 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | -0.833 | [-1.000, -0.583] | 0/10 | 0.002 |
| gpt-6-luna (openai) | none | no cap | -0.833 | [-1.000, -0.583] | 0/10 | 0.002 |

## longstate-900k

| Provider | Effort | Input cap | Cases | Right | Wrong | Non-answers | Accuracy | Answered acc. | Non-answer rate | Median s | $ per 1k | Over cap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| clef (Cloudflare) | n/a | n/a | 12 | 0 | 0 | 12 | 0.000 | - | 1.000 | 0.81 | unknown | 1.000 |
| clef-flash (Cloudflare) | n/a | n/a | 12 | 0 | 0 | 12 | 0.000 | - | 1.000 | 0.71 | unknown | 1.000 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | 12 | 0 | 0 | 12 | 0.000 | - | 1.000 | 1.10 | unknown | 0.000 |
| gpt-6-luna (copilot) | none | no cap | 12 | 0 | 0 | 12 | 0.000 | - | 1.000 | 3.39 | unknown | 0.000 |
| gpt-6-luna (openai) | none | no cap | 12 | 0 | 0 | 12 | 0.000 | - | 1.000 | 0.74 | unknown | 0.000 |

Details:

| Provider | Effort | Input cap | Chance-corrected | Macro-F1 | ECE | Brier | p95 s |
|---|---|---|---|---|---|---|---|
| clef (Cloudflare) | n/a | n/a | -0.538 | 0.000 | - | - | 1.60 |
| clef-flash (Cloudflare) | n/a | n/a | -0.538 | 0.000 | - | - | 0.93 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | -0.538 | 0.000 | - | - | 1.38 |
| gpt-6-luna (copilot) | none | no cap | -0.538 | 0.000 | - | - | 4.94 |
| gpt-6-luna (openai) | none | no cap | -0.538 | 0.000 | - | - | 1.12 |

Each row against the most accurate Run, clef (Cloudflare), on the same Cases (a negative diff means it did worse):

| Provider | Effort | Input cap | Accuracy diff | 95% interval | Wins/losses | McNemar p |
|---|---|---|---|---|---|---|
| clef-flash (Cloudflare) | n/a | n/a | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (copilot) | none | no cap | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (openai) | none | no cap | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |

## Overall

| Provider | Effort | Input cap | Cases | Right | Wrong | Non-answers | Accuracy | Answered acc. | Non-answer rate | Median s | $ per 1k | Over cap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| clef (Cloudflare) | n/a | n/a | 36 | 0 | 0 | 36 | 0.000 | - | 1.000 | 0.84 | unknown | 1.000 |
| clef-flash (Cloudflare) | n/a | n/a | 36 | 0 | 0 | 36 | 0.000 | - | 1.000 | 0.66 | unknown | 1.000 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | 36 | 0 | 0 | 36 | 0.000 | - | 1.000 | 0.89 | unknown | 0.000 |
| gpt-6-luna (copilot) | none | no cap | 36 | 22 | 2 | 12 | 0.611 | 0.917 | 0.333 | 5.40 | unknown | 0.000 |
| gpt-6-luna (openai) | none | no cap | 36 | 0 | 0 | 36 | 0.000 | - | 1.000 | 1.13 | unknown | 0.000 |

Details:

| Provider | Effort | Input cap | Chance-corrected | Macro-F1 | ECE | Brier | p95 s |
|---|---|---|---|---|---|---|---|
| clef (Cloudflare) | n/a | n/a | -0.538 | 0.000 | - | - | 1.64 |
| clef-flash (Cloudflare) | n/a | n/a | -0.538 | 0.000 | - | - | 0.97 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | -0.538 | 0.000 | - | - | 1.47 |
| gpt-6-luna (copilot) | none | no cap | 0.402 | 0.747 | 0.073 | 0.155 | 14.32 |
| gpt-6-luna (openai) | none | no cap | -0.538 | 0.000 | - | - | 1.44 |

## Sweeps

Accuracy by State length (`longstate-*` Families); `*` marks Runs with Cases over the Provider's documented input limit.

| Provider | Effort | Input cap | 512,000 tok | 768,000 tok | 900,000 tok |
|---|---|---|---|---|---|
| clef (Cloudflare) | n/a | n/a | 0.000* | 0.000* | 0.000* |
| clef-flash (Cloudflare) | n/a | n/a | 0.000* | 0.000* | 0.000* |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | 0.000 | 0.000 | 0.000 |
| gpt-6-luna (copilot) | none | no cap | 1.000 | 0.833 | 0.000 |
| gpt-6-luna (openai) | none | no cap | 0.000 | 0.000 | 0.000 |

## Runs

Row labels above and the exact spec each one stands for:

- **clef (Cloudflare)**: `cloudflare/clef`
- **clef-flash (Cloudflare)**: `cloudflare/clef-flash`
- **gpt-6-luna (OpenAI Decisions)**: `openai-decisions/gpt-6-luna`
- **gpt-6-luna (copilot) · effort none · no cap**: `ownbuild/copilot/gpt-6-luna?effort=none&mode=probabilities&samples=1`
- **gpt-6-luna (openai) · effort none · no cap**: `ownbuild/openai/gpt-6-luna?effort=none&mode=probabilities&samples=1`
