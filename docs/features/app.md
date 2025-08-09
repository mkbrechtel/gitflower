# Application Flow Architecture

GitFlower uses a layered architecture with centralized application state management.

## Architecture Overview

### Package Structure
```
gitflower/
├── app/                    # Core application with central state
├── repos/                  # Repository hierarchy and folder management
│   └── git/               # Individual Git repository operations  
├── iface/                  # User interfaces
│   ├── cli/               # Command-line interface
│   ├── web/               # Web server
│   └── mcp/               # Model Context Protocol (planned)
└── main.go                # Entry point
```

### Core Components

**Application (`app/`)**: Central application struct holding configuration, repository store, and logger. Single initialization point that creates all shared resources.

**Repository Store (`repos/`)**: Manages the repository hierarchy and folder structure. Provides discovery and organization of multiple repositories within the configured directory structure.

**Git Operations (`repos/git/`)**: Provides models and functions to work with Git bare repositories. Handles Git operations for individual repositories, merge request storage (as Git refs), and repository-specific functionality.

**Interfaces (`iface/`)**: Each interface (CLI, Web, MCP) receives the Application instance and its specific config section. Interfaces are independent and don't know about each other.

## Configuration

GitFlower uses a single YAML configuration file with package-specific sections:

```yaml
# Repository management settings
repos:
  directory: "./repos/"        # Where repositories are stored
  scan_depth: 3                # How deep to scan for repos
  default_branch: "main"       # Default branch name

# Web server settings  
web:
  address: ":8747"            # Web server address
  theme: "light"              # UI theme (light/dark)
  caching: true               # Enable caching

# CLI settings
cli:
  output_format: "table"      # Output format (table/json/yaml)
  colors: true                # Enable colored output
  pager: false                # Use pager for long output

# MCP server settings
mcp:
  stdio_mode: true            # Run in stdio mode

# Logging settings
log:
  level: "info"               # Log level (debug/info/warn/error)
```

Configuration can be:
- Stored at `~/.config/gitflower/config.yaml`
- Overridden with `GITFLOWER_CONFIG` environment variable
- Viewed with `gitflower config`
- Modified with `gitflower config <key> <value>` (planned)

## Dependency Flow

1. Main initializes Application with config path
2. Application loads YAML config and creates repository store
3. Interfaces are created with Application instance
4. All operations go through the central Application

This design ensures:
- No circular dependencies
- Clean hierarchical flow
- Centralized state management
- Easy testing through dependency injection
- Clear separation of concerns