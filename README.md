# GitFlower

A lean, local Git development server providing read-only web interface for repository visualization and management.

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
- (Optional) Tailwind CSS standalone CLI for CSS compilation

### Building from Source

```bash
# Clone the repository
git clone https://github.com/yourusername/gitflower.git
cd gitflower

# Build the application (includes Tailwind CSS if available)
./build.sh

# Or install Tailwind CSS first if missing
./build.sh --install-tailwind

# Or build manually:
make build

# Or just the Go binary:
go build -o bin/gitflower main.go
```

The `build.sh` script will:
1. Build Tailwind CSS (checks PATH first, then bin/tailwindcss)
2. Compile the Go binary to `bin/gitflower`

If Tailwind CSS is not found, run:
```bash
./build.sh --install-tailwind
```

This will automatically download the correct Tailwind CSS binary for your OS/architecture to `bin/tailwindcss`.

## Quick Start

1. **Create a repository:**
   ```bash
   gitflower create myproject.git
   ```

2. **List repositories:**
   ```bash
   gitflower list
   ```

3. **Start the web server:**
   ```bash
   gitflower web
   ```
   Then open http://localhost:8080 in your browser.

## Configuration

GitFlower uses YAML configuration stored at `~/.config/gitflower/config.yaml`:

```yaml
repos:
  directory: "./repos/"
  scan_depth: 3
  default_branch: "main"
web:
  address: ":8080"
  theme: "light"
  cache_ttl: 300
cli:
  output_format: "table"
  colors: true
  pager: "less"
log:
  level: "info"
  format: "text"
```

View or modify configuration:
```bash
# Show all configuration
gitflower config

# Get specific value
gitflower config repos.directory

# Set value (coming soon)
gitflower config repos.directory /path/to/repos
```

## Development

For development guidelines and architecture details, see [CLAUDE.md](CLAUDE.md).

### Development Server

```bash
# Run with auto-rebuild of CSS
make server

# Or run individual components
make tailwind-watch  # In one terminal
go run main.go web   # In another terminal
```

### Testing

```bash
# Run unit tests
go test ./...

# Run E2E tests
go test ./test/...
```

## Project Structure

```
gitflower/
├── app/       # Core application layer
├── repos/     # Repository management
├── iface/     # User interfaces
│   ├── cli/   # Command-line interface
│   ├── web/   # Web server
│   └── mcp/   # Model Context Protocol (planned)
├── docs/      # User documentation
├── pm/        # Project management
└── test/      # E2E tests
```

## License

MIT