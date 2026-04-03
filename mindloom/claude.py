import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_MAX_TURNS = 15


def has_claude_code() -> bool:
    return shutil.which("claude") is not None


def run_claude(
    vault: Path,
    prompt: str,
    tools: str = "Read,Edit,Write,Glob,Grep,Bash",
    max_turns: int = DEFAULT_MAX_TURNS,
    stream: bool = True,
) -> str:
    """Run claude -p. Raises RuntimeError if claude not installed."""
    if not has_claude_code():
        raise RuntimeError(
            "Claude Code not found. Install: npm i -g @anthropic-ai/claude-code"
        )
    cmd = [
        "claude",
        "-p",
        prompt,
        "--allowedTools",
        tools,
        "--max-turns",
        str(max_turns),
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=str(vault),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    lines = []
    assert proc.stdout is not None
    for line in proc.stdout:
        if stream:
            sys.stdout.write(line)
            sys.stdout.flush()
        lines.append(line)
    proc.wait()
    return "".join(lines)
