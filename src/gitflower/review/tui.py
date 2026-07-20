"""The review TUI (Textual).

Two modes, as in the spec: tree mode (sidebar focused, one section selected,
content peeking in the main pane) and diff/file mode (cursor locked to one
line in the main pane; events anchor to it). The on-disk .review is the
source of truth — every mutation goes through the Session and is written
back debounced at two seconds, plus an immediate write on explicit save and
a force-flush on quit.
"""

import re

from rich.segment import Segment
from rich.style import Style
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.geometry import Size
from textual.screen import ModalScreen
from textual.scroll_view import ScrollView
from textual.strip import Strip
from textual.widgets import Footer, Input, Label, TextArea, Tree

from gitflower.review import format as fmt
from gitflower.review.session import Row, Session

AUTOSAVE_SECONDS = 2.0

_QUOTE_SIGN_RE = re.compile(r"^> (?:\d+ )?(?:\d+: )?(.?)")


class EventEditor(ModalScreen[str | None]):
    """Multi-line body editor for comments, questions, answers, verdicts."""

    BINDINGS = [
        Binding("ctrl+s", "submit", "submit"),
        Binding("escape", "cancel", "cancel"),
    ]

    def __init__(self, title: str, text: str = "") -> None:
        super().__init__()
        self._title = title
        self._text = text

    def compose(self) -> ComposeResult:
        with Vertical(id="editor"):
            yield Label(self._title)
            yield TextArea(self._text, id="body")
            yield Label("ctrl+s submit · esc cancel", id="hint")

    def on_mount(self) -> None:
        self.query_one("#body", TextArea).focus()

    def action_submit(self) -> None:
        self.dismiss(self.query_one("#body", TextArea).text)

    def action_cancel(self) -> None:
        self.dismiss(None)


