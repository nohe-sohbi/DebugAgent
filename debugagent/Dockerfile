# Stage 1: Build
FROM golang:1.24-alpine AS builder

# Set the Current Working Directory inside the container
WORKDIR /app

# We copy the Go Module file first to leverage Docker's caching.
# This will prevent re-downloading of dependencies on every build.
COPY go.mod go.sum ./
RUN go mod download

# Copy the rest of the source code
COPY . .

# Build the Go app
# CGO_ENABLED=0 is used to build a statically linked binary.
# -ldflags="-w -s" is used to reduce the size of the binary.
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-w -s" -o /debugagent .

# Stage 2: Deploy
FROM alpine:latest

# Add ca-certificates to make SSL calls
RUN apk --no-cache add ca-certificates

# Create a non-root user for security
RUN addgroup -S appgroup && adduser -S appuser -G appgroup

# Set the Current Working Directory inside the container
WORKDIR /app

# Copy the built binary from the builder stage
COPY --from=builder /debugagent .
# Copy the configuration file
COPY config.yaml .

# Expose port 8080 to the outside world
EXPOSE 8080

# Switch to our non-root user
USER appuser

# Command to run the executable
CMD ["./debugagent"]
