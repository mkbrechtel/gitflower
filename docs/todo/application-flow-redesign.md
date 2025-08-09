# Application Flow Redesign

## Problem
The current architecture has no unified application context. Each CLI command independently loads configuration, the web server is disconnected from Git functionality, and there's no clean way to share state between components.

## Solution
Implement a layered architecture with centralized application state and YAML-based configuration where each package owns its config section.

## Architecture

### Package Structure
```
gitflower/
├── app/                    # Core application with central state
├── repos/                  # Repository hierarchy and folder management
│   └── git/               # Individual Git repository operations
├── iface/                  # User interfaces
│   ├── cli/               # Command-line interface
│   ├── web/               # Web server
│   └── mcp/               # Model Context Protocol (stdio)
└── main.go                # Entry point
```

### Configuration Design
Single YAML file with package-specific sections:
- `repos:` - Repository settings (directory, scan depth, default branch)
- `web:` - Web server settings (address, theme, caching)
- `cli:` - CLI settings (output format, colors, pager)
- `mcp:` - MCP settings (stdio mode)
- `log:` - Logging configuration

Each package defines its own Config struct and validation logic.

### Core Components

**Application (`app/`)**: Central application struct holding configuration, repository store, and logger. Single initialization point that creates all shared resources.

**Repository Store (`repos/`)**: Manages the repository hierarchy and folder structure. Provides discovery and organization of multiple repositories within the configured directory structure.

**Git Operations (`repos/git/`)**: Provides models and functions to work with Git bare repositories. Handles Git operations for individual repositories, merge request storage (as Git refs), and repository-specific functionality. No external database - everything stored in Git.

**Interfaces (`iface/`)**: Each interface (CLI, Web, MCP) receives the Application instance and its specific config section. Interfaces are independent and don't know about each other.

### Dependency Flow
- Main initializes Application with config path
- Application loads YAML config and creates repository store
- Interfaces are created with Application instance
- All operations go through the central Application

No circular dependencies - clean hierarchical flow.