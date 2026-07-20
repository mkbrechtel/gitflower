---
#SPDX-FileCopyrightText: 2026 Markus Katharina Brechtel <markus.katharina.brechtel@thengo.net>
#SPDX-License-Identifier: EUPL-1.2
---

# Per-repo configuration in the bare repo's git config

Every setting that describes *one repository* lives in that repository's own git config, in `gitflower.*` sections of the bare repo's `config` file. The global config narrows to what it actually is: server configuration — where repos live, how to scan them, what address to listen on.

The settings below are implemented. Settings that are wanted but have no feature behind them yet are listed under [Not yet configurable](#not-yet-configurable); they are not read, and setting them is an error until they are.

## Why the bare repo

The bare repo is the only place that is simultaneously per-repository, server-side, unversioned, and already present. A file in the working tree is versioned and cloned, so it describes project convention rather than server policy and travels to every client. A section in the global config would have to name repos by path and drift as they move. The bare repo's `config` moves with the repo, is readable by the same pygit2 handle the web UI already opens, and is editable over ssh with plain `git config`.

## What moves where

**Per-repo — the bare repo's `config`.** Branch rules and the protection policy that goes with them, plus the branch display settings `pinnedBranch` and `hiddenBranch`.

**Global — `~/.config/gitflower/config.yaml` or `/etc/gitflower/config.yaml`.** `repos.directory`, `repos.scan_depth`, `repos.default_branch` (used at repo creation), and `web.address`. Nothing that describes an individual repository.

Only the repository's own config file is read. A `gitflower.*` key in an admin's `~/.gitconfig` or in the system config has no effect on any repository, because policy that a home directory could change is not policy.

## The keys

One section per branch pattern carries both the routing decision and, for the `protected` workflow, what the branch is checked against. Display settings are flat multivars:

```ini
[gitflower]
	pinnedBranch = main
	pinnedBranch = integration
	hiddenBranch = archive
[gitflower "branch.main"]
	workflow = protected
	requireLinearHistory = true
[gitflower "branch.issues/*"]
	workflow = issue-tracker
[gitflower "branch.releases/v*"]
	workflow = release-manager
```

`workflow` is one of `protected`, `issue-tracker`, `release-manager`, and is required in every branch section. `enabled` (default true), `allowDirectPush` and `requireLinearHistory` take git's usual boolean spellings. Git folds key names to lower case but preserves the subsection verbatim, so patterns keep their case and a pattern containing dots — `branch.releases/v1.0` — survives, since the key is split on its last dot.

Pinned entries lead the repo view's branch list in the order given; hidden ones disappear from it and from the commit graph. Both match a branch of that exact name or anything under that folder.

An unknown `gitflower.*` key, an unknown workflow, a non-boolean where a boolean belongs, or a branch section with no workflow is an error. The push fails loudly rather than proceeding under a policy nobody wrote.

## Rule matching

Branch rules match **most-specific-wins**, so the order they appear in the file does not matter. A pattern with no wildcards beats one with any; then more path segments wins; then fewer wildcards; then more literal characters. `main` beats `*`, and `releases/v*` beats `releases/*` for `releases/v1`.

Routing is fail-closed in both directions. A branch matching no rule is refused, and so is a branch matching two rules that are equally specific by every one of those measures — an ambiguous configuration is reported, never silently resolved.

## Enforcement

A server-side `pre-receive` hook enforces policy in the same repository that holds the config, and is the only hook gitflower installs. Policy stops being advisory — `--no-verify` on the client no longer bypasses it, because the decision is made after the objects reach the server. Only `refs/heads/*` is routed; tags and other refs pass untouched, and branch deletions are skipped.

`gitflower init` and `gitflower install` therefore act on a bare repository and refuse a working tree, where the hook they install would never run.

Protection policy is what a server can see: `allowDirectPush` and `requireLinearHistory`. A clean working tree cannot be checked at the receiving end, and restricting pushes to named users needs an identity gitflower cannot yet obtain.

## Defaults

A repo with no `gitflower.*` keys gets the built-in default rules — `main` protected with linear history required, `issues/*` routed to the issue tracker, `releases/v*` to the release manager, `main`/`integration`/`releases` pinned and `archive` hidden. Nothing is written into the bare repo's config at creation, so a config that says nothing and a config that was never touched are the same thing. `gitflower init` reports the effective rules and writes nothing.

Rules and display settings default independently: configuring only `hiddenBranch` leaves the default branch rules in force.

## Web reads

The web UI reads each repository's config when rendering that repository, and falls back to the defaults if the config is broken rather than failing the page. Display is not enforcement — the hook is where a bad config must be loud.

## Not yet configurable

These are wanted per-repo but have no feature behind them yet, so they are not read and setting them is a config error:

**Web feature toggles.** Per-repo on/off for the merge-request view, docs, issues, and git-http clone. The web layer currently renders all of them unconditionally.

**Repo metadata.** Description, display name. `RepoInfo` carries only derived fields — branch count, MR count, size, last update — and nothing an owner authored.

**Identity-dependent settings.** `allowedPushUsers` and a private/public `visibility`. Both need an auth layer; see *Considerations*.

## Open questions

**Read cost in the web path.** Per-repo config is read on every repo view, uncached. Whether that wants the same caching as the repo scan is unmeasured.

**Migration.** A repository carrying the old versioned `.gitflower/config.yaml` is now governed by the defaults — the file is ignored, not translated. Whether a one-shot `gitflower migrate` is worth writing depends on how many repositories exist that were configured by it.

# Considerations

## Identity-dependent settings are deferred

`allowed_push_users` and a `visibility = private` metadata field were both in the original scope. Neither can be enforced without an auth layer: `pre-receive` learns who is pushing only if something authenticated the transport, and the web layer cannot gate on visibility it has no user to check against. Recording the keys unenforced was considered and rejected — a policy key that silently does nothing is worse than an absent one, because a reader reasonably assumes it works. They return when there is an identity to enforce them against.

## `pre-push` was dropped rather than kept for local feedback

Keeping the client hook as a fast-feedback path would spare the pusher a round-trip on an obvious violation. It was dropped because the client would then need the server's config, reintroducing exactly the distribution problem this design removes. One config, one hook, one place the decision happens. `require_clean_working_tree` goes with it, having no server-side meaning.

## Defaults are not written into the config at creation

Seeding the bare repo's config with the default rules would make policy visible in a single `git config --list` and editable without knowing what the defaults were. It was rejected because it freezes the defaults at creation time: repos created before a default changes keep the old policy forever, and there is no way to tell a deliberate choice from an inherited copy.

## Rules and protection were merged into one section per pattern

The old config had two lists — `branch_rules` and `protected_branches` — both keyed by branch pattern, with a fallback for a protected rule whose pattern no policy entry matched. Merging them removes the fallback and the case where a rule and a policy name overlapping but different patterns. The cost is that a policy can no longer be expressed at a different granularity than the routing decision, which nothing was using.

## Ordered rules were rejected

Keeping first-enabled-match-wins would have required either a `priority` key on every rule or an ordered multivar encoding pattern and workflow into one string. Both preserve current semantics, and both make the config file's meaning depend on something a reader cannot see at a glance. Most-specific-wins removes the question instead of encoding an answer to it.

## Layering the versioned file was rejected

Keeping `.gitflower/config.yaml` as reviewable project convention beneath a server-side override is attractive — policy changes would arrive through merge requests like everything else. It was rejected because two layers need a precedence rule, and a clone that carries policy it cannot enforce invites the reader to trust it.

## Splitting rules into a YAML file beside the bare config was rejected

Ordered branch rules in `<bare>/gitflower.yaml` with only flags in git config would have kept list ordering natural. Most-specific-wins made the ordering problem disappear, so the second file no longer buys anything.
