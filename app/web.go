package app

import (
	"flag"
	"fmt"

	"gitflower/tree"
	webapp "gitflower/web"
)

func webCmd(store *tree.Store, config webapp.Config, args []string) error {
	fs := flag.NewFlagSet("web", flag.ExitOnError)
	addr := fs.String("addr", "", "Server address (overrides config)")
	
	fs.Usage = func() {
		fmt.Fprintf(fs.Output(), "Usage: gitflower web [options]\n")
		fmt.Fprintf(fs.Output(), "\nStarts the GitFlower web server.\n")
		fmt.Fprintf(fs.Output(), "\nOptions:\n")
		fs.PrintDefaults()
	}
	
	if err := fs.Parse(args); err != nil {
		return err
	}
	
	// Override address if provided
	if *addr != "" {
		config.Address = *addr
	}
	
	// Call web.Run with store and config
	fmt.Printf("Starting web server on %s\n", config.Address)
	return webapp.Run(store, config)
}