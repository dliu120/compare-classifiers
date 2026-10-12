# Bakeoff report

_32 runs in `runs`, built 2026-10-10T16:32:47+00:00_

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
| clef (Cloudflare) | n/a | n/a | 20 | 19 | 1 | 0 | 0.950 | 0.950 | 0.000 | 0.53 | $0.3196 | 0.000 |
| clef-flash (Cloudflare) | n/a | n/a | 20 | 19 | 1 | 0 | 0.950 | 0.950 | 0.000 | 0.25 | $0.1198 | 0.000 |
| d1 (Liquid) | n/a | n/a | 20 | 19 | 1 | 0 | 0.950 | 0.950 | 0.000 | 0.22 | $0.0186 | 0.000 |
| decision-1 (Microsoft Foundry) | n/a | n/a | 20 | 16 | 4 | 0 | 0.800 | 0.800 | 0.000 | 0.26 | $0.0243 | 0.000 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | 20 | 15 | 5 | 0 | 0.750 | 0.750 | 0.000 | 0.13 | $0.0654 | 0.000 |
| gpt-6-luna (copilot) | none | no cap | 20 | 17 | 3 | 0 | 0.850 | 0.850 | 0.000 | 6.60 | $0.4218 | 0.000 |
| gpt-6-luna (openai) | none | no cap | 20 | 16 | 4 | 0 | 0.800 | 0.800 | 0.000 | 7.17 | $0.4237 | 0.000 |
| jev-1.13.0 | n/a | n/a | 20 | 16 | 4 | 0 | 0.800 | 0.800 | 0.000 | 0.08 | $0.0429 | 0.000 |

Details:

| Provider | Effort | Input cap | Chance-corrected | Macro-F1 | ECE | Brier | p95 s |
|---|---|---|---|---|---|---|---|
| clef (Cloudflare) | n/a | n/a | 0.949 | 0.959 | 0.095 | 0.047 | 0.78 |
| clef-flash (Cloudflare) | n/a | n/a | 0.949 | 0.959 | 0.065 | 0.085 | 0.62 |
| d1 (Liquid) | n/a | n/a | 0.949 | 0.959 | 0.081 | 0.084 | 0.40 |
| decision-1 (Microsoft Foundry) | n/a | n/a | 0.797 | 0.768 | 0.128 | 0.248 | 0.40 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | 0.747 | 0.692 | 0.158 | 0.267 | 0.16 |
| gpt-6-luna (copilot) | none | no cap | 0.848 | 0.805 | 0.199 | 0.335 | 7.84 |
| gpt-6-luna (openai) | none | no cap | 0.797 | 0.728 | 0.064 | 0.319 | 9.12 |
| jev-1.13.0 | n/a | n/a | 0.797 | 0.728 | 0.146 | 0.263 | 0.13 |

Each row against the most accurate Run, clef (Cloudflare), on the same Cases (a negative diff means it did worse):

| Provider | Effort | Input cap | Accuracy diff | 95% interval | Wins/losses | McNemar p |
|---|---|---|---|---|---|---|
| clef-flash (Cloudflare) | n/a | n/a | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| decision-1 (Microsoft Foundry) | n/a | n/a | -0.150 | [-0.300, +0.000] | 0/3 | 0.250 |
| jev-1.13.0 | n/a | n/a | -0.150 | [-0.300, +0.000] | 0/3 | 0.250 |
| d1 (Liquid) | n/a | n/a | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | -0.200 | [-0.400, -0.050] | 0/4 | 0.125 |
| gpt-6-luna (copilot) | none | no cap | -0.100 | [-0.250, +0.000] | 0/2 | 0.500 |
| gpt-6-luna (openai) | none | no cap | -0.150 | [-0.300, +0.000] | 0/3 | 0.250 |

## longstate-32k

| Provider | Effort | Input cap | Cases | Right | Wrong | Non-answers | Accuracy | Answered acc. | Non-answer rate | Median s | $ per 1k | Over cap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| clef (Cloudflare) | n/a | n/a | 12 | 12 | 0 | 0 | 1.000 | 1.000 | 0.000 | 7.00 | $8.6538 | 0.000 |
| clef-flash (Cloudflare) | n/a | n/a | 12 | 12 | 0 | 0 | 1.000 | 1.000 | 0.000 | 2.26 | $3.2452 | 0.000 |
| d1 (Liquid) | n/a | n/a | 12 | 12 | 0 | 0 | 1.000 | 1.000 | 0.000 | 1.58 | $3.3110 | 0.000 |
| decision-1 (Microsoft Foundry) | n/a | n/a | 12 | 0 | 0 | 12 | 0.000 | - | 1.000 | 0.61 | unknown | 0.000 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | 12 | 12 | 0 | 0 | 1.000 | 1.000 | 0.000 | 0.21 | $3.2382 | 0.000 |
| gpt-6-luna (copilot) | none | no cap | 12 | 12 | 0 | 0 | 1.000 | 1.000 | 0.000 | 2.22 | $0.3530 | 0.000 |
| gpt-6-luna (openai) | none | no cap | 12 | 12 | 0 | 0 | 1.000 | 1.000 | 0.000 | 2.16 | $0.3532 | 0.000 |
| jev-1.13.0 | n/a | n/a | 12 | 0 | 0 | 12 | 0.000 | - | 1.000 | 0.17 | unknown | 1.000 |

