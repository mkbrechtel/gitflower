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


def crossings(rows: list[dict]) -> int:
    """The edge-crossing count of a finished layout, via the untangle pass's
    own geometry model and the columns the layout put each line on."""
    bends, runs, _ = graph._strands(rows)
    return graph._tangles(graph._rivals(bends, runs), graph._columns(rows))


def test_a_blocked_corridor_shift_falls_back_to_the_far_right():
    """A branch mid-flight (dots already drawn) right of the merge pins its
    lane: the corridor may not shift it, so it opens at the far right and
    the link folds into the parent's dot over the last row. That far-right
    fallback costs a crossing — which the untangle pass then combs out by
    reordering the columns, so the built graph ends up crossing-free."""
    commits = [
        commit("t1", "m"),  # trunk tip, lane 0
        commit("b1", "b2"),  # a branch with dots on lane 1, still descending
        commit("m", "t2", "p"),  # the merge: its corridor cannot shift lane 1
        commit("b2", "p"),
        commit("t2", "p"),
        commit("p"),
    ]
    # the forward pass alone: the corridor lands on the appended lane 2
    rows = graph._place([graph._node(c) for c in commits], {}, {})
    at = {row["id"]: row for row in rows}
    assert at["b1"]["lane"] == at["b2"]["lane"] == 1  # untouched by the merge
    assert at["p"]["lane"] == 0
    assert at["m"]["corridors"]["p"] == 2  # the far-right fallback
    assert crossings(rows) == 1  # the link crosses the mid-flight branch

    # the full build unties it: same shapes, columns reordered, no crossing
    laid_out = graph.build(commits, tips={"t1", "b1"})
    assert_no_dot_pierced(laid_out)
    assert crossings(laid_out["rows"]) == 0
    at = {row["id"]: row for row in laid_out["rows"]}
    corridor = at["m"]["corridors"]["p"]
    assert corridor not in {at["t1"]["lane"], at["b1"]["lane"]}
    # the link still rides its corridor and folds into p's dot
    m, p = at["m"], at["p"]
    (link,) = [e for e in laid_out["edges"] if f"{graph._x(corridor)}" in e["d"]]
    assert link["d"].startswith(f"M {m['x']},{m['y']} C")
    assert link["d"].endswith(f"{p['x']},{p['y']}")
    assert corridor in link["lanes"]
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


def test_the_trunk_keeps_lane_zero_even_when_a_side_tip_is_newer():
    commits = [
        commit("s", "base"),  # side tip, newest — would grab lane 0 today
        commit("m", "base"),  # the trunk's tip
        commit("base"),
    ]
    branch_of = {"s": "side", "m": "main", "base": "main"}
    rows = graph.build(commits, tips={"s", "m"}, branch_of=branch_of, trunk="main")["rows"]
    at = {row["id"]: row for row in rows}
    assert at["m"]["lane"] == 0 and at["base"]["lane"] == 0
    assert at["s"]["lane"] == 1
    # without attribution, the newest tip takes lane 0 (unchanged behavior)
    rows = graph.build(commits, tips={"s", "m"})["rows"]
    assert {row["id"]: row["lane"] for row in rows} == {"s": 0, "m": 1, "base": 0}


def test_an_attributed_ancestor_lands_on_its_own_branch_line():
    """The shared-ancestor fixture again: with `p` attributed to the
    c-lineage's branch, its dot belongs on that line — the merge link
    folds into it instead of claiming the dot for its corridor."""
    commits = [
        commit("m1", "m2", "c1"),
        commit("m2", "t", "p"),
        commit("c1", "c2"),
        commit("c2", "p"),
        commit("p", "t"),
        commit("t"),
    ]
    branch_of = {"m1": "main", "m2": "main", "t": "main", "c1": "harness", "c2": "harness", "p": "harness"}
    laid_out = graph.build(commits, tips={"m1"}, branch_of=branch_of, trunk="main")
    assert_no_dot_pierced(laid_out)
    at = {row["id"]: row for row in laid_out["rows"]}
    assert at["p"]["lane"] == at["c2"]["lane"]  # the dot sits on its own line
    # …while unattributed, the corridor (leftmost waiter) receives the dot
    at = {r["id"]: r for r in graph.build(commits, tips={"m1"})["rows"]}
    assert at["p"]["lane"] != at["c2"]["lane"]


