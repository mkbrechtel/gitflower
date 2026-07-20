"""Hosting commands: they act on the configured repos directory."""

import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import click
import yaml

from gitflower import config as cfg, hooks
from gitflower.cli import _bare_repo_root, _emit, _global_config, _hosted_repo, _repo_root, main
from gitflower.workflows import Context, RouteError, execute

# ------------------------------------------------------------ hosting


@main.command()
@click.argument("path")
@click.pass_context
def create(ctx: click.Context, path: str) -> None:
    """Create a bare repository under the repos directory."""
    from gitflower import gitread
    from gitflower.slug import SlugError

    global_cfg = _global_config(ctx)
    if not path.endswith(".git"):
        path += ".git"
    try:
        full = gitread.create_repository(
            global_cfg.repos.directory, path, global_cfg.repos.default_branch
        )
    except (SlugError, gitread.GitReadError) as exc:
        raise click.ClickException(str(exc))
    click.echo(f"Created repository: {path}")
    click.echo()
    click.echo("To push to this repository:")
    click.echo(f"  git remote add origin {full}")
    click.echo(f"  git push -u origin {global_cfg.repos.default_branch}")


@main.command("list")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "json", "yaml"]),
    default="table",
    show_default=True,
)
@click.option("--warnings", is_flag=True, help="Print scan warnings to stderr.")
@click.pass_context
def list_repos(ctx: click.Context, fmt: str, warnings: bool) -> None:
    """List repositories in the repos directory."""
    from gitflower import gitread, models

    global_cfg = _global_config(ctx)
    result = gitread.scan_repos(global_cfg.repos.directory, global_cfg.repos.scan_depth)
    if warnings:
        for warning in result.warnings:
            click.echo(warning, err=True)
    data = models.RepoList.of(result)
    _emit(fmt, data, models.REPO_COLUMNS, data.rows(), "No repositories found")


@main.group("issues")
def issues_group() -> None:
    """Inspect in-tree issues across branches."""


@issues_group.command("list")
@click.argument("repo")
@click.option("--q", "query", default=None, help="JMESPath filter over the issue documents.")
@click.option("--branch", default=None, help="Only issues present on this branch.")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "json", "yaml"]),
    default="table",
    show_default=True,
)
@click.pass_context
def issues_list(
    ctx: click.Context, repo: str, query: str | None, branch: str | None, fmt: str
) -> None:
    """List a repository's issues across its branches."""
    from gitflower import issues, models

    try:
        data = models.IssueList.of(_hosted_repo(ctx, repo), repo, q=query, branch=branch)
    except issues.QueryError as exc:
        raise click.ClickException(str(exc))
    _emit(fmt, data, models.ISSUE_COLUMNS, data.rows(), "No issues found")


@issues_group.command("show")
@click.argument("repo")
@click.argument("uuid")
@click.option("--at", default=None, help="Show the version at this commit.")
@click.pass_context
def issues_show(ctx: click.Context, repo: str, uuid: str, at: str | None) -> None:
    """Show one issue: cross-branch state, history, and content."""
    from gitflower import issues

    detail = issues.issue_detail(_hosted_repo(ctx, repo), uuid, at=at)
    if detail is None:
        raise click.ClickException(f"no issue with id {uuid}" + (f" at {at}" if at else ""))
    meta = {
        "id": detail["id"],
        "title": detail["title"],
        "frontmatter": detail["frontmatter"],
        "branches": detail["branches"],
        "history": [
            {"commit": t["short"], "subject": t["subject"], "path": t["path"], "status": t["status"]}
            for t in detail["transitions"]
        ],
    }
    click.echo(yaml.safe_dump(meta, sort_keys=False), nl=False)
    click.echo("---")
    click.echo(detail["content"], nl=False)


@issues_group.command("fsck")
@click.argument("repo")
@click.pass_context
def issues_fsck(ctx: click.Context, repo: str) -> None:
    """Check issue integrity: duplicate ids, files without an id."""
    from gitflower import issues

    findings = issues.fsck(_hosted_repo(ctx, repo))
    for f in findings:
        what = f"duplicate id '{f['id']}'" if f["kind"] == "duplicate-id" else "missing id"
        click.echo(f"{f['branch']}: {what} — {f['path']}")
    if any(f["kind"] == "duplicate-id" for f in findings):
        sys.exit(1)
    if not findings:
        click.echo("OK: no findings.")


@main.command()
@click.pass_context
def maintenance(ctx: click.Context) -> None:
    """Refresh the commit-graph (with changed-path Bloom filters) of every
    hosted repository — keeps issue and history walks fast."""
    from gitflower import gitread

    global_cfg = _global_config(ctx)
    result = gitread.scan_repos(global_cfg.repos.directory, global_cfg.repos.scan_depth)
    failed = False
    for repo in result.repos:
        if not repo.is_valid:
            continue
        run = subprocess.run(
            [
                "git",
                "-C",
                str(Path(global_cfg.repos.directory) / repo.path),
                "commit-graph",
                "write",
                "--reachable",
                "--changed-paths",
            ],
            capture_output=True,
            text=True,
        )
        if run.returncode == 0:
            click.echo(f"{repo.path}: commit-graph written")
        else:
            failed = True
            click.echo(f"{repo.path}: ERROR {run.stderr.strip()}", err=True)
    if failed:
        sys.exit(1)


@main.command()
@click.option("--addr", default=None, help="Override the configured web address.")
@click.pass_context
def web(ctx: click.Context, addr: str | None) -> None:
    """Start the web server."""
    import uvicorn

    from gitflower.web.app import create_app

    global_cfg = _global_config(ctx)
    address = addr or global_cfg.web.address
    try:
        host, port = cfg.parse_address(address)
    except cfg.ConfigError as exc:
        raise click.ClickException(str(exc))
    click.echo(f"Starting web server on {address}")
    uvicorn.run(create_app(global_cfg), host=host, port=port, log_level="info")
