"""End-to-end: merge-request refs recorded by a real push.

The pre-receive hook decides whether the push happens; the post-receive hook
records what it meant. These tests push for real, through both shims, and
then read the bare repository's refs.
"""

import pygit2
import pytest

from gitflower import hooks, mr
from tests.conftest import git


@pytest.fixture
def hooked_remote(work_repo, bare_remote, gitflower_bin, monkeypatch):
    hooks.install(bare_remote)
    monkeypatch.setenv("GITFLOWER_BIN", str(gitflower_bin))
    # main is protected by the built-in defaults; issues/* passes through, so
    # it stands in for an ordinary work branch here
    return bare_remote


def request_on(repo, branch, title="add the thing"):
    git(repo, "checkout", "-q", "-b", branch)
    (repo / f"{branch.replace('/', '-')}.txt").write_text("work\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "the work")
    git(repo, "commit", "--allow-empty", "-m", f"MR: {title}")
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def test_push_records_the_request(work_repo, hooked_remote):
    oid = request_on(work_repo, "issues/42")
    result = git(work_repo, "push", "origin", "issues/42")
    assert result.returncode == 0, result.stderr
    remote = pygit2.Repository(str(hooked_remote))
    assert str(remote.references[mr.request_ref(oid)].target) == oid
    assert f"recorded merge request {oid[: mr.ABBREV]}" in result.stderr


def test_recording_is_idempotent(work_repo, hooked_remote):
    oid = request_on(work_repo, "issues/42")
    git(work_repo, "push", "origin", "issues/42")
    git(work_repo, "commit", "--allow-empty", "-m", "an afterthought")
    result = git(work_repo, "push", "origin", "issues/42")
    assert "recorded merge request" not in result.stderr
    remote = pygit2.Repository(str(hooked_remote))
    assert str(remote.references[mr.request_ref(oid)].target) == oid


def test_a_push_with_no_request_records_nothing(work_repo, hooked_remote):
    git(work_repo, "checkout", "-q", "-b", "issues/43")
    (work_repo / "quiet.txt").write_text("no request here\n")
    git(work_repo, "add", ".")
    git(work_repo, "commit", "-m", "unrequested work")
    git(work_repo, "push", "origin", "issues/43")
    remote = pygit2.Repository(str(hooked_remote))
    assert not [r for r in remote.references if r.startswith(mr.MR_REF_PREFIX)]


def test_bookkeeping_cannot_fail_a_push(work_repo, hooked_remote):
    """A broken recorder must not cost the user their push."""
    oid = request_on(work_repo, "issues/42")
    hook = hooks.hooks_dir(hooked_remote) / "post-receive"
    hook.write_text("#!/bin/sh\nexit 9\n")
    hook.chmod(0o755)
    result = git(work_repo, "push", "origin", "issues/42", check=False)
    assert result.returncode == 0, result.stderr
    remote = pygit2.Repository(str(hooked_remote))
    assert str(remote.references["refs/heads/issues/42"].target) == oid
    assert mr.request_ref(oid) not in remote.references  # nothing recorded, work kept


def test_install_writes_both_hooks(bare_repo):
    written = hooks.install(bare_repo)
    assert {p.name for p in written} == {"pre-receive", "post-receive"}
    assert all(p.exists() and p.stat().st_mode & 0o111 for p in written)


def test_uninstall_removes_both(bare_repo):
    hooks.install(bare_repo)
    removed = hooks.uninstall(bare_repo)
    assert {p.name for p in removed} == {"pre-receive", "post-receive"}


def test_install_refuses_a_foreign_post_receive(bare_repo):
    hook = hooks.hooks_dir(bare_repo)
    hook.mkdir(parents=True, exist_ok=True)
    (hook / "post-receive").write_text("#!/bin/sh\n# someone else's\n")
    with pytest.raises(hooks.HookError):
        hooks.install(bare_repo)
    # and refusing leaves the pre-receive alone rather than half-installing
    assert not (hook / "pre-receive").exists()
