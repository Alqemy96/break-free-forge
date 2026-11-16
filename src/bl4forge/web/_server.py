"""The HTTP server: a ThreadingHTTPServer, one request handler, and `serve()` for the cli.

Security model (local only; see docs/WEB_API.md):
  * the Host header must be localhost / 127.0.0.1 / [::1] (DNS-rebinding guard); an Origin header,
    when sent, must also name one of those hosts;
  * POST bodies must be `application/json` and at most 1 MiB; chunked bodies are refused;
  * no CORS headers are ever sent, and OPTIONS is a 405;
  * static files cannot escape their directory (see _static.py);
  * errors are always the JSON error object, never an HTML page or a traceback.
"""
from __future__ import annotations

import errno
import json
import os
import re
import shutil
import socket
import sys
import time
import traceback
import webbrowser
from email.utils import formatdate
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import parse_qs, unquote, urlsplit

from ..core.errors import ForgeError
from ..core.forge import Forge
from ._api import Api, Fields, ROUTES
from ._errors import ApiError, bad_request, not_found, translate
from ._static import FALLBACK, NO_CACHE, REJECT, StaticFiles, cache_control, content_type

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8734
MAX_BODY = 1024 * 1024                  # 1 MiB
DRAIN_CAP = 4 * 1024 * 1024             # an unread body up to this size is read off the wire before replying
IDLE_TIMEOUT = 30                       # seconds a connection may sit silent
DEFAULT_STATIC_DIR = Path(__file__).resolve().parent / "static"

_ALLOWED_HOSTNAMES = ("localhost", "127.0.0.1", "[::1]")
_HOST_RE = re.compile(r"(\[[0-9a-f:.]+\]|[a-z0-9.\-]+)(?::(\d{1,5}))?")
_MAX_QUERY_FIELDS = 64


class ServerStartError(ForgeError):
    """The server could not start (bad host, no permission, ...)."""


class PortInUse(ServerStartError):
    """Another program is already listening on the requested port."""


def host_allowed(value: Optional[str]) -> bool:
    """True for `localhost`, `127.0.0.1` and `[::1]`, with or without a numeric port."""
    if not value:
        return False
    m = _HOST_RE.fullmatch(value.strip().lower())
    return bool(m) and m.group(1) in _ALLOWED_HOSTNAMES


def origin_allowed(value: str) -> bool:
    """An `Origin` header is acceptable when its host is one of the allowed local names."""
    try:
        host = urlsplit(value).hostname
    except ValueError:
        return False
    return host in ("localhost", "127.0.0.1", "::1")


