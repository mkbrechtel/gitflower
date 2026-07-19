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

**Per-repo — the bare repo's `config`.** Branch rules and protected-branch policy, web feature toggles, branch display settings (`pinned_branches`, `hidden_branches`), and repo metadata (description, display name).

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

A server-side `pre-receive` hook enforces policy in the same repository that holds the config, and is the only hook gitflower installs. Policy stops being advisory — `--no-verify` on the client no longer bypasses it, because the decision is made after the objects reach the server. The pusher learns of a rejection from the push itself.

Protection policy is therefore what a server can see: `allow_direct_push` and `require_linear_history` against a branch pattern. `require_clean_working_tree` has no meaning at the receiving end and does not survive the move; `allowed_push_users` needs an identity gitflower cannot yet obtain and is out of scope until it has one.

## Defaults

A repo with no `gitflower.*` keys gets the built-in default rules — `main` protected with linear history required, `issues/*` routed to the issue tracker, `releases/v*` to the release manager. Nothing is written into the bare repo's config at creation, so a config that says nothing and a config that was never touched are the same thing.

## Replacing `.gitflower/config.yaml`

The versioned working-tree file is removed rather than layered. The bare repo's git config is the single source of truth for per-repo settings; there is no precedence chain to reason about and no way for a clone to carry stale policy.

## Open questions

**Specificity.** "Most specific" needs one definition the router can compute. Candidates: an exact literal beats any pattern, then more path segments wins, then fewer wildcards, then longer literal prefix — with ties being a config error rather than an arbitrary pick.

**Key shape and naming.** `[gitflower "branch.<pattern>"]` puts the pattern in the subsection name, which git treats as case-sensitive and matches literally — workable, but `branch.` as a prefix inside a subsection is unusual. Alternatives: a `[gitflower-branch "<pattern>"]` section, or `[gitflower "<pattern>"]` with rule keys distinguishing it from scalar settings.

**Read cost in the web path.** The web UI would read per-repo config on every repo view. Whether pygit2's `repo.config` is cheap enough per request or wants the same caching as the repo scan is unmeasured.

**Migration and bare-repo tooling.** `_repo_root()` requires a `.git` child, so `init` and `install` cannot run in a bare repo at all today; both need a bare-repo path. Existing repos carrying `.gitflower/config.yaml` need a migration route.

# Considerations

## Identity-dependent settings are deferred

`allowed_push_users` and a `visibility = private` metadata field were both in the original scope. Neither can be enforced without an auth layer: `pre-receive` learns who is pushing only if something authenticated the transport, and the web layer cannot gate on visibility it has no user to check against. Recording the keys unenforced was considered and rejected — a policy key that silently does nothing is worse than an absent one, because a reader reasonably assumes it works. They return when there is an identity to enforce them against.

## `pre-push` was dropped rather than kept for local feedback

Keeping the client hook as a fast-feedback path would spare the pusher a round-trip on an obvious violation. It was dropped because the client would then need the server's config, reintroducing exactly the distribution problem this design removes. One config, one hook, one place the decision happens. `require_clean_working_tree` goes with it, having no server-side meaning.

## Defaults are not written into the config at creation

Seeding the bare repo's config with the default rules would make policy visible in a single `git config --list` and editable without knowing what the defaults were. It was rejected because it freezes the defaults at creation time: repos created before a default changes keep the old policy forever, and there is no way to tell a deliberate choice from an inherited copy.

## Ordered rules were rejected

Keeping first-enabled-match-wins would have required either a `priority` key on every rule or an ordered multivar encoding pattern and workflow into one string. Both preserve current semantics, and both make the config file's meaning depend on something a reader cannot see at a glance. Most-specific-wins removes the question instead of encoding an answer to it.

## Layering the versioned file was rejected

Keeping `.gitflower/config.yaml` as reviewable project convention beneath a server-side override is attractive — policy changes would arrive through merge requests like everything else. It was rejected because two layers need a precedence rule, and a clone that carries policy it cannot enforce invites the reader to trust it.

## Splitting rules into a YAML file beside the bare config was rejected

Ordered branch rules in `<bare>/gitflower.yaml` with only flags in git config would have kept list ordering natural. Most-specific-wins made the ordering problem disappear, so the second file no longer buys anything.