def test_branch_colors_are_stable_and_trunk_wears_the_accent():
    commits = [
        commit("s", "base"),
        commit("m", "base"),
        commit("base"),
    ]
    branch_of = {"s": "side", "m": "main", "base": "main"}
    rows = graph.build(commits, tips={"s", "m"}, branch_of=branch_of, trunk="main")["rows"]
    at = {row["id"]: row for row in rows}
    assert at["m"]["color"] == graph.COLORS[0] == at["base"]["color"]
    assert at["s"]["color"] != graph.COLORS[0]
    assert at["s"]["color"] == graph._branch_color("side", "main", 99)  # lane-independent
    # no attribution -> lane colors, exactly as before
    rows = graph.build(commits, tips={"s", "m"})["rows"]
    assert [row["color"] for row in rows] == [graph._color(row["lane"]) for row in rows]


def test_pinned_branches_hold_the_left_lanes_in_config_order():
    commits = [
        commit("w", "base"),  # a work branch tip, newest
        commit("i", "base"),  # integration tip
        commit("m", "base"),  # main tip
        commit("base"),
    ]
    branch_of = {"w": "work/w", "i": "integration", "m": "main", "base": "main"}
    laid_out = graph.build(
        commits,
        tips={"w", "i", "m"},
        branch_of=branch_of,
        trunk="main",
        pinned=["main", "integration"],
    )
    at = {row["id"]: row for row in laid_out["rows"]}
    assert at["m"]["lane"] == 0 and at["base"]["lane"] == 0
    assert at["i"]["lane"] == 1
    assert at["w"]["lane"] == 2  # non-pinned branches start beyond the reserved lanes
    assert at["m"]["pinned"] and at["i"]["pinned"] and at["base"]["pinned"]
    assert not at["w"]["pinned"]


def test_untangle_reorders_free_columns_to_avoid_a_crossing():
    """A short-lived branch tipped later than a long-lived one, so the
    forward pass parked it one lane further out — and its fold back into
    the trunk crossed the long-lived line. The untangle pass swaps the two
    columns: short-lived work nestles against the trunk, the long-lived
    line arcs outside it, nothing crosses. The pinned trunk never moves."""
    commits = [
        commit("a1", "a0"),  # long-lived branch, newest tip
        commit("m1", "m2"),  # trunk tip
        commit("b1", "m2"),  # short-lived branch, folds into the trunk soon
        commit("m2", "m3"),
        commit("a0", "m3"),  # the long-lived line reaches far down
        commit("m3"),
    ]
    branch_of = {"a1": "aa", "a0": "aa", "b1": "bb", "m1": "main", "m2": "main", "m3": "main"}
    laid_out = graph.build(
        commits, tips={"a1", "m1", "b1"}, branch_of=branch_of, trunk="main", pinned=["main"]
    )
    assert_no_dot_pierced(laid_out)
    assert crossings(laid_out["rows"]) == 0
    at = {row["id"]: row for row in laid_out["rows"]}
    assert at["m1"]["lane"] == at["m2"]["lane"] == at["m3"]["lane"] == 0
    assert at["b1"]["lane"] == 1  # swapped inward, next to its fork point
    assert at["a1"]["lane"] == at["a0"]["lane"] == 2


def test_equal_crossing_lines_settle_next_to_the_pinned_block():
    """Greedy parked `a` beyond `b` because `b`'s line was still alive when
    `a` tipped — but `b` ends before `a` ever bends, so the crossing count
    is indifferent to their order. The travel tiebreak is not: it pulls
    `a` right up against the pinned trunk it folds into, one lane past
    the reserved block instead of the far edge."""
    commits = [
        commit("m1", "m2"),  # trunk tip
        commit("b1", "b2"),  # a line that is still alive when `a` tips…
        commit("a", "m3"),  # …so `a` greedily gets the lane beyond it
        commit("b2"),  # `b` ends (an independent root)
        commit("m2", "m3"),
        commit("m3"),
    ]
    branch_of = {"m1": "main", "m2": "main", "m3": "main", "a": "aa", "b1": "bb", "b2": "bb"}
    laid_out = graph.build(
        commits, tips={"m1", "b1", "a"}, branch_of=branch_of, trunk="main", pinned=["main"]
    )
    assert_no_dot_pierced(laid_out)
    assert crossings(laid_out["rows"]) == 0
    at = {row["id"]: row for row in laid_out["rows"]}
    assert at["m1"]["lane"] == 0
    assert at["a"]["lane"] == 1  # hugs the pinned block it folds into
    assert at["b1"]["lane"] == at["b2"]["lane"] == 2


