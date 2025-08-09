# GitFlower Coding Standards

This document outlines coding standards and development principles for the GitFlower project.

## Development Philosophy

1. **Simplicity First**: No databases, minimal dependencies, leverage Git as the source of truth
2. **Security by Design**: POSIX/SSH authentication, read-only web interface, filesystem permissions
3. **Local-First**: Everything runs on local infrastructure, no cloud dependencies
4. **Developer Experience**: Clear Git commands, helpful visualizations, AI-friendly APIs

## Architecture

### Layered Design

The application follows a clean layered architecture:

```
main.go
   ↓
app/Application (central state & config)
   ↓
tree/Store (repository management)
   ↓
app/* (user interfaces: CLI, Web, MCP)
```

### Configuration Design

Each package owns its configuration section in the YAML file:
- `repos:` - Repository settings (tree package)
- `web:` - Web server settings (iface/web package)
- `mcp:` - MCP settings (iface/mcp package)
- `log:` - Logging configuration (app package)

The Config struct is supposed to be in the package needing the config, for example web.Config contains the config for the web server. It gets included by the app package.

## Coding Standards

### Go Conventions
- Follow standard Go idioms and conventions
- Keep functions small and focused (< 50 lines preferred)
- Document all exported functions and types
- Use meaningful variable and function names
- Handle errors explicitly, don't ignore them

### Package Structure
- Each package should have a clear, single responsibility
- Avoid circular dependencies between packages
- Interfaces should be defined where they are used, not where implemented
- Keep package APIs minimal and focused

### Git Operations
- Use go-git/v6 library for all Git operations
- Always work with bare repositories for server-side operations
- Store metadata as Git refs (e.g., `refs/gitflower/merge-requests/*`)
- Never modify repository contents via web interface (read-only)

### Security
- Never trust user input from web interface
- Validate all Git references and paths
- Use OS permissions for access control
- Sanitize paths to prevent directory traversal
- No write operations via HTTP

### Testing
- Write unit tests for all new functionality
- Keep test coverage above 70%
- Use table-driven tests where appropriate
- Mock external dependencies in tests

## Feature Development Workflow

**IMPORTANT**: Developers must follow this workflow step-by-step when implementing features:

### 0. Feature Specification
- Check if a feature specification exists in `docs/features/proposals/<feature-name>.feature.md`
- If no spec exists, work with the maintainer to define requirements first
- Get maintainer approval on the feature specification before proceeding

### 1. Implementation Planning
- Read the feature specification thoroughly
- Review already implemented features in `docs/features/` to understand existing functionality
- Propose a detailed implementation plan to the maintainer
- Get explicit approval from the maintainer before proceeding

### 2. Feature Branch
- Create a new feature branch: `git checkout -b feature/<feature-name>`
- Keep the branch name descriptive and linked to the feature

### 3. Implementation
- Implement according to the approved spec
- Follow the package structure and coding standards
- Write clean, modular, testable code
- Ensure all existing features continue to work as documented in `docs/features/`

### 4. Testing
- Write comprehensive unit tests for all new code
- Create E2E test scenarios covering user stories in `test/e2e_<feature-name>_test.go`
- Run all existing E2E tests to ensure no regressions in implemented features
- Ensure all tests pass before proceeding

### 5. Documentation
- Update user documentation in docs/
- Document all new commands, features, and APIs
- Include practical examples and common use cases

### 6. Review & Merge
- Present the complete feature branch to the maintainer
- Demonstrate all implemented functionality
- Address any feedback from the maintainer
- Assist with merging to the main branch once approved

## Development Tools

### Go Documentation

**Note:** Developers should use `go doc` to explore and understand the codebase. This is the standard Go way to look up function signatures, type definitions, and package documentation.

### Usage
```bash
# View package documentation
go doc ./app
go doc ./tree

# View specific function
go doc tree.Store.Create

# View with examples
go doc -all ./tree
```


## Technology Stack

### Core Technologies
- **Go 1.24+** - Primary programming language
- **go-git/v6** - Pure Go Git implementation
- **net/http** - Built-in HTTP server (no external framework)
- **html/template** - Go's template engine with go:embed
- **Tailwind CSS** - Utility-first CSS (standalone CLI)

### Dependencies Policy
- Minimize external dependencies
- Prefer standard library over external packages
- All Git operations through go-git
- No database - Git is the source of truth
- No JavaScript framework - server-side rendering only

## Templates and Static Files
- ALWAYS use go:embed for templates in production code
- Templates go in `iface/web/templates/`
- Static files go in `iface/web/static/`
- CSS is built with Tailwind CSS to `iface/web/static/css/`

### CSS Styling Guidelines
- **ONLY use Tailwind utility classes** - No inline styles or custom CSS
- All styling must be done through Tailwind utility classes (e.g., `class="bg-blue-500 text-white p-4"`)
- DO NOT write static CSS styles or use `style=""` attributes
- DO NOT create custom CSS files beyond the Tailwind-generated output
- For repeated styling patterns, use Go templates/partials instead of @apply

## Error Handling
- Always return errors up the call stack
- Wrap errors with context using `fmt.Errorf`
- Log errors at the point where they're handled
- Never panic in library code

## Logging
- Use structured logging with slog
- Include relevant context in log messages
- Use appropriate log levels (debug, info, warn, error)
- Don't log sensitive information

## File Organization
- One type per file for large types
- Group related small types in a single file
- Test files should be in the same package
- Use `_test.go` suffix for test files

## Commit Messages
- Use conventional commit format when possible
- Keep first line under 50 characters
- Provide detailed description if needed
- Reference issues when applicable

## Project Management

- Feature specifications go in `docs/features/proposals/<feature-name>.feature.md`
- Once implemented, rewrite as user documentation in `docs/features/`
- Use Git issues for bug tracking
- Keep a CHANGELOG.md for releases

## Important Development Notes

- NEVER update git config automatically
- NEVER create files unless explicitly needed
- ALWAYS prefer editing existing files over creating new ones
- NEVER proactively create documentation unless requested
- DO NOT use git commands with interactive flags (-i)
- ALWAYS use the build script `./build.sh` to build gitflower
- ALWAYS check for existing feature specs before implementing
