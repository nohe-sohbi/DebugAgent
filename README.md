# DebugAgent

DebugAgent is a full-stack application that uses AI to analyze software projects and provide detailed explanations about code structure, functionality, and purpose. It consists of a Go backend API, a React frontend, and integrates with Ollama for AI-powered code analysis.

## Features

- **Project Analysis**: Upload and analyze entire project directories
- **AI-Powered Insights**: Uses Ollama models to provide intelligent code explanations
- **Real-time Streaming**: Get analysis results with live progress updates
- **Web Interface**: Modern React frontend with file upload and progress tracking
- **Docker Support**: Complete containerized deployment with Docker Compose
- **Production Ready**: Includes Nginx configuration for production deployment

## Architecture

- **Backend**: Go API server with streaming analysis capabilities
- **Frontend**: React application with Tailwind CSS
- **AI Engine**: Ollama integration for code analysis
- **Infrastructure**: Docker Compose orchestration with Nginx reverse proxy

## Prerequisites

- **Docker & Docker Compose** (recommended) OR
- **Go 1.18+** and **Node.js 18+** for local development
- **Ollama** running locally or in Docker

## Quick Start with Docker (Recommended)

1. **Clone the repository:**
   ```bash
   git clone https://github.com/nohe-sohbi/DebugAgent.git
   cd DebugAgent
   ```

2. **Start all services:**
   ```bash
   docker-compose up --build
   ```

3. **Access the application:**
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8080
   - Ollama: http://localhost:11434

For detailed Docker setup instructions, see [DOCKER_README.md](DOCKER_README.md).

## Local Development Setup

### Backend Setup

1. **Navigate to backend directory:**
   ```bash
   cd backend
   ```

2. **Install Go dependencies:**
   ```bash
   go mod tidy
   ```

3. **Configure environment (optional):**
   ```bash
   export DEBUGAGENT_OLLAMA_HOST="http://localhost:11434"
   export DEBUGAGENT_OLLAMA_MODEL="llama3.2:1b"
   export DEBUGAGENT_SERVER_PORT="8080"
   ```

4. **Run the backend:**
   ```bash
   go run .
   ```

### Frontend Setup

1. **Navigate to frontend directory:**
   ```bash
   cd frontend
   ```

2. **Install dependencies:**
   ```bash
   npm install
   ```

3. **Start development server:**
   ```bash
   npm start
   ```

## API Usage

### Web Interface

The easiest way to use DebugAgent is through the web interface at http://localhost:3000. Simply:

1. Upload your project files (drag & drop or file selection)
2. Ask a question about your project
3. Get real-time analysis with streaming progress updates

### Direct API Access

You can also interact directly with the API:

#### Analyze Endpoint

```bash
curl -X POST http://localhost:8080/analyze \
  -F "question=Explain the main purpose of this project" \
  -F "files=@src/main.go" \
  -F "files=@README.md"
```

#### Streaming Analysis

```bash
curl -X POST http://localhost:8080/analyze-stream \
  -F "question=How does the authentication work?" \
  -F "files=@auth.go" \
  -F "files=@middleware.go"
```

### API Endpoints

- `POST /analyze` - Standard analysis with JSON response
- `POST /analyze-stream` - Streaming analysis with Server-Sent Events
- `GET /health` - Health check endpoint

## Configuration

The application uses YAML configuration files:

- `backend/config.default.yaml` - Default configuration
- `backend/config.docker.yaml` - Docker-specific overrides

Configuration can be overridden with environment variables using the prefix `DEBUGAGENT_`.

## Project Structure

```
DebugAgent/
├── README.md              # Main documentation
├── DOCKER_README.md       # Docker setup guide
├── docker-compose.yml     # Docker orchestration
├── nginx.conf            # Production nginx config
├── backend/              # Go API server
│   ├── main.go
│   ├── engine.go         # Analysis engine
│   ├── config/           # Configuration management
│   └── ...
└── frontend/             # React application
    ├── src/
    ├── public/
    └── ...
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

## License

This project is licensed under the Creative Commons BY-NC License. See the [LICENSE](backend/LICENSE) file for details.
