"""The .review (dot-review) file format: model, parser, renderer.

Implements docs/spec/dot-review-format.md, version 0. The parser is strictly
line oriented and lossless: lines it does not recognise are preserved verbatim
and re-emitted in place, so foreign or future content round-trips unchanged.

The model is an ordered tree. A Review holds header key/value pairs and H1
sections; a Section holds an ordered list of items — quoted git content,
reviewer events, meta lines, prose, blanks, unknown lines, and child
sections. Order in the item list is what encodes anchoring: an event after a
quote line anchors to that line, an event before the first quote anchors to
the section.
"""

import re
from dataclasses import dataclass, field

FILE_VERSION_KEY = "dot-review-File-Version"
FILE_VERSION = "0"
INTRO_KEY = "dot-review-Intro"
DOCS_LINK_KEY = "dot-review-Docs-Link"
INTRO_TEXT = (
    "This file uses the .review format — a patch-quoting markdown-ish file "
    "format with a fixed chapter structure. Every heading is a review "
    "section, every `> ` line is verbatim git content, every list item "
    "(`-` or `*`) is a reviewer reaction."
)
DOCS_LINK = "https://cute-devops.patterns.how/apps/gitflower/docs/spec/dot-review-format"

VERDICT_STATES = ("Open", "ClarificationRequired", "RequestedChanges", "Approved", "Denied")

# Range-marker keywords use the `*` bullet; everything else uses `-`.
RANGE_KEYWORDS = ("Read", "Skipped")


class FormatError(Exception):
    pass


@dataclass
class Quote:
    """A `> ` line of verbatim git content, stored raw for byte round-trips."""

    raw: str


@dataclass
class MetaLine:
    """A `- Key: value` line under `# Review` (SPDX, Review-Branch, …)."""

    key: str
    value: str


@dataclass
class Prose:
    """An indented description line (Issue/Remark bodies), stored raw."""

    raw: str


@dataclass
class Blank:
    """An empty line, preserved in place."""


@dataclass
class Unknown:
    """Any line the parser does not recognise, preserved verbatim."""

    raw: str


@dataclass
class Event:
    """A reviewer action: `<bullet> <Keyword>-by: Name <email>[ @ts][; args]`.

    `keyword` is the verb without the `-by` suffix (`Commented`, `Read`, …).
    `body` holds the indented body lines with the body indentation stripped;
    an empty string is a paragraph separator. `children` are nested events
    (answers under questions, reactions under comments).
    """

    keyword: str
    name: str
    email: str
    timestamp: str | None = None
    args: str | None = None
    body: list[str] = field(default_factory=list)
    children: list["Event"] = field(default_factory=list)
    indent: int = 0
    raw_head: str | None = None  # original first line, kept for round-trips

    @property
    def bullet(self) -> str:
        return "*" if self.keyword in RANGE_KEYWORDS else "-"

    def head_line(self) -> str:
        if self.raw_head is not None:
            return self.raw_head
        line = f"{' ' * self.indent}{self.bullet} {self.keyword}-by: {self.name} <{self.email}>"
        if self.timestamp:
            line += f" @{self.timestamp}"
        if self.args is not None:
            line += f"; {self.args}"
        return line


Item = Quote | MetaLine | Prose | Blank | Unknown | Event


@dataclass
class Section:
    """A heading and everything under it, child sections included.

    `title` is the heading text without the leading hashes and without the
    ` @ <recipe>` tail; `recipe` is the literal git command after `@`, if any.
    """

    level: int
    title: str
    recipe: str | None = None
    items: list["Item | Section"] = field(default_factory=list)

    def heading(self) -> str:
        text = f"{'#' * self.level} {self.title}"
        if self.recipe:
            text += f" @ {self.recipe}"
        return text

    def sections(self) -> list["Section"]:
        return [item for item in self.items if isinstance(item, Section)]

    def events(self) -> list[Event]:
        return [item for item in self.items if isinstance(item, Event)]

    def quotes(self) -> list[Quote]:
        return [item for item in self.items if isinstance(item, Quote)]


@dataclass
class Review:
    header: list[tuple[str, str]] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)

    @property
    def review_section(self) -> Section:
        for section in self.sections:
            if section.level == 1 and section.title == "Review":
                return section
        raise FormatError("no # Review section")

    def meta(self, key: str) -> str | None:
        for item in self.review_section.items:
            if isinstance(item, MetaLine) and item.key == key:
                return item.value
        return None

    def all_events(self) -> list[Event]:
        found: list[Event] = []

        def walk(section: Section) -> None:
            for item in section.items:
                if isinstance(item, Event):
                    found.append(item)
                    found.extend(_descendants(item))
                elif isinstance(item, Section):
                    walk(item)

        for section in self.sections:
            walk(section)
        return found


