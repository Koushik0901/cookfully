from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError

from cookfully.domain.common import DomainError

logger = logging.getLogger(__name__)


def problem_response(
    request: Request,
    *,
    status: int,
    code: str,
    title: str,
    detail: str | None = None,
    field_errors: list[dict[str, str]] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"urn:cookfully:problem:{code}",
        "title": title,
        "status": status,
        "code": code,
        "instance": request.url.path,
    }
    if detail:
        body["detail"] = detail
    if field_errors:
        body["fieldErrors"] = field_errors
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


def install_problem_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        return problem_response(
            request,
            status=exc.status,
            code=exc.code,
            title=exc.safe_message,
            field_errors=list(exc.field_errors),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        fields = [
            {
                "field": ".".join(
                    str(part) for part in error["loc"] if part not in {"body", "query"}
                ),
                "code": str(error["type"]),
                "message": "Invalid value.",
            }
            for error in exc.errors()
        ]
        return problem_response(
            request,
            status=422,
            code="validation_error",
            title="One or more fields are invalid.",
            field_errors=fields,
        )

    @app.exception_handler(DataError)
    async def handle_unstorable_value(request: Request, exc: DataError) -> JSONResponse:
        """The database refused a value it could not store.

        That is input the request validators did not bound (a NUL byte in text, a number beyond
        the column's range), so it is the client's mistake, not a server fault. Validators should
        still reject known cases early; this is the safety net for the ones nobody thought of.
        """

        logger.warning("rejected an unstorable value on %s %s", request.method, request.url.path)
        return problem_response(
            request,
            status=422,
            code="invalid_value",
            title="A value is out of range or contains characters that cannot be stored.",
        )
