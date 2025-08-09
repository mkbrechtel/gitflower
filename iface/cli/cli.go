package cli

import (
	"flag"
	"fmt"
	"os"

	"gitflower/app"
)

type CLI struct {
	app      *app.Application
	commands map[string]*Command
}

type Command struct {
	Name        string
	Description string
	Run         func(cli *CLI, args []string) error
}

func New(application *app.Application) *CLI {
	cli := &CLI{
		app:      application,
		commands: make(map[string]*Command),
	}
	
	cli.register(&Command{
		Name:        "config",
		Description: "Get or set configuration values",
		Run:         executeConfig,
	})
	
	cli.register(&Command{
		Name:        "create",
		Description: "Create a new repository",
		Run:         executeCreate,
	})
	
	cli.register(&Command{
		Name:        "list",
		Description: "List repositories",
		Run:         executeList,
	})
	
	cli.register(&Command{
		Name:        "web",
		Description: "Start the web server",
		Run:         executeWeb,
	})
	
	return cli
}

func (c *CLI) register(cmd *Command) {
	c.commands[cmd.Name] = cmd
}

func (c *CLI) Execute(args []string) error {
	if len(args) < 1 {
		c.printUsage()
		return fmt.Errorf("no command specified")
	}
	
	cmdName := args[0]
	cmd, exists := c.commands[cmdName]
	if !exists {
		fmt.Fprintf(os.Stderr, "Unknown command: %s\n\n", cmdName)
		c.printUsage()
		return fmt.Errorf("unknown command: %s", cmdName)
	}
	
	flag.CommandLine = flag.NewFlagSet(cmdName, flag.ExitOnError)
	
	return cmd.Run(c, args[1:])
}

func (c *CLI) printUsage() {
	fmt.Fprintf(os.Stderr, "Usage: gitflower <command> [arguments]\n\n")
	fmt.Fprintf(os.Stderr, "Available commands:\n")
	for name, cmd := range c.commands {
		fmt.Fprintf(os.Stderr, "  %-10s %s\n", name, cmd.Description)
	}
}