def _printable(text: str, limit: int = 200) -> str:
    text = "".join(c if 32 <= ord(c) < 127 else "?" for c in text)
    return text if len(text) <= limit else text[:limit] + "..."


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = IDLE_TIMEOUT
    server_version = "bl4forge"
    sys_version = ""
    _status = 0
    _unread = 0

    # ---- plumbing ----
    def version_string(self) -> str:
        return "bl4forge"

    def log_request(self, code="-", size="-") -> None:      # we log one line ourselves
        pass

    def log_message(self, format, *args) -> None:           # http.server's own complaints (bad request line, ...)
        text = format % args
        if not self.server.quiet and not text.startswith("Request timed out"):   # an idle keep-alive timing out is normal
            self._emit("http.server: " + text)

    def _emit(self, line: str) -> None:
        try:
            sys.stderr.write(line + "\n")
            sys.stderr.flush()
        except Exception:
            pass

    def handle_one_request(self) -> None:
        self._status = 0
        self._unread = 0
        super().handle_one_request()

    def send_response(self, code, message=None) -> None:
        self._status = int(code)
        super().send_response(code, message)

    def send_error(self, code, message=None, explain=None) -> None:
        """http.server calls this for malformed requests; answer in the JSON error format."""
        if code == 501:
            err = ApiError(405, "bad_request", "method %s is not supported" % _printable(str(self.command), 20),
                           {"Allow": "GET, HEAD, POST"})
        else:
            status = int(code)
            try:
                phrase = HTTPStatus(status).phrase
            except ValueError:
                phrase = "error"
            err = ApiError(status, "not_found" if status == 404 else ("internal" if status >= 500 else "bad_request"),
                           (message or phrase))
        self.close_connection = True
        self._write_error(err)
        if self.command is None and not self.server.quiet:   # never reached _handle, so log it here
            self._emit("- %s %s" % (_printable(self.requestline or "-", 80), self._status or "-"))

    # ---- dispatch ----
    def do_GET(self): self._handle()
    do_HEAD = do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_GET

    def _handle(self) -> None:
        started = time.perf_counter()
        try:
            try:
                self._route()
            except (ConnectionError, TimeoutError):
                raise
            except Exception as ex:
                err = translate(ex)
                if err.code == "internal" and not isinstance(ex, (ApiError, ForgeError)):
                    self._emit("error handling %s %s:\n%s" % (
                        self.command, _printable(self.path), traceback.format_exc().rstrip()))
                if self._status:                   # a response was already started: cannot send another
                    self.close_connection = True
                else:
                    self._write_error(err)
        except (ConnectionError, TimeoutError, OSError):
            self.close_connection = True       # the client went away mid-response
        finally:
            if not self.server.quiet:
                ms = int((time.perf_counter() - started) * 1000)
                self._emit("%s %s %s %dms" % (self.command, _printable(self.path), self._status or "-", ms))

    def _route(self) -> None:
        method = self.command
        self._check_framing()
        self._check_host()
        path, query = self._split_target()
        if path == "/api" or path.startswith("/api/"):
            self._api(method, path, query)
        else:
            self._static(method, path)

    # ---- request checks ----
    def _check_framing(self) -> None:
        if self.headers.get("Transfer-Encoding") is not None:
            self.close_connection = True
            raise bad_request("chunked or encoded request bodies are not supported; send Content-Length")
        raw = self.headers.get("Content-Length")
        if raw is None:
            return
        if not re.fullmatch(r"\d{1,12}", raw.strip()):
            self.close_connection = True
            raise bad_request("invalid Content-Length")
        self._unread = int(raw.strip())

    def _check_host(self) -> None:
        hosts = self.headers.get_all("Host") or []
        if len(hosts) != 1 or not host_allowed(hosts[0]):
            raise bad_request("request rejected: the Host header must be localhost, 127.0.0.1 or [::1]")
        origin = self.headers.get("Origin")
        if origin is not None and not origin_allowed(origin):
            raise bad_request("request rejected: cross-origin requests are not allowed")

    def _split_target(self):
        target = self.path
        if target.startswith("/"):
            path, _, query = target.split("#", 1)[0].partition("?")
        else:                                           # absolute-form (proxy style) or garbage
            try:
                parts = urlsplit(target)
            except ValueError:
                raise bad_request("malformed request target")
            path, query = parts.path, parts.query
            if not path.startswith("/"):
                raise bad_request("malformed request target")
        return path, query

    # ---- API ----
    def _api(self, method: str, path: str, query: str) -> None:
        route = ROUTES.get(path)
        if route is None:
            raise not_found("no such endpoint: %s" % _printable(path, 80))
        verb, handler = route
        if method == "HEAD" and verb == "GET":
            method = "GET"
        if method != verb:
            allow = "GET, HEAD" if verb == "GET" else verb
            raise ApiError(405, "bad_request", "%s is not allowed here; use %s" % (self.command, allow),
                           {"Allow": allow})
        if verb == "POST":
            fields = Fields(self._read_json_object(), from_query=False)
        else:
            try:
                pairs = parse_qs(query, keep_blank_values=True, max_num_fields=_MAX_QUERY_FIELDS, errors="replace")
            except ValueError:
                raise bad_request("malformed or oversized query string")
            fields = Fields({k: v[-1] for k, v in pairs.items()}, from_query=True)
        self._send_json(200, handler(self.server.api, fields))

    def _read_json_object(self) -> dict:
        ctype = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if ctype != "application/json":
            raise ApiError(415, "bad_request", "Content-Type must be application/json")
        raw = self.headers.get("Content-Length")
        if raw is None:
            raise bad_request("a JSON body is required (Content-Length is missing)")
        length = self._unread
        if length > MAX_BODY:
            raise ApiError(413, "bad_request", "request body is too large (limit %d bytes)" % MAX_BODY)
        try:
            body = self.rfile.read(length) if length else b""
        except OSError:
            self.close_connection = True
            raise bad_request("could not read the request body")
        self._unread = 0
        if len(body) < length:
            self.close_connection = True
            raise bad_request("request body is shorter than its Content-Length")
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError) as ex:
            raise bad_request("request body is not valid JSON (%s)" % (
                ex if isinstance(ex, ValueError) and not isinstance(ex, UnicodeDecodeError) else "bad UTF-8"))
        if not isinstance(data, dict):
            raise bad_request("request body must be a JSON object")
        return data

    # ---- static ----
    def _static(self, method: str, path: str) -> None:
        decoded = unquote(path, errors="replace")
        if decoded == "/api" or decoded.startswith("/api/"):      # e.g. /api%2fmeta: never the SPA
            raise not_found("no such endpoint")
        if method not in ("GET", "HEAD"):
            raise ApiError(405, "bad_request", "%s is not allowed here; use GET" % method, {"Allow": "GET, HEAD"})
        kind, target = self.server.static.resolve(decoded)
        if kind == REJECT:
            raise not_found("not found")
        if target is None:
            raise not_found("the web UI has not been built (no index.html in the static directory)")
        self._send_file(target, "index.html" if kind == FALLBACK else self.server.static.rel(target))

    def _send_file(self, path: Path, rel: str) -> None:
        try:
            handle = open(path, "rb")
        except OSError:
            raise not_found("not found")
        with handle:
            st = os.fstat(handle.fileno())
            etag = 'W/"%x-%x"' % (st.st_mtime_ns, st.st_size)
            cache = NO_CACHE if rel == "index.html" else cache_control(rel)
            self._drain_unread()
            if any(etag == t.strip() for t in (self.headers.get("If-None-Match") or "").split(",")):
                self.send_response(304)
                self._common_headers()
                self.send_header("ETag", etag)
                self.send_header("Cache-Control", cache)
                self.end_headers()
                return
            self.send_response(200)
            self._common_headers()
            self.send_header("Content-Type", content_type(path))
            self.send_header("Content-Length", str(st.st_size))
            self.send_header("Cache-Control", cache)
            self.send_header("ETag", etag)
            self.send_header("Last-Modified", formatdate(st.st_mtime, usegmt=True))
            self.end_headers()
            if self.command != "HEAD":
                shutil.copyfileobj(handle, self.wfile, 65536)

    # ---- responses ----
    def _common_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")

    def _drain_unread(self) -> None:
        """Read an unconsumed request body off the wire before replying, so closing or reusing the
        connection cannot reset it under the client. Huge or stalled bodies just close the connection."""
        remaining = self._unread
        self._unread = 0
        if remaining <= 0:
            return
        if remaining > DRAIN_CAP:
            self.close_connection = True
            return
        try:
            self.connection.settimeout(2.0)
            while remaining > 0:
                chunk = self.rfile.read(min(remaining, 65536))
                if not chunk:
                    self.close_connection = True
                    break
                remaining -= len(chunk)
            self.connection.settimeout(self.timeout)
        except OSError:
            self.close_connection = True

    def _send_bytes(self, status: int, body: bytes, extra: Optional[Dict[str, str]] = None) -> None:
        if self.request_version == "HTTP/0.9":      # http.server's default for an unparsable request line:
            self.request_version = "HTTP/1.0"       # still answer with a status line and headers
        self._drain_unread()
        self.send_response(status)
        self._common_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        if self.close_connection:
            self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8", "replace")
        self._send_bytes(status, body)

    def _write_error(self, err: ApiError) -> None:
        body = json.dumps(err.body(), ensure_ascii=False, separators=(",", ":")).encode("utf-8", "replace")
        self._send_bytes(err.status, body, err.headers)


