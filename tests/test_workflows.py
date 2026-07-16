"""Protection workflow semantics — rejection messages pinned to the Go originals."""

import pytest

from gitflower.config import BranchRule, ProtectedBranch, RepoConfig, default_repo_config
from gitflower.workflows import Context, Result, RouteError, execute, find_policy, issue_tracker, protected, route
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
    result = execute(default_repo_config(), ctx(work_repo, branch="releases/v1"))
    assert result == Result(True, "Operation on branch 'releases/v1' allowed.")


# ------------------------------------------------------------ issue-tracker


def _issue_file(uuid: str, title: str) -> str:
    return f"---\nid: {uuid}\ntitle: {title}\n---\n\n# {title}\n"


def _issue_branch(work_repo, *files: tuple[str, str, str]):
    """An issues/* branch adding the given (name, uuid, title) issue files."""
    from tests.conftest import git as run

    run(work_repo, "checkout", "-b", "issues/batch")
    (work_repo / "issues").mkdir(exist_ok=True)
    for name, uuid, title in files:
        (work_repo / "issues" / name).write_text(_issue_file(uuid, title))
    run(work_repo, "add", ".")
    run(work_repo, "commit", "-m", "file issues")
    return run(work_repo, "rev-parse", "HEAD").stdout.strip()


def test_issue_tracker_allows_clean_push(work_repo):
    sha = _issue_branch(work_repo, ("a.md", "uuid-a", "Issue A"), ("b.md", "uuid-b", "Issue B"))
    result = issue_tracker(ctx(work_repo, branch="issues/batch", new_ref=sha))
    assert result == Result(True, "Push to issue branch 'issues/batch' allowed.")


def test_issue_tracker_rejects_duplicate_ids(work_repo):
    sha = _issue_branch(work_repo, ("a.md", "uuid-a", "Issue A"), ("twin.md", "uuid-a", "Twin"))
    result = issue_tracker(ctx(work_repo, branch="issues/batch", new_ref=sha))
    assert result == Result(
        False,
        "Duplicate issue id 'uuid-a' in 'issues/a.md' and 'issues/twin.md' "
        "on branch 'issues/batch'. Issue ids must be unique.",
    )


def test_issue_tracker_rejects_id_change(work_repo):
    old = _issue_branch(work_repo, ("a.md", "uuid-a", "Issue A"))
    (work_repo / "issues" / "a.md").write_text(_issue_file("uuid-changed", "Issue A"))
    git(work_repo, "add", ".")
    git(work_repo, "commit", "-m", "mangle the id")
    new = git(work_repo, "rev-parse", "HEAD").stdout.strip()
    result = issue_tracker(ctx(work_repo, branch="issues/batch", old_ref=old, new_ref=new))
    assert result == Result(
        False,
        "Issue id changed in 'issues/a.md' on branch 'issues/batch'. "
        "Issue ids are permanent — file a new issue instead.",
    )


def test_issue_tracker_allows_edit_keeping_id(work_repo):
    old = _issue_branch(work_repo, ("a.md", "uuid-a", "Issue A"))
    (work_repo / "issues" / "a.md").write_text(_issue_file("uuid-a", "Issue A renamed"))
    git(work_repo, "add", ".")
    git(work_repo, "commit", "-m", "retitle")
    new = git(work_repo, "rev-parse", "HEAD").stdout.strip()
    assert issue_tracker(ctx(work_repo, branch="issues/batch", old_ref=old, new_ref=new)).allowed


def test_issue_tracker_allows_branch_deletion(work_repo):
    result = issue_tracker(
        ctx(work_repo, branch="issues/gone", old_ref="f" * 40, new_ref="0" * 40)
    )
    assert result.allowed


def test_issue_tracker_ignores_idless_files(work_repo):
    git(work_repo, "checkout", "-b", "issues/notes")
    (work_repo / "issues").mkdir(exist_ok=True)
    (work_repo / "issues" / "notes.md").write_text("# just notes, no front matter\n")
    git(work_repo, "add", ".")
    git(work_repo, "commit", "-m", "notes")
    sha = git(work_repo, "rev-parse", "HEAD").stdout.strip()
    assert issue_tracker(ctx(work_repo, branch="issues/notes", new_ref=sha)).allowed


def test_issue_tracker_routed_by_default_config(work_repo):
    sha = _issue_branch(work_repo, ("a.md", "uuid-a", "Issue A"))
    result = execute(
        default_repo_config(), ctx(work_repo, branch="issues/batch", new_ref=sha)
    )
    assert result == Result(True, "Push to issue branch 'issues/batch' allowed.")
