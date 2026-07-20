import pytest
import yaml

from gitflower import config as cfg
from tests.conftest import git


def set_config(repo, key, value, add=False):
    git(repo, "config", "--add" if add else "--replace-all", key, value)


# ---------------------------------------------------------------- per-repo


def test_untouched_repo_means_defaults(bare_repo):
    assert cfg.load_repo_config(bare_repo) == cfg.default_repo_config()


def test_default_rules():
    defaults = cfg.default_repo_config()
    assert [(r.pattern, r.workflow) for r in defaults.branch_rules] == [
        ("main", "protected"),
        ("issues/*", "issue-tracker"),
        ("releases/v*", "release-manager"),
    ]
    protected = defaults.branch_rules[0]
    assert protected.allow_direct_push is False
    assert protected.require_linear_history is True


def test_rules_read_from_git_config(bare_repo):
    set_config(bare_repo, "gitflower.branch.main.workflow", "protected")
    set_config(bare_repo, "gitflower.branch.main.requireLinearHistory", "true")
    set_config(bare_repo, "gitflower.branch.topic/*.workflow", "issue-tracker")
    loaded = cfg.load_repo_config(bare_repo)
    assert [(r.pattern, r.workflow) for r in loaded.branch_rules] == [
        ("main", "protected"),
        ("topic/*", "issue-tracker"),
    ]
    assert loaded.branch_rules[0].require_linear_history is True
    assert loaded.branch_rules[0].allow_direct_push is False


def test_pattern_containing_dots_survives(bare_repo):
    """The key splits on its LAST dot, so a dotted pattern stays intact."""
    set_config(bare_repo, "gitflower.branch.releases/v1.0.workflow", "release-manager")
    loaded = cfg.load_repo_config(bare_repo)
    assert loaded.branch_rules[0].pattern == "releases/v1.0"


def test_key_case_is_folded_by_git(bare_repo):
    set_config(bare_repo, "gitflower.branch.main.workflow", "protected")
    set_config(bare_repo, "gitflower.branch.main.ALLOWDIRECTPUSH", "yes")
    assert cfg.load_repo_config(bare_repo).branch_rules[0].allow_direct_push is True


def test_pinned_and_hidden_multivars(bare_repo):
    set_config(bare_repo, "gitflower.pinnedBranch", "trunk")
    set_config(bare_repo, "gitflower.pinnedBranch", "integration", add=True)
    set_config(bare_repo, "gitflower.hiddenBranch", "attic")
    loaded = cfg.load_repo_config(bare_repo)
    assert loaded.pinned_branches == ["trunk", "integration"]
    assert loaded.hidden_branches == ["attic"]
    # rules were not configured, so they stay at the defaults
    assert loaded.branch_rules == cfg.default_repo_config().branch_rules


def test_display_settings_alone_keep_default_rules(bare_repo):
    set_config(bare_repo, "gitflower.hiddenBranch", "attic")
    assert cfg.load_repo_config(bare_repo).pinned_branches == cfg.DEFAULT_PINNED


def test_unknown_key_rejected(bare_repo):
    set_config(bare_repo, "gitflower.branch.main.workflow", "protected")
    set_config(bare_repo, "gitflower.branch.main.enabeld", "true")
    with pytest.raises(cfg.ConfigError, match="unknown key"):
        cfg.load_repo_config(bare_repo)


def test_unknown_flat_key_rejected(bare_repo):
    set_config(bare_repo, "gitflower.pinedBranch", "trunk")
    with pytest.raises(cfg.ConfigError, match="unknown key"):
        cfg.load_repo_config(bare_repo)


def test_unknown_workflow_rejected(bare_repo):
    set_config(bare_repo, "gitflower.branch.main.workflow", "nope")
    with pytest.raises(cfg.ConfigError, match="unknown workflow 'nope'"):
        cfg.load_repo_config(bare_repo)


def test_rule_without_workflow_rejected(bare_repo):
    set_config(bare_repo, "gitflower.branch.main.requireLinearHistory", "true")
    with pytest.raises(cfg.ConfigError, match="has no workflow"):
        cfg.load_repo_config(bare_repo)


