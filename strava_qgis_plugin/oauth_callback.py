"""Tiny localhost HTTP server that catches the OAuth redirect from Strava.

Strava redirects back to a URI like:
    http://localhost:PORT/?state=...&code=...&scope=read,activity:read_all

The server runs in a background thread, captures the first matching request,
stores the query parameters, and shuts down. The plugin then uses the code
to exchange for an access token.
"""

import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, Optional


_RESPONSE_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Strava — QGIS plugin</title></head>
<body style="font-family: system-ui, sans-serif; padding: 2em; max-width: 32em;">
  <h2>{title}</h2>
  <p>{body}</p>
  <p style="color:#888;">You can close this window and return to QGIS.</p>
</body></html>
"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - http.server API
        parsed = urllib.parse.urlparse(self.path)
        params = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        self.server.captured = params  # type: ignore[attr-defined]

        if "code" in params:
            body = _RESPONSE_TEMPLATE.format(
                title="Authorized",
                body="Strava authorization received. Returning to QGIS…",
            )
            self.send_response(200)
        else:
            err = params.get("error", "Missing authorization code.")
            body = _RESPONSE_TEMPLATE.format(title="Authorization failed", body=err)
            self.send_response(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, format, *args):  # noqa: A002 - silence default logging
        return


class OAuthCallbackServer:
    def __init__(self, port: int = 0):
        self._server = HTTPServer(("127.0.0.1", port), _Handler)
        self._server.captured = None  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def port(self) -> int:
        return self._server.server_address[1]

    @property
    def redirect_uri(self) -> str:
        return f"http://localhost:{self.port}/"

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def captured(self) -> Optional[Dict[str, str]]:
        return self._server.captured  # type: ignore[attr-defined]
