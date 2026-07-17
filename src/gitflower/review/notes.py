"""Persistence: the .review lives on a git notes ref, keyed by reviewed commit.

The notes ref (default `refs/notes/reviews`) is the source of truth; the
optional file mirror is rewritten on every save and never read back. The ref
is shared territory: note bodies that don't probe as .review (kernel-style
sign-offs, CI output) are imported into the scaffold as a `## Note`
subsection and never overwritten in place — the save path always writes a
full .review body.
"""

from pathlib import Path

import pygit2

from gitflower.review import format as fmt

DEFAULT_REF = "refs/notes/reviews"


def read_note(repo: pygit2.Repository, sha: str, ref: str = DEFAULT_REF) -> str | None:
    try:
        return repo.lookup_note(sha, ref).message
    except KeyError:
        return None


def load(repo: pygit2.Repository, sha: str, ref: str = DEFAULT_REF) -> fmt.Review | None:
    """The stored review for `sha`, or None if absent or not .review-format."""
    body = read_note(repo, sha, ref)
    if body is None or not fmt.is_dot_review(body):
        return None
    return fmt.parse(body)


def import_foreign_note(review: fmt.Review, body: str, sha: str, ref: str) -> None:
    """Quote a non-.review note body into the scaffold as a ## Note subsection.

    Kernel-style trailers stay grep-able in the imported body, so a gate hook
    keeps recognising sign-offs after the conversion.
    """
    subsection = fmt.Section(
        level=2,
        title="Note",
        recipe=f"git notes --ref={ref} show {sha[:12]}",
    )
    for number, line in enumerate(body.rstrip("\n").split("\n"), start=1):
        subsection.items.append(fmt.Quote(f"> {number}: {line}"))
    section = review.review_section
    section.items.append(fmt.Blank())
    section.items.append(subsection)


def save(
    repo: pygit2.Repository,
    review: fmt.Review,
    sha: str,
    ref: str = DEFAULT_REF,
    mirror: Path | None = None,
) -> str:
    """Write the review to the notes ref (and mirror). Returns the body's blob SHA."""
    body = fmt.render(review)
    signature = repo.default_signature
    repo.create_note(body, signature, signature, sha, ref, True)
    if mirror is not None:
        mirror.write_text(body)
    return str(pygit2.hash(body.encode()))
