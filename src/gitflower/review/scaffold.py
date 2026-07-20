"""Build the default .review scaffold from git objects (pygit2).

The default scaffold covers everything that changed since the last review:
one `# Diff <base>..<tip>` section spanning the full delta and one
`# Commit <sha>` (or `# Merge-Commit <sha>`) section per commit in
`base..tip`, oldest first. The base is the tip of the most recent `[Review]`
merge on the branch, falling back to `main`.

Every heading inlines an `@ <git command>` recipe with literal OIDs, so the
review names the exact objects it covers. OIDs are abbreviated to 12
characters, matching the spec's examples.
"""

import json
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pygit2
from pygit2.enums import DeltaStatus, SortMode

from gitflower.review import format as fmt

ABBREV = 12


class ScaffoldError(Exception):
    pass


def _short(oid) -> str:
    return str(oid)[:ABBREV]


def _jpath(path: str) -> str:
    return json.dumps(path, ensure_ascii=False)


def find_base(repo: pygit2.Repository, tip: pygit2.Commit) -> pygit2.Commit:
    """The tip of the most recent `[Review]` merge on the branch, else main."""
    commit = tip
    while True:
        if commit.message.startswith("[Review]") and len(commit.parents) > 1:
            return commit
        if not commit.parents:
            break
        commit = commit.parents[0]
    for name in ("main", "master"):
        if name in repo.branches.local:
            return repo[repo.branches.local[name].target]
    raise ScaffoldError("no [Review] merge found and no main branch to fall back to")


def scaffold(
    repo: pygit2.Repository,
    branch: str,
    reviewer_name: str,
    reviewer_email: str,
    base: pygit2.Commit | None = None,
    empty: bool = False,
) -> fmt.Review:
    if branch not in repo.branches.local:
        raise ScaffoldError(f"no such branch: {branch}")
    tip = repo[repo.branches.local[branch].target]

    review = fmt.Review(header=fmt.default_header())
    head_section = fmt.Section(level=1, title="Review")
    head_section.items.append(fmt.MetaLine("Review-Head-Commit", str(tip.id)))
    head_section.items.append(fmt.MetaLine("Review-Branch", branch))
    head_section.items.append(
        fmt.MetaLine("Created-By", f"{reviewer_name} <{reviewer_email}>")
    )
    review.sections.append(head_section)
    if empty:
        return review

    if base is None:
        base = find_base(repo, tip)

    if base.id != tip.id:
        diff_section = fmt.Section(
            level=1,
            title=f"Diff {_short(base.id)}..{_short(tip.id)}",
            recipe=f"git diff {_short(base.id)}..{_short(tip.id)}",
        )
        diff = repo.diff(base, tip, context_lines=3)
        diff.find_similar()
        for subsection in _file_subsections(repo, diff, level=2):
            diff_section.items.append(fmt.Blank())
            diff_section.items.append(subsection)
        review.sections.append(diff_section)

        walker = repo.walk(tip.id, SortMode.TOPOLOGICAL | SortMode.REVERSE)
        walker.hide(base.id)
        for commit in walker:
            review.sections.append(_commit_section(repo, commit))

    return review


# ---------------------------------------------------------- commit sections


def _commit_section(repo: pygit2.Repository, commit: pygit2.Commit) -> fmt.Section:
    if len(commit.parents) > 1:
        return _merge_commit_section(repo, commit)
    section = fmt.Section(
        level=1,
        title=f"Commit {_short(commit.id)}",
        recipe=f"git show {_short(commit.id)}",
    )
    section.items.extend(_commit_quote(commit))
    if commit.parents:
        diff = repo.diff(commit.parents[0], commit, context_lines=3)
    else:
        diff = commit.tree.diff_to_tree(swap=True)
    diff.find_similar()
    for subsection in _file_subsections(repo, diff, level=2):
        section.items.append(fmt.Blank())
        section.items.append(subsection)
    return section


def _merge_commit_section(repo: pygit2.Repository, commit: pygit2.Commit) -> fmt.Section:
    """N per-parent diff subsections, one per parent, including empty ones."""
    section = fmt.Section(
        level=1,
        title=f"Merge-Commit {_short(commit.id)}",
        recipe=f"git show -m {_short(commit.id)}",
    )
    section.items.extend(_commit_quote(commit))
    for number, parent in enumerate(commit.parents, start=1):
        subsection = fmt.Section(
            level=2,
            title=f"Diff from parent {number}",
            recipe=f"git show -m -{number} {_short(commit.id)}",
        )
        diff = repo.diff(parent, commit, context_lines=3)
        diff.find_similar()
        for file_subsection in _file_subsections(repo, diff, level=3):
            subsection.items.append(fmt.Blank())
            subsection.items.append(file_subsection)
        section.items.append(fmt.Blank())
        section.items.append(subsection)
    return section