def test_non_boolean_rejected(bare_repo):
    set_config(bare_repo, "gitflower.branch.main.workflow", "protected")
    set_config(bare_repo, "gitflower.branch.main.enabled", "maybe")
    with pytest.raises(cfg.ConfigError, match="expected a boolean"):
        cfg.load_repo_config(bare_repo)


def test_foreign_sections_ignored(bare_repo):
    set_config(bare_repo, "core.logAllRefUpdates", "true")
    set_config(bare_repo, "some.other.key", "value")
    assert cfg.load_repo_config(bare_repo) == cfg.default_repo_config()


def test_user_gitconfig_cannot_set_policy(bare_repo, tmp_path, monkeypatch):
    """Only the repository's own config is policy — not the admin's home."""
    home = tmp_path / "elsewhere"
    home.mkdir()
    (home / ".gitconfig").write_text(
        '[gitflower "branch.main"]\n\tallowDirectPush = true\n'
    )
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    assert cfg.load_repo_config(bare_repo) == cfg.default_repo_config()


def test_not_a_repository(tmp_path):
    with pytest.raises(cfg.ConfigError, match="not a git repository"):
        cfg.load_repo_config(tmp_path)


def test_dump_roundtrips_through_git(bare_repo):
    """What `config show` prints is what git config accepts back."""
    original = cfg.default_repo_config()
    (cfg.git_dir(bare_repo) / "config").write_text(cfg.dump_repo_config(original))
    assert cfg.load_repo_config(bare_repo) == original


# ----------------------------------------------------------------- global


def test_global_config_defaults(tmp_path, monkeypatch):
    # a missing $GITFLOWER_CONFIG file short-circuits the fallback chain, so
    # a real /etc/gitflower/config.yaml on the test host cannot interfere
    monkeypatch.setenv("GITFLOWER_CONFIG", str(tmp_path / "absent.yaml"))
    loaded = cfg.load_global_config()
    assert loaded.repos.directory == "./repos/"
    assert loaded.repos.scan_depth == 3
    assert loaded.repos.default_branch == "main"
    assert loaded.web.address == ":8747"


def test_global_config_explicit_path(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "repos": {"directory": "/srv/repos", "scan_depth": 5},
                "web": {"address": "127.0.0.1:9000"},
                "log": {"level": "info"},  # foreign section: ignored
            }
        )
    )
    loaded = cfg.load_global_config(path)
    assert loaded.repos.directory == "/srv/repos"
    assert loaded.repos.scan_depth == 5
    assert loaded.repos.default_branch == "main"
    assert loaded.web.address == "127.0.0.1:9000"
    assert loaded.path == path


def test_global_config_has_no_per_repo_settings():
    """Branch display settings belong to the repo, not the server."""
    assert not hasattr(cfg.WebConfig(), "pinned_branches")
    assert not hasattr(cfg.WebConfig(), "hidden_branches")


def test_global_config_env(tmp_path, monkeypatch):
    path = tmp_path / "env.yaml"
    path.write_text("repos:\n  directory: /env/repos\n")
    monkeypatch.setenv("GITFLOWER_CONFIG", str(path))
    assert cfg.load_global_config().repos.directory == "/env/repos"


def test_global_config_missing_explicit(tmp_path):
    with pytest.raises(cfg.ConfigError, match="config file not found"):
        cfg.load_global_config(tmp_path / "nope.yaml")


@pytest.mark.parametrize(
    "address,expected",
    [
        (":8747", ("0.0.0.0", 8747)),
        ("127.0.0.1:9000", ("127.0.0.1", 9000)),
        ("localhost:80", ("localhost", 80)),
    ],
)
def test_parse_address(address, expected):
    assert cfg.parse_address(address) == expected


@pytest.mark.parametrize("bad", ["8747", "host:", "host:abc", ""])
def test_parse_address_invalid(bad):
    with pytest.raises(cfg.ConfigError):
        cfg.parse_address(bad)
