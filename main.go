package main

import (
	"embed"
	"fmt"
	"io/fs"
	"log"
	"net/http"
	"os"
)

//go:embed kanji_app.html sprites
var content embed.FS

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	// Serve embedded static files
	mux := http.NewServeMux()

	// Main page
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/" {
			// Try to serve from embedded files
			http.FileServer(http.FS(content)).ServeHTTP(w, r)
			return
		}

		data, err := content.ReadFile("kanji_app.html")
		if err != nil {
			http.Error(w, "App not found", http.StatusNotFound)
			return
		}

		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.Write(data)
	})

	// Sprites directory
	spritesFS, err := fs.Sub(content, "sprites")
	if err != nil {
		log.Fatal("Failed to load sprites:", err)
	}
	mux.Handle("/sprites/", http.StripPrefix("/sprites/", http.FileServer(http.FS(spritesFS))))

	// Health check for Railway
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("OK"))
	})

	fmt.Printf("🎌 Kanji Test Server running on http://localhost:%s\n", port)
	log.Fatal(http.ListenAndServe(":"+port, mux))
}

