import os
import platform
import re
import subprocess
from pathlib import Path

LOOM_MARKER = ".loom.json"


class VaultNotFoundError(Exception):
    pass


def resolve_vault(vault_path: str) -> Path:
    """Resolve and validate the vault path."""
    p = Path(vault_path).expanduser().resolve()
    if not (p / LOOM_MARKER).exists():
        raise VaultNotFoundError(f"No loom vault at {p}. Run: loom init {p}")
    return p


def read_frontmatter(path: Path) -> dict:
    text = path.read_text()
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    result = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, val = line.split(":", 1)
            result[k.strip()] = val.strip().strip('"').strip("'")
    return result


def read_body(path: Path) -> str:
    return re.sub(r"^---.*?---\s*", "", path.read_text(), flags=re.DOTALL)


def slugify(t: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", t.lower().strip())
    hyphenated = re.sub(r"[-\s]+", "-", cleaned)
    return hyphenated[:60]



def open_in_obsidian(vault: Path, filepath: str) -> None:
    absolute_path = vault / filepath
    uri = f"obsidian://open?path={absolute_path}"
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.Popen(["open", uri])
        elif system == "Windows":
            getattr(os, "startfile")(uri)  # noqa: B009
        else:
            subprocess.Popen(["xdg-open", uri])
    except Exception:
        pass
