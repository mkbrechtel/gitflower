"""The gitflower command-line interface (click).

Two families of commands share this entry point, as in the Go originals:
per-repo workflow commands (init, install, uninstall, config, hook) that act
on the current working directory's repository, and hosting commands (create,
list, web) that act on the configured repos directory.

The group and the helpers every command family needs live here; the commands
themselves are grouped by what they act on. Importing the command modules at
the bottom is what registers them, so `gitflower.cli:main` — the console
script entry point — still resolves to a fully populated group.
"""

import subprocess
from dataclasses import asdict
from pathlib import Path

import click
import yaml

from gitflower import __version__, config as cfg

def _table(columns, rows, empty: str = "") -> None:
    """Render a list view as an aligned table.

    Columns come from gitflower.models, so the CLI and the TUI show the same
    fields in the same order without either owning the definition.
    """
    from gitflower import models

    header = tuple(c.header for c in columns)
    table = [header, tuple("-" * len(h) for h in header)]
    table.extend(tuple(models.cells(columns, row)) for row in rows)
    if not rows and empty:
        table.append((empty,) + ("",) * (len(header) - 1))
    widths = [max(len(row[i]) for row in table) for i in range(len(header))]
    for row in table:
        click.echo("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip())


def _emit(fmt: str, data, columns=None, rows=None, empty: str = "") -> bool:
    """Serve a view model as json/yaml through the one shared shaping point.

    Returns True when the structured format was emitted, so table callers can
    fall through. The JSON is byte-for-byte what the web endpoint returns for
    the same model — same to_dict, same model.
    """
    from gitflower import models

    if fmt == "json":
        click.echo(models.to_json(data))
        return True
    if fmt == "yaml":
        click.echo(yaml.safe_dump(models.to_dict(data), sort_keys=False), nl=False)
        return True
    _table(columns, rows, empty)
    return False


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



from gitflower.cli import host, mr, repo, review  # noqa: E402,F401  (registers commands)
