"""gitflower configuration.

Two configs, two homes:

* **Per-repo** — `gitflower.*` in the bare repository's own git config,
  consumed by the pre-receive hook and by the web UI. Strict: an unknown key
  or an unknown workflow is an error, so a typo fails the push loudly instead
  of silently allowing it.
* **Global** `~/.config/gitflower/config.yaml` (or /etc/gitflower/config.yaml
  for the system service) — server settings only: where repos live, how deep
  to scan, what address to listen on. Lenient: unknown sections are ignored so
  the file can carry settings for other tools.

Only the repository's *local* config is read — not the user's `~/.gitconfig`
or the system one. Policy belongs to the repository, and a setting in an
admin's home directory must never change what a push is allowed to do.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

import pygit2
import yaml

WORKFLOWS = ("protected", "issue-tracker", "release-manager")

SECTION = "gitflower"
BRANCH_PREFIX = "branch."

# git lowercases section and key names but preserves subsection case, so the
# keys arrive here folded while the branch pattern comes through verbatim.
_RULE_KEYS = {
    "workflow": "workflow",
    "enabled": "enabled",
    "allowdirectpush": "allow_direct_push",
    "requirelinearhistory": "require_linear_history",
}
_PINNED_KEY = "pinnedbranch"
_HIDDEN_KEY = "hiddenbranch"

_TRUE = ("true", "yes", "on", "1")
_FALSE = ("false", "no", "off", "0", "")


class ConfigError(ValueError):
    pass


# ---------------------------------------------------------------- per-repo


@dataclass
class BranchRule:
    """One `[gitflower "branch.<pattern>"]` section: which workflow the branch
    routes to, and — for the `protected` workflow — what it is checked against."""

    pattern: str
    workflow: str
    enabled: bool = True
    allow_direct_push: bool = False
    require_linear_history: bool = False

    def __post_init__(self) -> None:
        if self.workflow not in WORKFLOWS:
            raise ConfigError(
                f"unknown workflow '{self.workflow}' (expected one of: {', '.join(WORKFLOWS)})"
            )


@dataclass
class RepoConfig:
    branch_rules: list[BranchRule] = field(default_factory=list)
    pinned_branches: list[str] = field(default_factory=list)
    hidden_branches: list[str] = field(default_factory=list)


DEFAULT_PINNED = ["main", "integration", "releases"]
DEFAULT_HIDDEN = ["archive"]


def default_repo_config() -> RepoConfig:
    """What a repository with no `gitflower.*` keys is governed by."""
    return RepoConfig(
        branch_rules=[
            BranchRule(pattern="main", workflow="protected", require_linear_history=True),
            BranchRule(pattern="issues/*", workflow="issue-tracker"),
            BranchRule(pattern="releases/v*", workflow="release-manager"),
        ],
        pinned_branches=list(DEFAULT_PINNED),
        hidden_branches=list(DEFAULT_HIDDEN),
    )


def _parse_bool(value: str, where: str) -> bool:
    folded = (value or "").strip().lower()
    if folded in _TRUE:
        return True
    if folded in _FALSE:
        return False
    raise ConfigError(f"{where}: expected a boolean, got '{value}'")


def git_dir(repo_path: Path | str) -> Path:
    """The repository's git directory — itself when bare, `.git` otherwise."""
    try:
        repo = pygit2.Repository(str(repo_path))
    except pygit2.GitError as exc:
        raise ConfigError(f"{repo_path}: not a git repository") from exc
    return Path(repo.path)


def local_config(repo_path: Path | str) -> pygit2.Config:
    return pygit2.Config(str(git_dir(repo_path) / "config"))


def load_repo_config(repo_path: Path | str) -> RepoConfig:
    """The repository's gitflower settings; nothing set means the defaults."""
    where = f"{repo_path}: git config"
    rules: dict[str, dict] = {}
    pinned: list[str] = []
    hidden: list[str] = []

    for entry in local_config(repo_path):
        if not entry.name.startswith(SECTION + "."):
            continue
        rest = entry.name[len(SECTION) + 1 :]
        if rest == _PINNED_KEY:
            pinned.append(entry.value)
            continue
        if rest == _HIDDEN_KEY:
            hidden.append(entry.value)
            continue
        if not rest.startswith(BRANCH_PREFIX):
            raise ConfigError(f"{where}: unknown key '{entry.name}'")
        pattern, dot, key = rest[len(BRANCH_PREFIX) :].rpartition(".")
        if not dot or not pattern:
            raise ConfigError(f"{where}: malformed key '{entry.name}'")
        attr = _RULE_KEYS.get(key)
        if attr is None:
            raise ConfigError(f"{where}: unknown key '{entry.name}'")
        rule = rules.setdefault(pattern, {})
        if attr == "workflow":
            rule[attr] = entry.value
        else:
            rule[attr] = _parse_bool(entry.value, f"{where}: {entry.name}")

    if not rules and not pinned and not hidden:
        return default_repo_config()

    branch_rules = []
    for pattern, values in rules.items():
        if "workflow" not in values:
            raise ConfigError(
                f"{where}: branch '{pattern}' has no workflow "
                f"(set {SECTION}.{BRANCH_PREFIX}{pattern}.workflow)"
            )
        branch_rules.append(BranchRule(pattern=pattern, **values))

    return RepoConfig(
        branch_rules=branch_rules or default_repo_config().branch_rules,
        pinned_branches=pinned or list(DEFAULT_PINNED),
        hidden_branches=hidden or list(DEFAULT_HIDDEN),
    )


def dump_repo_config(config: RepoConfig) -> str:
    """The config as git-config text — the shape `git config --edit` shows."""
    lines = [f"[{SECTION}]"]
    for name in config.pinned_branches:
        lines.append(f"\tpinnedBranch = {name}")
    for name in config.hidden_branches:
        lines.append(f"\thiddenBranch = {name}")
    for rule in config.branch_rules:
        lines.append(f'[{SECTION} "{BRANCH_PREFIX}{rule.pattern}"]')
        lines.append(f"\tworkflow = {rule.workflow}")
        if not rule.enabled:
            lines.append("\tenabled = false")
        if rule.allow_direct_push:
            lines.append("\tallowDirectPush = true")
        if rule.require_linear_history:
            lines.append("\trequireLinearHistory = true")
    return "\n".join(lines) + "\n"


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
