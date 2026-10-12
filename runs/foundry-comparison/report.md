# Bakeoff report

_8 runs in `runs/foundry-comparison`, built 2026-10-10T16:32:47+00:00_

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

## banking77

| Provider | Effort | Input cap | Cases | Right | Wrong | Non-answers | Accuracy | Answered acc. | Non-answer rate | Median s | $ per 1k | Over cap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| decision-1 (Microsoft Foundry) | n/a | n/a | 20 | 16 | 4 | 0 | 0.800 | 0.800 | 0.000 | 0.26 | $0.0243 | 0.000 |
| gpt-6-luna (copilot) | none | no cap | 20 | 17 | 3 | 0 | 0.850 | 0.850 | 0.000 | 4.56 | $0.4256 | 0.000 |

Details:

| Provider | Effort | Input cap | Chance-corrected | Macro-F1 | ECE | Brier | p95 s |
|---|---|---|---|---|---|---|---|
| decision-1 (Microsoft Foundry) | n/a | n/a | 0.797 | 0.768 | 0.128 | 0.248 | 0.40 |
| gpt-6-luna (copilot) | none | no cap | 0.848 | 0.805 | 0.132 | 0.290 | 7.66 |

Each row against the most accurate Run, gpt-6-luna (copilot) · effort none · no cap, on the same Cases (a negative diff means it did worse):

| Provider | Effort | Input cap | Accuracy diff | 95% interval | Wins/losses | McNemar p |
|---|---|---|---|---|---|---|
| decision-1 (Microsoft Foundry) | n/a | n/a | -0.050 | [-0.150, +0.000] | 0/1 | 1.000 |

## longstate-32k

| Provider | Effort | Input cap | Cases | Right | Wrong | Non-answers | Accuracy | Answered acc. | Non-answer rate | Median s | $ per 1k | Over cap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| decision-1 (Microsoft Foundry) | n/a | n/a | 12 | 0 | 0 | 12 | 0.000 | - | 1.000 | 0.61 | unknown | 0.000 |
| gpt-6-luna (copilot) | none | no cap | 12 | 12 | 0 | 0 | 1.000 | 1.000 | 0.000 | 2.06 | $3.2741 | 0.000 |

Details:

| Provider | Effort | Input cap | Chance-corrected | Macro-F1 | ECE | Brier | p95 s |
|---|---|---|---|---|---|---|---|
| decision-1 (Microsoft Foundry) | n/a | n/a | -0.538 | 0.000 | - | - | 0.70 |
| gpt-6-luna (copilot) | none | no cap | 1.000 | 1.000 | 0.003 | 0.000 | 2.47 |

Each row against the most accurate Run, gpt-6-luna (copilot) · effort none · no cap, on the same Cases (a negative diff means it did worse):

| Provider | Effort | Input cap | Accuracy diff | 95% interval | Wins/losses | McNemar p |
|---|---|---|---|---|---|---|
| decision-1 (Microsoft Foundry) | n/a | n/a | -1.000 | [-1.000, -1.000] | 0/12 | 0.000 |

## rendered-images

| Provider | Effort | Input cap | Cases | Right | Wrong | Non-answers | Accuracy | Answered acc. | Non-answer rate | Median s | $ per 1k | Over cap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| decision-1 (Microsoft Foundry) | n/a | n/a | 27 | 0 | 0 | 27 | 0.000 | - | 1.000 | - | $0.0000 | 0.000 |
| gpt-6-luna (copilot) | none | no cap | 27 | 25 | 2 | 0 | 0.926 | 0.926 | 0.000 | 2.06 | $0.0913 | 0.000 |

Details:

| Provider | Effort | Input cap | Chance-corrected | Macro-F1 | ECE | Brier | p95 s |
|---|---|---|---|---|---|---|---|
| decision-1 (Microsoft Foundry) | n/a | n/a | -0.407 | 0.000 | - | - | - |
| gpt-6-luna (copilot) | none | no cap | 0.896 | 0.929 | 0.060 | 0.118 | 2.81 |

Each row against the most accurate Run, gpt-6-luna (copilot) · effort none · no cap, on the same Cases (a negative diff means it did worse):

| Provider | Effort | Input cap | Accuracy diff | 95% interval | Wins/losses | McNemar p |
|---|---|---|---|---|---|---|
| decision-1 (Microsoft Foundry) | n/a | n/a | -0.926 | [-1.000, -0.815] | 0/25 | 0.000 |

## routing-synthetic

| Provider | Effort | Input cap | Cases | Right | Wrong | Non-answers | Accuracy | Answered acc. | Non-answer rate | Median s | $ per 1k | Over cap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| decision-1 (Microsoft Foundry) | n/a | n/a | 60 | 58 | 2 | 0 | 0.967 | 0.967 | 0.000 | 0.27 | $0.0100 | 0.000 |
| gpt-6-luna (copilot) | none | no cap | 60 | 58 | 2 | 0 | 0.967 | 0.967 | 0.000 | 1.76 | $0.1012 | 0.000 |

Details:

| Provider | Effort | Input cap | Chance-corrected | Macro-F1 | ECE | Brier | p95 s |
|---|---|---|---|---|---|---|---|
| decision-1 (Microsoft Foundry) | n/a | n/a | 0.949 | 0.971 | 0.048 | 0.074 | 0.42 |
| gpt-6-luna (copilot) | none | no cap | 0.949 | 0.986 | 0.073 | 0.037 | 2.93 |

Each row against the most accurate Run, decision-1 (Microsoft Foundry), on the same Cases (a negative diff means it did worse):

| Provider | Effort | Input cap | Accuracy diff | 95% interval | Wins/losses | McNemar p |
|---|---|---|---|---|---|---|
| gpt-6-luna (copilot) | none | no cap | +0.000 | [-0.050, +0.050] | 1/1 | 1.000 |

## Overall

| Provider | Effort | Input cap | Cases | Right | Wrong | Non-answers | Accuracy | Answered acc. | Non-answer rate | Median s | $ per 1k | Over cap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| decision-1 (Microsoft Foundry) | n/a | n/a | 119 | 74 | 6 | 39 | 0.622 | 0.925 | 0.328 | 0.27 | unknown | 0.000 |
| gpt-6-luna (copilot) | none | no cap | 119 | 112 | 7 | 0 | 0.941 | 0.941 | 0.000 | 2.25 | $0.4850 | 0.000 |

Details:

| Provider | Effort | Input cap | Chance-corrected | Macro-F1 | ECE | Brier | p95 s |
|---|---|---|---|---|---|---|---|
| decision-1 (Microsoft Foundry) | n/a | n/a | 0.477 | 0.409 | 0.053 | 0.118 | 0.65 |
| gpt-6-luna (copilot) | none | no cap | 0.919 | 0.910 | 0.034 | 0.094 | 4.93 |

## Sweeps

Accuracy by State length (`longstate-*` Families); `*` marks Runs with Cases over the Provider's documented input limit.

| Provider | Effort | Input cap | 32,000 tok |
|---|---|---|---|
| decision-1 (Microsoft Foundry) | n/a | n/a | 0.000 |
| gpt-6-luna (copilot) | none | no cap | 1.000 |

## Runs

Row labels above and the exact spec each one stands for:

- **decision-1 (Microsoft Foundry)**: `foundry/decision-1`
- **gpt-6-luna (copilot) · effort none · no cap**: `ownbuild/copilot/gpt-6-luna?effort=none&mode=probabilities&samples=1`
