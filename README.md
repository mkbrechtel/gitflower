# GitFlower

A lean, local Git development server providing a read-only web interface for repository visualization and management.

## Features

- 📁 Repository management with organization folders
- 🌐 Read-only web interface for browsing
- 🔒 Security through filesystem permissions
- 🚀 Local-first, privacy-focused design
- 🤖 AI-friendly APIs (MCP support planned)

## Installation

### Prerequisites

- Go 1.21 or higher
- Git

### Quick Install

```bash
# Clone and build
git clone https://github.com/yourusername/gitflower.git
cd gitflower
./build.sh

# If Tailwind CSS is missing, install it:
./build.sh --install-tailwind
```

## Usage

### Basic Commands

```bash
# Create a new repository
gitflower create myproject.git

# List all repositories
gitflower list

# Start web interface (http://localhost:8747)
gitflower web

# View configuration
gitflower config
```

### Configuration

GitFlower stores configuration at `~/.config/gitflower/config.yaml`:

```yaml
repos:
  directory: "./repos/"        # Where repositories are stored
  scan_depth: 3                # How deep to scan for repos
  default_branch: "main"       # Default branch name
web:
  address: ":8747"            # Web server address
  theme: "light"              # UI theme (light/dark)
cli:
  output_format: "table"      # Output format (table/json/yaml)
  colors: true                # Enable colored output
log:
  level: "info"               # Log level (debug/info/warn/error)
```

Override config location with `GITFLOWER_CONFIG` environment variable:
```bash
export GITFLOWER_CONFIG=/path/to/config.yaml
gitflower list
```

## Development

### Quick Start

```bash
# Run with test configuration
./run.sh list
./run.sh web

# Build the project
./build.sh

# Run development server with auto-reload
make server
```

### Project Structure

```
gitflower/
├── app/       # Core application layer
├── repos/     # Repository management
├── iface/     # User interfaces
│   ├── cli/   # Command-line interface
│   ├── web/   # Web server
│   └── mcp/   # Model Context Protocol (planned)
├── docs/      # Documentation
│   └── todo/  # Feature specifications
└── test/      # Tests and test configuration
```

### Testing

```bash
# Run all tests
go test ./...

# Run with verbose output
go test -v ./...
```

## Contributing

See [CLAUDE.md](CLAUDE.md) for development guidelines and coding standards.

## License

MIT