Details:

| Provider | Effort | Input cap | Chance-corrected | Macro-F1 | ECE | Brier | p95 s |
|---|---|---|---|---|---|---|---|
| clef (Cloudflare) | n/a | n/a | 1.000 | 1.000 | 0.012 | 0.000 | 7.16 |
| clef-flash (Cloudflare) | n/a | n/a | 1.000 | 1.000 | 0.029 | 0.002 | 2.62 |
| d1 (Liquid) | n/a | n/a | 1.000 | 1.000 | 0.010 | 0.000 | 1.79 |
| decision-1 (Microsoft Foundry) | n/a | n/a | -0.538 | 0.000 | - | - | 0.70 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | 1.000 | 1.000 | 0.000 | 0.000 | 0.26 |
| gpt-6-luna (copilot) | none | no cap | 1.000 | 1.000 | 0.014 | 0.001 | 2.72 |
| gpt-6-luna (openai) | none | no cap | 1.000 | 1.000 | 0.008 | 0.000 | 2.72 |
| jev-1.13.0 | n/a | n/a | -0.538 | 0.000 | - | - | 0.18 |

Each row against the most accurate Run, clef (Cloudflare), on the same Cases (a negative diff means it did worse):

| Provider | Effort | Input cap | Accuracy diff | 95% interval | Wins/losses | McNemar p |
|---|---|---|---|---|---|---|
| clef-flash (Cloudflare) | n/a | n/a | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| decision-1 (Microsoft Foundry) | n/a | n/a | -1.000 | [-1.000, -1.000] | 0/12 | 0.000 |
| jev-1.13.0 | n/a | n/a | -1.000 | [-1.000, -1.000] | 0/12 | 0.000 |
| d1 (Liquid) | n/a | n/a | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (copilot) | none | no cap | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (openai) | none | no cap | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |

## rendered-images

| Provider | Effort | Input cap | Cases | Right | Wrong | Non-answers | Accuracy | Answered acc. | Non-answer rate | Median s | $ per 1k | Over cap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| clef (Cloudflare) | n/a | n/a | 27 | 27 | 0 | 0 | 1.000 | 1.000 | 0.000 | 0.53 | $0.1049 | 0.000 |
| clef-flash (Cloudflare) | n/a | n/a | 27 | 27 | 0 | 0 | 1.000 | 1.000 | 0.000 | 0.27 | $0.0393 | 0.000 |
| d1 (Liquid) | n/a | n/a | 27 | 27 | 0 | 0 | 1.000 | 1.000 | 0.000 | 0.29 | $0.0230 | 0.000 |
| decision-1 (Microsoft Foundry) | n/a | n/a | 27 | 0 | 0 | 27 | 0.000 | - | 1.000 | - | $0.0000 | 0.000 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | 27 | 27 | 0 | 0 | 1.000 | 1.000 | 0.000 | 0.15 | $0.0423 | 0.000 |
| gpt-6-luna (copilot) | none | no cap | 27 | 27 | 0 | 0 | 1.000 | 1.000 | 0.000 | 1.99 | $0.0900 | 0.000 |
| gpt-6-luna (openai) | none | no cap | 27 | 27 | 0 | 0 | 1.000 | 1.000 | 0.000 | 1.99 | $0.0902 | 0.000 |
| jev-1.13.0 | n/a | n/a | 27 | 0 | 0 | 27 | 0.000 | - | 1.000 | - | unknown | 0.000 |

Details:

| Provider | Effort | Input cap | Chance-corrected | Macro-F1 | ECE | Brier | p95 s |
|---|---|---|---|---|---|---|---|
| clef (Cloudflare) | n/a | n/a | 1.000 | 1.000 | 0.012 | 0.000 | 0.81 |
| clef-flash (Cloudflare) | n/a | n/a | 1.000 | 1.000 | 0.037 | 0.002 | 0.50 |
| d1 (Liquid) | n/a | n/a | 1.000 | 1.000 | 0.000 | 0.000 | 0.56 |
| decision-1 (Microsoft Foundry) | n/a | n/a | -0.407 | 0.000 | - | - | - |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | 1.000 | 1.000 | 0.001 | 0.000 | 0.21 |
| gpt-6-luna (copilot) | none | no cap | 1.000 | 1.000 | 0.004 | 0.000 | 3.48 |
| gpt-6-luna (openai) | none | no cap | 1.000 | 1.000 | 0.007 | 0.000 | 6.10 |
| jev-1.13.0 | n/a | n/a | -0.407 | 0.000 | - | - | - |

