"""The commit-graph lane layout — ported from cyblox's test suite, plus
gitflower-specific coverage for the interactive-graph metadata."""

from gitflower import graph


def commit(sha: str, *parents: str, subject: str = "work") -> dict:
    return {
        "sha": sha,
        "short": sha[:7],
        "parents": list(parents),
        "author": "tester",
        "date": "2026-01-01T00:00:00+00:00",
        "subject": subject,
    }


def test_a_linear_stretch_folds_into_one_gap_row():
    # a → b → c → d → e → f → g, only `a` has a branch on it
    chain = "abcdefg"
    commits = [commit(x, y) for x, y in zip(chain, chain[1:])] + [commit("g")]
    laid_out = graph.build(commits, tips={"a"})

    kinds = [row["kind"] for row in laid_out["rows"]]
    assert kinds == ["commit", "gap", "commit"]  # a, ⋯5 commits, g
    gap = laid_out["rows"][1]
    assert gap["count"] == 5 and gap["first"]["sha"] == "b" and gap["last"]["sha"] == "f"
    assert laid_out["collapsed"] == 4  # 5 commits shown as 1 row
    assert all(row["lane"] == 0 for row in laid_out["rows"])


def test_short_stretches_and_ref_tips_are_never_folded():
    chain = "abcd"
    commits = [commit(x, y) for x, y in zip(chain, chain[1:])] + [commit("d")]
    assert [row["kind"] for row in graph.build(commits, tips={"a"})["rows"]] == ["commit"] * 4
    # and with collapse off, even a long stretch stays whole
    long_chain = "abcdefg"
    commits = [commit(x, y) for x, y in zip(long_chain, long_chain[1:])] + [commit("g")]
    rows = graph.build(commits, tips={"a"}, collapse=False)["rows"]
    assert [row["kind"] for row in rows] == ["commit"] * 7


def test_a_tip_in_the_middle_breaks_the_run():
    chain = "abcdefghij"
    commits = [commit(x, y) for x, y in zip(chain, chain[1:])] + [commit("j")]
    rows = graph.build(commits, tips={"a", "f"})["rows"]
    # b..e folds; f is a tip and stays; g,h,i is a 3-run below MIN_COLLAPSE
    # (j is a root and never plain), so the tail stays whole
    assert [row["kind"] for row in rows] == ["commit", "gap"] + ["commit"] * 5
    gap = rows[1]
    assert gap["count"] == 4 and gap["first"]["sha"] == "b" and gap["last"]["sha"] == "e"


def test_a_merge_opens_a_lane_that_closes_at_the_merge_base():
    commits = [
        commit("m", "x", "y", subject="merge"),  # merge of the side branch
        commit("x", "base"),  # trunk side
        commit("y", "base"),  # side branch
        commit("base"),
    ]
    laid_out = graph.build(commits, tips={"m"})
    rows = laid_out["rows"]
    assert [row["lane"] for row in rows] == [0, 0, 1, 0]
    # every parent link is drawn, plus nothing dangling
    assert len(laid_out["edges"]) == 4
    assert not any(edge["stub"] for edge in laid_out["edges"])


def test_merge_extra_parent_leaves_its_lane_before_the_first_parent_line():
    """A merge's second parent that points at an *older* commit down-and-left
    must bend out of the merge's lane at once. The first parent keeps that lane
    going down, so a second-parent edge that lingered in it would draw straight
    over the first-parent line and through whatever commit sits on it."""
    commits = [
        commit("a", "b", "f"),  # trunk merge, opens lane 1 for f
        commit("f", "fp", "b"),  # merge on lane 1; 2nd parent b is old (lane 0)
        commit("fp", "b"),  # feature commit sitting in lane 1, points at b
        commit("b"),  # the shared, older base on lane 0
    ]
    laid_out = graph.build(commits, tips={"a"})
    at = {row["id"]: row for row in laid_out["rows"]}
    assert at["f"]["lane"] == 1 and at["fp"]["lane"] == 1  # both in the merge lane

    fx, fy = at["f"]["x"], at["f"]["y"]
    down_the_lane = f"M {fx},{fy} V"  # the first-parent shape: straight down
    from_f = [e for e in laid_out["edges"] if e["d"].startswith(f"M {fx},{fy}")]
    # f -> fp (first parent) runs straight down the lane...
    assert any(e["d"].startswith(down_the_lane) for e in from_f)
    # ...but f -> b (the extra parent) must curve away immediately, not trace it
    assert sum(e["d"].startswith(down_the_lane) for e in from_f) == 1
    assert any(e["d"].startswith(f"M {fx},{fy} C") for e in from_f)


def test_history_cut_off_by_the_limit_gets_a_dashed_stub():
    commits = [commit("a", "b")]  # b was never fetched
    laid_out = graph.build(commits, tips={"a"})
    (edge,) = laid_out["edges"]
    assert edge["stub"]


def test_two_roots_two_lanes():
    # two independent branches, never merged
    commits = [commit("a", "b"), commit("c", "d"), commit("b"), commit("d")]
    rows = graph.build(commits, tips={"a", "c"})["rows"]
    assert [row["lane"] for row in rows] == [0, 1, 0, 1]


def test_coordinates_and_dimensions():
    commits = [commit("a", "b"), commit("b")]
    laid_out = graph.build(commits, tips={"a"})
    first, second = laid_out["rows"]
    assert (first["x"], first["y"]) == (graph.PAD, graph.ROW / 2)
    assert (second["x"], second["y"]) == (graph.PAD, graph.ROW / 2 + graph.ROW)
    assert laid_out["height"] == 2 * graph.ROW
    assert laid_out["width"] == 2 * graph.PAD
    assert laid_out["row_height"] == graph.ROW


def test_lane_colors_cycle():
    assert graph._color(0) == graph.COLORS[0]
    assert graph._color(len(graph.COLORS)) == graph.COLORS[0]
    assert graph._color(len(graph.COLORS) + 2) == graph.COLORS[2]


def test_edges_carry_their_lanes_for_hover_highlighting():
    """The interactive graph highlights a lane's path on hover — every edge
    names the lanes it belongs to."""
    commits = [
        commit("m", "x", "y", subject="merge"),
        commit("x", "base"),
        commit("y", "base"),
        commit("base"),
    ]
    edges = graph.build(commits, tips={"m"})["edges"]
    lanes = [edge["lanes"] for edge in edges]
    assert [0] in lanes  # trunk straight-down links
    assert [0, 1] in lanes  # the merge link crossing lanes


def test_empty_history():
    laid_out = graph.build([], tips=set())
    assert laid_out["rows"] == [] and laid_out["edges"] == []
    assert laid_out["height"] == 0 and laid_out["collapsed"] == 0
