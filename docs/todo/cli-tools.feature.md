# Feature: CLI Tools

## Overview
Provide a comprehensive command-line interface for managing GitFlower repositories, creating merge requests, configuring the server, and integrating with existing Git workflows.

## Goals
- Enable all GitFlower operations from the command line
- Integrate seamlessly with existing Git workflows
- Provide clear, helpful command output
- Support automation and scripting
- Maintain consistency with Git conventions

## User Stories

1. As a user, I want to start the web server or MCP server from the command line
2. As a user, I want to initialize and manage GitFlower repositories from the command line
3. As a user, I want to create, list, update, and visualize merge requests and their stacks via CLI
4. As a user, I want to install and manage Git hooks that integrate with GitFlower
5. As a user, I want the CLI to generate helpful Git commands for common workflows
6. As a user, I want consistent, well-documented commands with helpful output and error messages
7. As a user, I want to export data in different formats (JSON, patches) for integration with other tools

## Acceptance Criteria

### Command Structure
- [ ] Main command: `gitflower` or `gf` alias
- [ ] Subcommands follow noun-verb pattern
- [ ] Consistent flag naming
- [ ] Help text for all commands
- [ ] Examples in help output

### Repository Commands
- [ ] `gitflower init [path]` - Initialize repository
- [ ] `gitflower repo list` - List repositories
- [ ] `gitflower repo add <path>` - Add existing repo
- [ ] `gitflower repo info` - Show repo details
- [ ] `gitflower repo config` - Manage settings

### MR Commands
- [ ] `gitflower mr create` - Create new MR
- [ ] `gitflower mr list` - List MRs
- [ ] `gitflower mr show <id>` - Show MR details
- [ ] `gitflower mr stack` - Show stack visualization
- [ ] `gitflower mr update <id>` - Update MR
- [ ] `gitflower mr rebase <id>` - Generate rebase commands

### Server Commands
- [ ] `gitflower web` - Start web server
- [ ] `gitflower mcp` - Start MCP server (CLI-only)
- [ ] `gitflower mcp --read-only` - Start MCP server in read-only mode

### Hook Commands
- [ ] `gitflower hook install` - Install Git hooks
- [ ] `gitflower hook remove` - Remove Git hooks
- [ ] `gitflower hook list` - Show installed hooks
- [ ] `gitflower hook config` - Configure hooks

### Output Formats
- [ ] Human-readable by default
- [ ] JSON output with --json flag
- [ ] Quiet mode with -q flag
- [ ] Verbose mode with -v flag
- [ ] Color output (respecting NO_COLOR)
