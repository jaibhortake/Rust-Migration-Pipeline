import asyncio
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.config import ROOT, settings

TOOLS = ROOT / ".tools"
CARGO_HOME = TOOLS / "cargo"
RUSTUP_HOME = TOOLS / "rustup"
MINGW_BIN = TOOLS / "mingw64" / "bin"


def tool_env() -> dict[str, str]:
    env = os.environ.copy()
    env["CARGO_HOME"] = str(CARGO_HOME)
    env["RUSTUP_HOME"] = str(RUSTUP_HOME)
    env["PATH"] = os.pathsep.join([str(CARGO_HOME / "bin"), str(MINGW_BIN), env.get("PATH", "")])
    return env


@dataclass
class RunResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


async def run(cmd: list[str], cwd: Path, timeout: int, stdin: str = "") -> RunResult:
    """Run a command without a shell, with a timeout and capped output."""
    env = tool_env()
    # On Windows the executable is resolved with the parent's PATH, so resolve it against ours.
    exe = shutil.which(cmd[0], path=env["PATH"]) or cmd[0]
    proc = await asyncio.create_subprocess_exec(
        exe,
        *cmd[1:],
        cwd=cwd,
        env=env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),  # no console pop-ups on Windows
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(stdin.encode()), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return RunResult(-1, "", "timed out", timed_out=True)
    cap = settings.max_output_bytes
    return RunResult(
        proc.returncode or 0,
        out[:cap].decode(errors="replace"),
        err[:cap].decode(errors="replace"),
    )
