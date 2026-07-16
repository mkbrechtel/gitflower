"""Row alignment for the merge-commit side-by-side view.

Pure geometry over diff data (like graph.py): the result file's lines plus
each parent's 0-context diff against the result come in; aligned multi-column
rows come out. No git, no I/O.

Every row carries one cell per parent plus the result line. The result column
is plain content — it is not a diff, it *is* the result. Parent cells encode
how that parent relates to each result line:

    same     the parent has this exact line
    changed  the parent has its own version (the cell carries that text)
    absent   the parent has no counterpart
    removed  (in `only` rows) a parent line the result dropped

A row is `merge_authored` when the result matches NO parent — a line the
merger inserted or hand-resolved, or a removal of a line every parent had.
Those are exactly the decisions invisible in any single-parent diff.
"""

from collections import deque
from difflib import SequenceMatcher

MIN_FOLD = 10  # all-same runs longer than this fold away…
CONTEXT = 3  # …keeping this many rows visible on each side
MAX_ROWS = 4000  # a file rendering more rows than this is truncated
PAIR_RATIO = 0.5  # minimum similarity for a '-' line to pair with a '+'


def _cell(status: str, no: int | None = None, text: str | None = None) -> dict:
    return {"status": status, "no": no, "text": text}


def _parent_changes(hunks: list[dict]) -> tuple[dict, set, dict]:
    """Digest one parent's 0-context hunks against the result.

    Returns (changed, absent, removals):
      changed: result lineno -> (parent lineno, parent text)
      absent: result linenos with no counterpart in this parent
      removals: anchor lineno -> deque of {"old", "text"} parent-only lines
                (anchor = the result line they sit in front of)

    Within a hunk each '-' pairs with its most-similar unpaired '+'
    (a changed line). Positional pairing would misattribute — e.g.
    `-timeout=10` would pair with an unrelated insertion that happens to
    come first instead of with `+timeout=30`.
    """
    changed: dict[int, tuple[int, str]] = {}
    absent: set[int] = set()
    removals: dict[int, deque] = {}
    for hunk in hunks:
        minus = [line for line in hunk["lines"] if line["origin"] == "-"]
        plus = [line for line in hunk["lines"] if line["origin"] == "+"]
        taken: set[int] = set()
        anchor = hunk["new_start"] if hunk["new_lines"] > 0 else hunk["new_start"] + 1
        for m in minus:
            best, best_ratio = None, PAIR_RATIO
            for i, p in enumerate(plus):
                if i in taken:
                    continue
                ratio = SequenceMatcher(None, m["text"], p["text"]).ratio()
                if ratio > best_ratio:
                    best, best_ratio = i, ratio
            if best is None:
                removals.setdefault(anchor, deque()).append(
                    {"old": m["old"], "text": m["text"]}
                )
            else:
                taken.add(best)
                changed[plus[best]["new"]] = (m["old"], m["text"])
        for i, p in enumerate(plus):
            if i not in taken:
                absent.add(p["new"])
    return changed, absent, removals


def _removal_rows(queues: list[deque], n: int, counters: list[int]) -> list[dict]:
    """Drain parent-only lines anchored at one position into `only` rows.

    Identical texts across parents collapse into ONE row — a line the merge
    itself removed when every parent had it. Leftovers stay per-parent."""
    rows = []
    while any(queues):
        lead = next(q[0]["text"] for q in queues if q)
        group = [i for i in range(n) if queues[i] and queues[i][0]["text"] == lead]
        cells = []
        for i in range(n):
            if i in group:
                record = queues[i].popleft()
                cells.append(_cell("removed", record["old"], record["text"]))
                counters[i] = record["old"] + 1
            else:
                cells.append(_cell("absent"))
        rows.append(
            {
                "kind": "only",
                "cells": cells,
                "result_no": None,
                "result_text": None,
                "merge_authored": len(group) == n,
            }
        )
    return rows


def _fold(rows: list[dict]) -> list[dict]:
    """Collapse long runs of all-same rows into fold markers, keeping
    CONTEXT rows on each side (the graph's gap-row pattern)."""

    def plain(row: dict) -> bool:
        return row["kind"] == "line" and all(c["status"] == "same" for c in row["cells"])

    out = []
    i = 0
    while i < len(rows):
        if not plain(rows[i]):
            out.append(rows[i])
            i += 1
            continue
        end = i
        while end + 1 < len(rows) and plain(rows[end + 1]):
            end += 1
        run = rows[i : end + 1]
        if len(run) > MIN_FOLD:
            folded = run[CONTEXT : len(run) - CONTEXT]
            out.extend(run[:CONTEXT])
            out.append(
                {
                    "kind": "fold",
                    "cells": [],
                    "result_no": None,
                    "result_text": None,
                    "merge_authored": False,
                    "count": len(folded),
                    "start": folded[0]["result_no"],
                    "end": folded[-1]["result_no"],
                }
            )
            out.extend(run[len(run) - CONTEXT :])
        else:
            out.extend(run)
        i = end + 1
    return out


def build(result_lines: list[str], parent_hunks: list[list[dict]], full: bool = False) -> dict:
    """Lay out one file of a merge. `result_lines` is the merged content;
    `parent_hunks` carries, per parent, the 0-context hunks of the diff
    parent → result (each hunk: {"new_start", "new_lines", "lines": [{
    "origin": "+"|"-", "old": int, "new": int, "text": str}]}). A parent the
    file is unchanged against contributes an empty hunk list."""
    n = len(parent_hunks)
    digested = [_parent_changes(h) for h in parent_hunks]
    counters = [1] * n  # each parent's own next line number

    rows: list[dict] = []
    for lineno in range(1, len(result_lines) + 2):
        queues = [digested[i][2].get(lineno, deque()) for i in range(n)]
        rows.extend(_removal_rows(queues, n, counters))
        if lineno > len(result_lines):
            break
        cells = []
        matches_a_parent = False
        for i in range(n):
            changed, absent, _removals = digested[i]
            if lineno in changed:
                old_no, old_text = changed[lineno]
                cells.append(_cell("changed", old_no, old_text))
                counters[i] = old_no + 1
            elif lineno in absent:
                cells.append(_cell("absent"))
            else:
                cells.append(_cell("same", counters[i]))
                counters[i] += 1
                matches_a_parent = True
        rows.append(
            {
                "kind": "line",
                "cells": cells,
                "result_no": lineno,
                "result_text": result_lines[lineno - 1],
                "merge_authored": not matches_a_parent,
            }
        )

    if not full:
        rows = _fold(rows)
    if len(rows) > MAX_ROWS:
        return {"rows": [], "truncated": True}
    return {"rows": rows, "truncated": False}
