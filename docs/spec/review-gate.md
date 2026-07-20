---
#SPDX-FileCopyrightText: 2026 Markus Katharina Brechtel <markus.katharina.brechtel@thengo.net>
#SPDX-License-Identifier: EUPL-1.2
---

# `review-gate` — branch protection through submitted reviews

The `review-gate` branch-protection workflow makes a protected push conditional on submitted `.review` files ([`dot-review-format.md`](./dot-review-format.md)). It runs server-side like every branch workflow and reads only review commits reachable in the pushed history — never notes refs; drafts gate nothing.

## What is gated

A push updating a protected branch must be a merge, and **every merge onto the integration branch since it forked from the protected branch** must meet the required conditions below. The reviewed object is always the merge commit itself: a covering review is a scoped `# Review Merge-Commit …` file whose heading names the merge's full OID. Coverage is by SHA — a redone integrator merge is a new object and starts with no verdicts.

## The two conditions

**Approval** — at least one `- Approved-by: <Name> <<email>>` from an eligible owner in a submitted review covering the merge, and no standing `- Rejected-by:` from an eligible owner.

**Review** — at least one `- Reviewed-by: <Name> <<email>>` from an eligible owner in a covering review, and every finding those reviews raised is resolved: each `## Issue` carries a `- Resolved-by:` line. Resolution may arrive in later review commits merged into the integration branch — validation is over the integration history, fix-forward.

Which conditions a branch requires is per-branch configuration: approval, review, or both.

## Eligibility — `CODEOWNERS`

Eligible approvers and reviewers come from a `CODEOWNERS` file at the root of the protected branch's tree, read at its pre-push tip — policy a work branch could edit is not policy; changes to `CODEOWNERS` take effect once merged.

Pattern-per-line syntax, owners written as plain email addresses matching the format's `Name <email>` event attribution.

Example:
```
*               maintainer@example.org
docs/**         docs-team@example.org maintainer@example.org
src/parser/**   parser@example.org
```

Owners are evaluated against the paths the gated merge touches: for each touched path the last matching pattern's owners apply, and a condition is met when every touched path has a satisfying verdict from one of its owners. A touched path no pattern matches has no owners and can never satisfy a required condition — own the rest with a catch-all `*` line.

## Configuration

Per-branch keys in the bare repository's git config, following [`repo-config.md`](./repo-config.md):

Example:
```
[gitflower "branch.main"]
    workflow = protected
    requireApproval = true
    requireReview = true
```

`requireApproval` and `requireReview` are independent booleans; unset means not required. Setting neither leaves the branch gated only by its other protection rules.

## Compatibility signal

The verdict events are kernel trailers verbatim, so trailer-grepping tools read submitted reviews natively. Kernel-style trailers in commit messages (`Reviewed-by:`, `Acked-by:`, `Signed-off-by:`) are surfaced as advisory sign-off signals; the gate's conditions are satisfied only by verdict events in submitted reviews.

# Considerations

## Self-approval

Whether the gate refuses an author approving their own merge, or merely surfaces it, is still open — tracked as Q3 in [`../../issues/review-approval.md`](../../issues/review-approval.md). An author can be a `CODEOWNERS` owner, so eligibility alone doesn't answer it.

## Unowned paths fail closed

GitHub's `CODEOWNERS` treats unowned files as needing no review; here an unowned touched path makes a required condition unsatisfiable instead. Silence should not waive review on the paths nobody thought about — the catch-all line makes the waiver explicit if a project wants one.

## Provisional key names

`requireApproval` / `requireReview` follow the `allowDirectPush` / `requireLinearHistory` naming style; final names land with the `review-gate` implementation in `repo-config.md`.

## Commit-message trailers don't gate

An earlier sketch accepted kernel trailers on commits as first-class approval. The gate reads submitted reviews only: a trailer in a commit message has no covering-object semantics, no `CODEOWNERS` path evaluation, and no findings to resolve — it stays an advisory signal for humans and dashboards.
