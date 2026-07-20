"""The import direction, enforced.

gitflower is deliberately flat, so nothing but a test stops a surface from
reaching past the view models into git reads, or a domain module from
importing a surface. These rules keep the convergence real: if the web, the
CLI and the TUI all go through `models`, they cannot drift; if one of them
assembles its own view, this fails.

The rules are narrow on purpose. Surfaces may open repositories — that is
handle acquisition, not assembly — but they may not lay out a graph or read
branch and commit lists themselves.
"""

import ast
from pathlib import Path

import pytest

import gitflower

SRC = Path(gitflower.__file__).resolve().parent

# modules that render or drive a surface
SURFACES = {"__main__", "cli", "tui", "web", "review.tui"}

# gitread/graph calls that build a view — a surface calling one of these is
# assembling a model behind the models' back
VIEW_READS = {"branches", "commits", "born_on", "reachable", "diff_detail", "tree_entries"}

# write paths: the web is read-only, and that is a property of the imports
WRITE_MODULES = {"mr", "merge", "hooks", "review.submit"}


def module_name(path: Path) -> str:
    rel = path.relative_to(SRC).with_suffix("")
    parts = [p for p in rel.parts if p != "__init__"]
    return ".".join(parts)


def sources():
    for path in sorted(SRC.rglob("*.py")):
        yield module_name(path), path, ast.parse(path.read_text())


def imported(tree) -> set[str]:
    """Every gitflower module this file imports, by dotted name."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "gitflower":
                names.update(a.name for a in node.names)
            elif node.module.startswith("gitflower."):
                tail = node.module[len("gitflower."):]
                names.add(tail)
                names.update(f"{tail}.{a.name}" for a in node.names)
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("gitflower."):
                    names.add(a.name[len("gitflower."):])
    return names


def is_surface(name: str) -> bool:
    return any(name == s or name.startswith(s + ".") for s in SURFACES)


def calls_on(tree, receiver: str) -> set[str]:
    """Attribute calls like `gitread.commits(...)`, by attribute name."""
    found = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == receiver
        ):
            found.add(node.func.attr)
    return found


ALL = list(sources())


@pytest.mark.parametrize("name,path,tree", ALL, ids=[m[0] for m in ALL])
def test_no_domain_module_imports_a_surface(name, path, tree):
    if is_surface(name):
        return
    leaked = {i for i in imported(tree) if is_surface(i)}
    assert not leaked, f"{name} imports surface(s) {sorted(leaked)}"


@pytest.mark.parametrize("name,path,tree", ALL, ids=[m[0] for m in ALL])
def test_surfaces_do_not_assemble_view_models(name, path, tree):
    """A surface may open a repo; it may not build a view out of git reads."""
    if not is_surface(name):
        return
    for receiver in ("gitread", "graph", "graphlayout"):
        offending = calls_on(tree, receiver) & VIEW_READS
        assert not offending, (
            f"{name} calls {receiver}.{sorted(offending)[0]}() directly — "
            "assemble it on the view model instead"
        )
    assert "build" not in calls_on(tree, "graph"), f"{name} lays out a graph itself"


@pytest.mark.parametrize("name,path,tree", ALL, ids=[m[0] for m in ALL])
def test_models_import_no_surface_and_no_writes(name, path, tree):
    if not (name == "models" or name.startswith("models.")):
        return
    names = imported(tree)
    assert not {i for i in names if is_surface(i)}, "models must not import a surface"
    assert not (names & WRITE_MODULES), "models is a read contract — no write modules"


@pytest.mark.parametrize("name,path,tree", ALL, ids=[m[0] for m in ALL])
def test_web_is_read_only(name, path, tree):
    if not name.startswith("web"):
        return
    leaked = imported(tree) & WRITE_MODULES
    assert not leaked, f"{name} imports write module(s) {sorted(leaked)}"


@pytest.mark.parametrize("name,path,tree", ALL, ids=[m[0] for m in ALL])
def test_review_does_not_import_mr_or_merge(name, path, tree):
    """Reviews are older than merge requests and stay independent of them —
    an MR may reference a review, never the other way round."""
    if not name.startswith("review"):
        return
    leaked = {i for i in imported(tree) if i.split(".")[0] in ("mr", "merge")}
    assert not leaked, f"{name} imports {sorted(leaked)}"
