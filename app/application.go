package app

import (
	"fmt"
	"log/slog"
	"os"

	"gitflower/repos"
)

// Run is the main entry point for the application
func Run(args []string) int {
	// Load configuration and parse global flags
	config, remainingArgs, err := load(args)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error loading configuration: %v\n", err)
		return 1
	}

	// Create logger
	logger := slog.New(slog.NewTextHandler(os.Stderr, nil))

	// Create repository store
	store, err := repos.NewStore(config.Repos, logger)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error creating repository store: %v\n", err)
		return 1
	}

	// Execute command
	if err := executeCommand(store, config, remainingArgs); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		return 1
	}

	return 0
}

// executeCommand routes to the appropriate command handler
func executeCommand(store *repos.Store, config *globalConfig, args []string) error {
	if len(args) == 0 {
		return fmt.Errorf("no command specified")
	}

	cmd := args[0]
	cmdArgs := args[1:]

	switch cmd {
	case "list":
		return list(store, cmdArgs)
	case "create":
		return create(store, config.Repos, cmdArgs)
	case "web":
		return webCmd(store, config.Web, cmdArgs)
	case "config":
		return configCmd(config, cmdArgs)
	default:
		return fmt.Errorf("unknown command: %s", cmd)
	}
}
