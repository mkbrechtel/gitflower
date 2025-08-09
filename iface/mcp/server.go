package mcp

import (
	"fmt"

	"gitflower/app"
)

type Server struct {
	app *app.Application
}

func NewServer(application *app.Application) *Server {
	return &Server{
		app: application,
	}
}

func (s *Server) Start() error {
	return fmt.Errorf("MCP server not yet implemented")
}