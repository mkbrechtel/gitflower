"""End-to-end: real `git push` through the installed pre-push shim.

The shim invokes $GITFLOWER_BIN (a wrapper around `python3 -m gitflower`
here, the console script in production) once per pushed ref.
"""

import os

import pytest

from gitflower import config as cfg, hooks
from tests.conftest import git


@pytest.fixture
def hooked_repo(work_repo, bare_remote, gitflower_bin, monkeypatch):
    hooks.install(work_repo)
    monkeypatch.setenv("GITFLOWER_BIN", str(gitflower_bin))
    return work_repo


def push(repo, *refspec, expect_ok=True):
    result = git(repo, "push", "origin", *refspec, check=False)
    if expect_ok:
        assert result.returncode == 0, result.stderr
    else:
        assert result.returncode != 0, "push unexpectedly succeeded"
    return result


def test_protected_branch_rejected(hooked_repo):
    result = push(hooked_repo, "main", expect_ok=False)
    assert (
        "Direct push to protected branch 'main' is not allowed. "
        "Please use a merge request." in result.stderr
    )
    # the shim's own message goes to the hook's stdout
    assert "gitflower: Push rejected by workflow" in result.stdout + result.stderr


def test_unconfigured_branch_rejected(hooked_repo):
    git(hooked_repo, "checkout", "-b", "feature/x")
    result = push(hooked_repo, "feature/x", expect_ok=False)
    assert (
        "no workflow found for branch 'feature/x' - branch not allowed by configuration"
        in result.stderr
    )


def test_passthrough_branch_allowed(hooked_repo):
    git(hooked_repo, "checkout", "-b", "issues/42")
    push(hooked_repo, "issues/42")


def test_deletion_skipped(hooked_repo):
    git(hooked_repo, "checkout", "-b", "issues/9")
    push(hooked_repo, "issues/9")
    push(hooked_repo, ":issues/9")  # deletion: zero sha, shim skips it


def test_allow_direct_push_config(hooked_repo):
    config = cfg.default_repo_config()
    config.protected_branches[0].allow_direct_push = True
    path = cfg.repo_config_path(hooked_repo)
    path.parent.mkdir(exist_ok=True)
    path.write_text(cfg.dump_repo_config(config))
    push(hooked_repo, "main")


def test_install_refuses_foreign_hook(work_repo):
    hook_path = hooks.hooks_dir(work_repo) / "pre-push"
    hook_path.parent.mkdir(parents=True, exist_ok=True)
    hook_path.write_text("#!/bin/sh\nexit 0\n")
    with pytest.raises(hooks.HookError, match="use --force"):
        hooks.install(work_repo)
    hooks.install(work_repo, force=True)
    assert hooks.MARKER in hook_path.read_text()


def test_uninstall_removes_only_gitflower_hooks(work_repo):
    hooks.install(work_repo)
    foreign = hooks.hooks_dir(work_repo) / "pre-commit"
    foreign.write_text("#!/bin/sh\n# my own hook\nexit 0\n")
    removed = hooks.uninstall(work_repo)
    assert [p.name for p in removed] == ["pre-push"]
    assert foreign.exists()
    assert not (hooks.hooks_dir(work_repo) / "pre-push").exists()
