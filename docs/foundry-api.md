# Microsoft-Decision-1 on Microsoft Foundry

## Your own deployment

This repository publishes benchmark results, not access to a running Foundry resource.
Deploy Microsoft-Decision-1 in your own account and send `POST` requests to:

```text
https://example-foundry-account.services.ai.azure.com/providers/microsoft/v1/systemone
```

The hostname above is a placeholder. Use your resource's hostname and deployment alias.
The recorded benchmark used the alias `decision-1` for Microsoft-Decision-1 version `1`,
not a general-purpose chat model.

Requests need an Entra bearer token and Azure RBAC access to your resource. The recorded
smoke request returned HTTP 200; the same request without authentication returned 401.
The sanitized payload and response are in
[`runs/foundry-live-smoke.json`](../runs/foundry-live-smoke.json). Account, subscription,
resource-group, endpoint, and deployment inventory are intentionally not published.

## Call the API

With an Azure CLI session signed in to your authorized tenant, set `AZURE_SUBSCRIPTION_ID`
and `FOUNDRY_ENDPOINT` to your own resource values. This example obtains a short-lived
Cognitive Services token in memory. It never prints or saves the credential:

```sh
uv run python - <<'PY'
import json
import os
import subprocess

import httpx

result = subprocess.run(
    [
        "az", "account", "get-access-token",
        "--subscription", os.environ["AZURE_SUBSCRIPTION_ID"],
        "--resource", "https://cognitiveservices.azure.com",
        "--output", "json",
    ],
    check=True, capture_output=True, text=True,
)
token = json.loads(result.stdout)["accessToken"]
body = {
    "model": "decision-1",
    "state": "I was charged twice for my subscription.",
    "questions": {
        "team": {
            "type": "choice",
            "instructions": "Which team should handle this support request?",
            "criteria": {
                "billing": "Charges, invoices, refunds, or subscription payments",
                "technical": "Software bugs or integration problems",
                "account": "Sign-in, password, or account-access problems",
            },
        },
    },
}
response = httpx.post(
    os.environ["FOUNDRY_ENDPOINT"].rstrip("/") + "/providers/microsoft/v1/systemone",
    headers={"Authorization": f"Bearer {token}"},
    json=body,
    timeout=60,
    follow_redirects=False,
)
response.raise_for_status()
print(json.dumps(response.json(), indent=2))
PY
```

A successful reply has named `answers`, each with its question type and probabilities,
plus reported `usage`. Supported question types are `choice`, `noul` (yes/no), and `score`
(an ordered list of rubric levels). The API accepts structured text States as well as strings;
images are unsupported. See the [live three-type payload](../runs/foundry-live-smoke.json).

Token acquisition uses the current CLI identity. Refresh the token when it expires; the
benchmark adapter takes an explicitly supplied token and does not renew it. For a deployed
application, use its own Entra identity and the Cognitive Services scope
`https://cognitiveservices.azure.com/.default`, with appropriate resource RBAC.

## Run the bakeoff

The provider spec is `foundry` or `foundry/<deployment>`. Configure the resource base URL,
not the full route:

```sh
export FOUNDRY_ENDPOINT=https://example-foundry-account.services.ai.azure.com
export AZURE_SUBSCRIPTION_ID=your-subscription-id
export FOUNDRY_DEPLOYMENT_NAME=decision-1
export FOUNDRY_REQUESTS_PER_MINUTE=30
export FOUNDRY_ACCESS_TOKEN="$(az account get-access-token \
  --subscription "$AZURE_SUBSCRIPTION_ID" \
  --resource https://cognitiveservices.azure.com --query accessToken -o tsv)"

uv run bakeoff run -p foundry \
  -f routing-synthetic -f banking77 -f longstate-32k -f rendered-images \
  --limit 20 --budget 2 --runs-dir runs/my-foundry-comparison
uv run bakeoff report --runs-dir runs/my-foundry-comparison
unset FOUNDRY_ACCESS_TOKEN
```

Do not run with shell tracing (`set -x`) or commit tokens to `.env` or results. Request
headers are excluded from raw capture, and the loaded Foundry token is included in the
store's credential scrubber. Endpoint validation restricts credential-bearing calls to
HTTPS `*.services.ai.azure.com` resource base URLs, without user information, extra paths,
query strings, fragments, or nonstandard ports; redirects remain disabled.

The adapter paces initial calls at the configured allocation and uses one in-flight
request. Normal harness retries still apply; this is not a production load test or a
guaranteed rate limiter across processes. Recorded latency excludes intentional pacing
waits; successful rows measure the answering HTTP attempt, and failed rows include the
actual retry/backoff time. The client can reject images without contacting the service.

Existing smoke Families are tracked; deterministic `longstate-*` inputs can be regenerated
with `build_longstate_cases` in `bakeoff.datasets.longstate` (seed 0, six Cases per length).
Use a new runs directory for a fresh measurement: completed Cases are skipped on resume.
The published [comparison](foundry-comparison-2026-10-10.md) identifies the exact inputs,
denominators, run dates, costs, and limitations.

## Limits and pricing

- The model catalog documents a **32,768-token full prompt** and text-only input. This is
  not a 32,768-token State allowance: questions, formatting, the model tokenizer, and the
  decision token consume context too. The harness's `o200k_base` count is a proxy.
- In this bakeoff, the service accepted the tested 8k and 16k States and rejected all tested
  24k and larger States with HTTP 422. This brackets this dataset's usable range; it does
  not establish an exact universal maximum.
- Published price on 2026-10-10: **$0.042 per million input tokens, output free**. The
  response can report nonzero output usage; the price calculation correctly charges it
  at zero. Reported token counts support list-price estimates, not actual Azure invoices.
  Error responses without usage retain unknown cost, not an invented zero.
- Availability and lifecycle are time-bound. Inspect the current catalog and your own
  deployment before relying on a production support claim.

Sources: [announcement and pricing](https://commandline.microsoft.com/microsoft-decision-1-model-foundry/),
[model catalog](https://ai.azure.com/catalog/models/Microsoft-Decision-1), and
[Foundry integration example](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/introducing-microsoft-decision-1-in-microsoft-foundry-for-decision-and-classific/4562742).
