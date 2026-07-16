"""Branch workflows — what a routed push is checked against.

Message strings are byte-identical to the Go original: users and scripts have
seen these exact rejections since the Go version, and the tests pin them.

Workflow git checks shell out to real git (not pygit2): the hook runs inside
a live repository where `status --porcelain` and `rev-list --parents` must
mean exactly what they mean to the git that is doing the push.
"""

import os
import subprocess
from dataclasses import dataclass

from gitflower.config import ProtectedBranch, RepoConfig
from gitflower.matcher import BadPattern, match

ZERO_SHA = "0" * 40


@dataclass
class Context:
    repo_path: str
    branch: str
    old_ref: str = ""
    new_ref: str = ""
    ref_name: str = ""
    operation: str = "push"
    user: str = ""

    def __post_init__(self) -> None:
        if not self.user:
            self.user = os.environ.get("USER", "unknown")


@dataclass
class Result:
    allowed: bool
    message: str


def _git(repo_path: str, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", repo_path, *args], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return result.stdout


def _is_merge_commit(repo_path: str, sha: str) -> bool:
    out = _git(repo_path, "rev-list", "--parents", "-n", "1", sha)
    return len(out.split()) > 2  # commit + more than one parent


def _working_tree_dirty(repo_path: str) -> bool:
    return bool(_git(repo_path, "status", "--porcelain").strip())


def protected(ctx: Context, policy: ProtectedBranch) -> Result:
    """The protection checks, in the Go original's order — first failure wins."""
    if not policy.allow_direct_push and ctx.operation == "push":
        return Result(
            False,
            f"Direct push to protected branch '{ctx.branch}' is not allowed. "
            "Please use a merge request.",
        )
    if policy.allowed_push_users and ctx.user not in policy.allowed_push_users:
        return Result(
            False,
            f"User '{ctx.user}' is not allowed to push to protected branch '{ctx.branch}'.",
        )
    if (
        policy.require_linear_history
        and ctx.old_ref
        and ctx.new_ref
        and ctx.new_ref != ZERO_SHA
        and _is_merge_commit(ctx.repo_path, ctx.new_ref)
    ):
        return Result(
            False,
            f"Protected branch '{ctx.branch}' requires linear history. "
            "Merge commits are not allowed. Please use rebase.",
        )
    if policy.require_clean_working_tree and _working_tree_dirty(ctx.repo_path):
        return Result(
            False,
            "Protected branch requires a clean working tree. "
            "Please commit or stash your changes.",
        )
    return Result(True, f"Push to protected branch '{ctx.branch}' allowed.")


def passthrough(ctx: Context, policy: ProtectedBranch | None = None) -> Result:
    return Result(True, f"Operation on branch '{ctx.branch}' allowed.")


def _issues_directory(repo_path: str) -> str:
    result = subprocess.run(
        ["git", "-C", repo_path, "config", "--get", "gitflower.issues.directory"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip().strip("/") or "issues" if result.returncode == 0 else "issues"


def _tree_issue_ids(repo_path: str, ref: str, directory: str) -> dict[str, str | None]:
    """path → front-matter id for every issue file in the tree at `ref`."""
    from gitflower.issues import parse_frontmatter

    out = subprocess.run(
        ["git", "-C", repo_path, "ls-tree", "-r", "-z", ref, "--", f"{directory}/"],
        capture_output=True,
    )
    ids: dict[str, str | None] = {}
    if out.returncode != 0:
        return ids
    for entry in out.stdout.decode("utf-8", errors="replace").split("\0"):
        if not entry or "\t" not in entry:
            continue
        meta, path = entry.split("\t", 1)
        mode_type_oid = meta.split(" ")
        if len(mode_type_oid) != 3 or mode_type_oid[1] != "blob" or not path.endswith(".md"):
            continue
        blob = subprocess.run(
            ["git", "-C", repo_path, "cat-file", "blob", mode_type_oid[2]],
            capture_output=True,
        )
        fm = parse_frontmatter(blob.stdout) if blob.returncode == 0 else None
        issue_id = (fm or {}).get("id")
        ids[path] = str(issue_id) if issue_id is not None else None
    return ids


def issue_tracker(ctx: Context) -> Result:
    """Id integrity for issue files (see issues/issues-view.md): a pushed
    tree must not carry one id twice, and a push must not change or remove
    the id of an issue file that keeps its path."""
    if ctx.new_ref == ZERO_SHA:
        return Result(True, f"Deleting issue branch '{ctx.branch}' allowed.")
    directory = _issues_directory(ctx.repo_path)
    new_ref = ctx.new_ref or ctx.branch
    new_ids = _tree_issue_ids(ctx.repo_path, new_ref, directory)

    seen: dict[str, str] = {}
    for path, issue_id in sorted(new_ids.items()):
        if issue_id is None:
            continue
        if issue_id in seen:
            return Result(
                False,
                f"Duplicate issue id '{issue_id}' in '{seen[issue_id]}' and "
                f"'{path}' on branch '{ctx.branch}'. Issue ids must be unique.",
            )
        seen[issue_id] = path

    if ctx.old_ref and ctx.old_ref != ZERO_SHA:
        old_ids = _tree_issue_ids(ctx.repo_path, ctx.old_ref, directory)
        for path, old_id in old_ids.items():
            if old_id is None or path not in new_ids:
                continue
            if new_ids[path] != old_id:
                return Result(
                    False,
                    f"Issue id changed in '{path}' on branch '{ctx.branch}'. "
                    "Issue ids are permanent — file a new issue instead.",
                )
    return Result(True, f"Push to issue branch '{ctx.branch}' allowed.")


class RouteError(Exception):
    pass


def route(config: RepoConfig, branch: str):
    """First enabled rule whose pattern matches wins. No match, or a malformed
    pattern, rejects the push — unconfigured branches are not allowed."""
    for rule in config.branch_rules:
        if not rule.enabled:
            continue
        try:
            if match(rule.pattern, branch):
                return rule
        except BadPattern as exc:
            raise RouteError(f"branch rule pattern '{rule.pattern}' is malformed: {exc}")
    raise RouteError(
        f"no workflow found for branch '{branch}' - branch not allowed by configuration"
    )


def find_policy(config: RepoConfig, branch: str) -> ProtectedBranch:
    """The first protected_branches entry matching the branch; a protected rule
    with no matching policy entry falls back to the strictest default."""
    for policy in config.protected_branches:
        try:
            if match(policy.pattern, branch):
                return policy
        except BadPattern:
            continue
    return ProtectedBranch(pattern=branch)


def execute(config: RepoConfig, ctx: Context) -> Result:
    rule = route(config, ctx.branch)
    if rule.workflow == "protected":
        return protected(ctx, find_policy(config, ctx.branch))
    if rule.workflow == "issue-tracker":
        return issue_tracker(ctx)
    return passthrough(ctx)
