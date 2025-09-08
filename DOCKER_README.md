# DebugAgent Docker Setup

This repository contains a complete Docker Compose setup for the DebugAgent application, including frontend, backend, and AI services.

## Services

- **Frontend**: React application with Tailwind CSS (port 3000)
- **Backend**: Go API server (port 8080)
- **Ollama**: AI model service for code analysis (port 11434)
- **Nginx**: Reverse proxy for production (port 80) - optional

## Prerequisites

- Docker Engine 20.10+ 
- Docker Compose 2.0+
- At least 8GB RAM (for Ollama models)
- 10GB+ free disk space

## Quick Start

### Development Mode

1. **Clone and navigate to the project:**
   ```bash
   cd /path/to/DebugAgent
   ```

2. **Start all services:**
   ```bash
   docker-compose up --build
   ```

3. **Wait for services to be ready:**
   - Ollama will download the `gemma3:latest` model on first run (this may take several minutes)
   - Backend will start once Ollama is healthy
   - Frontend will start once backend is healthy

4. **Access the application:**
   - Frontend: http://localhost:3001
   - Backend API: http://localhost:8080
   - Ollama API: http://localhost:11434

### Production Mode

For production deployment with Nginx reverse proxy:

```bash
docker-compose --profile production up --build -d
```

Access via: http://localhost

## Configuration

### Environment Variables

You can override default settings by creating a `.env` file:

```env
# Frontend
REACT_APP_API_URL=http://localhost:8080

# Backend
OLLAMA_HOST=http://ollama:11434
OLLAMA_MODEL=gemma3:latest

# Ports
FRONTEND_PORT=3001
BACKEND_PORT=8080
OLLAMA_PORT=11434
NGINX_PORT=80
```

### Ollama Model Management

The service uses `gemma3:latest` by default. To use a different model:

1. **Access the Ollama container:**
   ```bash
   docker-compose exec ollama bash
   ```

2. **Pull a different model:**
   ```bash
   ollama pull codellama:latest
   # or
   ollama pull llama2:latest
   ```

3. **Update the backend configuration:**
   Edit `debugagent/config.docker.yaml` and change the model name.

4. **Restart the backend:**
   ```bash
   docker-compose restart backend
   ```

## Usage

### API Endpoints

- `POST /analyze` - Analyze uploaded project files with a question
  - Form data: `question` (string), `files` (multipart files)
  - Response: JSON with analysis results

### File Upload

The API accepts project files via multipart form upload. Supported formats include source code files, configuration files, etc. Binary and large files are automatically filtered out.

## Development

### Hot Reload

The frontend supports hot reload in development mode. Source files are mounted as volumes, so changes will be reflected immediately.

### Logs

View service logs:

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend
docker-compose logs -f frontend
docker-compose logs -f ollama
```

### Debugging

Enter a running container for debugging:

```bash
# Backend container
docker-compose exec backend sh

# Frontend container
docker-compose exec frontend sh
```

## Troubleshooting

### Common Issues

1. **Ollama model download fails:**
   - Ensure sufficient disk space (models can be 4GB+)
   - Check internet connection
   - Try pulling the model manually: `docker-compose exec ollama ollama pull gemma3:latest`

2. **Backend can't connect to Ollama:**
   - Verify Ollama service is healthy: `docker-compose ps`
   - Check network connectivity: `docker-compose exec backend ping ollama`

3. **Frontend build fails:**
   - Clear node_modules: `docker-compose run --rm frontend rm -rf node_modules`
   - Rebuild: `docker-compose build --no-cache frontend`

4. **Permission issues:**
   - On Linux, ensure your user can access Docker: `sudo usermod -aG docker $USER`
   - Restart your session after adding to docker group

### Health Checks

Monitor service health:

```bash
# Check all services
docker-compose ps

# Detailed health status
docker-compose exec backend wget --spider http://localhost:8080/
docker-compose exec frontend wget --spider http://localhost:3000/
docker-compose exec ollama curl http://localhost:11434/api/tags
```

## Cleanup

Stop and remove all containers, networks, and volumes:

```bash
# Stop services
docker-compose down

# Remove volumes (WARNING: This will delete Ollama models)
docker-compose down -v

# Remove images
docker-compose down --rmi all
```

## Architecture

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Frontend  │────│   Nginx     │────│   Backend   │
│  (React)    │    │  (Proxy)    │    │   (Go)      │
│   :3000     │    │    :80      │    │   :8080     │
└─────────────┘    └─────────────┘    └─────────────┘
                                              │
                                              │
                                   ┌─────────────┐
                                   │   Ollama    │
                                   │   (AI)      │
                                   │   :11434    │
                                   └─────────────┘
```

## Security Notes

- The Nginx configuration includes basic security headers
- Rate limiting is configured for API endpoints
- File uploads are limited to 100MB
- Consider using HTTPS in production
- Review and adjust security settings for your use case