class WebServer(ThreadingHTTPServer):
    daemon_threads = True              # a lingering keep-alive connection must not block shutdown
    request_queue_size = 128
    # On Windows SO_REUSEADDR lets a second process bind a port that is already in use, which would
    # make "port busy" undetectable; there we take the port exclusively instead.
    allow_reuse_address = os.name != "nt"

    def __init__(self, address, api: Api, static: StaticFiles, quiet: bool = False):
        self.api = api
        self.static = static
        self.quiet = quiet
        self.address_family = socket.AF_INET6 if ":" in address[0] else socket.AF_INET
        super().__init__(address, Handler)

    def server_bind(self) -> None:
        exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if os.name == "nt" and exclusive is not None:
            self.socket.setsockopt(socket.SOL_SOCKET, exclusive, 1)
        # Not HTTPServer.server_bind: its getfqdn() reverse lookup can stall startup for seconds.
        import socketserver
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name, self.server_port = host, port

    def handle_error(self, request, client_address) -> None:
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionError, TimeoutError)):
            return
        if not self.quiet:
            sys.stderr.write("error serving %s:\n%s\n" % (client_address[0], traceback.format_exc().rstrip()))

    @property
    def url(self) -> str:
        host, port = self.server_address[:2]
        if ":" in host:
            host = "[%s]" % host
        return "http://%s:%d/" % (host, port)


