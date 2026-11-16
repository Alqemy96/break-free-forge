"""Local web UI server (outer layer, like the cli): consumes a `Forge`, holds no domain logic.

    from bl4forge.web import create_server, serve
    server = create_server(forge, port=0)       # bind; server.url has the address
    threading.Thread(target=server.serve_forever, daemon=True).start()

The contract with the UI is docs/WEB_API.md. Importing this package does no work.


DISCLOSURE (what this code does)
  Reads: the built UI files in web/static/ (when present) and, through the API, bytes and text that the browser sends. Writes: nothing to disk (the save endpoints return bytes for the browser to save). Network: a local HTTP server on 127.0.0.1:8734 by default. It refuses any Host/Origin that is not localhost, sends no CORS headers, accepts JSON bodies up to 1 MiB, and has NO login. Risk: binding another address (needs --allow-remote on the command line) would expose a save decrypt/encrypt service to that network. It makes no outbound connections.
"""
from ._errors import ApiError
from ._server import (DEFAULT_HOST, DEFAULT_PORT, MAX_BODY, PortInUse, ServerStartError, WebServer,
                      create_server, host_allowed, serve)

__all__ = ["ApiError", "DEFAULT_HOST", "DEFAULT_PORT", "MAX_BODY", "PortInUse", "ServerStartError",
           "WebServer", "create_server", "host_allowed", "serve"]
