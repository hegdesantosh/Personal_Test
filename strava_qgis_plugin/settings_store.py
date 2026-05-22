"""Persist Strava credentials and tokens in QgsSettings.

QgsSettings stores values in QGIS's user profile (an INI-style file on disk).
The plugin keeps everything under the `strava/` prefix so it's easy to find
and remove via the QGIS Options dialog if needed.

Note on secrets: QgsSettings is not an encrypted secret store. Users who
need stronger guarantees should use QGIS's authentication database
(`QgsAuthManager`) — that's a future enhancement.
"""

from typing import Dict

from qgis.core import QgsSettings

PREFIX = "strava/"

_DEFAULTS: Dict[str, str] = {
    "client_id": "",
    "client_secret": "",
    "access_token": "",
    "refresh_token": "",
    "expires_at": "0",
}


def load() -> Dict[str, str]:
    s = QgsSettings()
    return {key: s.value(PREFIX + key, default) for key, default in _DEFAULTS.items()}


def save(values: Dict[str, str]) -> None:
    s = QgsSettings()
    for key, value in values.items():
        if key in _DEFAULTS:
            s.setValue(PREFIX + key, value)


def clear_tokens() -> None:
    s = QgsSettings()
    for key in ("access_token", "refresh_token", "expires_at"):
        s.setValue(PREFIX + key, _DEFAULTS[key])
