package cli

import (
	"flag"
	"fmt"
	"path/filepath"

	"codeflow/cfg"
	"codeflow/git"
)

func init() {
	Register(&Command{
		Name:        "create",
		Description: "Create a new bare repository",
		Run:         executeCreate,
	})
}

func executeCreate(args []string) error {
	fs := flag.NewFlagSet("create", flag.ExitOnError)
	fs.Usage = func() {
		fmt.Println("Usage: codeflow create <name>")
		fmt.Println("\nCreate a new bare repository in the configured repos directory.")
		fmt.Println("\nArguments:")
		fmt.Println("  name    Repository name (must end with .git)")
		fmt.Println("\nExamples:")
		fmt.Println("  codeflow create my-project.git")
		fmt.Println("  codeflow create work/backend-api.git")
	}

	if err := fs.Parse(args); err != nil {
		return err
	}

	if fs.NArg() != 1 {
		fs.Usage()
		return fmt.Errorf("expected exactly one argument")
	}

	repoPath := fs.Arg(0)

	// Load configuration
	if err := cfg.Load(); err != nil {
		return fmt.Errorf("loading config: %w", err)
	}

	// Validate the repository path
	if err := git.ValidatePath(repoPath); err != nil {
		return err
	}

	// Create the repository
	if err := git.CreateRepository(repoPath); err != nil {
		return err
	}

	absPath := filepath.Join(cfg.ReposDirectory(), repoPath)
	fmt.Printf("Created repository: %s\n", absPath)
	
	return nil
}