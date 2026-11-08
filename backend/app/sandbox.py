"""Where untrusted code is compiled and run.

DockerSandbox (default): one container per job, started from the sandbox image with no network, a memory, CPU and
process limit, all capabilities dropped, no-new-privileges and a non-root user. The job directory is the only host
path it can see. Every command runs through `timeout` inside the container and is also killed from the host.

LocalSandbox: runs on the host with only a timeout and an output cap. For development when Docker is unavailable;
it gives NO isolation and must be enabled explicitly with SANDBOX=local.
"""

import asyncio
import os
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.config import ROOT, settings

TOOLS = ROOT / ".tools"


@dataclass
class RunResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


async def _exec(argv: list[str], *, cwd: Path | None, env: dict | None, stdin: str, timeout: float) -> RunResult:
    """Run argv (no shell) with a hard timeout and capped output."""
    t0 = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        env=env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    cap = settings.max_output_bytes

    async def read(stream: asyncio.StreamReader) -> bytes:
        buf = bytearray()
        while chunk := await stream.read(65536):
            if len(buf) < cap:
                buf += chunk[: cap - len(buf)]
        return bytes(buf)

    async def feed() -> None:
        try:
            if stdin:
                proc.stdin.write(stdin.encode())  # type: ignore[union-attr]
                await proc.stdin.drain()  # type: ignore[union-attr]
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            proc.stdin.close()  # type: ignore[union-attr]

    try:
        _, out, err, _ = await asyncio.wait_for(
            asyncio.gather(feed(), read(proc.stdout), read(proc.stderr), proc.wait()),  # type: ignore[arg-type]
            timeout,
        )
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return RunResult(-1, "", "timed out", timed_out=True, seconds=round(time.monotonic() - t0, 3))
    rc = proc.returncode or 0
    return RunResult(
        rc,
        out.decode(errors="replace"),
        err.decode(errors="replace"),
        timed_out=rc == 124,  # coreutils `timeout` exit code inside the container
        seconds=round(time.monotonic() - t0, 3),
    )


class Sandbox:
    """Interface: paths given to run() are relative to the job directory; cwd is relative too."""

    name = "base"
    python: list[str]
    exe_suffix = ""
    target_dir: str  # CARGO_TARGET_DIR as seen by commands
    scratch: str  # fast private directory for tool data (coverage databases), as seen by commands

    def __init__(self, job_dir: Path):
        self.job_dir = job_dir

    async def start(self) -> None: ...
    async def stop(self) -> None: ...

    async def run(self, cmd: list[str], cwd: str = ".", stdin: str = "", timeout: float | None = None) -> RunResult:
        raise NotImplementedError

    def rust_exe(self) -> str:
        return f"{self.target_dir}/release/migrated{self.exe_suffix}"


class DockerSandbox(Sandbox):
    name = "docker"
    python = ["python3"]
    target_dir = "/tmp/target"  # inside the container: faster than the bind mount
    scratch = "/tmp"  # tmpfs; SQLite on the Windows bind mount is very slow

    def __init__(self, job_dir: Path):
        super().__init__(job_dir)
        self.container = f"mig-{uuid.uuid4().hex[:12]}"

    async def start(self) -> None:
        r = await _exec(
            [
                "docker",
                "run",
                "-d",
                "--rm",
                "--name",
                self.container,
                "--label",
                "rust-migrator=1",
                "-e",
                "PYTHONDONTWRITEBYTECODE=1",
                "--network",
                "none",
                "--memory",
                settings.sandbox_memory,
                "--memory-swap",
                settings.sandbox_memory,
                "--cpus",
                settings.sandbox_cpus,
                "--pids-limit",
                str(settings.sandbox_pids),
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--tmpfs",
                "/tmp:rw,exec,size=2g",
                "-e",
                f"CARGO_TARGET_DIR={self.target_dir}",
                "-v",
                f"{self.job_dir.resolve()}:/work",
                "-w",
                "/work",
                settings.sandbox_image,
                "sleep",
                "infinity",
            ],
            cwd=None,
            env=None,
            stdin="",
            timeout=60,
        )
        if not r.ok:
            raise SandboxError(f"could not start sandbox container: {r.stderr.strip()[:500]}")

    async def stop(self) -> None:
        await _exec(["docker", "rm", "-f", self.container], cwd=None, env=None, stdin="", timeout=30)

    async def run(self, cmd: list[str], cwd: str = ".", stdin: str = "", timeout: float | None = None) -> RunResult:
        t = int(timeout or settings.run_timeout_s)
        workdir = "/work" if cwd in (".", "") else f"/work/{cwd}"
        argv = ["docker", "exec", "-i", "-w", workdir, self.container, "timeout", "-k", "2", str(t), *cmd]
        return await _exec(argv, cwd=None, env=None, stdin=stdin, timeout=t + 15)


class LocalSandbox(Sandbox):
    name = "local"
    exe_suffix = ".exe" if os.name == "nt" else ""

    def __init__(self, job_dir: Path):
        super().__init__(job_dir)
        self.python = [sys.executable, "-E", "-s"]
        self.target_dir = str((job_dir / "rust" / "target").resolve())
        self.scratch = str((job_dir / "cov").resolve())

    def _env(self) -> dict[str, str]:
        env = os.environ.copy()
        if (TOOLS / "cargo").exists():
            env["CARGO_HOME"] = str(TOOLS / "cargo")
            env["RUSTUP_HOME"] = str(TOOLS / "rustup")
        extra = [TOOLS / "cargo" / "bin", TOOLS / "mingw64" / "bin"]
        env["PATH"] = os.pathsep.join([*(str(p) for p in extra), env.get("PATH", "")])
        env["CARGO_TARGET_DIR"] = self.target_dir
        return env

    async def run(self, cmd: list[str], cwd: str = ".", stdin: str = "", timeout: float | None = None) -> RunResult:
        env = self._env()
        exe = cmd[0]
        if exe.startswith("./"):
            exe = str((self.job_dir / cwd / exe[2:]).resolve()) + ("" if exe.endswith(self.exe_suffix) else self.exe_suffix)
        else:
            exe = shutil.which(exe, path=env["PATH"]) or exe
        if cmd[0] == "python3":
            return await self.run([*self.python, *cmd[1:]], cwd, stdin, timeout)
        return await _exec([exe, *cmd[1:]], cwd=self.job_dir / cwd, env=env, stdin=stdin, timeout=timeout or settings.run_timeout_s)


class SandboxError(RuntimeError):
    pass


def make_sandbox(job_dir: Path) -> Sandbox:
    return DockerSandbox(job_dir) if settings.sandbox == "docker" else LocalSandbox(job_dir)


async def sandbox_status() -> dict:
    if settings.sandbox == "local":
        return {"mode": "local", "ready": True, "warning": "SANDBOX=local runs untrusted code on the host"}
    r = await _exec(["docker", "image", "inspect", settings.sandbox_image, "--format", "{{.Id}}"], cwd=None, env=None, stdin="", timeout=20)
    return {
        "mode": "docker",
        "ready": r.ok,
        "image": settings.sandbox_image,
        "error": "" if r.ok else "sandbox image missing: run scripts/setup.ps1 (or docker build sandbox)",
    }


async def remove_orphans() -> None:
    """Containers left behind when the server was killed mid-job."""
    if settings.sandbox != "docker":
        return
    r = await _exec(["docker", "ps", "-aq", "--filter", "label=rust-migrator=1"], cwd=None, env=None, stdin="", timeout=30)
    ids = r.stdout.split()
    if ids:
        await _exec(["docker", "rm", "-f", *ids], cwd=None, env=None, stdin="", timeout=60)
