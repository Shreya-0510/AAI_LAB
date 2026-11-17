from __future__ import annotations
from pathlib import Path
import os
import subprocess
import sys
import time
from dart.config import get_settings

def run_pytest(repository: str, test_files: list[str], timeout_seconds: int | None = None) -> dict:
    root = Path(repository).resolve()
    settings = get_settings()
    timeout = max(5, min(int(timeout_seconds or settings.test_timeout_seconds), 900))
    # Targets have already been checked against discovered test files. Do not use a shell.
    command = [sys.executable, "-m", "pytest", *test_files]
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            command,
            cwd=root,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        duration = time.perf_counter() - started
        output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        output = output[-settings.max_test_output_chars:]
        counts = {key: 0 for key in ("passed", "failed", "errors", "skipped")}
        import re
        for key in counts:
            match = re.search(rf"(\d+)\s+{key}", output)
            if match: counts[key] = int(match.group(1))
        return {"status": "passed" if proc.returncode == 0 else "failed", "return_code": proc.returncode, "duration_seconds": round(duration, 4), **counts, "output": output, "timed_out": False, "command_targets": test_files}
    except subprocess.TimeoutExpired as exc:
        duration = time.perf_counter() - started
        output = ((exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or ""))
        return {"status": "timeout", "return_code": None, "duration_seconds": round(duration, 4), "passed": 0, "failed": 0, "errors": 0, "skipped": 0, "output": output[-settings.max_test_output_chars:], "timed_out": True, "command_targets": test_files}
    except OSError as exc:
        return {"status": "error", "return_code": None, "duration_seconds": round(time.perf_counter() - started, 4), "passed": 0, "failed": 0, "errors": 1, "skipped": 0, "output": str(exc), "timed_out": False, "command_targets": test_files}
