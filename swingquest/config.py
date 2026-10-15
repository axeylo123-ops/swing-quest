"""Loads settings from config/*.yaml and private values from .env."""
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
CACHE_DIR = ROOT / "cache"          # big re-creatable downloads (gitignored)
DATA_OUT_DIR = ROOT / "docs" / "data"  # JSON the dashboard reads (committed)

load_dotenv(ROOT / ".env")


def load_yaml(name: str) -> dict:
    with open(CONFIG_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def settings() -> dict:
    return load_yaml("settings.yaml")


def sec_user_agent() -> str:
    """The SEC requires a 'Name email' User-Agent. Fail loudly if missing."""
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if "@" not in ua:
        raise RuntimeError(
            "SEC_USER_AGENT is not set. Copy .env.example to .env and add your "
            "name and email (or set the GitHub secret in Actions)."
        )
    return ua