Each row against the most accurate Run, clef (Cloudflare), on the same Cases (a negative diff means it did worse):

| Provider | Effort | Input cap | Accuracy diff | 95% interval | Wins/losses | McNemar p |
|---|---|---|---|---|---|---|
| clef-flash (Cloudflare) | n/a | n/a | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| decision-1 (Microsoft Foundry) | n/a | n/a | -1.000 | [-1.000, -1.000] | 0/27 | 0.000 |
| jev-1.13.0 | n/a | n/a | -1.000 | [-1.000, -1.000] | 0/27 | 0.000 |
| d1 (Liquid) | n/a | n/a | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (copilot) | none | no cap | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |
| gpt-6-luna (openai) | none | no cap | +0.000 | [+0.000, +0.000] | 0/0 | 1.000 |

## routing-synthetic

| Provider | Effort | Input cap | Cases | Right | Wrong | Non-answers | Accuracy | Answered acc. | Non-answer rate | Median s | $ per 1k | Over cap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| clef (Cloudflare) | n/a | n/a | 60 | 59 | 1 | 0 | 0.983 | 0.983 | 0.000 | 0.51 | $0.1165 | 0.000 |
| clef-flash (Cloudflare) | n/a | n/a | 60 | 57 | 3 | 0 | 0.950 | 0.950 | 0.000 | 0.26 | $0.0437 | 0.000 |
| d1 (Liquid) | n/a | n/a | 60 | 57 | 3 | 0 | 0.950 | 0.950 | 0.000 | 0.22 | $0.0152 | 0.000 |
| decision-1 (Microsoft Foundry) | n/a | n/a | 60 | 58 | 2 | 0 | 0.967 | 0.967 | 0.000 | 0.27 | $0.0100 | 0.000 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | 60 | 58 | 2 | 0 | 0.967 | 0.967 | 0.000 | 0.21 | $0.0524 | 0.000 |
| gpt-6-luna (copilot) | none | no cap | 60 | 59 | 1 | 0 | 0.983 | 0.983 | 0.000 | 1.76 | $0.1019 | 0.000 |
| gpt-6-luna (openai) | none | no cap | 60 | 58 | 2 | 0 | 0.967 | 0.967 | 0.000 | 2.10 | $0.1021 | 0.000 |
| jev-1.13.0 | n/a | n/a | 60 | 57 | 3 | 0 | 0.950 | 0.950 | 0.000 | 0.11 | $0.0229 | 0.000 |

Details:

| Provider | Effort | Input cap | Chance-corrected | Macro-F1 | ECE | Brier | p95 s |
|---|---|---|---|---|---|---|---|
| clef (Cloudflare) | n/a | n/a | 0.975 | 0.986 | 0.068 | 0.037 | 0.72 |
| clef-flash (Cloudflare) | n/a | n/a | 0.924 | 0.956 | 0.112 | 0.105 | 1.04 |
| d1 (Liquid) | n/a | n/a | 0.924 | 0.971 | 0.100 | 0.108 | 0.44 |
| decision-1 (Microsoft Foundry) | n/a | n/a | 0.949 | 0.971 | 0.048 | 0.074 | 0.42 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | 0.949 | 0.986 | 0.037 | 0.045 | 0.45 |
| gpt-6-luna (copilot) | none | no cap | 0.975 | 1.000 | 0.058 | 0.029 | 2.13 |
| gpt-6-luna (openai) | none | no cap | 0.949 | 0.971 | 0.062 | 0.064 | 3.47 |
| jev-1.13.0 | n/a | n/a | 0.924 | 0.956 | 0.045 | 0.085 | 0.31 |

Each row against the most accurate Run, clef (Cloudflare), on the same Cases (a negative diff means it did worse):

| Provider | Effort | Input cap | Accuracy diff | 95% interval | Wins/losses | McNemar p |
|---|---|---|---|---|---|---|
| clef-flash (Cloudflare) | n/a | n/a | -0.033 | [-0.083, +0.000] | 0/2 | 0.500 |
| decision-1 (Microsoft Foundry) | n/a | n/a | -0.017 | [-0.050, +0.000] | 0/1 | 1.000 |
| jev-1.13.0 | n/a | n/a | -0.033 | [-0.083, +0.000] | 0/2 | 0.500 |
| d1 (Liquid) | n/a | n/a | -0.033 | [-0.083, +0.000] | 0/2 | 0.500 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | -0.017 | [-0.050, +0.000] | 0/1 | 1.000 |
| gpt-6-luna (copilot) | none | no cap | +0.000 | [-0.050, +0.050] | 1/1 | 1.000 |
| gpt-6-luna (openai) | none | no cap | -0.017 | [-0.067, +0.033] | 1/2 | 1.000 |

