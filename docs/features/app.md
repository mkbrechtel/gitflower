# Application Architecture

GitFlower follows a clean, lightweight architecture with minimal dependencies and clear separation of concerns.

## Architecture Overview

### Package Structure
```
gitflower/
├── app/                    # Core application and CLI commands
│   ├── web/               # Web server
│   └── mcp/               # Model Context Protocol (planned)
├── repos/                  # Repository management
│   └── git/               # Git operations
└── main.go                # Minimal entry point
```

## Core Design

### main.go
- Minimal entry point - just 3 lines
- Calls `app.Run(os.Args)` and exits with return code
- No business logic or configuration

### app package
The app package contains all CLI logic and orchestration:

- **application.go**: Main `Run()` function that orchestrates everything
- **config.go**: Configuration loading with private `load()` function
- **list.go, create.go, web.go**: Command implementations
- Each command is a simple function named after the command

### Command Flow

1. `main.go` → `app.Run(args)`
2. `app.Run()` calls private `load()` to parse global flags and read config
3. Creates `repos.Store` with configuration
4. Routes to command function based on first argument
5. Command functions receive Store and relevant config
6. For interfaces like web: `web.Run(store, config)`

## Configuration

### Priority Order (highest wins)
1. **Defaults** - Hardcoded in `load()` function
2. **Config file** - YAML from `~/.config/gitflower/config.yaml`
3. **Environment variables**:
   - `GITFLOWER_CONFIG` - Config file path
   - `GITFLOWER_REPOS` - Repositories directory
4. **Command-line flags** (highest priority):
   - `-c` - Config file path
   - `-r` - Repositories directory

### Config Structure
```yaml
# Repository settings (used by repos package)
repos:
  directory: "./repos/"
  scan_depth: 3
  default_branch: "main"

# Web server settings (used by app/web)
web:
  address: ":8747"

# Logging settings
log:
  level: "info"
```

Note: CLI doesn't need configuration - it uses flags per command.

## Package Dependencies

```
main.go (3 lines)
   ↓
app.Run() (orchestration)
   ↓
repos.Store (repository management)
   ↓
app/web.Run() (web server, when needed)
```

### Key Design Principles

1. **No circular dependencies**: The app package imports web.Config for type definition, but web.Run is called dynamically
2. **Private configuration**: The `load()` function is private to the app package
3. **Run pattern**: Interfaces like web use `Run(store, config)` for clean separation
4. **Minimal main**: Entry point has no logic, just forwarding
5. **Command = function**: Each command is a simple function (list, create, web)

## Adding New Commands

To add a new command:

1. Create a new file in `app/` named after the command (e.g., `app/status.go`)
2. Define a function with signature: `func commandName(store *repos.Store, args []string) error`
3. Add a case in `executeCommand()` in `application.go`
4. Parse command-specific flags inside the function

Example:
```go
// app/status.go
package app

func status(store *repos.Store, args []string) error {
    // Parse flags, implement command
    return nil
}
```

## Interface Pattern

For complex subsystems (web, MCP), use the Run pattern:

```go
// app/web/server.go
func Run(store *repos.Store, config Config) error {
    // Start server with store and config
}
```

This keeps the subsystem decoupled while allowing the app package to orchestrate.