from __future__ import annotations
from pathlib import Path
import subprocess

MAX_DIFF_CHARS = 50000

def _git(repo: Path, *args: str, timeout: int = 15) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )

def repository_snapshot(repository: str, base_ref: str | None = None, head_ref: str | None = "HEAD") -> dict:
    repo = Path(repository).expanduser().resolve()
    if not repo.is_dir():
        raise ValueError(f"Repository directory does not exist: {repo}")
    py_files = sorted(p.relative_to(repo).as_posix() for p in repo.rglob("*.py") if not any(part in {".git", ".venv", "venv", "__pycache__", ".tox", "site-packages"} for part in p.parts))
    tests = sorted(p for p in py_files if Path(p).name.startswith("test_") or Path(p).parent.name == "tests" or Path(p).name.endswith("_test.py"))
    changed: list[str] = []
    diff_text = ""
    commit = "unknown"
    git_root = _git(repo, "rev-parse", "--show-toplevel")
    if git_root.returncode == 0:
        rev = _git(repo, "rev-parse", "HEAD")
        if rev.returncode == 0: commit = rev.stdout.strip()
        if base_ref:
            diff = _git(repo, "diff", "--name-only", f"{base_ref}...{head_ref or 'HEAD'}")
            patch = _git(repo, "diff", "--no-ext-diff", f"{base_ref}...{head_ref or 'HEAD'}")
            if diff.returncode == 0: changed = [x for x in diff.stdout.splitlines() if x.strip()]
            if patch.returncode == 0: diff_text = patch.stdout[:MAX_DIFF_CHARS]
        else:
            diff = _git(repo, "diff", "--name-only", "HEAD")
            patch = _git(repo, "diff", "--no-ext-diff", "HEAD")
            if diff.returncode == 0: changed = [x for x in diff.stdout.splitlines() if x.strip()]
            if patch.returncode == 0: diff_text = patch.stdout[:MAX_DIFF_CHARS]
        if not changed:
            # For a new/demo repository or clean worktree, fall back to a recent commit diff.
            diff = _git(repo, "diff", "--name-only", "HEAD~1", "HEAD")
            patch = _git(repo, "diff", "--no-ext-diff", "HEAD~1", "HEAD")
            if diff.returncode == 0: changed = [x for x in diff.stdout.splitlines() if x.strip()]
            if patch.returncode == 0 and patch.stdout.strip(): diff_text = patch.stdout[:MAX_DIFF_CHARS]
    if not changed:
        # Non-git repositories still provide a useful scope; clearly mark this as inferred.
        changed = [p for p in py_files if p not in tests][:100]
    return {"repository": str(repo), "commit_hash": commit, "python_files": py_files, "python_file_count": len(py_files), "test_files": tests, "changed_files": changed, "diff_text": diff_text, "git_available": git_root.returncode == 0}
