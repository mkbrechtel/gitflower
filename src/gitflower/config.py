"""gitflower configuration — everything is YAML.

Two config files:

* **Per-repo** `.gitflower/config.yaml` — branch rules and protection policy,
  consumed by the pre-push hook engine. Strict: unknown keys are an error, so
  a typo fails the hook loudly instead of silently allowing a push.
* **Global** `~/.config/gitflower/config.yaml` (or /etc/gitflower/config.yaml
  for the system service) — repo hosting + web UI settings. Lenient: unknown
  sections are ignored so the file can carry settings for other tools.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO_CONFIG_DIR = ".gitflower"
REPO_CONFIG_NAME = "config.yaml"

WORKFLOWS = ("protected", "issue-tracker", "release-manager")


class ConfigError(ValueError):
    pass


# ---------------------------------------------------------------- per-repo


@dataclass
class BranchRule:
    pattern: str
    workflow: str
    enabled: bool = True

    def __post_init__(self) -> None:
        if self.workflow not in WORKFLOWS:
            raise ConfigError(
                f"unknown workflow '{self.workflow}' (expected one of: {', '.join(WORKFLOWS)})"
            )


@dataclass
class ProtectedBranch:
    pattern: str
    allow_direct_push: bool = False
    require_linear_history: bool = False
    allowed_push_users: list[str] = field(default_factory=list)
    require_clean_working_tree: bool = False


@dataclass
class RepoConfig:
    branch_rules: list[BranchRule] = field(default_factory=list)
    protected_branches: list[ProtectedBranch] = field(default_factory=list)


def default_repo_config() -> RepoConfig:
    return RepoConfig(
        branch_rules=[
            BranchRule(pattern="main", workflow="protected"),
            BranchRule(pattern="issues/*", workflow="issue-tracker"),
            BranchRule(pattern="releases/v*", workflow="release-manager"),
        ],
        protected_branches=[
            ProtectedBranch(pattern="main", require_linear_history=True),
        ],
    )


def _build(cls, data: dict, where: str):
    if not isinstance(data, dict):
        raise ConfigError(f"{where}: expected a mapping, got {type(data).__name__}")
    fields = {f.name for f in cls.__dataclass_fields__.values()}
    unknown = set(data) - fields
    if unknown:
        raise ConfigError(f"{where}: unknown keys: {', '.join(sorted(unknown))}")
    return cls(**data)


def repo_config_path(repo_root: Path | str) -> Path:
    return Path(repo_root) / REPO_CONFIG_DIR / REPO_CONFIG_NAME


def load_repo_config(repo_root: Path | str) -> RepoConfig:
    """The repo's config; a missing file means the defaults (as in Go)."""
    path = repo_config_path(repo_root)
    if not path.exists():
        return default_repo_config()
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: expected a mapping at the top level")
    unknown = set(data) - {"branch_rules", "protected_branches"}
    if unknown:
        raise ConfigError(f"{path}: unknown keys: {', '.join(sorted(unknown))}")
    return RepoConfig(
        branch_rules=[
            _build(BranchRule, rule, f"{path}: branch_rules[{i}]")
            for i, rule in enumerate(data.get("branch_rules") or [])
        ],
        protected_branches=[
            _build(ProtectedBranch, pb, f"{path}: protected_branches[{i}]")
            for i, pb in enumerate(data.get("protected_branches") or [])
        ],
    )


def dump_repo_config(config: RepoConfig) -> str:
    data = {
        "branch_rules": [
            {"pattern": r.pattern, "workflow": r.workflow, "enabled": r.enabled}
            for r in config.branch_rules
        ],
        "protected_branches": [
            {
                "pattern": p.pattern,
                "allow_direct_push": p.allow_direct_push,
                "require_linear_history": p.require_linear_history,
                "allowed_push_users": p.allowed_push_users,
                "require_clean_working_tree": p.require_clean_working_tree,
            }
            for p in config.protected_branches
        ],
    }
    return yaml.safe_dump(data, sort_keys=False)


# ----------------------------------------------------------------- global


@dataclass
class ReposConfig:
    directory: str = "./repos/"
    scan_depth: int = 3
    default_branch: str = "main"


@dataclass
class WebConfig:
    address: str = ":8747"


@dataclass
class GlobalConfig:
    repos: ReposConfig = field(default_factory=ReposConfig)
    web: WebConfig = field(default_factory=WebConfig)
    path: Path | None = None  # where this config was loaded from, if anywhere


def global_config_candidates() -> list[Path]:
    xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return [Path(xdg) / "gitflower" / "config.yaml", Path("/etc/gitflower/config.yaml")]


def load_global_config(explicit_path: str | Path | None = None) -> GlobalConfig:
    """--config flag > $GITFLOWER_CONFIG > XDG > /etc > defaults. First file wins."""
    candidates: list[Path] = []
    if explicit_path:
        candidates = [Path(explicit_path)]
    elif os.environ.get("GITFLOWER_CONFIG"):
        candidates = [Path(os.environ["GITFLOWER_CONFIG"])]
    else:
        candidates = global_config_candidates()

    for path in candidates:
        if path.is_file():
            data = yaml.safe_load(path.read_text()) or {}
            if not isinstance(data, dict):
                raise ConfigError(f"{path}: expected a mapping at the top level")
            cfg = GlobalConfig(path=path)
            repos = data.get("repos") or {}
            web = data.get("web") or {}
            for key, value in repos.items():
                if hasattr(cfg.repos, key):
                    setattr(cfg.repos, key, value)
            for key, value in web.items():
                if hasattr(cfg.web, key):
                    setattr(cfg.web, key, value)
            return cfg
    if explicit_path:
        raise ConfigError(f"config file not found: {explicit_path}")
    return GlobalConfig()


def parse_address(address: str) -> tuple[str, int]:
    """':8747' listens on all interfaces; 'host:port' on that host."""
    host, sep, port = address.rpartition(":")
    if not sep or not port.isdigit():
        raise ConfigError(f"invalid web address '{address}' (expected [host]:port)")
    return host or "0.0.0.0", int(port)
