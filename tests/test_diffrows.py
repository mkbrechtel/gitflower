"""The side-by-side row alignment — one test per taxonomy variant.

Hunks are written by hand in the 0-context shape gitread._patch_hunks emits,
so every case is exact and independent of git."""

from gitflower import diffrows


def hunk(new_start: int, new_lines: int, *lines: tuple) -> dict:
    return {
        "new_start": new_start,
        "new_lines": new_lines,
        "lines": [{"origin": o, "old": old, "new": new, "text": t} for o, old, new, t in lines],
    }


def statuses(row: dict) -> list[str]:
    return [c["status"] for c in row["cells"]]


# The worked example from the plan: parent 1 has a timeout tweak and
# old_helper; parent 2 has the logging work; the merge hand-resolves
# timeout=30, inserts retry, and drops a TODO comment both parents had.
RESULT = [
    "import os",
    "import logging",
    "",
    "def fetch(url):",
    "    logging.debug(url)",
    "    retry = True",
    "    r = get(url, timeout=30)",
    "    return r",
]
# 0-context hunks exactly as git emits them: unchanged lines never appear,
# and a pure deletion's new_start is the result line BEFORE the gap.
P1_HUNKS = [
    hunk(2, 1, ("+", -1, 2, "import logging")),
    hunk(3, 0, ("-", 3, -1, "# TODO drop this")),
    hunk(5, 3,
         ("-", 5, -1, "    r = get(url, timeout=10)"),
         ("+", -1, 5, "    logging.debug(url)"),
         ("+", -1, 6, "    retry = True"),
         ("+", -1, 7, "    r = get(url, timeout=30)")),
    hunk(8, 0,
         ("-", 7, -1, ""),
         ("-", 8, -1, "def old_helper():"),
         ("-", 9, -1, "    return legacy()")),
]
P2_HUNKS = [
    hunk(3, 0, ("-", 4, -1, "# TODO drop this")),
    hunk(6, 2,
         ("-", 7, -1, "    r = get(url, timeout=60)"),
         ("+", -1, 6, "    retry = True"),
         ("+", -1, 7, "    r = get(url, timeout=30)")),
]


def build_example(full: bool = False) -> list[dict]:
    return diffrows.build(RESULT, [P1_HUNKS, P2_HUNKS], full=full)["rows"]


def test_every_input_line_appears_exactly_once_per_column():
    rows = build_example()
    for col, expected in ((0, list(range(1, 10))), (1, list(range(1, 9)))):
        nos = [r["cells"][col]["no"] for r in rows if r["cells"] and r["cells"][col]["no"]]
        assert nos == expected
    assert [r["result_no"] for r in rows if r["kind"] == "line"] == list(range(1, 9))


def test_taken_from_one_side_is_not_merge_authored():
    rows = build_example()
    logging_row = next(r for r in rows if r["result_text"] == "import logging")
    assert statuses(logging_row) == ["absent", "same"]  # came from parent 2
    assert not logging_row["merge_authored"]


def test_merge_added_line_matches_no_parent():
    rows = build_example()
    retry = next(r for r in rows if r["result_text"] == "    retry = True")
    assert statuses(retry) == ["absent", "absent"]
    assert retry["merge_authored"]


def test_merge_modified_line_carries_both_parents_text():
    rows = build_example()
    resolved = next(r for r in rows if r["result_text"] == "    r = get(url, timeout=30)")
    assert statuses(resolved) == ["changed", "changed"]
    assert resolved["cells"][0]["text"] == "    r = get(url, timeout=10)"
    assert resolved["cells"][1]["text"] == "    r = get(url, timeout=60)"
    assert resolved["merge_authored"]


def test_identical_removal_in_all_parents_collapses_to_one_row():
    rows = build_example()
    todo = [r for r in rows if r["kind"] == "only" and "TODO" in (r["cells"][0]["text"] or "")]
    assert len(todo) == 1
    assert statuses(todo[0]) == ["removed", "removed"]
    assert todo[0]["cells"][0]["no"] == 3 and todo[0]["cells"][1]["no"] == 4
    assert todo[0]["merge_authored"]
    # …and it sits before the `def fetch` result line
    assert rows.index(todo[0]) < rows.index(
        next(r for r in rows if r["result_text"] == "def fetch(url):")
    )


def test_one_sided_removal_stays_per_parent():
    rows = build_example()
    helper = next(r for r in rows if r["kind"] == "only" and "old_helper" in (r["cells"][0]["text"] or ""))
    assert statuses(helper) == ["removed", "absent"]
    assert not helper["merge_authored"]  # parent 2 never had it: p2's side was taken


def test_similarity_pairing_beats_positional():
    """p1's -timeout=10 must pair with +timeout=30, not with the unrelated
    +logging.debug insertion that comes first in the hunk."""
    rows = build_example()
    debug_row = next(r for r in rows if r["result_text"] == "    logging.debug(url)")
    assert statuses(debug_row) == ["absent", "same"]  # NOT "changed"


def test_unchanged_parent_contributes_all_same_cells():
    rows = diffrows.build(["a", "b"], [[], [hunk(1, 1, ("+", -1, 1, "a"))]])["rows"]
    assert statuses(rows[0]) == ["same", "absent"]
    assert statuses(rows[1]) == ["same", "same"]


def test_file_deleted_by_the_merge_is_all_only_rows():
    hunks = [hunk(0, 0, ("-", 1, -1, "gone"), ("-", 2, -1, "lines"))]
    rows = diffrows.build([], [hunks, hunks])["rows"]
    assert [r["kind"] for r in rows] == ["only", "only"]
    assert all(r["merge_authored"] for r in rows)


def test_long_same_runs_fold_with_context():
    lines = [f"line {i}" for i in range(1, 31)]
    rows = diffrows.build(lines, [[], []])["rows"]
    kinds = [r["kind"] for r in rows]
    assert kinds == ["line"] * 3 + ["fold"] + ["line"] * 3
    fold = rows[3]
    assert (fold["count"], fold["start"], fold["end"]) == (24, 4, 27)


def test_short_runs_and_full_do_not_fold():
    lines = [f"line {i}" for i in range(1, 11)]  # exactly MIN_FOLD: stays whole
    assert all(r["kind"] == "line" for r in diffrows.build(lines, [[], []])["rows"])
    long_lines = [f"line {i}" for i in range(1, 31)]
    full = diffrows.build(long_lines, [[], []], full=True)["rows"]
    assert len(full) == 30 and all(r["kind"] == "line" for r in full)


def test_changed_rows_break_a_fold():
    lines = [f"line {i}" for i in range(1, 31)]
    hunks = [hunk(15, 1, ("-", 15, -1, "old 15"), ("+", -1, 15, "line 15"))]
    rows = diffrows.build(lines, [hunks, []])["rows"]
    changed = next(r for r in rows if r["result_no"] == 15)
    assert statuses(changed) == ["changed", "same"]
    assert sum(1 for r in rows if r["kind"] == "fold") == 2  # folds on both sides


def test_oversized_files_truncate():
    lines = [f"line {i}" for i in range(diffrows.MAX_ROWS + 2)]
    laid_out = diffrows.build(lines, [[], []], full=True)
    assert laid_out["truncated"] and laid_out["rows"] == []
