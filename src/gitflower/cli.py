"""The gitflower command-line interface (click).

Two families of commands share this entry point, as in the Go originals:
per-repo workflow commands (init, install, uninstall, config, hook) that act
on the current working directory's repository, and hosting commands (create,
list, web) that act on the configured repos directory.
"""

import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import click
import yaml

from gitflower import __version__, config as cfg, hooks
from gitflower.workflows import Context, RouteError, execute


def _repo_root() -> Path:
    """The repository the per-repo commands act on: cwd must hold a .git."""
    cwd = Path.cwd()
    if not (cwd / ".git").exists():
        raise click.ClickException("not a git repository (or any parent up to mount point)")
    return cwd


@click.group()
@click.version_option(__version__)
@click.option(
    "--config",
    "config_path",
    type=click.Path(),
    default=None,
    help="Global config file (default: $GITFLOWER_CONFIG, ~/.config/gitflower/config.yaml, /etc/gitflower/config.yaml).",
)
@click.pass_context
def main(ctx: click.Context, config_path: str | None) -> None:
    """gitflower - a git-based development platform."""
    ctx.obj = {"config_path": config_path}


def _global_config(ctx: click.Context) -> cfg.GlobalConfig:
    try:
        return cfg.load_global_config(ctx.obj.get("config_path"))
    except cfg.ConfigError as exc:
        raise click.ClickException(str(exc))


# ----------------------------------------------------------- per-repo


@main.command()
def init() -> None:
    """Initialize gitflower in the current repository."""
    root = _repo_root()
    path = cfg.repo_config_path(root)
    path.parent.mkdir(mode=0o755, exist_ok=True)
    if not path.exists():
        path.write_text(cfg.dump_repo_config(cfg.default_repo_config()))
    click.echo("Gitflower initialized successfully!")
    click.echo(f"Configuration file created at: {path}")
    click.echo()
    click.echo("Next steps:")
    click.echo("  1. Review and customize the configuration: gitflower config show")
    click.echo("  2. Install git hooks: gitflower install")


@main.command()
@click.option("--force", is_flag=True, help="Overwrite a foreign pre-push hook.")
def install(force: bool) -> None:
    """Install git hooks."""
    root = _repo_root()
    try:
        cfg.load_repo_config(root)  # surface config errors before installing
        hooks.install(root, force=force)
    except (cfg.ConfigError, hooks.HookError) as exc:
        raise click.ClickException(str(exc))
    click.echo("Git hooks installed successfully!")


@main.command()
def uninstall() -> None:
    """Uninstall git hooks."""
    hooks.uninstall(_repo_root())
    click.echo("Git hooks uninstalled successfully!")


@main.group("config")
def config_group() -> None:
    """Show or edit configuration."""


@config_group.command("show")
@click.pass_context
def config_show(ctx: click.Context) -> None:
    """Print the effective configuration."""
    root = Path.cwd()
    repo_config = cfg.repo_config_path(root)
    if repo_config.exists():
        click.echo(repo_config.read_text(), nl=False)
        return
    if (root / ".git").exists():
        click.echo("# no .gitflower/config.yaml — defaults in effect:")
        click.echo(cfg.dump_repo_config(cfg.default_repo_config()), nl=False)
        return
    global_cfg = _global_config(ctx)
    click.echo(f"# global config ({global_cfg.path or 'built-in defaults'}):")
    data = {
        "repos": asdict(global_cfg.repos),
        "web": asdict(global_cfg.web),
    }
    click.echo(yaml.safe_dump(data, sort_keys=False), nl=False)


@config_group.command("edit")
def config_edit() -> None:
    """Open the repo configuration in $EDITOR and validate the result."""
    root = _repo_root()
    path = cfg.repo_config_path(root)
    if not path.exists():
        raise click.ClickException("no configuration yet — run `gitflower init` first")
    editor = os.environ.get("EDITOR", "nano")
    result = subprocess.run([editor, str(path)])
    if result.returncode != 0:
        raise click.ClickException(f"{editor} exited with {result.returncode}")
    try:
        cfg.load_repo_config(root)
    except cfg.ConfigError as exc:
        raise click.ClickException(f"config is now invalid: {exc}")
    click.echo("Configuration OK.")


