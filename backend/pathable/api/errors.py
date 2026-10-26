"""Structured API errors.

Every error reaches the client as ``{"error": {"code", "message", "details"}}``
so the frontend can show a plain-language message and choose a recovery action.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from pathable.engine.pipeline import OutOfAreaError
from pathable.engine.profiles import UnknownProfileError
from pathable.engine.search import SnapTooFarError

logger = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
        self.headers = headers or {}
        super().__init__(message)


def _body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(exc.code, exc.message, exc.details),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        details = []
        for item in exc.errors():
            details.append(
                {
                    "location": ".".join(str(part) for part in item.get("loc", [])),
                    "message": str(item.get("msg", "invalid value")),
                    "type": str(item.get("type", "value_error")),
                }
            )
        return JSONResponse(
            status_code=422,
            content=_body(
                "invalid_request",
                "The request contains invalid or missing values. Check the highlighted fields.",
                {"fields": details},
            ),
        )

    @app.exception_handler(OutOfAreaError)
    async def _out_of_area(_request: Request, exc: OutOfAreaError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_body(
                "out_of_area",
                str(exc),
                {
                    "point": exc.which,
                    "distance_m": round(exc.distance_m, 1),
                    "radius_m": exc.radius_m,
                },
            ),
        )

    @app.exception_handler(SnapTooFarError)
    async def _snap_too_far(_request: Request, exc: SnapTooFarError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_body(
                "snap_too_far",
                str(exc),
                {"distance_m": round(exc.distance_m, 1), "limit_m": exc.limit_m},
            ),
        )

    @app.exception_handler(UnknownProfileError)
    async def _bad_profile(_request: Request, exc: UnknownProfileError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_body("invalid_profile", str(exc), {}),
        )
