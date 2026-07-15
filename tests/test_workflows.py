"""Protection workflow semantics — rejection messages pinned to the Go originals."""

import pytest

from gitflower.config import BranchRule, ProtectedBranch, RepoConfig, default_repo_config
from gitflower.workflows import Context, Result, RouteError, execute, find_policy, protected, route
from tests.conftest import git


def ctx(work_repo, branch="main", **kwargs):
    return Context(repo_path=str(work_repo), branch=branch, user="alice", **kwargs)


def test_direct_push_blocked(work_repo):
    result = protected(ctx(work_repo), ProtectedBranch(pattern="main"))
    assert result == Result(
        False,
        "Direct push to protected branch 'main' is not allowed. Please use a merge request.",
    )


def test_allowed_users(work_repo):
    policy = ProtectedBranch(
        pattern="main", allow_direct_push=True, allowed_push_users=["bob"]
    )
    result = protected(ctx(work_repo), policy)
    assert result == Result(
        False, "User 'alice' is not allowed to push to protected branch 'main'."
    )
    policy.allowed_push_users = ["alice"]
    assert protected(ctx(work_repo), policy).allowed


def _merge_commit(repo):
    git(repo, "checkout", "-b", "side")
    (repo / "side.txt").write_text("side\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "side work")
    git(repo, "checkout", "main")
    (repo / "main.txt").write_text("main\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "main work")
    git(repo, "merge", "--no-ff", "side", "-m", "merge side")
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def test_linear_history(work_repo):
    merge_sha = _merge_commit(work_repo)
    parent = git(work_repo, "rev-parse", "HEAD~1").stdout.strip()
    policy = ProtectedBranch(
        pattern="main", allow_direct_push=True, require_linear_history=True
    )
    result = protected(ctx(work_repo, old_ref=parent, new_ref=merge_sha), policy)
    assert result == Result(
        False,
        "Protected branch 'main' requires linear history. "
        "Merge commits are not allowed. Please use rebase.",
    )
    # a plain commit passes
    plain = git(work_repo, "rev-parse", "HEAD~1").stdout.strip()
    assert protected(ctx(work_repo, old_ref="x", new_ref=plain), policy).allowed


def test_clean_working_tree(work_repo):
    policy = ProtectedBranch(
        pattern="main", allow_direct_push=True, require_clean_working_tree=True
    )
    assert protected(ctx(work_repo), policy).allowed
    (work_repo / "dirty.txt").write_text("uncommitted\n")
    result = protected(ctx(work_repo), policy)
    assert result == Result(
        False,
        "Protected branch requires a clean working tree. "
        "Please commit or stash your changes.",
    )


def test_allow_message(work_repo):
    policy = ProtectedBranch(pattern="main", allow_direct_push=True)
    assert protected(ctx(work_repo), policy) == Result(
        True, "Push to protected branch 'main' allowed."
    )


def test_route_first_match_wins():
    config = default_repo_config()
    assert route(config, "main").workflow == "protected"
    assert route(config, "issues/42").workflow == "issue-tracker"
    assert route(config, "releases/v1.0").workflow == "release-manager"


def test_route_unconfigured_branch_rejected():
    with pytest.raises(
        RouteError,
        match="no workflow found for branch 'feature/x' - branch not allowed by configuration",
    ):
        route(default_repo_config(), "feature/x")


def test_route_disabled_rule_skipped():
    config = RepoConfig(
        branch_rules=[
            BranchRule(pattern="main", workflow="protected", enabled=False),
            BranchRule(pattern="*", workflow="issue-tracker"),
        ]
    )
    assert route(config, "main").workflow == "issue-tracker"


def test_route_glob_does_not_cross_slash():
    config = default_repo_config()
    with pytest.raises(RouteError):
        route(config, "issues/42/subtask")


def test_find_policy_falls_back_to_strict():
    policy = find_policy(RepoConfig(), "main")
    assert policy.allow_direct_push is False


def test_execute_passthrough(work_repo):
    result = execute(default_repo_config(), ctx(work_repo, branch="issues/7"))
    assert result == Result(True, "Operation on branch 'issues/7' allowed.")