@main.group(hidden=True)
def hook() -> None:
    """Internal hook handlers (invoked by the installed git hooks)."""


@hook.command("pre-push")
@click.option("--branch", required=True)
@click.option("--old-ref", default="")
@click.option("--new-ref", default="")
@click.option("--ref", "ref_name", default="")
def hook_pre_push(branch: str, old_ref: str, new_ref: str, ref_name: str) -> None:
    root = Path.cwd()
    try:
        repo_config = cfg.load_repo_config(root)
        result = execute(
            repo_config,
            Context(
                repo_path=str(root),
                branch=branch,
                old_ref=old_ref,
                new_ref=new_ref,
                ref_name=ref_name,
            ),
        )
    except (cfg.ConfigError, RouteError, RuntimeError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    if not result.allowed:
        click.echo(f"Error: {result.message}", err=True)
        sys.exit(1)
    if result.message:
        click.echo(result.message)


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
    from gitflower import gitread

    global_cfg = _global_config(ctx)
    result = gitread.scan_repos(global_cfg.repos.directory, global_cfg.repos.scan_depth)
    if warnings:
        for warning in result.warnings:
            click.echo(warning, err=True)
    rows = [asdict(repo) for repo in result.repos]
    if fmt == "json":
        click.echo(json.dumps(rows, indent=2))
        return
    if fmt == "yaml":
        click.echo(yaml.safe_dump(rows, sort_keys=False), nl=False)
        return
    header = ("PATH", "BRANCHES", "MR", "SIZE", "LAST UPDATE", "STATUS")
    table = [header, tuple("-" * len(h) for h in header)]
    for repo in result.repos:
        status = "OK" if repo.is_valid else f"ERROR: {repo.error}"
        table.append(
            (
                repo.path,
                str(repo.branch_count),
                str(repo.mr_count),
                f"{repo.size / (1024 * 1024):.2f} MB",
                repo.last_update or "",
                status,
            )
        )
    if not result.repos:
        table.append(("No repositories found", "", "", "", "", ""))
    widths = [max(len(row[i]) for row in table) for i in range(len(header))]
    for row in table:
        click.echo("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip())


def _hosted_repo(ctx: click.Context, repo_path: str):
    from gitflower import gitread
    from gitflower.slug import SlugError

    global_cfg = _global_config(ctx)
    if not repo_path.endswith(".git"):
        repo_path += ".git"
    try:
        return gitread.open_repo(global_cfg.repos.directory, repo_path)
    except (SlugError, gitread.GitReadError) as exc:
        raise click.ClickException(str(exc))


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
    from gitflower import issues

    data = issues.documents(_hosted_repo(ctx, repo))
    docs = data["issues"]
    if branch:
        docs = [d for d in docs if branch in d["branches"]]
    if query:
        try:
            docs = issues.filter_documents(docs, query)
        except issues.QueryError as exc:
            raise click.ClickException(str(exc))
    if fmt == "json":
        click.echo(json.dumps(docs, indent=2))
        return
    if fmt == "yaml":
        click.echo(yaml.safe_dump(docs, sort_keys=False), nl=False)
        return
    header = ("TITLE", "ID", "BRANCHES")
    table = [header, tuple("-" * len(h) for h in header)]
    for doc in docs:
        states = " ".join(
            f"{name}:{state['state']}" for name, state in sorted(doc["branches"].items())
        )
        table.append((doc["title"], doc["id"] or "(no id)", states))
    if not docs:
        table.append(("No issues found", "", ""))
    widths = [max(len(row[i]) for row in table) for i in range(len(header))]
    for row in table:
        click.echo("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip())


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
