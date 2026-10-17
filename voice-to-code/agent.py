"""Hand a spoken instruction to Claude Code, safely, on a fresh git branch.

We deliberately:
  * create a new branch first, so the current branch is never touched;
  * run Claude Code in `acceptEdits` mode with no shell tool, so it can change
    files but cannot run arbitrary commands;
  * leave the result uncommitted, so you review the diff in VS Code before
    anything is merged.
"""

import datetime as dt
import subprocess
from pathlib import Path

from config import settings


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=120
    )


def run_agent(instruction: str) -> dict:
    """Apply `instruction` to the project and return a summary of what happened."""
    project = Path(settings.project_dir).expanduser().resolve()
    if not project.is_dir():
        raise FileNotFoundError(f"PROJECT_DIR does not exist: {project}")
    if not (project / ".git").exists():
        raise RuntimeError(f"PROJECT_DIR is not a git repository: {project}")

    # 1. Safety net: work on a throwaway branch.
    branch = f"{settings.agent_branch_prefix}/{dt.datetime.now():%Y%m%d-%H%M%S}"
    checkout = _git(["checkout", "-b", branch], project)
    if checkout.returncode != 0:
        raise RuntimeError(f"git checkout -b failed: {checkout.stderr.strip()}")

    # 2. Run Claude Code headless.
    prompt = (
        "You are being driven by a spoken phone instruction. Apply the "
        "instruction below to this project. Make the smallest set of edits "
        "that satisfies it, then stop. Do not commit, do not push, and do not "
        "run shell commands.\n\n"
        f"Instruction: {instruction}"
    )
    cmd = [
        settings.claude_binary,
        "--print",
        "--permission-mode", settings.agent_permission_mode,
        "--allowedTools", settings.agent_allowed_tools,
        prompt,
    ]
    proc = subprocess.run(
        cmd,
        cwd=project,
        capture_output=True,
        text=True,
        timeout=settings.agent_timeout_seconds,
    )

    # 3. Summarise the changes; leave them uncommitted for review.
    diff = _git(["diff", "--stat"], project)
    return {
        "branch": branch,
        "returncode": proc.returncode,
        "output": (proc.stdout or "").strip(),
        "error": (proc.stderr or "").strip(),
        "diff_stat": (diff.stdout or "").strip(),
    }
