import pytest
import yaml

from gitflower import config as cfg


def test_default_repo_config_roundtrip(tmp_path):
    (tmp_path / ".gitflower").mkdir()
    path = cfg.repo_config_path(tmp_path)
    path.write_text(cfg.dump_repo_config(cfg.default_repo_config()))
    loaded = cfg.load_repo_config(tmp_path)
    assert loaded == cfg.default_repo_config()


def test_missing_repo_config_means_defaults(tmp_path):
    assert cfg.load_repo_config(tmp_path) == cfg.default_repo_config()


def test_default_rules():
    defaults = cfg.default_repo_config()
    assert [(r.pattern, r.workflow) for r in defaults.branch_rules] == [
        ("main", "protected"),
        ("issues/*", "issue-tracker"),
        ("releases/v*", "release-manager"),
    ]
    protected = defaults.protected_branches[0]
    assert protected.pattern == "main"
    assert protected.allow_direct_push is False
    assert protected.require_linear_history is True


def test_unknown_key_rejected(tmp_path):
    path = cfg.repo_config_path(tmp_path)
    path.parent.mkdir()
    path.write_text("branch_rules:\n- pattern: main\n  workflow: protected\n  enabeld: true\n")
    with pytest.raises(cfg.ConfigError, match="unknown keys: enabeld"):
        cfg.load_repo_config(tmp_path)


def test_unknown_workflow_rejected(tmp_path):
    path = cfg.repo_config_path(tmp_path)
    path.parent.mkdir()
    path.write_text("branch_rules:\n- pattern: main\n  workflow: nope\n")
    with pytest.raises(cfg.ConfigError, match="unknown workflow 'nope'"):
        cfg.load_repo_config(tmp_path)


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
