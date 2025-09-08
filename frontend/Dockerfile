# Multi-stage build for React frontend

# Stage 1: Build the React application
FROM node:18-alpine AS builder

WORKDIR /app

# Copy package files first for better caching
COPY package.json ./

# Install dependencies (will create new package-lock.json)
RUN npm install

# Copy source code
COPY . .

# Build the application
RUN npm run build

# Stage 2: Production server
FROM node:18-alpine AS production

WORKDIR /app

# Install serve to run the built app
RUN npm install -g serve

# Copy built files from builder stage
COPY --from=builder /app/build ./build

# Expose port 3000
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:3000/ || exit 1

# Start the application
CMD ["serve", "-s", "build", "-l", "3000"]