def _commit_quote(commit: pygit2.Commit) -> list:
    author = commit.author
    when = datetime.fromtimestamp(
        author.time, timezone(timedelta(minutes=author.offset))
    )
    lines = commit.message.rstrip("\n").split("\n")
    subject, body = lines[0], lines[1:]
    while body and not body[0].strip():
        body = body[1:]
    items: list = [
        fmt.Quote(f"> From: {author.name} <{author.email}>"),
        fmt.Quote(f"> Date: {format_datetime(when)}"),
        fmt.Quote(f"> Subject: {subject}"),
    ]
    if body:
        items.append(fmt.Quote("> Message:"))
        for line in body:
            items.append(fmt.Quote(f"> > {line}" if line else "> >"))
    return items


# ------------------------------------------------------- per-file sections


def _file_subsections(
    repo: pygit2.Repository, diff: pygit2.Diff, level: int
) -> list[fmt.Section]:
    sections = []
    for patch in diff:
        delta = patch.delta
        old, new = delta.old_file, delta.new_file
        if delta.status == DeltaStatus.ADDED:
            section = fmt.Section(
                level=level,
                title=f"File {_jpath(new.path)} created",
                recipe=f"git show {_short(new.id)}",
            )
            _object_body(section, repo, new.id)
        elif delta.status == DeltaStatus.DELETED:
            section = fmt.Section(
                level=level,
                title=f"File {_jpath(old.path)} deleted",
                recipe=f"git show {_short(old.id)}",
            )
            _deletion_body(section, repo, old.id)
        elif delta.status == DeltaStatus.RENAMED and not patch.hunks:
            section = fmt.Section(
                level=level,
                title=f"File {_jpath(old.path)} moved to {_jpath(new.path)}",
            )
        elif delta.status == DeltaStatus.RENAMED:
            section = fmt.Section(
                level=level,
                title=f"File {_jpath(old.path)} modified and moved to {_jpath(new.path)}",
                recipe=f"git diff {_short(old.id)}..{_short(new.id)}",
            )
            _diff_body(section, patch)
        else:
            section = fmt.Section(
                level=level,
                title=f"File {_jpath(new.path)} modified",
                recipe=f"git diff {_short(old.id)}..{_short(new.id)}",
            )
            _diff_body(section, patch)
        sections.append(section)
    return sections


def _blob_lines(repo: pygit2.Repository, oid) -> list[str] | None:
    blob = repo[oid]
    if blob.is_binary:
        return None
    return blob.data.decode("utf-8", errors="replace").splitlines()


def _object_body(section: fmt.Section, repo: pygit2.Repository, oid) -> None:
    lines = _blob_lines(repo, oid)
    if lines is None:
        section.items.append(fmt.Unknown("(binary file — content not quoted)"))
        return
    for number, line in enumerate(lines, start=1):
        section.items.append(fmt.Quote(f"> {number}: {line}"))


def _deletion_body(section: fmt.Section, repo: pygit2.Repository, oid) -> None:
    lines = _blob_lines(repo, oid)
    if lines is None:
        section.items.append(fmt.Unknown("(binary file — content not quoted)"))
        return
    for number, line in enumerate(lines, start=1):
        section.items.append(fmt.Quote(f"> {number}: -{line}"))


def _diff_body(section: fmt.Section, patch: pygit2.Patch) -> None:
    if patch.delta.is_binary:
        section.items.append(fmt.Unknown("(binary file — content not quoted)"))
        return
    for hunk in patch.hunks:
        header = f"@@ -{hunk.old_start},{hunk.old_lines} +{hunk.new_start},{hunk.new_lines} @@"
        section.items.append(fmt.Quote(f"> {header}"))
        for line in hunk.lines:
            text = line.content.rstrip("\n")
            if line.origin == "-":
                section.items.append(fmt.Quote(f"> {line.old_lineno}: -{text}"))
            elif line.origin == "+":
                section.items.append(fmt.Quote(f"> {line.new_lineno}: +{text}"))
            elif line.origin == " ":
                section.items.append(
                    fmt.Quote(f"> {line.old_lineno} {line.new_lineno}: {text}")
                )
            # other origins (\ No newline at end of file, …) are dropped —
            # they carry no reviewable content
