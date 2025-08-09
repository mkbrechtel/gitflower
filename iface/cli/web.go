package cli

import (
	"flag"
	"fmt"

	"gitflower/iface/web"
)

func executeWeb(cli *CLI, args []string) error {
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
	
	serverAddr := cli.app.Config().Web.Address
	if *addr != "" {
		serverAddr = *addr
	}
	
	server, err := web.NewServer(cli.app)
	if err != nil {
		return fmt.Errorf("creating server: %w", err)
	}
	
	cli.app.Logger().Info("Starting web server", "address", serverAddr)
	return server.Start(serverAddr)
}