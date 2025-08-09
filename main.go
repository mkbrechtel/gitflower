package main

import (
	"fmt"
	"os"

	"gitflower/app"
	"gitflower/iface/cli"
)

func main() {
	// Get config path from environment or use default
	configPath := os.Getenv("GITFLOWER_CONFIG")
	
	// Initialize application with all components
	application, err := app.New(configPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error initializing application: %v\n", err)
		os.Exit(1)
	}
	
	// Create CLI interface
	cliInterface := cli.New(application)
	
	// Execute CLI with remaining arguments
	if err := cliInterface.Execute(os.Args[1:]); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
}