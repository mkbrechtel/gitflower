# Feature: Merge Request System

## Overview
Implement a local merge request system that supports stacked (dependent) merge requests, enabling complex feature development workflows similar to the linux kernel development workflow but with modern tooling. All MR data is stored directly in bare Git repositories with no database required.

## Goals
- Create and manage merge requests locally without external services
- Support stacked MRs where features build on each other
- Display per-layer changes (what each MR adds independently)
- Generate rebase instructions when base branches change
- Implement MRs using Git operations only (branches, refs, commits) - no external metadata

## User Stories

1. As a user, I want to create merge requests from feature branches with descriptions and target branches (including other MRs for stacking)
2. As a user, I want to visualize MR stacks showing dependencies and what each layer adds independently
3. As a user, I want to see when base branches change and get rebase commands to update my stack
4. As a user, I want to track review status and approvals for MRs in the stack
5. As a user, I want to view per-layer diffs (only this MR's changes) or cumulative diffs (all changes up to this point)
6. As an AI agent, I want to create and query MRs programmatically for automation

## Acceptance Criteria

### MR Creation
- [ ] CLI command creates MR with metadata
- [ ] MR ID generated automatically
- [ ] Target branch can be another MR
- [ ] Description supports markdown
- [ ] Reviewers can be specified

### MR Storage
- [ ] MRs represented using Git refs and branches only
- [ ] Source branch and target branch tracked via Git refs
- [ ] MR descriptions stored as commit messages or ref annotations
- [ ] Stack relationships determined by branch topology
- [ ] Survives repository cloning
- [ ] Bare repository based only - no database
- [ ] All data retrievable from standard Git operations
- [ ] Implementation details to be specified during planning phase

### Stack Visualization
- [ ] Show MR dependency tree
- [ ] Highlight current MR in stack
- [ ] Show approval status
- [ ] Display commit count per MR
- [ ] Show base branch changes

### Diff Display
- [ ] Per-layer diff (only commits from this MR)
- [ ] Cumulative diff (all changes up to this MR)
- [ ] Base comparison updates dynamically
- [ ] File change summary

### Rebase Management
- [ ] Detect when base branch updated
- [ ] Generate rebase commands
- [ ] Show conflicts preview
- [ ] Update stack after rebase
- [ ] Preserve MR metadata

### Web Interface
- [ ] MR list view with filters
- [ ] MR detail view with stack context
- [ ] Diff viewer with layer toggle
- [ ] Copy Git commands easily
- [ ] Mobile-responsive design
