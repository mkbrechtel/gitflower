package web

import (
	"embed"
	"html/template"
	"log"
	"net/http"
	"time"
)

//go:embed templates/*
var templateFS embed.FS

//go:embed static/*
var staticFS embed.FS

type Server struct {
	templates *template.Template
}

func NewServer() (*Server, error) {
	templates, err := template.ParseFS(templateFS, "templates/*.html")
	if err != nil {
		return nil, err
	}

	return &Server{
		templates: templates,
	}, nil
}

func (s *Server) HandleIndex(w http.ResponseWriter, r *http.Request) {
	data := struct {
		Time string
	}{
		Time: time.Now().Format("2006-01-02 15:04:05"),
	}

	err := s.templates.ExecuteTemplate(w, "index.html", data)
	if err != nil {
		log.Printf("Error rendering template: %v", err)
		http.Error(w, "Internal Server Error", http.StatusInternalServerError)
	}
}

func (s *Server) Start(addr string) error {
	mux := http.NewServeMux()
	
	// Serve static files
	mux.Handle("/static/", http.FileServer(http.FS(staticFS)))
	
	// Routes
	mux.HandleFunc("/", s.HandleIndex)

	log.Printf("Starting CodeFlow server on %s", addr)
	return http.ListenAndServe(addr, mux)
}