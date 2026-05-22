# Strava Activities — QGIS Plugin

Import your Strava activities into QGIS as a styled line layer. Each feature
carries the GPS track plus key metadata (name, type, distance, time,
elevation, heart rate, kudos, link back to strava.com).

## Features

- OAuth 2.0 connect flow: the plugin spins up a local callback server,
  opens your browser, and exchanges the code for an access + refresh token.
- Tokens are auto-refreshed before expiry; you only authorize once.
- Filter imports by date range and activity count.
- Activities are rendered as a categorized line layer, color-coded by
  activity type (Ride, Run, Walk, Hike, Swim…).
- Decodes Strava's encoded polyline locally — no extra Python dependencies.
- All attribute fields are typed (distances in meters, times in seconds,
  speeds in m/s).

## Install

1. Copy or symlink the `strava_qgis_plugin` directory into your QGIS
   plugins folder:
   - Linux: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
   - macOS: `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/`
   - Windows: `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`
2. Restart QGIS and enable **Strava Activities** in `Plugins → Manage and Install Plugins → Installed`.

## Set up Strava API credentials

1. Go to <https://www.strava.com/settings/api> and create an application.
2. Set **Authorization Callback Domain** to `localhost`.
3. Copy the **Client ID** and **Client Secret** into the plugin dialog
   (`Web → Strava → Strava Activities`, or the toolbar icon).
4. Click **Connect to Strava…** — your browser opens, you approve the
   `read,activity:read_all` scope, and the plugin captures the redirect.

## Use

- Open the plugin (toolbar icon or `Web → Strava`).
- Pick a date range and activity limit.
- Click **Import activities**.
- A new memory layer named `Strava (N activities)` is added to the
  project, styled by activity type, with the canvas zoomed to its extent.

Activities without GPS data (e.g. indoor rides on a turbo trainer) are
skipped — the dialog reports the count.

## Files

| File | Purpose |
| --- | --- |
| `__init__.py` | QGIS plugin factory |
| `metadata.txt` | Plugin metadata for QGIS plugin manager |
| `strava_plugin.py` | Toolbar/menu integration, dialog lifecycle |
| `strava_dialog.py` | Settings + OAuth + import dialog (built in code) |
| `strava_client.py` | Strava v3 REST client (stdlib only) |
| `oauth_callback.py` | Localhost HTTP server for the OAuth redirect |
| `polyline_codec.py` | Decoder for Strava's encoded polylines |
| `layer_builder.py` | Builds the QgsVectorLayer + categorized renderer |
| `settings_store.py` | Persists credentials/tokens in `QgsSettings` |
| `icon.png` | Toolbar icon |

## Notes & limitations

- Tokens are stored in `QgsSettings`, which is plain on disk. For stronger
  protection, migrate to `QgsAuthManager` (TODO).
- Only the activity **summary polyline** is fetched, which keeps imports
  fast but gives a slightly simplified track. Higher-resolution streams
  (`/activities/{id}/streams`) could be wired in later.
- Strava enforces rate limits (currently 100 requests / 15 minutes,
  1000 / day). The plugin paginates `/athlete/activities` so a single
  import normally uses ≤ a handful of requests.
