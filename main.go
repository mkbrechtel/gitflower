package main

import (
	"os"

	"gitflower/app"
)

func main() {
	os.Exit(app.Run(os.Args))
}