# Stage 1: Frontend build
FROM node:18 AS frontend-builder

WORKDIR /app/frontend

# Copy frontend package.json and package-lock.json
COPY frontend/package.json frontend/package-lock.json ./

# Install frontend dependencies
RUN npm install

# Copy the rest of the frontend source code
COPY frontend/ ./

# Build the frontend
RUN npm run build

# Stage 2: Go build
FROM golang:1.24 AS go-builder

WORKDIR /app

# Copy Go module files
COPY backend/go.mod backend/go.sum ./
RUN go mod download

# Copy the rest of the source code
COPY backend/ .

# Build the Go app
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-w -s" -o /debugagent .

# Stage 3: Final image
FROM alpine:latest

# Add ca-certificates to make SSL calls
RUN apk --no-cache add ca-certificates

# Create a non-root user for security
RUN addgroup -S appgroup && adduser -S appuser -G appgroup

# Set the Current Working Directory inside the container
WORKDIR /app

# Copy the built Go binary from the go-builder stage
COPY --from=go-builder /debugagent .
# Copy the built frontend from the frontend-builder stage
COPY --from=frontend-builder /app/frontend/build ./static
# Copy the configuration file
COPY backend/config.default.yaml ./config.default.yaml

# Expose port 8080 to the outside world
EXPOSE 8080

# Switch to our non-root user
USER appuser

# Command to run the executable
CMD ["./debugagent"]
