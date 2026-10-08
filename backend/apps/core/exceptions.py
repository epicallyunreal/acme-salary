"""Domain exceptions raised by services and the DRF handler that maps them to responses.

Invalid is a 400 with per-field messages. Conflict is a 409 with a detail and optional extras.
Forbidden is a 403 with per-field messages, for the demo reset's password and confirmation (D72).
Services raise these; views never build error responses by hand.
"""

from collections.abc import Mapping, Sequence

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler

# A message repeats at most this much of any value it names (D56): a sheet cell can be
# 100,000 characters, messages are stored on every staged row, and a 400 names what it refused.
ECHO_LIMIT = 64


def clip(value: object, limit: int = ECHO_LIMIT) -> str:
    """`value` as text, cut to `limit` characters with an ellipsis when it is longer."""
    text = str(value)
    return text if len(text) <= limit else f"{text[: limit - 1]}\u2026"


class DomainError(Exception):
    pass


class Invalid(DomainError):
    def __init__(self, errors: Mapping[str, Sequence[str] | str]):
        self.errors: dict[str, list[str]] = {
            field: [messages] if isinstance(messages, str) else list(messages)
            for field, messages in errors.items()
        }
        super().__init__(self.errors)


class Forbidden(Invalid):
    """Refused on what the caller gave, with per-field messages, as a 403."""


class Conflict(DomainError):
    def __init__(self, detail: str, **extra):
        self.detail = detail
        self.extra = extra
        super().__init__(detail)


class PayloadTooLarge(APIException):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_detail = "upload is larger than the 10 MB limit"
    default_code = "payload_too_large"


class ApplyFailed(APIException):
    """An approve that failed mid-way: the batch is marked failed, the rows are kept (D24)."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "approve failed, the batch is marked failed"
    default_code = "apply_failed"

    def __init__(self, error_summary: str):
        super().__init__({"detail": self.default_detail, "error_summary": error_summary})


def handler(exc, context):
    if isinstance(exc, Forbidden):
        return Response(exc.errors, status=status.HTTP_403_FORBIDDEN)
    if isinstance(exc, Invalid):
        return Response(exc.errors, status=status.HTTP_400_BAD_REQUEST)
    if isinstance(exc, Conflict):
        return Response({"detail": exc.detail, **exc.extra}, status=status.HTTP_409_CONFLICT)
    return exception_handler(exc, context)
