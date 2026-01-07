# Build stage
FROM golang:1.21-alpine AS builder

WORKDIR /app

# Copy go mod files
COPY go.mod go.sum* ./

# Download dependencies
RUN go mod download

# Copy source code and static files
COPY main.go ./
COPY kanji_app.html ./
COPY sprites/ ./sprites/

# Build the binary
RUN CGO_ENABLED=0 GOOS=linux go build -o server .

# Runtime stage
FROM alpine:latest

# Install CA certificates for HTTPS
RUN apk --no-cache add ca-certificates

WORKDIR /app

# Copy the binary from builder
COPY --from=builder /app/server .

# Expose port
EXPOSE 8080

# Run the server
CMD ["./server"]
