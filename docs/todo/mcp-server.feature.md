# Feature: MCP Server

## Overview
Implement a Model Context Protocol (MCP) server that exposes Git repository information to AI agents, enabling them to understand project structure, analyze code, and assist with development tasks. The server supports both read-only and read-write modes for different agent capabilities.

## Goals
- Provide structured access to repository data for AI agents
- Enable context-aware assistance for developers
- Support efficient querying of large repositories
- Configure agents with different permission levels (read-only vs read-write)
- Provide instructional prompts to guide LLMs in using GitFlower effectively
- Integrate seamlessly with AI development tools

## User Stories

1. As an AI agent, I want to discover and query repositories with their metadata and current status
2. As an AI agent, I want to read file contents and understand project structure for code analysis
3. As an AI agent, I want to access branch information, commit history, and understand development flow
4. As an AI agent, I want to query merge requests, their dependencies, and analyze changes
5. As a developer, I want my AI assistant to have context about my current work and suggest appropriate Git commands
6. As an AI agent with write permissions, I want to create branches, commits, and merge requests programmatically
7. As a developer, I want to configure which agents have read-only vs read-write access
8. As an AI agent, I want to access prompts that teach me how to use GitFlower effectively
9. As an AI agent, I want efficient, structured access to repository data with proper error handling

## Acceptance Criteria

### MCP Stdio Server
- [ ] JSON-RPC 2.0 compliant stdio server
- [ ] Proper error handling and codes
- [ ] Request/response logging
- [ ] Mode configuration (read-only or read-write)
- [ ] Graceful shutdown handling

### MCP Tools Implementation

#### Read-Only Tools
- [ ] `repository_list` - List all repositories
- [ ] `repository_info` - Get repository details
- [ ] `file_read` - Read file contents
- [ ] `file_list` - List directory contents
- [ ] `file_search` - Search for files
- [ ] `git_branches` - List branches
- [ ] `git_commits` - Get commit history
- [ ] `git_diff` - Get diff between refs
- [ ] `mr_list` - List merge requests
- [ ] `mr_info` - Get MR details with stack information
- [ ] `mr_diff` - Get MR changes

#### Write Tools (when mode enabled)
- [ ] `git_branch_create` - Create new branch
- [ ] `git_commit_create` - Create new commit
- [ ] `git_push` - Push changes
- [ ] `file_write` - Write file contents
- [ ] `file_delete` - Delete files
- [ ] `mr_create` - Create new MR
- [ ] `mr_update` - Update MR metadata

### MCP Prompts Implementation
- [ ] `gitflower_overview` - How to use GitFlower system
- [ ] `repository_navigation` - How to explore repositories
- [ ] `mr_workflow` - How to work with merge requests
- [ ] `stacked_mrs` - Understanding stacked MRs
- [ ] `code_review` - How to review code effectively
- [ ] `git_commands` - Common Git operations in GitFlower
- [ ] `best_practices` - GitFlower development best practices
