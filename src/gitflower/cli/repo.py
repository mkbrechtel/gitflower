"""Commands acting on one repository: init, install, config, and the hooks."""

import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import click
import yaml

from gitflower import config as cfg, hooks
from gitflower.cli import _bare_repo_root, _emit, _global_config, _hosted_repo, _repo_root, main
from gitflower.workflows import Context, RouteError, execute

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


@hook.command("post-receive")
@click.option("--branch", required=True)
@click.option("--old-ref", default="")
@click.option("--new-ref", default="")
@click.option("--ref", "ref_name", default="")
def hook_post_receive(branch: str, old_ref: str, new_ref: str, ref_name: str) -> None:
    """Record what the accepted push means for merge requests.

    The push is already durable. Nothing here may fail it, so every error is
    reported and swallowed: losing a ref that can be recomputed is a much
    smaller harm than rejecting work that was already accepted.
    """
    import pygit2

    from gitflower import mr

    try:
        repo = pygit2.Repository(str(Path.cwd()))
        for note in mr.record_push(repo, branch, old_ref, new_ref):
            click.echo(f"gitflower: {note}")
    except Exception as exc:  # noqa: BLE001 — bookkeeping never fails a push
        click.echo(f"gitflower: could not record merge requests: {exc}", err=True)


