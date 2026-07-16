"""Installing and running the git hooks that enforce branch workflows.

`install` writes a small /bin/sh shim into .git/hooks/pre-push; the shim
calls back into `gitflower hook pre-push` once per pushed ref. All policy
lives in Python — the shim only splits git's stdin lines.
"""

import stat
from pathlib import Path

MARKER = "gitflower"

PRE_PUSH_SHIM = """\
#!/bin/sh
# gitflower pre-push hook

GITFLOWER_BIN="${GITFLOWER_BIN:-gitflower}"

while read local_ref local_sha remote_ref remote_sha; do
    if [ "$local_sha" = "0000000000000000000000000000000000000000" ]; then
        # Branch deletion, skip
        continue
    fi
    branch_name=${remote_ref#refs/heads/}
    "$GITFLOWER_BIN" hook pre-push \\
        --branch "$branch_name" \\
        --old-ref "$remote_sha" \\
        --new-ref "$local_sha" \\
        --ref "$remote_ref"
    if [ $? -ne 0 ]; then
        echo "gitflower: Push rejected by workflow"
        exit 1
    fi
done
exit 0
"""

# hook names gitflower may have owned in some version; uninstall scans these
HOOK_NAMES = (
    "pre-push",
    "pre-commit",
    "update",
    "pre-receive",
    "post-receive",
    "post-checkout",
)


class HookError(Exception):
    pass


def hooks_dir(repo_root: Path | str) -> Path:
    git_path = Path(repo_root) / ".git"
    if git_path.is_file():
        # worktree: ".git" is a pointer file — hooks live in the common dir
        pointed = Path(git_path.read_text().split(":", 1)[1].strip())
        if pointed.parent.name == "worktrees":
            return pointed.parent.parent / "hooks"
        return pointed / "hooks"
    return git_path / "hooks"


def install(repo_root: Path | str, force: bool = False) -> Path:
    hook = hooks_dir(repo_root) / "pre-push"
    if hook.exists() and MARKER not in hook.read_text() and not force:
        raise HookError(
            f"{hook} exists and was not installed by gitflower; use --force to overwrite"
        )
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(PRE_PUSH_SHIM)
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return hook


def uninstall(repo_root: Path | str) -> list[Path]:
    """Remove gitflower-owned hooks; foreign hooks are left untouched."""
    removed = []
    directory = hooks_dir(repo_root)
    for name in HOOK_NAMES:
        hook = directory / name
        if hook.is_file() and MARKER in hook.read_text():
            hook.unlink()
            removed.append(hook)
    return removed
