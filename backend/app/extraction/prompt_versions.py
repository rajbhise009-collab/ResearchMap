"""Version-pinned prompt loader with content hashing.

Every prompt version is a directory under `prompts/` (e.g.
`prompts/v1.0.0/`) containing at least `extract.md`. The content hash
of the file (sha256, first 12 hex chars — the "prompt hash") is
attached to every extraction so we can trace which prompt version
produced any given `Claim`, `Limitation`, etc.

Rule: changing a prompt requires a new version directory. Never edit
`v1.0.0/extract.md` in place after any extraction has been persisted
against it. If you do, the prompt-hash lookup will lie about what
produced the data on disk.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from string import Template

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


class _StrictTemplate(Template):
    """`string.Template` with `$name` syntax so JSON braces in prompt
    bodies don't conflict with the substitution grammar."""


@dataclass(frozen=True)
class PromptVersion:
    version: str  # e.g. "v1.0.0"
    path: Path
    body: str
    sha256_full: str   # 64 hex chars
    hash: str          # sha256[:12] — the short id used in extractions

    def render(self, **fields) -> str:
        """Fill the prompt template's `$placeholder` fields. Uses
        `string.Template.substitute` so JSON `{}` in the body is
        passed through literally. Missing fields raise ValueError so
        the caller finds the bug immediately rather than shipping a
        prompt with an unfilled `$paper_id`."""
        try:
            return _StrictTemplate(self.body).substitute(**fields)
        except KeyError as e:
            raise ValueError(
                f"Prompt {self.version} is missing a required field: {e}"
            ) from e


_VERSION_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def available_versions() -> list[str]:
    """Every subdirectory of prompts/ matching v<major>.<minor>.<patch>."""
    if not PROMPTS_DIR.exists():
        return []
    out = []
    for p in sorted(PROMPTS_DIR.iterdir()):
        if p.is_dir() and _VERSION_RE.match(p.name):
            out.append(p.name)
    return out


def latest_version() -> str:
    """Highest-versioned prompt directory. Raises if none exist."""
    versions = available_versions()
    if not versions:
        raise FileNotFoundError(
            f"No prompt versions found under {PROMPTS_DIR}. "
            "At least one v<major>.<minor>.<patch>/extract.md must exist."
        )
    # semver sort
    def key(v: str) -> tuple[int, ...]:
        m = _VERSION_RE.match(v)
        assert m
        return tuple(int(x) for x in m.groups())
    return max(versions, key=key)


@lru_cache(maxsize=None)
def load(version: str) -> PromptVersion:
    """Load a prompt version by name (e.g. 'v1.0.0'). Cached by name;
    editing a prompt file in place requires a Python restart to pick
    up the change — that's deliberate."""
    if not _VERSION_RE.match(version):
        raise ValueError(
            f"Invalid prompt version {version!r}; expected "
            "'v<major>.<minor>.<patch>'."
        )
    path = PROMPTS_DIR / version / "extract.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    body = path.read_text(encoding="utf-8")
    sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return PromptVersion(
        version=version,
        path=path,
        body=body,
        sha256_full=sha,
        hash=sha[:12],
    )


__all__ = [
    "PROMPTS_DIR",
    "PromptVersion",
    "available_versions",
    "latest_version",
    "load",
]
