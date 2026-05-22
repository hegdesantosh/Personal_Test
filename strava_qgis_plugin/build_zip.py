"""Build a QGIS-installable zip of the Strava plugin.

Usage:
    python3 strava_qgis_plugin/build_zip.py

Produces `dist/strava_qgis_plugin-<version>.zip` at the repo root. The zip
contains a top-level `strava_qgis_plugin/` folder, which is what QGIS's
"Install from ZIP" expects.
"""

import configparser
import os
import zipfile
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent
REPO_ROOT = PLUGIN_DIR.parent
DIST_DIR = REPO_ROOT / "dist"

EXCLUDE_DIRS = {"__pycache__", ".git", ".mypy_cache", ".pytest_cache"}
EXCLUDE_FILES = {".DS_Store"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}


def read_version() -> str:
    cfg = configparser.ConfigParser()
    cfg.read(PLUGIN_DIR / "metadata.txt", encoding="utf-8")
    return cfg["general"]["version"]


def should_include(path: Path) -> bool:
    if path.name in EXCLUDE_FILES:
        return False
    if path.suffix in EXCLUDE_SUFFIXES:
        return False
    if any(part in EXCLUDE_DIRS for part in path.parts):
        return False
    return True


def main() -> Path:
    version = read_version()
    DIST_DIR.mkdir(exist_ok=True)
    target = DIST_DIR / f"strava_qgis_plugin-{version}.zip"
    if target.exists():
        target.unlink()

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(PLUGIN_DIR.rglob("*")):
            if path.is_dir() or not should_include(path):
                continue
            arcname = Path("strava_qgis_plugin") / path.relative_to(PLUGIN_DIR)
            zf.write(path, arcname.as_posix())

    print(f"Built {target.relative_to(REPO_ROOT)} ({target.stat().st_size} bytes)")
    return target


if __name__ == "__main__":
    main()
