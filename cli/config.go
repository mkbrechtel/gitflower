package cli

import (
	"flag"
	"fmt"
	"strings"

	"codeflow/cfg"
)

func init() {
	Register(&Command{
		Name:        "config",
		Description: "Get or set configuration values",
		Run:         executeConfig,
	})
}

func executeConfig(args []string) error {
	fs := flag.NewFlagSet("config", flag.ExitOnError)
	fs.Usage = func() {
		fmt.Println("Usage: codeflow config <key> [value]")
		fmt.Println("\nGet or set configuration values.")
		fmt.Println("\nAvailable keys:")
		fmt.Println("  reposDirectory    Directory containing repositories (default: ./repos/)")
		fmt.Println("\nExamples:")
		fmt.Println("  codeflow config reposDirectory           # Get current value")
		fmt.Println("  codeflow config reposDirectory ~/repos   # Set new value")
	}

	if err := fs.Parse(args); err != nil {
		return err
	}

	if fs.NArg() < 1 {
		fs.Usage()
		return fmt.Errorf("expected at least one argument")
	}

	key := fs.Arg(0)

	// Load configuration
	if err := cfg.Load(); err != nil {
		return fmt.Errorf("loading config: %w", err)
	}

	// Get value
	if fs.NArg() == 1 {
		value, err := cfg.Get(key)
		if err != nil {
			return err
		}
		fmt.Println(value)
		return nil
	}

	// Set value
	value := strings.Join(fs.Args()[1:], " ")
	if err := cfg.Set(key, value); err != nil {
		return err
	}

	fmt.Printf("Set %s = %s\n", key, value)
	return nil
}