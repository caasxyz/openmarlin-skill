"""Helpers for reading persisted OpenClaw skill config."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


SKILL_KEY = "claw-federation-registration"
SKILL_KEY_ALIASES = [SKILL_KEY, "claw-federation"]


def _candidate_config_paths() -> list[Path]:
    return [
        Path.home() / ".openclaw" / "openclaw.json",
        Path("/data/.clawdbot/openclaw.json"),
    ]


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _skill_entry(config: dict[str, Any]) -> dict[str, Any] | None:
    skills = config.get("skills")
    if not isinstance(skills, dict):
        return None
    entries = skills.get("entries")
    if not isinstance(entries, dict):
        return None
    for key in SKILL_KEY_ALIASES:
        entry = entries.get(key)
        if isinstance(entry, dict):
            return entry
    return None


def load_openclaw_skill_entry() -> tuple[dict[str, Any] | None, str | None]:
    for path in _candidate_config_paths():
        parsed = _load_json(path)
        if not parsed:
            continue
        entry = _skill_entry(parsed)
        if entry is not None:
            return entry, str(path)
    return None, None


def get_skill_env(var_name: str) -> tuple[str | None, str | None]:
    env_value = os.environ.get(var_name, "").strip()
    if env_value:
        return env_value, "process-env"

    entry, config_path = load_openclaw_skill_entry()
    if not entry:
        return None, None

    env_block = entry.get("env")
    if not isinstance(env_block, dict):
        return None, config_path

    value = env_block.get(var_name)
    if isinstance(value, str) and value.strip():
        return value.strip(), f"openclaw-config:{config_path}"

    return None, config_path