def _descendants(event: Event) -> list[Event]:
    out: list[Event] = []
    for child in event.children:
        out.append(child)
        out.extend(_descendants(child))
    return out


def is_dot_review(text: str) -> bool:
    """Readers probe the exact first-line shape to recognise a .review."""
    return text.startswith(f"{FILE_VERSION_KEY}:")


def default_header() -> list[tuple[str, str]]:
    return [
        (FILE_VERSION_KEY, FILE_VERSION),
        (INTRO_KEY, INTRO_TEXT),
        (DOCS_LINK_KEY, DOCS_LINK),
    ]


# --------------------------------------------------------------- parsing

_HEADER_RE = re.compile(r"^([A-Za-z][A-Za-z0-9-]*): (.*)$")
_HEADING_RE = re.compile(r"^(#{1,3}) (.*)$")
_EVENT_RE = re.compile(r"^( *)([-*]) ([A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*)-by: (.*)$")
_META_RE = re.compile(r"^- ([A-Za-z][A-Za-z0-9_-]*): (.*)$")
_ATTRIBUTION_RE = re.compile(
    r"^(?P<name>[^<]*?) <(?P<email>[^>]*)>(?: @(?P<ts>[^;\s]+))?(?:; (?P<args>.*))?$"
)


def _split_heading(text: str) -> tuple[str, str | None]:
    """Split `<title> @ <recipe>` — the recipe is a literal git command."""
    if " @ " in text:
        title, recipe = text.split(" @ ", 1)
        return title, recipe
    return text, None


def parse(text: str) -> Review:
    """Parse a .review file. Raises FormatError if the version probe fails."""
    if not is_dot_review(text):
        raise FormatError(f"not a .review file: first line must be `{FILE_VERSION_KEY}:`")
    lines = text.splitlines()
    review = Review()

    # Header block: `Key: value` lines terminated by `---` on its own line.
    i = 0
    while i < len(lines):
        line = lines[i]
        if line == "---":
            i += 1
            break
        match = _HEADER_RE.match(line)
        if not match:
            raise FormatError(f"header line {i + 1} is not `Key: value`: {line!r}")
        review.header.append((match.group(1), match.group(2)))
        i += 1
    else:
        raise FormatError("header block never terminated by `---`")

    section_stack: list[Section] = []  # open sections by heading level
    event_stack: list[Event] = []  # open events by indent

    def container_items() -> list:
        if not section_stack:
            raise FormatError("body content before the first section heading")
        return section_stack[-1].items

    body_lines = lines[i:]
    for position, line in enumerate(body_lines):
        heading = _HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            title, recipe = _split_heading(heading.group(2))
            section = Section(level=level, title=title, recipe=recipe)
            while section_stack and section_stack[-1].level >= level:
                section_stack.pop()
            if section_stack:
                section_stack[-1].items.append(section)
            else:
                review.sections.append(section)
            section_stack.append(section)
            event_stack.clear()
            continue

        if line.startswith(">"):
            container_items().append(Quote(raw=line))
            event_stack.clear()
            continue

        event_match = _EVENT_RE.match(line)
        if event_match:
            indent = len(event_match.group(1))
            event = _parse_event(event_match, line)
            while event_stack and event_stack[-1].indent >= indent:
                event_stack.pop()
            if event_stack:
                event_stack[-1].children.append(event)
            else:
                container_items().append(event)
            event_stack.append(event)
            continue

        if not line.strip():
            # Inside an event body a blank is a paragraph separator (encoded
            # with the body indent, but editors strip trailing whitespace, so
            # peek: if the body continues after this line, keep it as a
            # separator either way).
            if event_stack and _body_continues(body_lines, position + 1, event_stack[-1].indent):
                event_stack[-1].body.append("")
            else:
                event_stack.clear()
                container_items().append(Blank())
            continue

        if event_stack:
            body_indent = event_stack[-1].indent + 2
            if line.startswith(" " * body_indent):
                event_stack[-1].body.append(line[body_indent:])
                continue
            event_stack.clear()

        meta = _META_RE.match(line)
        if meta and not meta.group(1).endswith("-by"):
            container_items().append(MetaLine(key=meta.group(1), value=meta.group(2)))
            continue

        if line.startswith(" "):
            container_items().append(Prose(raw=line))
            continue

        container_items().append(Unknown(raw=line))

    # Trailing blank body lines only ever encode the separator before nested
    # events; the renderer re-emits it, so the model doesn't keep it.
    for event in review.all_events():
        while event.body and not event.body[-1].strip():
            event.body.pop()

    return review


