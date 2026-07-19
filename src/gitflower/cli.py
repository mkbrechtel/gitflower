"""The gitflower command-line interface (click).

Two families of commands share this entry point, as in the Go originals:
per-repo workflow commands (init, install, uninstall, config, hook) that act
on the current working directory's repository, and hosting commands (create,
list, web) that act on the configured repos directory.
"""

import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import click
import yaml

from gitflower import __version__, config as cfg, hooks
from gitflower.workflows import Context, RouteError, execute


def _repo_root() -> Path:
    """The repository the per-repo commands act on: cwd must be one."""
    cwd = Path.cwd()
    try:
        cfg.git_dir(cwd)
    except cfg.ConfigError:
        raise click.ClickException("not a git repository (or any parent up to mount point)")
    return cwd


def _bare_repo_root() -> Path:
    """As `_repo_root`, but refuses a working tree.

    gitflower enforces policy in a server-side pre-receive hook, so the
    settings and the hook both belong to the bare repository being pushed to.
    Installing into a clone would produce a hook that never runs.
    """
    root = _repo_root()
    import pygit2

    if not pygit2.Repository(str(root)).is_bare:
        raise click.ClickException(
            "not a bare repository — gitflower policy is enforced server-side, "
            "so run this in the bare repository that receives pushes"
        )
    return root


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
    root = _bare_repo_root()
    try:
        cfg.load_repo_config(root)
    except cfg.ConfigError as exc:
        raise click.ClickException(str(exc))
    click.echo("Gitflower initialized successfully!")
    click.echo(f"Configuration lives in {cfg.git_dir(root) / 'config'} under [gitflower].")
    click.echo("Nothing was written — the built-in defaults are already in effect.")
    click.echo()
    click.echo("Next steps:")
    click.echo("  1. Review the effective configuration: gitflower config show")
    click.echo("  2. Install the git hook: gitflower install")


@main.command()
@click.option("--force", is_flag=True, help="Overwrite a foreign pre-receive hook.")
def install(force: bool) -> None:
    """Install the pre-receive hook."""
    root = _bare_repo_root()
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
@click.option("--global", "want_global", is_flag=True, help="Show the server config.")
@click.pass_context
def config_show(ctx: click.Context, want_global: bool) -> None:
    """Print the effective configuration."""
    if not want_global:
        try:
            root = _repo_root()
        except click.ClickException:
            root = None
        if root is not None:
            try:
                click.echo(cfg.dump_repo_config(cfg.load_repo_config(root)), nl=False)
            except cfg.ConfigError as exc:
                raise click.ClickException(str(exc))
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
    """Open the repository's git config in an editor and validate the result."""
    root = _repo_root()
    result = subprocess.run(["git", "-C", str(root), "config", "--edit"])
    if result.returncode != 0:
        raise click.ClickException(f"git config --edit exited with {result.returncode}")
    try:
        cfg.load_repo_config(root)
    except cfg.ConfigError as exc:
        raise click.ClickException(f"config is now invalid: {exc}")
    click.echo("Configuration OK.")


@main.group(hidden=True)
def hook() -> None:
    """Internal hook handlers (invoked by the installed git hooks)."""


@hook.command("pre-receive")
@click.option("--branch", required=True)
@click.option("--old-ref", default="")
@click.option("--new-ref", default="")
@click.option("--ref", "ref_name", default="")
def hook_pre_receive(branch: str, old_ref: str, new_ref: str, ref_name: str) -> None:
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
