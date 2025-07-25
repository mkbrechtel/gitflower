package cli

import (
	"flag"
	"fmt"
	"os"
)

type Command struct {
	Name        string
	Description string
	Run         func(args []string) error
}

var commands = map[string]*Command{}

func Register(cmd *Command) {
	commands[cmd.Name] = cmd
}

func Execute() {
	if len(os.Args) < 2 {
		printUsage()
		os.Exit(1)
	}

	cmdName := os.Args[1]
	cmd, exists := commands[cmdName]
	if !exists {
		fmt.Fprintf(os.Stderr, "Unknown command: %s\n\n", cmdName)
		printUsage()
		os.Exit(1)
	}

	// Reset flag parsing for subcommand
	flag.CommandLine = flag.NewFlagSet(cmdName, flag.ExitOnError)
	
	if err := cmd.Run(os.Args[2:]); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
}

func printUsage() {
	fmt.Fprintf(os.Stderr, "Usage: gitflower <command> [arguments]\n\n")
	fmt.Fprintf(os.Stderr, "Available commands:\n")
	for name, cmd := range commands {
		fmt.Fprintf(os.Stderr, "  %-10s %s\n", name, cmd.Description)
	}
}