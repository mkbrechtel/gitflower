# Feature: Repository Management

## Overview
Enable users to discover, browse, and manage bare Git repositories through CLI commands, with documentation available in the web interface.

## Goals
- Provide easy discovery of local bare repositories via CLI
- Display repository metadata and health status
- Control repository visibility and access
- Support repository initialization and configuration
- Document repository management workflows in web UI

## User Stories

1. As a user, I want to discover all bare repositories in configured directories via CLI with their metadata
2. As a user, I want to initialize new CodeFlow repositories or convert existing bare repos with a single command
3. As a user, I want to list and filter repositories by name, activity, or other criteria using CLI
4. As a user, I want repository access controlled by filesystem permissions for security
5. As a user, I want to see documentation in the web UI about how to manage repositories
6. As an AI agent, I want to list and query repository information programmatically

## Acceptance Criteria

### CLI Commands
- [ ] `codeflow init <path>` creates new bare repository
- [ ] `codeflow init --convert <path>` converts existing bare repo
- [ ] `codeflow config repo.scan-paths` configures scan directories
- [ ] `codeflow list` shows all repositories

### Web Interface
- [ ] Documentation page explaining how to use CLI commands
- [ ] Examples of common repository management tasks
- [ ] Command reference with descriptions
- [ ] No actual repository management functionality in web UI

### Repository Metadata
- [ ] Repository size calculated from objects
- [ ] Last update time from most recent commit
- [ ] Branch count includes all refs/heads/*
- [ ] MR count from refs/codeflow/merge-requests/*

### Performance
- [ ] Repository listing loads in <2 seconds for 100 repos
- [ ] Metadata is cached and refreshed periodically
- [ ] Large repositories don't block UI
