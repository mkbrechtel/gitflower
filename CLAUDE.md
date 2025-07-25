# GitFlower Development Guidelines

This document provides instructions for AI assistants and developers working on the GitFlower project.

## Project Overview

GitFlower is a lean, local Git development server that provides:
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
gitflower/
├── cli/      # Command-line interface
├── web/      # Web server and UI
├── git/      # Git operations library
├── mcp/      # Model Context Protocol server
└── pm/       # Project management docs
```

## Development Tools

### Go Documentation
- Use `go doc` to view documentation for Go packages and functions
- Examples:
  - `go doc fmt.Printf` - View documentation for a specific function
  - `go doc -all ./git` - View all documentation for a package
  - `go doc github.com/go-git/go-git/v6` - View external package documentation

## Feature Development Workflow

**IMPORTANT**: When implementing a feature, go through this workflow step-by-step and inform the user which step you are currently working on. This ensures transparency and allows the user to guide the process.

### 0. Feature Specification
- Check if a feature specification exists in `pm/<feature-name>.feature.md`
- Read and understand all requirements, goals, and acceptance criteria
- If no spec exists, work with the user to define requirements first
- Get user approval on the feature specification before proceeding to Step 1
- After approval, commit the feature specification to version control

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

### 6. Documentation
- Move the feature specification from `pm/` to `docs/` directory
- Rewrite the feature specification as user-facing documentation
- Transform acceptance criteria into usage examples
- Document all new features, commands, and workflows
- Include practical examples and troubleshooting sections
- Use clear, concise language focused on how to use the feature

### 7. Feature Review & Merge
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

## Technology Stack

### Core Technologies
- **Go 1.24.2** - Primary programming language
- **go-git/v6** - Pure Go implementation for Git operations
- **net/http** - Built-in Go HTTP server (no external framework needed)
- **html/template** - Go's standard template engine with go:embed
- **Tailwind CSS** - Utility-first CSS framework (standalone CLI)
- **Templates** - Always use go:embed for templates in production code

### Build System
- **Make** - Build automation with targets for:
  - `make tailwind` - Build CSS
  - `make tailwind-watch` - Watch mode for CSS development
  - `make server` - Run the development server
  - `make build` - Build all binaries
  - `make clean` - Clean build artifacts

### Project Dependencies
- Minimal external dependencies by design
- go-git for all Git operations
- No database - Git is the source of truth
- No JavaScript framework - server-side rendering only

### Development Commands
- `go run main.go web` - Run the web server
- `bin/gitflower web -addr :8080` - Run web server with compiled binary
- `make server` - Run development server with auto-built CSS
- `make build` - Build the gitflower binary
