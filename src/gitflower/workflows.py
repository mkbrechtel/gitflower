"""Branch workflows — what a routed push is checked against.

Message strings are byte-identical to the Go original: users and scripts have
seen these exact rejections since the Go version, and the tests pin them.

Workflow git checks shell out to real git (not pygit2): the hook runs inside
a live repository where `rev-list --parents` must mean exactly what it means
to the git that is receiving the push.
"""

import subprocess
from dataclasses import dataclass

from gitflower.config import BranchRule, RepoConfig
from gitflower.matcher import BadPattern, match

ZERO_SHA = "0" * 40

WILDCARDS = "*?["


@dataclass
class Context:
    repo_path: str
    branch: str
    old_ref: str = ""
    new_ref: str = ""
    ref_name: str = ""
    operation: str = "push"


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


def protected(ctx: Context, rule: BranchRule) -> Result:
    """The protection checks, in the Go original's order — first failure wins."""
    if not rule.allow_direct_push and ctx.operation == "push":
        return Result(
            False,
            f"Direct push to protected branch '{ctx.branch}' is not allowed. "
            "Please use a merge request.",
        )
    if (
        rule.require_linear_history
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
    return Result(True, f"Push to protected branch '{ctx.branch}' allowed.")


def passthrough(ctx: Context, rule: BranchRule | None = None) -> Result:
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


def specificity(pattern: str) -> tuple:
    """Sort key ranking a pattern's precision, most specific first.

    A pattern with no wildcards beats one with any; then more path segments
    wins, then fewer wildcards, then more literal characters. Two patterns
    tie only when they are equally precise by every one of those measures.
    """
    wildcards = sum(1 for c in pattern if c in WILDCARDS)
    literals = len(pattern) - wildcards
    segments = pattern.count("/") + 1
    return (1 if wildcards else 0, -segments, wildcards, -literals)


def route(config: RepoConfig, branch: str) -> BranchRule:
    """The most specific enabled rule whose pattern matches wins. No match, a
    malformed pattern, or a tie rejects the push — unconfigured branches are
    not allowed, and an ambiguous configuration is not silently resolved."""
    matched = []
    for rule in config.branch_rules:
        if not rule.enabled:
            continue
        try:
            if match(rule.pattern, branch):
                matched.append(rule)
        except BadPattern as exc:
            raise RouteError(f"branch rule pattern '{rule.pattern}' is malformed: {exc}")
    if not matched:
        raise RouteError(
            f"no workflow found for branch '{branch}' - branch not allowed by configuration"
        )
    matched.sort(key=lambda r: specificity(r.pattern))
    if len(matched) > 1 and specificity(matched[0].pattern) == specificity(
        matched[1].pattern
    ):
        raise RouteError(
            f"branch '{branch}' matches equally specific rules "
            f"'{matched[0].pattern}' and '{matched[1].pattern}'"
        )
    return matched[0]


def execute(config: RepoConfig, ctx: Context) -> Result:
    rule = route(config, ctx.branch)
    if rule.workflow == "protected":
        return protected(ctx, rule)
    if rule.workflow == "issue-tracker":
        return issue_tracker(ctx)
    return passthrough(ctx, rule)