def _body_continues(lines: list[str], position: int, event_indent: int) -> bool:
    """Whether the next non-blank line still belongs to the open event's body."""
    for line in lines[position:]:
        if line.strip():
            return line.startswith(" " * (event_indent + 2))
    return False


def _parse_event(match: re.Match, line: str) -> Event:
    indent, _bullet, keyword, rest = match.groups()
    attribution = _ATTRIBUTION_RE.match(rest)
    if not attribution:
        # Unparseable attribution: keep the head verbatim, attribute nobody.
        return Event(keyword=keyword, name=rest, email="", indent=len(indent), raw_head=line)
    return Event(
        keyword=keyword,
        name=attribution.group("name").strip(),
        email=attribution.group("email"),
        timestamp=attribution.group("ts"),
        args=attribution.group("args"),
        indent=len(indent),
        raw_head=line,
    )


# -------------------------------------------------------------- rendering


def render(review: Review) -> str:
    lines: list[str] = []
    for key, value in review.header:
        lines.append(f"{key}: {value}")
    lines.append("---")
    for section in review.sections:
        _render_section(section, lines)
    return "\n".join(lines) + "\n"


def _render_section(section: Section, lines: list[str]) -> None:
    lines.append(section.heading())
    for item in section.items:
        if isinstance(item, Section):
            _render_section(item, lines)
        elif isinstance(item, Event):
            _render_event(item, lines)
        elif isinstance(item, Quote):
            lines.append(item.raw)
        elif isinstance(item, MetaLine):
            lines.append(f"- {item.key}: {item.value}")
        elif isinstance(item, Prose):
            lines.append(item.raw)
        elif isinstance(item, Blank):
            lines.append("")
        else:
            lines.append(item.raw)


def _render_event(event: Event, lines: list[str]) -> None:
    lines.append(event.head_line())
    body_indent = " " * (event.indent + 2)
    for body_line in event.body:
        # A paragraph separator is encoded with the body indent kept (the
        # spec's `  \n  \n` shape), so the indentation level stays consistent.
        lines.append(body_indent + body_line)
    if event.body and event.children:
        # The blank line between a question's body and its nested answer
        # matters — without it the answer would parse as inline prose.
        lines.append(body_indent)
    for child in event.children:
        _render_event(child, lines)


# ------------------------------------------------------- event operations


def set_verdict(review: Review, name: str, email: str, state: str, body: str = "",
                timestamp: str | None = None) -> Event:
    """Set the reviewer's verdict — at most one per (name, email), replace in place."""
    section = review.review_section
    body_lines = body.splitlines() if body else []
    for index, item in enumerate(section.items):
        if isinstance(item, Event) and item.keyword == "Verdict-reached" and item.email == email:
            replacement = Event(
                keyword="Verdict-reached", name=name, email=email,
                timestamp=timestamp, args=state, body=body_lines,
            )
            section.items[index] = replacement
            return replacement
    event = Event(
        keyword="Verdict-reached", name=name, email=email,
        timestamp=timestamp, args=state, body=body_lines,
    )
    _insert_event_after_meta(section, event)
    return event


def verdict_of(review: Review, email: str) -> str:
    for item in review.review_section.items:
        if isinstance(item, Event) and item.keyword == "Verdict-reached" and item.email == email:
            return item.args if item.args in VERDICT_STATES else "Open"
    return "Open"


def add_reaction(parent_items: list, anchor_index: int, name: str, email: str,
                 emoji: str, timestamp: str | None = None) -> Event:
    """React at an anchor — at most one of each emoji per (author, anchor)."""
    insert_at = anchor_index + 1
    while insert_at < len(parent_items):
        item = parent_items[insert_at]
        if isinstance(item, Event):
            if item.keyword == "Reacted" and item.email == email and item.args == emoji:
                item.timestamp = timestamp or item.timestamp
                return item
            insert_at += 1
        else:
            break
    event = Event(keyword="Reacted", name=name, email=email, timestamp=timestamp, args=emoji)
    parent_items.insert(insert_at, event)
    return event


def _insert_event_after_meta(section: Section, event: Event) -> None:
    """Insert under `# Review` after the meta lines and existing verdicts."""
    position = 0
    for index, item in enumerate(section.items):
        if isinstance(item, (MetaLine, Event)):
            position = index + 1
        elif isinstance(item, Section):
            break
    section.items.insert(position, event)
