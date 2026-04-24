from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PROFILE_PATH = Path(__file__).parent / "profiles" / "HERMES-voltagrid-tx3.md"


@dataclass(frozen=True)
class Playbook:
    key: str
    template: str

    def render(self, **ctx: object) -> str:
        class _DefaultDict(dict):
            def __missing__(self, key):  # type: ignore[override]
                return "<unset>"

        return self.template.format_map(_DefaultDict(**{k: v for k, v in ctx.items()}))


_H2 = re.compile(r"^##\s+(.+)$", re.MULTILINE)
_H3 = re.compile(r"^###\s+(.+)$", re.MULTILINE)
_CODE_BLOCK = re.compile(r"^```\s*\n(.+?)\n```", re.MULTILINE | re.DOTALL)
_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*", re.DOTALL)


@lru_cache(maxsize=1)
def profile_text() -> str:
    return PROFILE_PATH.read_text()


def profile_metadata(path: Path | None = None) -> dict[str, Any]:
    text = Path(path).read_text() if path else profile_text()
    match = _FRONTMATTER.match(text)
    if not match:
        raise ValueError("missing YAML frontmatter")
    data = yaml.safe_load(match.group(1)) or {}
    if "site_profile" not in data:
        raise ValueError("profile frontmatter must declare site_profile")
    if not data.get("supported_event_kinds"):
        raise ValueError("profile frontmatter must declare supported_event_kinds")
    return data


def _section(heading: str, level: int = 2, path: Path | None = None) -> str:
    text = Path(path).read_text() if path else profile_text()
    pattern = _H2 if level == 2 else _H3
    for match in pattern.finditer(text):
        if match.group(1).strip() == heading:
            start = match.end()
            terminators = re.compile(rf"^#{{1,{level}}}\s+.+$", re.MULTILINE)
            tail = text[start:]
            term = terminators.search(tail)
            end = start + term.start() if term else len(text)
            return text[start:end].strip()
    raise KeyError(f"section not found at level {level}: {heading}")


@lru_cache(maxsize=1)
def identity() -> str:
    return _section("Identity")


@lru_cache(maxsize=1)
def playbooks_map() -> dict[str, Playbook]:
    section = _section("Playbooks")
    out: dict[str, Playbook] = {}
    h3s = list(_H3.finditer(section))
    for i, match in enumerate(h3s):
        key = match.group(1).strip()
        body_start = match.end()
        body_end = h3s[i + 1].start() if i + 1 < len(h3s) else len(section)
        code = _CODE_BLOCK.search(section[body_start:body_end])
        if code:
            out[key] = Playbook(key=key, template=code.group(1).strip())
    return out


def playbook(key: str) -> Playbook:
    try:
        return playbooks_map()[key]
    except KeyError as e:
        known = ", ".join(sorted(playbooks_map()))
        raise KeyError(f"unknown playbook '{key}'. known: {known}") from e


def playbook_keys() -> list[str]:
    return sorted(playbooks_map())


def system_message() -> dict[str, str]:
    return {"role": "system", "content": identity()}


def action_message(playbook_key: str, **context: object) -> dict[str, str]:
    return {"role": "user", "content": playbook(playbook_key).render(**context)}
