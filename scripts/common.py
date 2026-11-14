"""Shared helpers for the scripts: read .env and connect to MariaDB."""
import os
from pathlib import Path

import mariadb

ROOT = Path(__file__).resolve().parent.parent


def env():
    """Settings from .env (git-ignored), overridden by real environment variables."""
    values = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.split(" #")[0].strip()          # allow trailing comments
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    values.update({k: v for k, v in os.environ.items() if k in values})
    return values


def connect():
    e = env()
    return mariadb.connect(host=e.get("DB_HOST", "127.0.0.1"), port=int(e.get("DB_PORT", 3306)),
                           user=e["DB_USER"], password=e["DB_PASSWORD"],
                           database=e.get("DB_NAME", "wiki"))
