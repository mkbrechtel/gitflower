---
#SPDX-FileCopyrightText: 2026 Markus Katharina Brechtel <markus.katharina.brechtel@thengo.net>
#SPDX-License-Identifier: EUPL-1.2
---

# Per-repo configuration in the bare repo's git config

Every setting that describes *one repository* lives in that repository's own git config, in `gitflower.*` sections of the bare repo's `config` file. The global config narrows to what it actually is: server configuration — where repos live, how to scan them, what address to listen on.

This is a design document under active interview. Settled decisions are stated declaratively below; everything still open is gathered under [Open questions](#open-questions) and is not yet a commitment.

## Why the bare repo

The bare repo is the only place that is simultaneously per-repository, server-side, unversioned, and already present. A file in the working tree is versioned and cloned, so it describes project convention rather than server policy and travels to every client. A section in the global config would have to name repos by path and drift as they move. The bare repo's `config` moves with the repo, is readable by the same pygit2 handle the web UI already opens, and is editable over ssh with plain `git config`.

## What moves where

**Per-repo — the bare repo's `config`.** Branch rules and protected-branch policy, web feature toggles, branch display settings (`pinned_branches`, `hidden_branches`), and repo metadata (description, display name, visibility).

**Global — `~/.config/gitflower/config.yaml` or `/etc/gitflower/config.yaml`.** `repos.directory`, `repos.scan_depth`, `repos.default_branch` (used at repo creation), and `web.address`. Nothing that describes an individual repository.

`pinned_branches` and `hidden_branches` are the clearest case: they are consumed only in the single-repo view, and `gitread.branches` already accepts them as parameters rather than reading a global, so moving them down is a change of source, not of plumbing.

## Rule matching

Branch rules match **most-specific-wins**. The matching rule is chosen by pattern specificity, not by file order, so the flat and unordered nature of git config stops being a constraint:

```ini
[gitflower "branch.main"]
	workflow = protected
[gitflower "branch.issues/*"]
	workflow = issue-tracker
[gitflower "branch.releases/v*"]
	workflow = release-manager
```

A push to `main` matches `main` rather than any wildcard that would also cover it. Routing stays fail-closed: a branch matching no rule is refused, as it is today.

## Enforcement

A server-side `pre-receive` hook enforces policy in the same repository that holds the config. Policy stops being advisory — `--no-verify` on the client no longer bypasses it, because the decision is made after the objects reach the server.

## Replacing `.gitflower/config.yaml`

The versioned working-tree file is removed rather than layered. The bare repo's git config is the single source of truth for per-repo settings; there is no precedence chain to reason about and no way for a clone to carry stale policy.

## Open questions

**Specificity.** "Most specific" needs one definition the router can compute. Candidates: an exact literal beats any pattern, then more path segments wins, then fewer wildcards, then longer literal prefix — with ties being a config error rather than an arbitrary pick.

**Key shape and naming.** `[gitflower "branch.<pattern>"]` puts the pattern in the subsection name, which git treats as case-sensitive and matches literally — workable, but `branch.` as a prefix inside a subsection is unusual. Alternatives: a `[gitflower-branch "<pattern>"]` section, or `[gitflower "<pattern>"]` with rule keys distinguishing it from scalar settings.

**`require_clean_working_tree` server-side.** There is no working tree at the receiving end. The check either disappears with the client hook, or is reinterpreted as something a server can see.

**`allowed_push_users` without authentication.** `pre-receive` knows the transport identity only if something authenticated it, and gitflower has no auth layer today. Without one, this setting cannot be enforced server-side even though it is the setting most in need of server-side enforcement.

**Visibility without authentication.** Same gap. `visibility = private` implies an access decision the web layer currently cannot make. Possibly this metadata field is recorded now and enforced later, but that should be a deliberate choice rather than an accident.

**Does `pre-push` survive?** Round 1 chose to add `pre-receive`. Whether the client hook remains as a fast-feedback path — one workflow engine, two entry points with different available checks — or is dropped entirely is not yet decided.

**Defaults when unset.** A repo with no `gitflower.*` keys currently means "the built-in default rules". Whether that stays true, or whether `gitflower init` writes the defaults explicitly into the bare repo's config so the policy is always visible in one `git config --list`, is open.

**Read cost in the web path.** The web UI would read per-repo config on every repo view. Whether pygit2's `repo.config` is cheap enough per request or wants the same caching as the repo scan is unmeasured.

**Migration and bare-repo tooling.** `_repo_root()` requires a `.git` child, so `init` and `install` cannot run in a bare repo at all today; both need a bare-repo path. Existing repos carrying `.gitflower/config.yaml` need a migration route.

# Considerations

## Ordered rules were rejected

Keeping first-enabled-match-wins would have required either a `priority` key on every rule or an ordered multivar encoding pattern and workflow into one string. Both preserve current semantics, and both make the config file's meaning depend on something a reader cannot see at a glance. Most-specific-wins removes the question instead of encoding an answer to it.

## Layering the versioned file was rejected

Keeping `.gitflower/config.yaml` as reviewable project convention beneath a server-side override is attractive — policy changes would arrive through merge requests like everything else. It was rejected because two layers need a precedence rule, and a clone that carries policy it cannot enforce invites the reader to trust it.

## Splitting rules into a YAML file beside the bare config was rejected

Ordered branch rules in `<bare>/gitflower.yaml` with only flags in git config would have kept list ordering natural. Most-specific-wins made the ordering problem disappear, so the second file no longer buys anything.
