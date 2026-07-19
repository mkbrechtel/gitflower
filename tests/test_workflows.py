"""Protection workflow semantics — rejection messages pinned to the Go originals."""

import pytest

from gitflower.config import BranchRule, RepoConfig, default_repo_config
from gitflower.workflows import (
    Context,
    Result,
    RouteError,
    execute,
    protected,
    route,
    specificity,
)
from tests.conftest import git


def ctx(work_repo, branch="main", **kwargs):
    return Context(repo_path=str(work_repo), branch=branch, **kwargs)


def rule(pattern="main", workflow="protected", **kwargs):
    return BranchRule(pattern=pattern, workflow=workflow, **kwargs)


def test_direct_push_blocked(work_repo):
    result = protected(ctx(work_repo), rule())
    assert result == Result(
        False,
        "Direct push to protected branch 'main' is not allowed. Please use a merge request.",
    )


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
    policy = rule(allow_direct_push=True, require_linear_history=True)
    result = protected(ctx(work_repo, old_ref=parent, new_ref=merge_sha), policy)
    assert result == Result(
        False,
        "Protected branch 'main' requires linear history. "
        "Merge commits are not allowed. Please use rebase.",
    )
    # a plain commit passes
    plain = git(work_repo, "rev-parse", "HEAD~1").stdout.strip()
    assert protected(ctx(work_repo, old_ref="x", new_ref=plain), policy).allowed


def test_allow_message(work_repo):
    assert protected(ctx(work_repo), rule(allow_direct_push=True)) == Result(
        True, "Push to protected branch 'main' allowed."
    )


def test_route_defaults():
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
            rule(workflow="protected", enabled=False),
            rule(pattern="*", workflow="issue-tracker"),
        ]
    )
    assert route(config, "main").workflow == "issue-tracker"


def test_route_glob_does_not_cross_slash():
    config = default_repo_config()
    with pytest.raises(RouteError):
        route(config, "issues/42/subtask")


def test_route_most_specific_wins_regardless_of_order():
    """The literal beats the wildcard whichever way round they are written."""
    literal = rule(pattern="main", workflow="protected")
    wild = rule(pattern="*", workflow="issue-tracker")
    assert route(RepoConfig(branch_rules=[wild, literal]), "main").workflow == "protected"
    assert route(RepoConfig(branch_rules=[literal, wild]), "main").workflow == "protected"


def test_route_longer_literal_prefix_wins():
    config = RepoConfig(
        branch_rules=[
            rule(pattern="releases/*", workflow="issue-tracker"),
            rule(pattern="releases/v*", workflow="release-manager"),
        ]
    )
    assert route(config, "releases/v1").workflow == "release-manager"
    assert route(config, "releases/old").workflow == "issue-tracker"


def test_route_ambiguous_rules_rejected():
    config = RepoConfig(
        branch_rules=[
            rule(pattern="*/x", workflow="issue-tracker"),
            rule(pattern="a/*", workflow="release-manager"),
        ]
    )
    with pytest.raises(RouteError, match="equally specific rules"):
        route(config, "a/x")


def test_specificity_ordering():
    """More precise patterns sort first."""
    patterns = ["*", "issues/*", "issues/v*", "main", "issues/exact"]
    assert sorted(patterns, key=specificity) == [
        "issues/exact",
        "main",
        "issues/v*",
        "issues/*",
        "*",
    ]


def test_execute_passthrough(work_repo):
    result = execute(default_repo_config(), ctx(work_repo, branch="issues/7"))
    assert result == Result(True, "Operation on branch 'issues/7' allowed.")
