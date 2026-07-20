"""End-to-end: real `git push` through the installed pre-receive shim.

The shim invokes $GITFLOWER_BIN (a wrapper around `python3 -m gitflower`
here, the console script in production) once per pushed ref, inside the bare
repository that is receiving the push.
"""

import pytest

from gitflower import hooks
from tests.conftest import git


@pytest.fixture
def hooked_remote(work_repo, bare_remote, gitflower_bin, monkeypatch):
    hooks.install(bare_remote)
    monkeypatch.setenv("GITFLOWER_BIN", str(gitflower_bin))
    return bare_remote


def push(repo, *refspec, expect_ok=True):
    result = git(repo, "push", "origin", *refspec, check=False)
    if expect_ok:
        assert result.returncode == 0, result.stderr
    else:
        assert result.returncode != 0, "push unexpectedly succeeded"
    return result


def test_protected_branch_rejected(work_repo, hooked_remote):
    result = push(work_repo, "main", expect_ok=False)
    assert (
        "Direct push to protected branch 'main' is not allowed. "
        "Please use a merge request." in result.stderr
    )
    assert "gitflower: Push rejected by workflow" in result.stdout + result.stderr


def test_no_verify_cannot_bypass(work_repo, hooked_remote):
    """Server-side enforcement is the point: the client cannot opt out."""
    result = git(work_repo, "push", "--no-verify", "origin", "main", check=False)
    assert result.returncode != 0
    assert "Direct push to protected branch 'main'" in result.stderr


def test_unconfigured_branch_rejected(work_repo, hooked_remote):
    git(work_repo, "checkout", "-b", "feature/x")
    result = push(work_repo, "feature/x", expect_ok=False)
    assert (
        "no workflow found for branch 'feature/x' - branch not allowed by configuration"
        in result.stderr
    )


def test_passthrough_branch_allowed(work_repo, hooked_remote):
    git(work_repo, "checkout", "-b", "issues/42")
    push(work_repo, "issues/42")


def test_deletion_skipped(work_repo, hooked_remote):
    git(work_repo, "checkout", "-b", "issues/9")
    push(work_repo, "issues/9")
    push(work_repo, ":issues/9")  # deletion: zero sha, shim skips it


def test_allow_direct_push_config(work_repo, hooked_remote):
    git(hooked_remote, "config", "gitflower.branch.main.workflow", "protected")
    git(hooked_remote, "config", "gitflower.branch.main.allowDirectPush", "true")
    push(work_repo, "main")


def test_tags_are_not_routed(work_repo, hooked_remote):
    """Only refs/heads/* goes through the router; a tag push is untouched."""
    git(work_repo, "tag", "v1")
    push(work_repo, "v1")


def test_install_refuses_foreign_hook(bare_repo):
    hook_path = hooks.hooks_dir(bare_repo) / "pre-receive"
    hook_path.parent.mkdir(parents=True, exist_ok=True)
    hook_path.write_text("#!/bin/sh\nexit 0\n")
    with pytest.raises(hooks.HookError, match="use --force"):
        hooks.install(bare_repo)
    hooks.install(bare_repo, force=True)
    assert hooks.MARKER in hook_path.read_text()


def test_uninstall_removes_only_gitflower_hooks(bare_repo):
    hooks.install(bare_repo)
    foreign = hooks.hooks_dir(bare_repo) / "pre-commit"
    foreign.write_text("#!/bin/sh\n# my own hook\nexit 0\n")
    removed = hooks.uninstall(bare_repo)
    assert sorted(p.name for p in removed) == ["post-receive", "pre-receive"]
    assert foreign.exists()
    assert not (hooks.hooks_dir(bare_repo) / "pre-receive").exists()
    assert not (hooks.hooks_dir(bare_repo) / "post-receive").exists()
