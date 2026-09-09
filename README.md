# Claims Intake Service

This service takes a first notice of loss from the claims portal, checks it
against the policy master and the rule table in `docs/api-contract.md`, and either
records the notification with a claim reference or refuses it with a specific
reason. It answers whether a notification is well formed and admissible. It does
not decide whether the claim will be paid.

## Where things are

| Path | What it holds |
| --- | --- |
| `docs/api-contract.md` | What the service accepts, returns, and refuses. The authority. |
| `docs/requirements-brief.md` | Open work items and their acceptance criteria. |
| `docs/payload-triage.md` | Day 1 classification of the edge payloads. |
| `data/` | Synthetic policies and notification payloads. |
| `src/claims/` | The service. |
| `tests/` | Unit tests mirror `src/claims/`. Integration tests hit HTTP. |

## Working in this repository

You are already inside a Linux container. Confirm that before you start:

```
uname -sm     # Linux aarch64
pwd           # /workspaces/claims-intake
```

Dependencies land when the container is created. There is no install step. If a
tool you need is missing, treat that as a defect in the image specification and
report it rather than patching around it.

```
uv run pytest
uv run ruff check .
uv run mypy
```

## Running the service

From the repository root:

```
uv run uvicorn claims.api.routes:app --host 0.0.0.0 --port 8000
```

The service exposes one endpoint: `POST /notifications`.

Accepted notification (expect `201` and a `claim_reference`):

```
curl -sS -X POST http://127.0.0.1:8000/notifications \
  -H 'Content-Type: application/json' \
  -d '{
    "policy_number": "MOT-4471",
    "loss_date": "2026-04-02",
    "claim_type": "collision",
    "estimated_amount": "4200.00",
    "description": "Rear ended at a junction."
  }'
```

Unknown policy (expect `422` with code `POLICY_NOT_FOUND`):

```
curl -sS -X POST http://127.0.0.1:8000/notifications \
  -H 'Content-Type: application/json' \
  -d '{
    "policy_number": "MOT-9999",
    "loss_date": "2026-03-12",
    "claim_type": "collision",
    "estimated_amount": "3000.00"
  }'
```

## Running the tests

```
uv run pytest
```

Integration tests live in `tests/integration/` and go through the HTTP surface.
Unit tests live in `tests/unit/` and call the models, repository, and rule engine
directly.

## Building and running the image

Build for the architecture the service will actually run on:

```
docker buildx build --platform linux/amd64 -t claims-intake:day4 .
```

Then run it:

```
docker run --rm -p 8000:8000 claims-intake:day4
```

The same `curl` examples above work against the container on port 8000.

### Why `--platform linux/amd64`

Course laptops and a lot of developer machines are ARM (`linux/arm64`). This
service deploys to `linux/amd64`. A plain `docker build` with no platform flag
targets whichever machine ran the build. On an ARM laptop that means an ARM
image. It starts fine locally, then fails on the cluster with an architecture
mismatch, or it limps along under emulation with odd performance. Passing
`--platform linux/amd64` makes the image match the deployment target even when
you build on a different chip. If Docker warns when you run that image on an ARM
host, that is expected. It means the platform flag did what it was supposed to.

## Data

Everything in `data/` is synthetic and was written for this program. No real
client data, no named clients.
