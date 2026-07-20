"""Installing and running the git hooks that enforce and record.

`install` writes small /bin/sh shims into the bare repository's hooks; each
calls back into `gitflower hook …` once per pushed ref. All policy lives in
Python — the shims only split git's stdin lines. Enforcement is server-side,
so `--no-verify` on the client cannot bypass it.

Two hooks, for two different jobs. **pre-receive** decides: it runs before
anything is durable and its exit code rejects the push. **post-receive**
records: it runs after, when the objects are certainly there, and it cannot
fail a push no matter what happens inside it. The merge-request refs are
bookkeeping, so they are written there — a record of what happened must not
be able to prevent it happening.
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

POST_RECEIVE_SHIM = """\
#!/bin/sh
# gitflower post-receive hook
#
# Bookkeeping only: the push has already been accepted and is durable. This
# hook never fails it — every branch is tried, and the exit status is 0.

GITFLOWER_BIN="${GITFLOWER_BIN:-gitflower}"

while read old_sha new_sha ref_name; do
    case "$ref_name" in
        refs/heads/*) ;;
        *) continue ;;
    esac
    if [ "$new_sha" = "0000000000000000000000000000000000000000" ]; then
        continue
    fi
    branch_name=${ref_name#refs/heads/}
    "$GITFLOWER_BIN" hook post-receive \\
        --branch "$branch_name" \\
        --old-ref "$old_sha" \\
        --new-ref "$new_sha" \\
        --ref "$ref_name" || true
done
exit 0
"""

SHIMS = {
    "pre-receive": PRE_RECEIVE_SHIM,
    "post-receive": POST_RECEIVE_SHIM,
}

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


def install(repo_root: Path | str, force: bool = False) -> list[Path]:
    """Write both shims, refusing to clobber a foreign hook."""
    directory = hooks_dir(repo_root)
    for name in SHIMS:
        hook = directory / name
        if hook.exists() and MARKER not in hook.read_text() and not force:
            raise HookError(
                f"{hook} exists and was not installed by gitflower; use --force to overwrite"
            )
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for name, shim in SHIMS.items():
        hook = directory / name
        hook.write_text(shim)
        hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        written.append(hook)
    return written


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
