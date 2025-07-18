# Feature: CLI Tools

## Overview
Provide a comprehensive command-line interface for managing CodeFlow repositories, creating merge requests, configuring the server, and integrating with existing Git workflows.

## Goals
- Enable all CodeFlow operations from the command line
- Integrate seamlessly with existing Git workflows
- Provide clear, helpful command output
- Support automation and scripting
- Maintain consistency with Git conventions

## User Stories

1. As a user, I want to start the web server or MCP server from the command line
2. As a user, I want to initialize and manage CodeFlow repositories from the command line
3. As a user, I want to create, list, update, and visualize merge requests and their stacks via CLI
4. As a user, I want to install and manage Git hooks that integrate with CodeFlow
5. As a user, I want the CLI to generate helpful Git commands for common workflows
6. As a user, I want consistent, well-documented commands with helpful output and error messages
7. As a user, I want to export data in different formats (JSON, patches) for integration with other tools

## Acceptance Criteria

### Command Structure
- [ ] Main command: `codeflow` or `cf` alias
- [ ] Subcommands follow noun-verb pattern
- [ ] Consistent flag naming
- [ ] Help text for all commands
- [ ] Examples in help output

### Repository Commands
- [ ] `codeflow init [path]` - Initialize repository
- [ ] `codeflow repo list` - List repositories
- [ ] `codeflow repo add <path>` - Add existing repo
- [ ] `codeflow repo info` - Show repo details
- [ ] `codeflow repo config` - Manage settings

### MR Commands
- [ ] `codeflow mr create` - Create new MR
- [ ] `codeflow mr list` - List MRs
- [ ] `codeflow mr show <id>` - Show MR details
- [ ] `codeflow mr stack` - Show stack visualization
- [ ] `codeflow mr update <id>` - Update MR
- [ ] `codeflow mr rebase <id>` - Generate rebase commands

### Server Commands
- [ ] `codeflow web` - Start web server
- [ ] `codeflow mcp` - Start MCP server (CLI-only)
- [ ] `codeflow mcp --read-only` - Start MCP server in read-only mode

### Hook Commands
- [ ] `codeflow hook install` - Install Git hooks
- [ ] `codeflow hook remove` - Remove Git hooks
- [ ] `codeflow hook list` - Show installed hooks
- [ ] `codeflow hook config` - Configure hooks

### Output Formats
- [ ] Human-readable by default
- [ ] JSON output with --json flag
- [ ] Quiet mode with -q flag
- [ ] Verbose mode with -v flag
- [ ] Color output (respecting NO_COLOR)
