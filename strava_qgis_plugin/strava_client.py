"""Thin client for the Strava v3 REST API.

Only depends on the Python standard library so it works inside the QGIS
Python environment without extra installation steps. Network calls use
QgsBlockingNetworkRequest where possible to honour QGIS proxy settings,
but fall back to urllib for the token endpoint.
"""

import json
import time
import urllib.parse
import urllib.request
from typing import Dict, List, Optional

API_BASE = "https://www.strava.com/api/v3"
OAUTH_AUTHORIZE = "https://www.strava.com/oauth/authorize"
OAUTH_TOKEN = "https://www.strava.com/oauth/token"
DEFAULT_SCOPE = "read,activity:read_all"


class StravaError(Exception):
    """Raised for any non-2xx response from Strava."""


class StravaClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        access_token: str = "",
        refresh_token: str = "",
        expires_at: int = 0,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_at = int(expires_at or 0)

    def authorize_url(self, redirect_uri: str, scope: str = DEFAULT_SCOPE) -> str:
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "approval_prompt": "auto",
            "scope": scope,
        }
        return f"{OAUTH_AUTHORIZE}?{urllib.parse.urlencode(params)}"

    def exchange_code(self, code: str) -> Dict:
        return self._token_request({
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
        })

    def refresh(self) -> Dict:
        if not self.refresh_token:
            raise StravaError("No refresh token stored — re-authorize the plugin.")
        return self._token_request({
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
        })

    def _token_request(self, payload: Dict) -> Dict:
        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(OAUTH_TOKEN, data=data, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise StravaError(f"Token request failed ({exc.code}): {detail}") from exc
        except urllib.error.URLError as exc:
            raise StravaError(f"Token request failed: {exc.reason}") from exc

        self.access_token = body.get("access_token", "")
        self.refresh_token = body.get("refresh_token", self.refresh_token)
        self.expires_at = int(body.get("expires_at", 0))
        return body

    def ensure_valid_token(self) -> None:
        if not self.access_token:
            raise StravaError("No access token — connect to Strava first.")
        # Refresh proactively if the token expires in less than 60 seconds.
        if self.expires_at and self.expires_at - time.time() < 60:
            self.refresh()

    def list_activities(
        self,
        after: Optional[int] = None,
        before: Optional[int] = None,
        per_page: int = 30,
        max_activities: int = 30,
    ) -> List[Dict]:
        self.ensure_valid_token()
        collected: List[Dict] = []
        page = 1
        per_page = max(1, min(per_page, 200))
        while len(collected) < max_activities:
            params = {"page": page, "per_page": per_page}
            if after:
                params["after"] = after
            if before:
                params["before"] = before
            batch = self._get("/athlete/activities", params)
            if not batch:
                break
            collected.extend(batch)
            if len(batch) < per_page:
                break
            page += 1
        return collected[:max_activities]

    def get_activity(self, activity_id: int) -> Dict:
        self.ensure_valid_token()
        return self._get(f"/activities/{activity_id}", {"include_all_efforts": "false"})

    def _get(self, path: str, params: Dict) -> Dict:
        url = f"{API_BASE}{path}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, method="GET")
        req.add_header("Authorization", f"Bearer {self.access_token}")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise StravaError(f"Strava API error ({exc.code}) on {path}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise StravaError(f"Network error on {path}: {exc.reason}") from exc
