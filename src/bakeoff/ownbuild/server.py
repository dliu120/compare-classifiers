"""The Own build as a drop-in System One endpoint (docs/adr/0001).

``POST /v1/systemone`` answers a SystemOneRequest with a SystemOneResponse. Non-answers are
data, so they come back with HTTP 200 (the engine's ``evaluate`` never raises and always
returns a response); only an invalid request is a 422. ``GET /v1/models`` lists the one
configured model. Every answer carries an ``X-Bakeoff-Latency-Ms`` header.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from bakeoff.config import Settings
from bakeoff.ownbuild.config import OwnBuildConfig
from bakeoff.ownbuild.engine import OwnBuildEngine
from bakeoff.systemone import SystemOneRequest, SystemOneResponse

LATENCY_HEADER = "X-Bakeoff-Latency-Ms"


def create_app(spec: str, settings: Settings) -> FastAPI:
    """Build the engine from an ``ownbuild/...`` spec and serve it. The engine lives on
    ``app.state.engine`` so a test can swap it for a fake."""
    config, extra = OwnBuildConfig.from_spec(spec)
    if extra:
        raise ValueError(f"spec keys {sorted(extra)} are not valid for serving: {spec!r}")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        await app.state.engine.aclose()

    app = FastAPI(title="Decision bakeoff: Own build", lifespan=lifespan)
    app.state.config = config
    app.state.engine = OwnBuildEngine(config, settings)

    @app.post("/v1/systemone", response_model=SystemOneResponse)
    async def systemone(request: SystemOneRequest) -> JSONResponse:
        result = await app.state.engine.evaluate(request)
        return JSONResponse(
            result.response.model_dump(mode="json", exclude_none=True),
            headers={LATENCY_HEADER: f"{result.latency_s * 1000:.1f}"},
        )

    @app.get("/v1/models")
    async def models() -> dict:
        model = {"id": config.model, "object": "model", "owned_by": "bakeoff", "spec": config.spec}
        return {"object": "list", "data": [model]}

    return app
