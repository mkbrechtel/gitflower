# CodeFlow Development Guidelines

This document provides instructions for AI assistants and developers working on the CodeFlow project.

## Project Overview

CodeFlow is a lean, local Git development server that provides:
- Read-only web interface for repository visualization
- Stacked merge request workflows
- Local-first, privacy-focused design
- Integration with AI agents via MCP

## Development Philosophy

1. **Simplicity First**: No databases, minimal dependencies, leverage Git as the source of truth
2. **Security by Design**: POSIX/SSH authentication, read-only web interface, filesystem permissions
3. **Local-First**: Everything runs on local infrastructure, no cloud dependencies
4. **Developer Experience**: Clear Git commands, helpful visualizations, AI-friendly APIs

## Project Structure

```
codeflow/
├── cli/      # Command-line interface
├── web/      # Web server and UI
├── git/      # Git operations library
├── mcp/      # Model Context Protocol server
└── pm/       # Project management docs
```

## Development Workflow

### 1. Implementation Planning
- Read the feature specification in `pm/<feature-name>.feature.md`
- Propose a detailed implementation spec to the user
- Refine the spec based on user feedback
- Get explicit approval before proceeding

### 2. Feature Branch Creation
- Create a new feature branch: `git checkout -b feature/<feature-name>`
- Keep the branch name descriptive and linked to the feature

### 3. Implementation
- Implement the feature according to the approved spec
- Follow the package structure (git/, cli/, web/, mcp/)
- Write clean, modular code
- Focus on completing the functionality first

### 4. Unit Testing
- Write comprehensive unit tests for all new code
- Run tests and fix any failures
- Ensure good test coverage
- Commit with message indicating preliminary implementation

### 5. End-to-End Testing
- Create E2E test scenarios in `test/` directory
- Test all user stories from the feature spec
- Verify the feature works as intended
- Make another commit for the completed feature

### 6. Feature Review & Merge
- Present the complete feature branch to the user
- Demonstrate all implemented functionality
- Help user perform acceptance testing
- Propose merging to main branch
- Assist with the merge process

### Code Style
- Follow standard Go conventions
- Keep functions small and focused
- Document exported functions
- Use meaningful variable names

### Git Operations
- Use go-git library for Git operations
- Always work with bare repositories
- Store metadata as Git refs (e.g., `refs/codeflow/merge-requests/*`)
- Never modify repository contents via web interface

## Security Considerations

- Never trust user input from web interface
- Validate all Git references
- Use OS permissions for access control
- Sanitize paths to prevent directory traversal
- No write operations via HTTP

## Project Management

Project management is done in the `pm/` directory with markdown files.
