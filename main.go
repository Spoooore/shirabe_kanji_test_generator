package main

import (
	"database/sql"
	"embed"
	"encoding/json"
	"fmt"
	"io/fs"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	_ "github.com/lib/pq"
)

//go:embed kanji_app.html sprites
var content embed.FS

var db *sql.DB

type Score struct {
	ID        int       `json:"id"`
	Name      string    `json:"name"`
	Score     int       `json:"score"`
	Total     int       `json:"total"`
	Percent   float64   `json:"percent"`
	Ranges    string    `json:"ranges"`
	CreatedAt time.Time `json:"created_at"`
}

type LeaderboardEntry struct {
	Rank       int     `json:"rank"`
	Name       string  `json:"name"`
	TotalScore int     `json:"total_score"`
	TestsTaken int     `json:"tests_taken"`
	AvgPercent float64 `json:"avg_percent"`
}

type SubmitScoreRequest struct {
	Name   string `json:"name"`
	Score  int    `json:"score"`
	Total  int    `json:"total"`
	Ranges string `json:"ranges"`
}

func initDB() error {
	dbURL := os.Getenv("DATABASE_URL")
	if dbURL == "" {
		// Local development fallback
		dbURL = "postgres://localhost/kanji_test?sslmode=disable"
	}

	var err error
	db, err = sql.Open("postgres", dbURL)
	if err != nil {
		return fmt.Errorf("failed to connect to database: %v", err)
	}

	// Test connection
	if err = db.Ping(); err != nil {
		return fmt.Errorf("failed to ping database: %v", err)
	}

	// Create tables
	_, err = db.Exec(`
		CREATE TABLE IF NOT EXISTS scores (
			id SERIAL PRIMARY KEY,
			name VARCHAR(50) NOT NULL,
			score INTEGER NOT NULL,
			total INTEGER NOT NULL,
			percent DECIMAL(5,2) NOT NULL,
			ranges VARCHAR(255),
			created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
		);
		
		CREATE INDEX IF NOT EXISTS idx_scores_name ON scores(name);
		CREATE INDEX IF NOT EXISTS idx_scores_percent ON scores(percent DESC);
	`)
	if err != nil {
		return fmt.Errorf("failed to create tables: %v", err)
	}

	log.Println("✅ Database initialized")
	return nil
}

func submitScoreHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req SubmitScoreRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}

	// Sanitize name
	name := strings.TrimSpace(req.Name)
	if len(name) == 0 || len(name) > 50 {
		http.Error(w, "Invalid name", http.StatusBadRequest)
		return
	}

	// Calculate percent
	percent := 0.0
	if req.Total > 0 {
		percent = float64(req.Score) / float64(req.Total) * 100
	}

	// Insert score
	_, err := db.Exec(
		"INSERT INTO scores (name, score, total, percent, ranges) VALUES ($1, $2, $3, $4, $5)",
		name, req.Score, req.Total, percent, req.Ranges,
	)
	if err != nil {
		log.Printf("Error inserting score: %v", err)
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
}

func leaderboardHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	// Get aggregated leaderboard (top 10 by total score)
	rows, err := db.Query(`
		SELECT 
			name,
			SUM(score) as total_score,
			COUNT(*) as tests_taken,
			AVG(percent) as avg_percent
		FROM scores
		GROUP BY name
		ORDER BY total_score DESC, avg_percent DESC
		LIMIT 10
	`)
	if err != nil {
		log.Printf("Error querying leaderboard: %v", err)
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	var leaderboard []LeaderboardEntry
	rank := 1
	for rows.Next() {
		var entry LeaderboardEntry
		if err := rows.Scan(&entry.Name, &entry.TotalScore, &entry.TestsTaken, &entry.AvgPercent); err != nil {
			log.Printf("Error scanning row: %v", err)
			continue
		}
		entry.Rank = rank
		leaderboard = append(leaderboard, entry)
		rank++
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(leaderboard)
}

func recentScoresHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	// Get recent scores
	rows, err := db.Query(`
		SELECT name, score, total, percent, ranges, created_at
		FROM scores
		ORDER BY created_at DESC
		LIMIT 5
	`)
	if err != nil {
		log.Printf("Error querying recent scores: %v", err)
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	var scores []Score
	for rows.Next() {
		var s Score
		if err := rows.Scan(&s.Name, &s.Score, &s.Total, &s.Percent, &s.Ranges, &s.CreatedAt); err != nil {
			log.Printf("Error scanning row: %v", err)
			continue
		}
		scores = append(scores, s)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(scores)
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	// Initialize database
	if err := initDB(); err != nil {
		log.Printf("⚠️ Database not available: %v", err)
		log.Println("Running without leaderboard functionality")
	}

	mux := http.NewServeMux()

	// API endpoints
	mux.HandleFunc("/api/score", submitScoreHandler)
	mux.HandleFunc("/api/leaderboard", leaderboardHandler)
	mux.HandleFunc("/api/recent", recentScoresHandler)

	// Main page
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/" {
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

	// Health check
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("OK"))
	})

	fmt.Printf("🎌 Kanji Test Server running on http://localhost:%s\n", port)
	log.Fatal(http.ListenAndServe(":"+port, mux))
}
