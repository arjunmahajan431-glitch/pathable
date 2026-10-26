"""FastAPI application for PathAble.

Start with::

    uvicorn pathable.api.main:app --reload --port 8000

The graph is loaded once during startup. If no live cache exists we serve the
committed sample extract with a demo warning rather than fabricating data.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from pathable.api.errors import register_error_handlers
from pathable.api.routes import router
from pathable.api.state import AppState
from pathable.config import AppConfig, load_config
from pathable.geocode import NominatimClient
from pathable.graph.loader import GraphBundle, graph_counts, load_area_graph
from pathable.reports.store import ReportStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("pathable")


def create_app(
    config: AppConfig | None = None,
    *,
    graph_bundle: GraphBundle | None = None,
    store: ReportStore | None = None,
    allow_download: bool = False,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        cfg = config or load_config()
        report_store = store or ReportStore(cfg.database_path)
        report_store.initialize()
        audits = report_store.audits()
        bundle = graph_bundle
        graph_error: str | None = None
        if bundle is None:
            try:
                bundle = load_area_graph(cfg, allow_download=allow_download, audits=audits)
            except Exception as exc:
                logger.exception("Could not load the pedestrian graph")
                graph_error = f"{type(exc).__name__}: {exc}"
        state = AppState(
            config=cfg,
            store=report_store,
            geocoder=NominatimClient(cfg),
            graph=bundle.graph if bundle else None,
            meta=bundle.meta if bundle else None,
            load_warnings=bundle.warnings if bundle else [],
            graph_error=graph_error,
            field_audits=len(audits),
            started_at=datetime.now(UTC),
        )
        app.state.pathable = state
        if state.graph is not None:
            node_count, edge_count = graph_counts(state.graph)
            logger.info(
                "Loaded graph: area=%s nodes=%s edges=%s demo=%s",
                state.meta.area_id if state.meta else "?",
                node_count,
                edge_count,
                state.meta.demo_mode if state.meta else "?",
            )
        else:
            logger.error("Graph unavailable: %s", graph_error)
        yield

    cfg = config or load_config()
    app = FastAPI(
        title="PathAble API",
        version="0.1.0",
        description=(
            "Explainable, uncertainty-aware pedestrian routing. Coverage counts mapped "
            "length, not route quality."
        ),
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    if cfg.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cfg.cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization", "X-Admin-Token"],
        )

    @app.middleware("http")
    async def _privacy_and_limits(request: Request, call_next):  # type: ignore[no-untyped-def]
        # Route requests contain start/end points. Never let a browser or proxy
        # cache them, and never log them.
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > 100_000:
            return JSONResponse(
                status_code=413,
                content={
                    "error": {
                        "code": "body_too_large",
                        "message": "Request body is too large.",
                        "details": {},
                    }
                },
            )
        response = await call_next(request)
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    register_error_handlers(app)
    app.include_router(router)

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {
            "name": "PathAble API",
            "docs": "/api/docs",
            "note": "Coverage measures mapping completeness, not accessibility.",
        }

    return app


app = create_app()
