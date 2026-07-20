"""Installing and running the git hook that enforces branch workflows.

`install` writes a small /bin/sh shim into the bare repository's
hooks/pre-receive; the shim calls back into `gitflower hook pre-receive` once
per pushed ref. All policy lives in Python — the shim only splits git's stdin
lines. Enforcement is server-side, so `--no-verify` on the client cannot
bypass it.
"""

import stat
from pathlib import Path

from gitflower.config import git_dir

MARKER = "gitflower"

PRE_RECEIVE_SHIM = """\
#!/bin/sh
# gitflower pre-receive hook

GITFLOWER_BIN="${GITFLOWER_BIN:-gitflower}"

while read old_sha new_sha ref_name; do
    case "$ref_name" in
        refs/heads/*) ;;
        *) continue ;;   # tags and other refs are not routed
    esac
    if [ "$new_sha" = "0000000000000000000000000000000000000000" ]; then
        # Branch deletion, skip
        continue
    fi
    branch_name=${ref_name#refs/heads/}
    "$GITFLOWER_BIN" hook pre-receive \\
        --branch "$branch_name" \\
        --old-ref "$old_sha" \\
        --new-ref "$new_sha" \\
        --ref "$ref_name"
    if [ $? -ne 0 ]; then
        echo "gitflower: Push rejected by workflow"
        exit 1
    fi
done
exit 0
"""

# hook names gitflower may have owned in some version; uninstall scans these
HOOK_NAMES = (
    "pre-receive",
    "pre-push",
    "pre-commit",
    "update",
    "post-receive",
    "post-checkout",
)


class HookError(Exception):
    pass


def hooks_dir(repo_root: Path | str) -> Path:
    """Where git looks for hooks — the git directory's `hooks`, bare or not."""
    return git_dir(repo_root) / "hooks"


def install(repo_root: Path | str, force: bool = False) -> Path:
    hook = hooks_dir(repo_root) / "pre-receive"
    if hook.exists() and MARKER not in hook.read_text() and not force:
        raise HookError(
            f"{hook} exists and was not installed by gitflower; use --force to overwrite"
        )
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(PRE_RECEIVE_SHIM)
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
