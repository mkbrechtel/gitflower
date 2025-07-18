.PHONY: all download-tailwind tailwind tailwind-watch server build clean

# All template files that trigger CSS rebuild
TEMPLATES := $(shell find web/templates -name '*.html')

all: build

# Download Tailwind CSS if not present
bin/tailwindcss:
	@mkdir -p bin
	@if [ ! -f bin/tailwindcss ]; then \
		echo "Downloading Tailwind CSS..."; \
		curl -sL https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-linux-x64 -o bin/tailwindcss; \
		chmod +x bin/tailwindcss; \
	fi

# Build CSS when templates change
web/static/css/style.css: web/static/css/input.css $(TEMPLATES) | bin/tailwindcss
	bin/tailwindcss -i $< -o $@ --minify

# Alias for building CSS
tailwind: web/static/css/style.css

# Watch Tailwind CSS for changes
tailwind-watch: bin/tailwindcss
	bin/tailwindcss -i ./web/static/css/input.css -o ./web/static/css/style.css --watch

# Run the web server
server: web/static/css/style.css
	go run cmd/codeflow/main.go web

# Build all binaries
bin/codeflow: cmd/codeflow/main.go web/static/css/style.css
	mkdir -p bin
	go build -o $@ $<

build: bin/codeflow

# Clean build artifacts
clean:
	rm -rf bin/
	rm -f web/static/css/style.css