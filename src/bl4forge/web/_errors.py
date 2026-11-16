"""HTTP error vocabulary for the web layer: one exception type, one translation table.

Every failure leaves the server as `{"error": {"code": "...", "message": "..."}}` (docs/WEB_API.md).
Codes: bad_request, serial_error, save_error, key_missing (503), module_unavailable (503), data_missing (503), not_found, internal.
A traceback never reaches a response body."""
from __future__ import annotations

import re
from typing import Dict, Optional

from ..core.errors import (ConfigError, DataMissing, ForgeError, ModuleUnavailable, SaveError, SaveKeyMissing,
                           SerialError)

HINT = "run 'bl4forge doctor' for details"
_MODULE_RE = re.compile(r"module '([A-Za-z_][A-Za-z0-9_]*)'")


class ApiError(Exception):
    """A failure with a known HTTP status and contract error code."""

    def __init__(self, status: int, code: str, message: str,
                 headers: Optional[Dict[str, str]] = None, **extra):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.headers = dict(headers or {})
        self.extra = extra

    def body(self) -> dict:
        err = {"code": self.code, "message": self.message}
        err.update(self.extra)
        return {"error": err}


def bad_request(message: str) -> ApiError:
    return ApiError(400, "bad_request", message)


def not_found(message: str) -> ApiError:
    return ApiError(404, "not_found", message)


def module_unavailable(name: Optional[str], detail: str) -> ApiError:
    """503 naming the module (in the message and in `error.module`)."""
    text = (detail or "").strip() or ("module '%s' is unavailable" % name if name else "a module is unavailable")
    extra = {"module": name} if name else {}
    return ApiError(503, "module_unavailable", "%s (%s)" % (text, HINT), **extra)


def translate(exc: BaseException) -> ApiError:
    """Map anything a handler (or a module behind it) raised to an ApiError."""
    if isinstance(exc, ApiError):
        return exc
    if isinstance(exc, ModuleUnavailable):
        found = _MODULE_RE.search(str(exc))
        return module_unavailable(found.group(1) if found else None, str(exc))
    if isinstance(exc, NotImplementedError):          # a skeleton module that is not built yet
        found = _MODULE_RE.search(str(exc))
        return module_unavailable(found.group(1) if found else None, str(exc))
    if isinstance(exc, DataMissing):
        return ApiError(503, "data_missing", "required data is missing: %s (%s)" % (exc, HINT))
    if isinstance(exc, SerialError):
        return ApiError(400, "serial_error", str(exc))
    if isinstance(exc, SaveKeyMissing):
        return ApiError(503, "key_missing", "%s" % exc)
    if isinstance(exc, SaveError):
        return ApiError(400, "save_error", str(exc))
    if isinstance(exc, ConfigError):
        return ApiError(500, "internal", "configuration error: %s" % exc)
    if isinstance(exc, ForgeError):                    # intentional, human-readable text
        return ApiError(500, "internal", str(exc))
    return ApiError(500, "internal", "internal error (%s); see the server log" % type(exc).__name__)
