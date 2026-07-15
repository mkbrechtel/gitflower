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
    return passthrough(ctx)
