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


def _verticals(d: str) -> list[tuple[float, float, float]]:
    """(x, y_top, y_bottom) of every straight vertical run in an edge path."""
    tokens = d.replace(",", " ").split()
    out, x, y, i = [], 0.0, 0.0, 0
    while i < len(tokens):
        if tokens[i] == "M":
            x, y = float(tokens[i + 1]), float(tokens[i + 2])
            i += 3
        elif tokens[i] == "C":
            x, y = float(tokens[i + 5]), float(tokens[i + 6])
            i += 7
        elif tokens[i] == "V":
            y2 = float(tokens[i + 1])
            out.append((x, min(y, y2), max(y, y2)))
            y = y2
            i += 2
        else:
            i += 1
    return out


def assert_no_dot_pierced(laid_out: dict) -> None:
    """No edge's vertical stretch may run through a commit it does not
    terminate at — a line must reach its parent's dot, not cross others."""
    dots = [(row["x"], row["y"]) for row in laid_out["rows"]]
    for edge in laid_out["edges"]:
        for x, top, bottom in _verticals(edge["d"]):
            for dx, dy in dots:
                assert not (dx == x and top < dy < bottom), (edge["d"], dx, dy)


def test_link_to_a_shared_ancestor_rides_a_corridor_beside_the_lineage():
    """The cute-devops mail-stack shape: two merges share the ancestor `p`
    through different parents — `m1`'s parent `c1` descends to `p`, while
    `m2` points at `p` directly. The direct link must not ride the c-lineage
    lane (through c1's and c2's dots); it gets a corridor inserted beside
    the merge, and — being the leftmost lane waiting for `p` — the corridor
    receives p's dot, so the link is the straight line into it."""
    commits = [
        commit("m1", "m2", "c1"),  # top merge (7335d3b)
        commit("m2", "t", "p"),  # merge pointing at the old ancestor (1b05b47)
        commit("c1", "c2"),  # the other parent's lineage… (6cda0af)
        commit("c2", "p"),  # …which also descends to p
        commit("p", "t"),  # the shared ancestor (e34046c)
        commit("t"),
    ]
    laid_out = graph.build(commits, tips={"m1"})
    assert_no_dot_pierced(laid_out)
    at = {row["id"]: row for row in laid_out["rows"]}
    # the corridor was inserted between the merge and the lineage
    assert at["m2"]["lane"] == 0 and at["c1"]["lane"] == at["c2"]["lane"] == 2
    assert at["p"]["lane"] == 1  # the corridor got the dot
    # …and the m2→p link runs its whole stretch down the corridor
    m2, p = at["m2"], at["p"]
    (link,) = [
        e
        for e in laid_out["edges"]
        if e["d"].startswith(f"M {m2['x']},{m2['y']} C") and e["d"].endswith(f"V {p['y']}")
    ]
    assert (graph._x(1), m2["y"] + graph.ROW, p["y"]) in _verticals(link["d"])


def test_a_blocked_corridor_shift_falls_back_to_the_far_right():
    """A branch mid-flight (dots already drawn) right of the merge pins its
    lane: the corridor may not shift it, so it opens at the far right and
    the link folds into the parent's dot over the last row."""
    commits = [
        commit("t1", "m"),  # trunk tip, lane 0
        commit("b1", "b2"),  # a branch with dots on lane 1, still descending
        commit("m", "t2", "p"),  # the merge: its corridor cannot shift lane 1
        commit("b2", "p"),
        commit("t2", "p"),
        commit("p"),
    ]
    laid_out = graph.build(commits, tips={"t1", "b1"})
    assert_no_dot_pierced(laid_out)
    at = {row["id"]: row for row in laid_out["rows"]}
    assert at["b1"]["lane"] == at["b2"]["lane"] == 1  # untouched by the merge
    assert at["p"]["lane"] == 0
    # the link rides the appended corridor (lane 2) and folds into p's dot
    m, p = at["m"], at["p"]
    (link,) = [e for e in laid_out["edges"] if f"{graph._x(2)}" in e["d"]]
    assert link["d"].startswith(f"M {m['x']},{m['y']} C")
    assert link["d"].endswith(f"{p['x']},{p['y']}")
    assert 2 in link["lanes"]
    # the dot-less corridor still counts into the width
    assert laid_out["width"] == graph._x(2) + graph.PAD


def test_existing_merge_fixtures_never_pierce_a_dot():
    fixtures = [
        [commit("m", "x", "y"), commit("x", "base"), commit("y", "base"), commit("base")],
        [commit("a", "b", "f"), commit("f", "fp", "b"), commit("fp", "b"), commit("b")],
    ]
    for commits in fixtures:
        assert_no_dot_pierced(graph.build(commits, tips={commits[0]["sha"]}))


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
