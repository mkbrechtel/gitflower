"""The merge-request commands.

Reading works from either side: `--repo <path>` opens a hosted repository,
and without it the repository you are standing in. Every list and detail
view is the same `models.MrList` / `models.MrDetail` the web serves, so
`gitflower mr list --format json` and `GET …/mrs/?format=json` agree by
construction rather than by two pieces of parallel code.

Making a request is client-side only. gitflower enforces policy in the
server's pre-receive hook, so a client command is pure mechanism: it writes
the commit, and the push is where anything gets decided.
"""

from pathlib import Path

import click

from gitflower import models
from gitflower.cli import _emit, _global_config, _hosted_repo, main

STATE_EXIT = {
    "merged": 0,
    "open": 2,
    "closed": 3,
    "rejected": 4,
    "superseded": 5,
}


def _repo(ctx: click.Context, repo_path: str | None):
    """A hosted repository by path, or the one the shell is standing in."""
    if repo_path:
        return _hosted_repo(ctx, repo_path)
    import pygit2

    found = pygit2.discover_repository(str(Path.cwd()))
    if found is None:
        raise click.ClickException(
            "not a git repository — run this inside one, or name a hosted "
            "repository with --repo"
        )
    return pygit2.Repository(found)


def _path_of(repo, repo_path: str | None) -> str:
    """What the view model calls this repository. The web has it from the
    URL; here it is the --repo argument, or the directory's own name."""
    if repo_path:
        return repo_path if repo_path.endswith(".git") else repo_path + ".git"
    return Path(repo.path.rstrip("/")).name


repo_option = click.option(
    "--repo", "repo_path", default=None, help="A hosted repository, instead of the current one."
)
format_option = click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "json", "yaml"]),
    default="table",
    show_default=True,
)


@main.group("mr", invoke_without_command=True)
@click.pass_context
def mr_group(ctx: click.Context) -> None:
    """Merge requests: the empty `MR: …` commits offered for merging."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@mr_group.command("list")
@repo_option
@format_option
@click.option(
    "--state",
    type=click.Choice(list(STATE_EXIT)),
    default=None,
    help="Only merge requests in this state.",
)
@click.pass_context
def mr_list(ctx: click.Context, repo_path: str | None, fmt: str, state: str | None) -> None:
    """List merge requests."""
    repo = _repo(ctx, repo_path)
    data = models.MrList.of(repo, _path_of(repo, repo_path), state=state)
    _emit(fmt, data, models.MR_COLUMNS, data.rows(), "No merge requests found")


@mr_group.command("show")
@click.argument("request")
@repo_option
@click.option(
    "--format", "fmt", type=click.Choice(["text", "json", "yaml"]), default="text", show_default=True
)
@click.pass_context
def mr_show(ctx: click.Context, request: str, repo_path: str | None, fmt: str) -> None:
    """Show one merge request, by id or by the branch offering it."""
    repo = _repo(ctx, repo_path)
    data = _resolve(repo, _path_of(repo, repo_path), request)
    if fmt in ("json", "yaml"):
        _emit(fmt, data)
        return
    click.echo(f"{data.short}  {data.state}  {data.title}")
    click.echo(f"author   {data.author} <{data.email}>  {data.date}")
    click.echo(f"source   {data.source or '(no branch offers it)'}")
    click.echo(f"target   {data.target or '(the mainline)'}")
    if data.stacked_on:
        click.echo(f"stacked  on {data.stacked_on[:12]}")
    if data.merge_oid:
        click.echo(f"merged   by {data.merge_oid[:12]}")
    elif data.resolution_kind:
        click.echo(f"{data.resolution_kind.lower():8} {data.resolution_message}")
    if data.body:
        click.echo()
        click.echo(data.body)
    click.echo()
    click.echo(f"{len(data.commits)} commits:")
    for commit in data.commits:
        click.echo(f"  {commit.short}  {commit.subject}")


@mr_group.command("status")
@click.argument("request")
@repo_option
@click.pass_context
def mr_status(ctx: click.Context, request: str, repo_path: str | None) -> None:
    """Print one merge request's state, and exit with a code that means it.

    For scripts: 0 merged, 2 open, 3 closed, 4 rejected, 5 superseded.
    """
    repo = _repo(ctx, repo_path)
    data = _resolve(repo, _path_of(repo, repo_path), request)
    click.echo(f"{data.short} {data.state}")
    ctx.exit(STATE_EXIT.get(data.state, 1))


@mr_group.command("create")
@click.option("--branch", default=None, help="The branch to put the request on (default: current).")
@click.option("--target", default=None, help="An explicit target branch, for special cases.")
@click.option("--topic", default=None, help="A topic, when the branch name is not the subject.")
@click.option("-m", "--message", default=None, help="The title; without it, an editor opens.")
@click.pass_context
def mr_create(
    ctx: click.Context,
    branch: str | None,
    target: str | None,
    topic: str | None,
    message: str | None,
) -> None:
    """Offer the current branch for merging.

    Writes the empty `MR: <title>` commit. Nothing is pushed — the request
    reaches the server the way every other commit does.
    """
    from gitflower import mr as mrs

    repo = _repo(ctx, None)
    branch = branch or _current_branch(repo)
    title, body = _title_and_body(message, branch)
    if not title:
        raise click.ClickException("a merge request needs a title")
    existing = mrs.is_ready(repo, branch, target or mrs.default_branch(repo) or "main")
    if existing is not None:
        raise click.ClickException(
            f"branch '{branch}' already offers {existing.short} — "
            "commit the rework first, then ask again"
        )
    try:
        oid = mrs.create_request(
            repo, branch, title, body=body, topic=topic, target=target
        )
    except mrs.MRError as exc:
        raise click.ClickException(str(exc))
    click.echo(f"Opened merge request {oid[: mrs.ABBREV]} on {branch}.")
    click.echo(f"  git push origin {branch}")


def _current_branch(repo) -> str:
    if repo.head_is_detached:
        raise click.ClickException("HEAD is detached — check out the branch you mean")
    if repo.head_is_unborn:
        raise click.ClickException("this branch has no commits yet")
    return repo.head.shorthand


def _title_and_body(message: str | None, branch: str) -> tuple[str, str]:
    if message:
        title, _, body = message.partition("\n")
        return title.strip(), body.strip()
    template = (
        f"MR: \n\n"
        f"# The title above says what merging {branch} would bring in.\n"
        "# Lines starting with # are dropped. An empty title aborts.\n"
    )
    edited = click.edit(template)
    if edited is None:
        raise click.ClickException("aborted")
    kept = [line for line in edited.splitlines() if not line.startswith("#")]
    text = "\n".join(kept).strip()
    text = text[3:].strip() if text.startswith("MR:") else text
    title, _, body = text.partition("\n")
    return title.strip(), body.strip()


def _resolve(repo, path: str, request: str) -> models.MrDetail:
    """A merge request by id, id prefix, or the branch that offers it."""
    from gitflower import mr as mrs

    data = models.MrDetail.of(repo, path, request)
    if data is not None:
        return data
    for found in mrs.discover(repo):
        if found.branch == request:
            return models.MrDetail.of(repo, path, found.oid)
    raise click.ClickException(f"no merge request matching '{request}'")