## Overall

| Provider | Effort | Input cap | Cases | Right | Wrong | Non-answers | Accuracy | Answered acc. | Non-answer rate | Median s | $ per 1k | Over cap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| clef (Cloudflare) | n/a | n/a | 119 | 117 | 2 | 0 | 0.983 | 0.983 | 0.000 | 0.54 | $0.9506 | 0.000 |
| clef-flash (Cloudflare) | n/a | n/a | 119 | 115 | 4 | 0 | 0.966 | 0.966 | 0.000 | 0.26 | $0.3565 | 0.000 |
| d1 (Liquid) | n/a | n/a | 119 | 115 | 4 | 0 | 0.966 | 0.966 | 0.000 | 0.25 | $0.3182 | 0.000 |
| decision-1 (Microsoft Foundry) | n/a | n/a | 119 | 74 | 6 | 39 | 0.622 | 0.925 | 0.328 | 0.27 | unknown | 0.000 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | 119 | 112 | 7 | 0 | 0.941 | 0.941 | 0.000 | 0.15 | $0.3429 | 0.000 |
| gpt-6-luna (copilot) | none | no cap | 119 | 115 | 4 | 0 | 0.966 | 0.966 | 0.000 | 2.16 | $0.2180 | 0.000 |
| gpt-6-luna (openai) | none | no cap | 119 | 113 | 6 | 0 | 0.950 | 0.950 | 0.000 | 2.36 | $0.2188 | 0.000 |
| jev-1.13.0 | n/a | n/a | 119 | 73 | 7 | 39 | 0.613 | 0.912 | 0.328 | 0.10 | unknown | 0.101 |

Details:

| Provider | Effort | Input cap | Chance-corrected | Macro-F1 | ECE | Brier | p95 s |
|---|---|---|---|---|---|---|---|
| clef (Cloudflare) | n/a | n/a | 0.977 | 0.985 | 0.054 | 0.027 | 6.92 |
| clef-flash (Cloudflare) | n/a | n/a | 0.954 | 0.980 | 0.074 | 0.068 | 2.27 |
| d1 (Liquid) | n/a | n/a | 0.954 | 0.982 | 0.043 | 0.068 | 1.54 |
| decision-1 (Microsoft Foundry) | n/a | n/a | 0.477 | 0.409 | 0.053 | 0.118 | 0.65 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | 0.919 | 0.900 | 0.039 | 0.067 | 0.39 |
| gpt-6-luna (copilot) | none | no cap | 0.954 | 0.938 | 0.026 | 0.071 | 7.17 |
| gpt-6-luna (openai) | none | no cap | 0.930 | 0.909 | 0.040 | 0.086 | 8.73 |
| jev-1.13.0 | n/a | n/a | 0.465 | 0.394 | 0.070 | 0.129 | 0.29 |

## Sweeps

Accuracy by State length (`longstate-*` Families); `*` marks Runs with Cases over the Provider's documented input limit.

| Provider | Effort | Input cap | 32,000 tok |
|---|---|---|---|
| clef (Cloudflare) | n/a | n/a | 1.000 |
| clef-flash (Cloudflare) | n/a | n/a | 1.000 |
| d1 (Liquid) | n/a | n/a | 1.000 |
| decision-1 (Microsoft Foundry) | n/a | n/a | 0.000 |
| gpt-6-luna (OpenAI Decisions) | n/a | n/a | 1.000 |
| gpt-6-luna (copilot) | none | no cap | 1.000 |
| gpt-6-luna (openai) | none | no cap | 1.000 |
| jev-1.13.0 | n/a | n/a | 0.000* |

## Runs

Row labels above and the exact spec each one stands for:

- **clef (Cloudflare)**: `cloudflare/clef`
- **clef-flash (Cloudflare)**: `cloudflare/clef-flash`
- **d1 (Liquid)**: `liquid/d1`
- **decision-1 (Microsoft Foundry)**: `foundry/decision-1`
- **gpt-6-luna (OpenAI Decisions)**: `openai-decisions/gpt-6-luna`
- **gpt-6-luna (copilot) · effort none · no cap**: `ownbuild/copilot/gpt-6-luna?effort=none&mode=probabilities&samples=1`
- **gpt-6-luna (openai) · effort none · no cap**: `ownbuild/openai/gpt-6-luna?effort=none&mode=probabilities&samples=1`
- **jev-1.13.0**: `jev`
