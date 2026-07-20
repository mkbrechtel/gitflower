"""The review command: scaffold a review of a branch and open the TUI."""

import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import click
import yaml

from gitflower import config as cfg, hooks
from gitflower.cli import _bare_repo_root, _emit, _global_config, _hosted_repo, _repo_root, main
from gitflower.workflows import Context, RouteError, execute

# ------------------------------------------------------------- review


@main.command()
@click.option("--branch", default=None, help="Branch to review (default: current branch).")
@click.option("--base", "base_ref", default=None,
              help="Base ref for the diff range (default: last [Review] merge, else main).")
@click.option("--notes-ref", default=None,
              help="Notes ref to read and write (default: refs/notes/reviews).")
@click.option("-o", "mirror", type=click.Path(), default=None,
              help="Mirror the .review body to a file in addition to the notes ref.")
@click.option("--no-tui", is_flag=True, help="Scaffold and exit without launching the TUI.")
@click.option("--empty-review", is_flag=True,
              help="Skip the change-covering scaffold; header and # Review only.")
@click.option("--read-rate", type=float, default=10.0, show_default=True,
              help="Auto-read pacing for the TUI (lines/second).")
@click.option("--with-timestamps", is_flag=True,
              help="Record per-event timestamps (off by default for privacy).")
def review(branch: str | None, base_ref: str | None, notes_ref: str | None,
           mirror: str | None, no_tui: bool, empty_review: bool,
           read_rate: float, with_timestamps: bool) -> None:
    """Review a branch: scaffold a .review and open the TUI."""
    import pygit2

    from gitflower.review import format as fmt, notes, scaffold
    from gitflower.review.session import Session

    discovered = pygit2.discover_repository(str(Path.cwd()))
    if discovered is None:
        raise click.ClickException("not a git repository")
    repo = pygit2.Repository(discovered)
    try:
        signature = repo.default_signature
    except (KeyError, pygit2.GitError):
        raise click.ClickException("git user.name / user.email are not configured")

    if branch is None:
        if repo.head_is_unborn or repo.head_is_detached:
            raise click.ClickException("no current branch — pass --branch")
        branch = repo.head.shorthand
    if branch not in repo.branches.local:
        raise click.ClickException(f"no such branch: {branch}")
    tip_sha = str(repo.branches.local[branch].target)
    ref = notes_ref or notes.DEFAULT_REF

    # Re-running is non-destructive: an existing .review for the tip loads
    # as-is; a foreign note body is imported into a fresh scaffold.
    existing = notes.read_note(repo, tip_sha, ref)
    if existing is not None and fmt.is_dot_review(existing):
        try:
            body = fmt.parse(existing)
        except fmt.FormatError as exc:
            raise click.ClickException(f"stored review does not parse: {exc}")
    else:
        base = None
        if base_ref is not None:
            try:
                base_commit, _ = repo.resolve_refish(base_ref)
                base = base_commit
            except (KeyError, pygit2.GitError):
                raise click.ClickException(f"cannot resolve base ref: {base_ref}")
        try:
            body = scaffold.scaffold(
                repo, branch, signature.name, signature.email,
                base=base, empty=empty_review,
            )
        except scaffold.ScaffoldError as exc:
            raise click.ClickException(str(exc))
        if existing is not None:
            notes.import_foreign_note(body, existing, tip_sha, ref)

    mirror_path = Path(mirror) if mirror else None
    review_session = Session(
        repo, body, tip_sha, notes_ref=ref, mirror=mirror_path,
        with_timestamps=with_timestamps, read_rate=read_rate,
    )

    if no_tui:
        blob_sha = review_session.save()
        click.echo("Your review went to:")
        click.echo(f"  notes ref: git notes --ref={ref} show {tip_sha}  (follows edits)")
        click.echo(f"  snapshot:  git cat-file blob {blob_sha}  (this save, immutable)")
        if mirror_path is not None:
            click.echo(f"  mirror:    {mirror_path}")
        return

    from gitflower.review.tui import ReviewApp

    ReviewApp(review_session).run()


