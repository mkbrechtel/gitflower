"""A live review session: one reviewer editing one .review.

Wraps the parsed Review with everything the TUI (and tests) need that isn't
format: the reviewer's identity, opt-in timestamps, read/skip tracking over
quote lines, event insertion at anchors, and persistence through the notes
ref plus the optional file mirror.

Read state lives in memory as a set of read quote positions per section; on
save it coalesces into `* Read-by: …; begin` / `; end` marker pairs around
contiguous runs, replacing the reviewer's previous markers. Loading
reconstructs the set from the markers, so read state round-trips through the
file without a side channel.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pygit2

from gitflower.review import format as fmt, notes


@dataclass
class Row:
    """One display line of a section subtree, mapped back to the model.

    `container` and `index` locate the underlying item so mutations know
    where to insert; `quote_position` numbers the quote lines of the whole
    subtree consecutively (the unit of read tracking and line anchoring).
    """

    text: str
    kind: str  # "heading" | "quote" | "event" | "body" | "meta" | "prose" | "blank" | "eof"
    container: list | None = None
    index: int = -1
    quote_position: int = -1
    event: fmt.Event | None = None


class Session:
    def __init__(
        self,
        repo: pygit2.Repository,
        review: fmt.Review,
        tip_sha: str,
        notes_ref: str = notes.DEFAULT_REF,
        mirror: Path | None = None,
        with_timestamps: bool = False,
        read_rate: float = 10.0,
    ):
        self.repo = repo
        self.review = review
        self.tip_sha = tip_sha
        self.notes_ref = notes_ref
        self.mirror = mirror
        self.with_timestamps = with_timestamps
        self.read_rate = read_rate
        signature = repo.default_signature
        self.reviewer_name = signature.name
        self.reviewer_email = signature.email
        # read/skip state: section id -> set of read quote positions
        self._read: dict[int, set[int]] = {}
        self._load_read_state()

    # ------------------------------------------------------------ identity

    def timestamp(self) -> str | None:
        if not self.with_timestamps:
            return None
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _event(self, keyword: str, args: str | None = None, body: str = "") -> fmt.Event:
        return fmt.Event(
            keyword=keyword,
            name=self.reviewer_name,
            email=self.reviewer_email,
            timestamp=self.timestamp(),
            args=args,
            body=body.splitlines() if body else [],
        )

    # ------------------------------------------------------- display rows

    def rows(self, section: fmt.Section) -> list[Row]:
        rows: list[Row] = []
        counter = [0]
        self._section_rows(section, rows, counter)
        rows.append(Row(text="── end of section ──", kind="eof", container=section.items))
        return rows

    def _section_rows(self, section: fmt.Section, rows: list[Row], counter: list[int]) -> None:
        rows.append(Row(text=section.heading(), kind="heading", container=section.items))
        for index, item in enumerate(section.items):
            if isinstance(item, fmt.Section):
                self._section_rows(item, rows, counter)
            elif isinstance(item, fmt.Quote):
                rows.append(Row(
                    text=item.raw, kind="quote", container=section.items,
                    index=index, quote_position=counter[0],
                ))
                counter[0] += 1
            elif isinstance(item, fmt.Event):
                self._event_rows(item, rows, section.items, index)
            elif isinstance(item, fmt.MetaLine):
                rows.append(Row(text=f"- {item.key}: {item.value}", kind="meta",
                                container=section.items, index=index))
            elif isinstance(item, fmt.Prose):
                rows.append(Row(text=item.raw, kind="prose",
                                container=section.items, index=index))
            elif isinstance(item, fmt.Blank):
                rows.append(Row(text="", kind="blank", container=section.items, index=index))
            else:
                rows.append(Row(text=item.raw, kind="prose",
                                container=section.items, index=index))

    def _event_rows(self, event: fmt.Event, rows: list[Row],
                    container: list, index: int) -> None:
        rows.append(Row(text=event.head_line(), kind="event",
                        container=container, index=index, event=event))
        indent = " " * (event.indent + 2)
        for line in event.body:
            rows.append(Row(text=indent + line, kind="body",
                            container=container, index=index, event=event))
        for child in event.children:
            self._event_rows(child, rows, container, index)

    # --------------------------------------------------------- mutations

    def add_event(self, section: fmt.Section, row: Row, keyword: str,
                  body: str = "", args: str | None = None) -> fmt.Event:
        """Insert an event anchored at the row's quote line.

        A row past the last quote (the EOF marker) or on a heading inserts at
        the top of the section — the "comment from the bottom" shortcut; on
        disk the result is identical to writing at the top.
        """
        event = self._event(keyword, args=args, body=body)
        if row.kind == "quote":
            row.container.insert(row.index + 1, event)
        else:
            _insert_at_section_top(section, event)
        self._reindex_after_insert(section)
        return event

    def add_reaction(self, section: fmt.Section, row: Row, emoji: str) -> fmt.Event:
        if row.kind == "quote":
            event = fmt.add_reaction(row.container, row.index, self.reviewer_name,
                                     self.reviewer_email, emoji, self.timestamp())
        elif row.kind in ("event", "body") and row.event is not None:
            for existing in row.event.children:
                if (existing.keyword == "Reacted" and existing.email == self.reviewer_email
                        and existing.args == emoji):
                    return existing
            event = self._event("Reacted", args=emoji)
            event.indent = row.event.indent + 2
            row.event.children.append(event)
        else:
            event = self._event("Reacted", args=emoji)
            _insert_at_section_top(section, event)
        self._reindex_after_insert(section)
        return event

    def answer(self, question: fmt.Event, body: str) -> fmt.Event:
        event = self._event("Answer-given", body=body)
        event.indent = question.indent + 2
        question.children.append(event)
        return event

    def delete_event(self, section: fmt.Section, event: fmt.Event) -> bool:
        def scrub(items: list) -> bool:
            for index, item in enumerate(items):
                if item is event:
                    del items[index]
                    return True
                if isinstance(item, fmt.Event) and _remove_child(item, event):
                    return True
                if isinstance(item, fmt.Section) and scrub(item.items):
                    return True
            return False

        return scrub(section.items)

    def add_issue(self, title: str, body: str) -> fmt.Section:
        issue = fmt.Section(level=2, title=f"Issue {title}")
        for line in body.splitlines():
            issue.items.append(fmt.Prose(raw=f" {line}" if line else " "))
        issue.items.append(self._event("Issued"))
        section = self.review.review_section
        section.items.append(fmt.Blank())
        section.items.append(issue)
        return issue

    def cycle_verdict(self, forward: bool = True) -> str:
        states = list(fmt.VERDICT_STATES)
        current = fmt.verdict_of(self.review, self.reviewer_email)
        position = states.index(current) if current in states else 0
        state = states[(position + (1 if forward else -1)) % len(states)]
        fmt.set_verdict(self.review, self.reviewer_name, self.reviewer_email,
                        state, timestamp=self.timestamp())
        return state

    def _reindex_after_insert(self, section: fmt.Section) -> None:
        # Row indexes shift on insertion; callers rebuild rows() afterwards.
        # Read positions are keyed by quote order, which insertion of events
        # never changes, so the read sets stay valid.
        pass

    # ------------------------------------------------------ read tracking

    def is_read(self, section: fmt.Section, quote_position: int) -> bool:
        return quote_position in self._read.setdefault(id(section), set())

    def mark_read(self, section: fmt.Section, quote_position: int) -> None:
        if quote_position >= 0:
            self._read.setdefault(id(section), set()).add(quote_position)

    def mark_unread(self, section: fmt.Section, quote_position: int) -> None:
        self._read.setdefault(id(section), set()).discard(quote_position)

    def _load_read_state(self) -> None:
        for section in self.review.sections:
            reads = self._read.setdefault(id(section), set())
            position = -1
            begin: int | None = None
            skipped_begin: int | None = None

            def walk(items: list) -> None:
                nonlocal position, begin, skipped_begin
                for item in items:
                    if isinstance(item, fmt.Quote):
                        position += 1
                    elif isinstance(item, fmt.Section):
                        walk(item.items)
                    elif isinstance(item, fmt.Event) and item.email == self.reviewer_email:
                        if item.keyword == "Read":
                            if item.args == "begin":
                                begin = position
                            elif item.args == "end" and begin is not None:
                                reads.update(range(begin, position + 1))
                                begin = None

            walk(section.items)

    def _write_read_markers(self) -> None:
        """Replace the reviewer's Read-by markers with the current read runs."""
        for section in self.review.sections:
            reads = self._read.get(id(section), set())
            self._scrub_markers(section)
            if reads:
                self._insert_markers(section, reads)

    def _scrub_markers(self, section: fmt.Section) -> None:
        def scrub(items: list) -> None:
            items[:] = [
                item for item in items
                if not (isinstance(item, fmt.Event) and item.keyword in ("Read", "Skipped")
                        and item.email == self.reviewer_email)
            ]
            for item in items:
                if isinstance(item, fmt.Section):
                    scrub(item.items)

        scrub(section.items)

    def _insert_markers(self, section: fmt.Section, reads: set[int]) -> None:
        position = -1

        def walk(items: list) -> None:
            nonlocal position
            index = 0
            while index < len(items):
                item = items[index]
                if isinstance(item, fmt.Section):
                    walk(item.items)
                elif isinstance(item, fmt.Quote):
                    position += 1
                    markers = []
                    if position in reads and position - 1 not in reads:
                        markers.append(self._event("Read", args="begin"))
                    if position in reads and position + 1 not in reads:
                        markers.append(self._event("Read", args="end"))
                    for offset, marker in enumerate(markers, start=1):
                        items.insert(index + offset, marker)
                    index += len(markers)
                index += 1

        walk(section.items)

    # -------------------------------------------------------- persistence

    def save(self) -> str:
        self._write_read_markers()
        try:
            return notes.save(self.repo, self.review, self.tip_sha,
                              self.notes_ref, self.mirror)
        finally:
            # Markers are regenerated from the in-memory sets on every save;
            # scrub them again so repeated saves don't see stale positions.
            for section in self.review.sections:
                self._scrub_markers(section)


def _insert_at_section_top(section: fmt.Section, event: fmt.Event) -> None:
    position = 0
    for index, item in enumerate(section.items):
        if isinstance(item, (fmt.Quote, fmt.Section)):
            break
        position = index + 1
    section.items.insert(position, event)


def _remove_child(parent: fmt.Event, event: fmt.Event) -> bool:
    for index, child in enumerate(parent.children):
        if child is event:
            del parent.children[index]
            return True
        if _remove_child(child, event):
            return True
    return False
