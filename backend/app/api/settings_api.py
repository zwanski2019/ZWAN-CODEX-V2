"""Settings API — read/write live configuration.

API keys are stored encrypted (Fernet). GET responses mask sensitive values.
PUT updates DB + rewrites the .env file so settings survive restart.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.base import get_db
from app.db.models import AppSetting

router = APIRouter(prefix="/settings", tags=["settings"])

_ENV_PATH = Path(__file__).parents[3] / ".env"

# Which keys are user-visible / editable through the UI
_SCHEMA: list[dict] = [
    # key, label, section, is_sensitive, description
    {"key": "ANTHROPIC_API_KEY",       "label": "Anthropic API Key",       "section": "ai",    "sensitive": True,  "desc": "Primary LLM provider (Claude models)"},
    {"key": "OPENROUTER_API_KEY",      "label": "OpenRouter API Key",       "section": "ai",    "sensitive": True,  "desc": "Free-model fallback when Anthropic budget runs out"},
    {"key": "OPENROUTER_MODEL_HEAVY",  "label": "OR Heavy Model",           "section": "ai",    "sensitive": False, "desc": "Free model for deep reasoning tasks"},
    {"key": "OPENROUTER_MODEL_MID",    "label": "OR Mid Model",             "section": "ai",    "sensitive": False, "desc": "Free model for general analysis"},
    {"key": "OPENROUTER_MODEL_LIGHT",  "label": "OR Light Model",           "section": "ai",    "sensitive": False, "desc": "Free model for quick classification"},
    {"key": "LLM_BUDGET_DEFAULT",      "label": "Default LLM Budget (USD)", "section": "ai",    "sensitive": False, "desc": "Per-engagement budget cap"},
    {"key": "BURP_API_KEY",            "label": "Burp Suite API Key",       "section": "tools", "sensitive": True,  "desc": "Burp Pro REST API key (optional)"},
    {"key": "BURP_API_URL",            "label": "Burp API URL",             "section": "tools", "sensitive": False, "desc": "Default: http://127.0.0.1:1337"},
    {"key": "INTERACTSH_SERVER",       "label": "Interactsh Server",        "section": "oast",  "sensitive": False, "desc": "Leave blank to use oast.pro"},
    {"key": "INTERACTSH_TOKEN",        "label": "Interactsh Token",         "section": "oast",  "sensitive": True,  "desc": "Required only for self-hosted Interactsh"},
    {"key": "FERNET_KEY",             "label": "Encryption Key (Fernet)",  "section": "crypto","sensitive": True,  "desc": "Used to encrypt stored secrets — do not change after first run"},
]

_SCHEMA_MAP = {s["key"]: s for s in _SCHEMA}


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return value[:6] + "***" + value[-2:]


def _read_env() -> dict[str, str]:
    out: dict[str, str] = {}
    if not _ENV_PATH.exists():
        return out
    for line in _ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        out[key.strip()] = val.strip()
    return out


def _write_env(updates: dict[str, str]) -> None:
    existing = _ENV_PATH.read_text() if _ENV_PATH.exists() else ""
    lines = existing.splitlines()
    applied: set[str] = set()

    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue
        key, _, _ = stripped.partition("=")
        key = key.strip()
        if key in updates:
            new_lines.append(f"{key}={updates[key]}")
            applied.add(key)
        else:
            new_lines.append(line)

    for key, val in updates.items():
        if key not in applied:
            new_lines.append(f"{key}={val}")

    _ENV_PATH.write_text("\n".join(new_lines) + "\n")


def _live_value(key: str) -> str:
    """Read current live value from settings singleton."""
    attr = key.lower()
    return str(getattr(settings, attr, "") or "")


class SettingOut(BaseModel):
    key: str
    value: str        # masked for sensitive
    raw_set: bool     # true if a non-empty value is configured
    section: str
    label: str
    sensitive: bool
    desc: str


class SettingsPut(BaseModel):
    updates: dict[str, str]


@router.get("/", response_model=list[SettingOut])
async def get_settings(db: Annotated[AsyncSession, Depends(get_db)]) -> list[SettingOut]:
    env_vals = _read_env()
    out: list[SettingOut] = []

    for meta in _SCHEMA:
        key = meta["key"]
        # Prefer DB row, fall back to .env, fall back to live settings
        result = await db.execute(select(AppSetting).where(AppSetting.key == key))
        row = result.scalar_one_or_none()

        if row:
            raw = row.value
        else:
            raw = env_vals.get(key, _live_value(key))

        out.append(SettingOut(
            key=key,
            value=_mask(raw) if meta["sensitive"] else raw,
            raw_set=bool(raw),
            section=meta["section"],
            label=meta["label"],
            sensitive=meta["sensitive"],
            desc=meta["desc"],
        ))

    return out


@router.put("/")
async def put_settings(
    body: SettingsPut,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    env_updates: dict[str, str] = {}
    applied: list[str] = []

    for key, val in body.updates.items():
        if key not in _SCHEMA_MAP:
            continue

        # Skip placeholder masks — user didn't change this field
        if val.endswith("***") and "***" in val:
            continue

        meta = _SCHEMA_MAP[key]

        # Upsert in DB
        result = await db.execute(select(AppSetting).where(AppSetting.key == key))
        row = result.scalar_one_or_none()
        if row:
            row.value = val
            row.is_sensitive = meta["sensitive"]
        else:
            db.add(AppSetting(key=key, value=val, is_sensitive=meta["sensitive"]))

        env_updates[key] = val
        applied.append(key)

        # Update live settings singleton so agents immediately see new values
        attr = key.lower()
        if hasattr(settings, attr):
            try:
                setattr(settings, attr, type(getattr(settings, attr))(val))
            except Exception:
                pass

    await db.commit()

    # Persist to .env so values survive restart
    if env_updates:
        _write_env(env_updates)

    return {"saved": applied, "restart_required": _needs_restart(applied)}


def _needs_restart(keys: list[str]) -> list[str]:
    """Keys that require a service restart to take full effect."""
    restart_keys = {"ANTHROPIC_API_KEY", "DATABASE_URL", "REDIS_URL", "FERNET_KEY"}
    return [k for k in keys if k in restart_keys]