class IssueEditor(ModalScreen[tuple[str, str] | None]):
    """Title field plus body area; Tab switches focus between them."""

    BINDINGS = [
        Binding("ctrl+s", "submit", "submit"),
        Binding("escape", "cancel", "cancel"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="editor"):
            yield Label("New issue")
            yield Input(placeholder="title", id="title")
            yield TextArea(id="body")
            yield Label("ctrl+s submit · esc cancel · tab switch", id="hint")

    def on_mount(self) -> None:
        self.query_one("#title", Input).focus()

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        self.query_one("#body", TextArea).focus()

    def action_submit(self) -> None:
        title = self.query_one("#title", Input).value.strip()
        if not title:
            self.query_one("#title", Input).focus()
            return
        self.dismiss((title, self.query_one("#body", TextArea).text))

    def action_cancel(self) -> None:
        self.dismiss(None)


class SectionPane(ScrollView, can_focus=True):
    """Line-cursor view over one section subtree's display rows."""

    BINDINGS = [
        Binding("j,down", "cursor(1)", "line", show=False),
        Binding("k,up", "cursor(-1)", "line"),
        Binding("space", "walk", "walk"),
        Binding("c,enter", "comment", "comment"),
        Binding("exclamation_mark,question_mark", "question", "question"),
        Binding("a,g", "react('👍')", "like", show=False),
        Binding("b", "react('👎')", "dislike", show=False),
        Binding("u", "unread", "unread", show=False),
        Binding("n", "next_event(1)", "next event", show=False),
        Binding("N", "next_event(-1)", "prev event", show=False),
        Binding("d", "delete_event", "delete", show=False),
        Binding("h,left", "to_tree", "tree"),
    ]

    def __init__(self, session: Session) -> None:
        super().__init__()
        self.session = session
        self.section: fmt.Section | None = None
        self.rows: list[Row] = []
        self.cursor = 0
        self._walk_timer = None
        self._dwell_generation = 0

    # ------------------------------------------------------------- content

    def show_section(self, section: fmt.Section) -> None:
        self.stop_walk()
        self.section = section
        self.reload(cursor=0)
        self.scroll_to(y=0, animate=False)
        self._schedule_dwell()

    def reload(self, cursor: int | None = None) -> None:
        if self.section is None:
            return
        self.rows = self.session.rows(self.section)
        if cursor is not None:
            self.cursor = cursor
        self.cursor = max(0, min(self.cursor, len(self.rows) - 1))
        width = max((len(row.text) for row in self.rows), default=0)
        self.virtual_size = Size(width, len(self.rows))
        self.refresh()

    def render_line(self, y: int) -> Strip:
        scroll_x, scroll_y = self.scroll_offset
        index = y + scroll_y
        if index >= len(self.rows):
            return Strip.blank(self.size.width)
        row = self.rows[index]
        style = self._row_style(row)
        if index == self.cursor and self.has_focus:
            style += Style(reverse=True)
        text = row.text.ljust(self.size.width + scroll_x)
        strip = Strip([Segment(text, style)])
        return strip.crop(scroll_x, scroll_x + self.size.width)

    def _row_style(self, row: Row) -> Style:
        if row.kind == "heading":
            return Style(bold=True, color="cyan")
        if row.kind == "quote":
            read = self.session.is_read(self._quote_section(row), row.quote_position)
            sign = _QUOTE_SIGN_RE.match(row.text)
            color = None
            if row.text.startswith("> @@"):
                color = "cyan"
            elif sign and sign.group(1) == "+":
                color = "green"
            elif sign and sign.group(1) == "-":
                color = "red"
            return Style(color=color, dim=read, bold=not read)
        if row.kind == "event":
            marker = row.event is not None and row.event.keyword in fmt.RANGE_KEYWORDS
            return Style(color="magenta" if marker else "yellow", dim=marker)
        if row.kind == "body":
            return Style(color="yellow", dim=True)
        if row.kind == "meta":
            return Style(color="blue")
        if row.kind == "eof":
            return Style(dim=True, italic=True)
        return Style(dim=True)

    def _quote_section(self, _row: Row) -> fmt.Section:
        # Read positions are numbered over the whole displayed subtree, and
        # the session keys them by the root section shown here.
        assert self.section is not None
        return self.section

    # -------------------------------------------------------------- cursor

    def action_cursor(self, delta: int) -> None:
        self.move_cursor(self.cursor + delta)

    def move_cursor(self, index: int) -> None:
        if not self.rows:
            return
        self.cursor = max(0, min(index, len(self.rows) - 1))
        self.scroll_to_region_visible()
        self._schedule_dwell()
        self.refresh()

    def scroll_to_region_visible(self) -> None:
        top = self.scroll_offset.y
        height = self.size.height
        if self.cursor < top:
            self.scroll_to(y=self.cursor, animate=False)
        elif self.cursor >= top + height:
            self.scroll_to(y=self.cursor - height + 1, animate=False)

    def current_row(self) -> Row | None:
        if 0 <= self.cursor < len(self.rows):
            return self.rows[self.cursor]
        return None

    def action_next_event(self, direction: int) -> None:
        indices = [i for i, row in enumerate(self.rows) if row.kind == "event"]
        if not indices:
            return
        if direction > 0:
            following = [i for i in indices if i > self.cursor]
            self.move_cursor(following[0] if following else indices[0])
        else:
            preceding = [i for i in indices if i < self.cursor]
            self.move_cursor(preceding[-1] if preceding else indices[-1])

    # ------------------------------------------------------- read tracking

    def _mark_row_read(self, row: Row) -> None:
        if row.kind == "quote" and self.section is not None:
            self.session.mark_read(self.section, row.quote_position)

    def action_walk(self) -> None:
        """Auto-advance at read-rate lines/second, marking traversed lines read."""
        if self._walk_timer is not None:
            self.stop_walk()
            return
        rate = max(self.session.read_rate, 0.1)
        self._walk_timer = self.set_interval(1.0 / rate, self._walk_step)

    def _walk_step(self) -> None:
        row = self.current_row()
        if row is not None:
            self._mark_row_read(row)
        if self.cursor >= len(self.rows) - 1:
            self.stop_walk()
            return
        self.move_cursor(self.cursor + 1)

    def stop_walk(self) -> None:
        if self._walk_timer is not None:
            self._walk_timer.stop()
            self._walk_timer = None

    def _schedule_dwell(self) -> None:
        """Lines visible without scroll for visible/read-rate seconds flip read."""
        if self.section is None:
            return
        self._dwell_generation += 1
        generation = self._dwell_generation
        top, height = self.scroll_offset.y, max(self.size.height, 1)
        visible = self.rows[top:top + height]
        unread = [
            row for row in visible
            if row.kind == "quote"
            and not self.session.is_read(self.section, row.quote_position)
        ]
        if not unread:
            return
        delay = max(len(visible) / max(self.session.read_rate, 0.1), 0.001)

        def flip() -> None:
            if generation != self._dwell_generation or self.section is None:
                return
            for row in unread:
                self.session.mark_read(self.section, row.quote_position)
            self.app.mark_dirty()
            self.refresh()

        self.set_timer(delay, flip)

    def action_unread(self) -> None:
        row = self.current_row()
        if row is not None and row.kind == "quote" and self.section is not None:
            self.session.mark_unread(self.section, row.quote_position)
            self._schedule_dwell()
            self.app.mark_dirty()
            self.refresh()

    # ------------------------------------------------------------- events

    def action_comment(self) -> None:
        row = self.current_row()
        if row is None or self.section is None:
            return
        if row.event is not None and row.event.keyword == "Question-asked":
            question = row.event

            def submit_answer(text: str | None) -> None:
                if text:
                    self.session.answer(question, text)
                    self.app.mark_dirty()
                    self.reload()

            self.app.push_screen(EventEditor("Answer"), submit_answer)
            return

        def submit(text: str | None) -> None:
            if text:
                self.session.add_event(self.section, row, "Commented", body=text)
                self.app.mark_dirty()
                self.reload()

        self.app.push_screen(EventEditor("Comment"), submit)

    def action_question(self) -> None:
        row = self.current_row()
        if row is None or self.section is None:
            return

        def submit(text: str | None) -> None:
            if text:
                self.session.add_event(self.section, row, "Question-asked", body=text)
                self.app.mark_dirty()
                self.reload()

        self.app.push_screen(EventEditor("Question"), submit)

    def action_react(self, emoji: str) -> None:
        row = self.current_row()
        if row is None or self.section is None:
            return
        self.session.add_reaction(self.section, row, emoji)
        self.app.mark_dirty()
        self.reload()

    def action_delete_event(self) -> None:
        row = self.current_row()
        if row is None or row.event is None or self.section is None:
            return
        if self.session.delete_event(self.section, row.event):
            self.app.mark_dirty()
            self.reload(cursor=self.cursor - 1)

    def action_to_tree(self) -> None:
        self.stop_walk()
        self.app.query_one(Tree).focus()

    def watch_scroll_y(self, old_value: float, new_value: float) -> None:
        super().watch_scroll_y(old_value, new_value)
        self._schedule_dwell()


class ReviewApp(App):
    """gitflower review — read, comment, and reach a verdict."""

    CSS = """
    #sidebar { width: 34; border-right: solid $primary; }
    SectionPane { width: 1fr; }
    #editor { border: round $primary; background: $surface; padding: 1;
              width: 80%; height: auto; max-height: 80%; }
    #editor TextArea { height: 12; }
    #hint { color: $text-muted; }
    IssueEditor, EventEditor { align: center middle; }
    """

    BINDINGS = [
        Binding("q", "quit_flush", "quit"),
        Binding("s", "save_now", "save"),
        Binding("greater_than_sign", "verdict(1)", "verdict"),
        Binding("less_than_sign", "verdict(-1)", "verdict", show=False),
        Binding("V", "verdict_editor", "verdict text", show=False),
        Binding("i", "new_issue", "issue"),
    ]

    def __init__(self, review_session: Session) -> None:
        super().__init__()
        self.session = review_session
        self._dirty = False
        self._save_scheduled = False

    # -------------------------------------------------------------- layout

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Tree("Review", id="sidebar")
            yield SectionPane(self.session)
        yield Footer()

    def on_mount(self) -> None:
        self.rebuild_tree()
        self.refresh_title()
        self.query_one(Tree).focus()

    def rebuild_tree(self) -> None:
        tree = self.query_one(Tree)
        tree.clear()
        tree.root.expand()
        review = self.session.review
        review_section = review.review_section

        tree.root.add_leaf("Sources", data=review_section)
        tree.root.add_leaf("Verdicts", data=review_section)

        issues = tree.root.add("General Issues", data=review_section, expand=True)
        for subsection in review_section.sections():
            if subsection.title.startswith("Issue "):
                resolved = any(
                    event.keyword == "Resolved" for event in subsection.events()
                )
                label = subsection.title[len("Issue "):]
                issues.add_leaf(("✓ " if resolved else "") + label, data=subsection)

        for section in review.sections:
            if section.title.startswith("Diff "):
                changes = tree.root.add(section.title, data=section, expand=True)
                for subsection in section.sections():
                    if subsection.title.startswith("File "):
                        changes.add_leaf(_file_label(subsection), data=subsection)
        commits = [
            section for section in review.sections
            if section.title.startswith(("Commit ", "Merge-Commit "))
        ]
        if commits:
            node = tree.root.add("Commits", expand=True)
            for section in commits:
                node.add_leaf(section.title, data=section)

    def refresh_title(self) -> None:
        verdict = fmt.verdict_of(self.session.review, self.session.reviewer_email)
        branch = self.session.review.meta("Review-Branch") or "?"
        self.title = f"gitflower review — {branch}"
        self.sub_title = f"verdict: {verdict}" + ("  [+]" if self._dirty else "")

    # ---------------------------------------------------------- navigation

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        section = event.node.data
        if isinstance(section, fmt.Section):
            pane = self.query_one(SectionPane)
            pane.show_section(section)
            pane.focus()

    # ------------------------------------------------------------- actions

    def action_verdict(self, direction: int) -> None:
        self.session.cycle_verdict(forward=direction > 0)
        self.mark_dirty()
        self.query_one(SectionPane).reload()

    def action_verdict_editor(self) -> None:
        current = fmt.verdict_of(self.session.review, self.session.reviewer_email)

        def submit(text: str | None) -> None:
            if text is not None:
                fmt.set_verdict(
                    self.session.review, self.session.reviewer_name,
                    self.session.reviewer_email, current, body=text,
                    timestamp=self.session.timestamp(),
                )
                self.mark_dirty()
                self.query_one(SectionPane).reload()

        self.push_screen(EventEditor(f"Verdict summary ({current})"), submit)

    def action_new_issue(self) -> None:
        def submit(result: tuple[str, str] | None) -> None:
            if result is not None:
                title, body = result
                self.session.add_issue(title, body)
                self.mark_dirty()
                self.rebuild_tree()

        self.push_screen(IssueEditor(), submit)

    # -------------------------------------------------------------- saving

    def mark_dirty(self) -> None:
        self._dirty = True
        self.refresh_title()
        if not self._save_scheduled:
            self._save_scheduled = True
            self.set_timer(AUTOSAVE_SECONDS, self._autosave)

    def _autosave(self) -> None:
        self._save_scheduled = False
        if self._dirty:
            self._do_save()

    def _do_save(self) -> None:
        self.session.save()
        self._dirty = False
        self.refresh_title()

    def action_save_now(self) -> None:
        self._do_save()

    def action_quit_flush(self) -> None:
        if self._dirty:
            self._do_save()
        self.exit()


def _file_label(section: fmt.Section) -> str:
    """Sidebar label for a `## File "<path>" <lifecycle>` subsection."""
    match = re.match(r'^File ("(?:[^"\\]|\\.)*")(.*)$', section.title)
    if not match:
        return section.title
    import json

    path = json.loads(match.group(1))
    lifecycle = match.group(2).strip()
    marker = {"created": "+", "deleted": "-"}.get(lifecycle.split(" ")[0], "±")
    return f"{marker} {path}"