def test_untangle_leaves_pinned_lanes_in_place():
    """A work branch folding into the trunk must cross the pinned
    integration line between them — the one move that would fix it is
    moving a reserved column, which the pass may not do. The crossing
    stays; the pinned lanes staying leftmost is the constraint it
    optimizes within."""
    commits = [
        commit("w", "mb"),  # work tip, folds into the trunk at mb
        commit("i1", "i2"),  # integration tip
        commit("m1", "mb"),  # trunk tip
        commit("mb", "base"),
        commit("i2", "base"),  # the integration line spans the fold
        commit("base"),
    ]
    branch_of = {
        "w": "work",
        "i1": "integration",
        "i2": "integration",
        "m1": "main",
        "mb": "main",
        "base": "main",
    }
    laid_out = graph.build(
        commits,
        tips={"w", "i1", "m1"},
        branch_of=branch_of,
        trunk="main",
        pinned=["main", "integration"],
    )
    assert_no_dot_pierced(laid_out)
    at = {row["id"]: row for row in laid_out["rows"]}
    assert at["m1"]["lane"] == 0 and at["i1"]["lane"] == at["i2"]["lane"] == 1
    assert at["w"]["lane"] == 2
    assert crossings(laid_out["rows"]) == 1  # the price of the pinned order


def test_dimmed_shas_grey_their_rows_and_edges():
    commits = [
        commit("a", "c"),
        commit("b", "c"),
        commit("c"),
    ]
    laid_out = graph.build(commits, tips={"a", "b"}, dimmed={"b"})
    at = {row["id"]: row for row in laid_out["rows"]}
    assert at["b"]["dimmed"]
    assert not at["a"]["dimmed"] and not at["c"]["dimmed"]
    assert [edge["dimmed"] for edge in laid_out["edges"]].count(True) == 1  # b→c only


def test_a_merge_corridor_beyond_the_reserved_lanes():
    """Regression: with several pinned branches reserving lanes, a merge at
    the very top needs a corridor before the lane list has grown to the
    reserved width — the corridor must land on a real lane, not a clamped
    insert's phantom index."""
    commits = [
        commit("m", "a", "s"),  # merge on the trunk, newest row
        commit("t2", "a"),
        commit("t3", "a"),
        commit("s", "a"),
        commit("a"),
    ]
    branch_of = {"m": "main", "a": "main", "t2": "two", "t3": "three", "s": "side"}
    laid_out = graph.build(
        commits,
        tips={"m", "t2", "t3", "s"},
        branch_of=branch_of,
        trunk="main",
        pinned=["main", "two", "three"],
    )
    at = {row["id"]: row for row in laid_out["rows"]}
    assert at["m"]["lane"] == 0 and at["a"]["lane"] == 0
    assert at["t2"]["lane"] == 1 and at["t3"]["lane"] == 2
    assert at["s"]["lane"] == 3  # the side line stays out of the reserved columns


def test_a_segment_with_no_extent_takes_no_part_in_untangling():
    """A lane that holds its column for no rows at all — it never runs
    through a gap and never bends — has no extent to compare. It cannot
    cross anything and nothing has to make room for it, so the untangle pass
    must leave it out rather than ask where it reaches."""
    from gitflower import graph

    rows = graph.build(
        [
            {"sha": "d", "parents": ["b", "c"], "subject": "merge", "author": "a",
             "date": "2026-01-04T00:00:00+00:00", "short": "d"},
            {"sha": "c", "parents": ["a"], "subject": "side", "author": "a",
             "date": "2026-01-03T00:00:00+00:00", "short": "c"},
            {"sha": "b", "parents": ["a"], "subject": "main", "author": "a",
             "date": "2026-01-02T00:00:00+00:00", "short": "b"},
            {"sha": "a", "parents": [], "subject": "root", "author": "a",
             "date": "2026-01-01T00:00:00+00:00", "short": "a"},
        ],
        {"d"},
        collapse=False,
        trunk="main",
        pinned=["main"],
    )
    assert rows["rows"] and rows["width"] >= 1
