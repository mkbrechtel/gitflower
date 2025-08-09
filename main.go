package main

import (
	"fmt"
	"os"

	"gitflower/app"
	"gitflower/iface/cli"
	"gitflower/repos"
)

func main() {
	// Get config path from environment or use default
	configPath := os.Getenv("GITFLOWER_CONFIG")
	
	// Initialize application
	application, err := app.New(configPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error initializing application: %v\n", err)
		os.Exit(1)
	}
	
	// Initialize repository store
	repoStore := repos.NewStore(&application.Config().Repos, application.Logger())
	application.SetRepoStore(repoStore)
	
	// Create CLI interface
	cliInterface := cli.New(application)
	
	// Execute CLI with remaining arguments
	if err := cliInterface.Execute(os.Args[1:]); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
}