def create_server(forge: Forge, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, *,
                  quiet: bool = False, static_dir=None) -> WebServer:
    """Bind a server for `forge` (nothing is served until `serve_forever()`). Pass `port=0` for a
    free port (see `.url`). Raises PortInUse / ServerStartError."""
    static = StaticFiles(Path(static_dir) if static_dir else DEFAULT_STATIC_DIR)
    try:
        return WebServer((host, port), Api(forge), static, quiet)
    except OverflowError:
        raise ServerStartError("port must be from 0 to 65535, got %r" % (port,))
    except socket.gaierror as ex:
        raise ServerStartError("cannot use host %r: %s" % (host, ex))
    except OSError as ex:
        busy = ex.errno == errno.EADDRINUSE or getattr(ex, "winerror", None) in (10048, 10013)
        if busy:
            raise PortInUse("port %s is already in use on %s (another bl4forge serve, or a different program?). "
                            "Choose another with --port, or stop the other one." % (port, host))
        raise ServerStartError("cannot listen on %s:%s: %s" % (host, port, ex.strerror or ex))


def serve(forge: Forge, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, *, open_browser: bool = False,
          quiet: bool = False, static_dir=None) -> int:
    """Run until Ctrl+C. Returns the process exit code (0 after a clean stop)."""
    server = create_server(forge, host, port, quiet=quiet, static_dir=static_dir)
    try:
        if host not in ("127.0.0.1", "localhost", "::1"):
            sys.stderr.write("warning: listening on %s makes the port reachable from other machines; "
                             "requests whose Host header is not localhost/127.0.0.1/[::1] are still refused\n" % host)
        if not (server.static.index).is_file():
            sys.stderr.write("note: the web UI bundle is not built (no index.html in %s); the JSON API works but "
                             "the pages will answer 404. Build it with: cd ui && npm install --include=dev && "
                             "npm run build (see docs/runbooks/DEVELOPER.md)\n" % server.static.root)
        for name, state in sorted(forge.states.items()):
            if state.state != "ok":
                sys.stderr.write("warning: module '%s' is %s (%s); endpoints that need it will answer 503 - "
                                 "run 'bl4forge doctor' for details\n" % (name, state.state, state.detail or "no detail"))
        print("bl4forge web UI: %s  (Ctrl+C to stop)" % server.url, flush=True)
        if open_browser:
            try:
                webbrowser.open(server.url)
            except Exception:
                pass
        try:
            server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            pass
        print("stopped", flush=True)
        return 0
    finally:
        server.server_close()
