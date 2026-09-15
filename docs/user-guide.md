# Kovanica Agent User Guide

## Introduction

The Kovanica Agent is an AI-powered engineering assistant that helps developers with code changes, reviews, and repository operations through a conversational interface.

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Access to a Large Language Model (LLM) API (OpenAI, Anthropic, etc.)
- Qdrant vector database (for RAG capabilities)

### Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd kovanica-agent
   ```

2. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

3. Edit `.env` to configure your LLM provider and other settings:
   ```
   # LLM Configuration
   OPENAI_API_KEY=your_openai_key_here
   # OR
   ANTHROPIC_API_KEY=your_anthropic_key_here
   # OR
   VLLM_BASE_URL=http://your-vllm-server:8000
   
   # Vector Database
   QDRANT_URL=http://localhost:6333
   
   # Authentication (for development)
   AGENT_AUTH_MODE=dev
   AGENT_DEV_TOKEN=dev-token-123
   ```

4. Start the services:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d
   ```

### Using the Agent

#### Web Interface

Once the services are running, access the web interface at:
- http://localhost:8080

#### API Usage

You can also interact with the agent programmatically:

```bash
# Start a new session
SESSION_ID=$(uuidgen)

# Send a message
curl -X POST http://localhost:8080/chat \
  -H "Authorization: Bearer dev-token-123" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "'"$SESSION_ID"'",
    "message": "Create a simple Python function that calculates Fibonacci numbers"
  }'
```

#### Chat Commands

The agent supports various commands through the chat interface:

- `!help` - Show available commands
- `!task add <description>` - Add a task to your todo list
- `!task list` - Show your todo list
- `!task done <id>` - Mark a task as completed
- `!session list` - List active sessions
- `!memory store <key> <value>` - Store information in persistent memory
- `!memory recall <key>` - Recall information from persistent memory
- `!glob <pattern>` - Search for files by name pattern
- `!grep <pattern>` - Search for content in files
- `!subagent spawn <type> <task>` - Spawn a specialized subagent
- `!diff <path> <why> <patch>` - Propose a code change

## Features

### Core Capabilities

1. **Conversational Coding**: Describe what you want to build in natural language
2. **Human-in-the-Loop**: All code changes require explicit approval before being applied
3. **Git Integration**: Approved changes create branches and draft pull requests
4. **Session Management**: Conversation state is persisted per session
5. **Multi-Agent Orchestration**: Spawn specialized subagents for different tasks
6. **Retrieval-Augmented Generation**: Uses your codebase and documentation for context-aware responses

### Subagent Types

The agent can spawn specialized subagents for different tasks:

- `code-reviewer` - Reviews code for quality and best practices
- `test-engineer` - Writes and executes tests
- `security-auditor` - Performs security analysis
- `doc-writer` - Generates documentation
- `api-designer` - Designs APIs and data models
- `migration-engineer` - Handles database migrations
- `performance-engineer` - Optimizes code for performance
- `release-engineer` - Manages release processes
- `devops-engineer` - Handles deployment and infrastructure
- `vault-sync` - Synchronizes with secret management systems

### Persistent Memory

The agent maintains persistent memory across sessions:
- Store facts, preferences, and context
- Recall information when needed
- Forget information when it's no longer relevant

## Configuration

Environment variables can be set in `.env` or passed directly to Docker Compose:

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key | (required for OpenAI) |
| `ANTHROPIC_API_KEY` | Anthropic API key | (required for Anthropic) |
| `VLLM_BASE_URL` | URL for vLLM server | (required for vLLM) |
| `QDRANT_URL` | Qdrant vector database URL | `http://qdrant:6333` |
| `AGENT_AUTH_MODE` | Authentication mode (`dev` or `jwks`) | `dev` |
| `AGENT_DEV_TOKEN` | Development token (when auth_mode=dev) | `dev-token` |
| `AUTH_JWKS_URL` | JWKS URL for production auth | (required for jwks mode) |
| `AGENT_RATE_LIMIT` | Requests per window for rate limiting | `30` |
| `AGENT_RATE_WINDOW_S` | Rate limit window in seconds | `60` |
| `AGENT_AUDIT_LOG` | Path to audit log file | `/data/audit.jsonl` |
| `LOG_LEVEL` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |

## Troubleshooting

### Common Issues

1. **Agent doesn't respond**
   - Check that all containers are running: `docker compose ps`
   - Check the logs: `docker compose logs -f agent`

2. **LLM connection issues**
   - Verify your API key is correct in `.env`
   - Check that the LLM service is accessible
   - For vLLM, ensure the server is running and accessible

3. **Vector database issues**
   - Ensure Qdrant is running: `docker compose ps qdrant`
   - Check Qdrant logs: `docker compose logs -f qdrant`

4. **Permission denied errors**
   - Ensure you're using the correct authentication token
   - In dev mode, use the token set in `AGENT_DEV_TOKEN`

### Getting Help

- Check the logs: `docker compose logs -f <service>`
- Restart services: `docker compose restart`
- Rebuild containers: `docker compose up -d --build`
- Consult the [Troubleshooting Guide](troubleshooting.md)

## License

MIT License - see [LICENSE](../LICENSE) for details.