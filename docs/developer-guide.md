# Kovanica Agent Developer Guide

## Overview

This guide provides information for developers who want to contribute to the Kovanica Agent, understand its architecture, or extend its functionality.

## Architecture

### High-Level Components

1. **FastAPI Application** (`agent/main.py`)
   - HTTP API endpoints
   - Authentication and authorization
   - Request/response handling
   - Static file serving

2. **Agent Graph** (`agent/graph.py`)
   - LangGraph-based workflow orchestration
   - State management
   - Tool execution routing
   - Memory and context handling

3. **Tools System** (`agent/tools_ext.py`, `agent/tools.py`)
   - Extensible tool framework
   - Pre-built tools for common operations
   - Tool permission system

4. **Subagent System** (`agent/subagents.py`)
   - Predefined specialized agents
   - Agent spawning and management
   - Result collection and reporting

5. **Observability** (`agent/observability.py`, `agent/observability_enhanced.py`)
   - Metrics collection
   - Performance tracking
   - Analytics and reporting

6. **Permission System** (`agent/permission.py`, `agent/permission_enhanced.py`)
   - Role-based access control (RBAC)
   - Team and organization management
   - Fine-grained permissions

7. **Data Export/Import** (`agent/data_export_import.py`)
   - Backup and restore functionality
   - Migration tools
   - Data export capabilities

## Key Design Patterns

### Tool Registration

Tools are registered using the `@register_action` decorator:

```python
@register_action(
    "/my-tool",
    MyToolRequest,
    summary="My custom tool",
    description="Does something useful",
    tags=["custom"]
)
async def my_tool_handler(req: MyToolRequest, request: Request):
    # Implementation here
    return MyToolResponse(result="success")
```

### Subagent Creation

Subagents are defined in `agent/subagents.py` and can be spawned via:

```python
from subagents import spawn_subagent

# Spawn a code reviewer subagent
run_id = await spawn_subagent(
    agent_type="code-reviewer",
    task="Review the authentication module for security issues",
    session_id="session-123"
)
```

### Permission System

Permissions are checked using the enhanced permission system:

```python
from permission_enhanced import PermissionManager

perm_manager = PermissionManager()
if perm_manager.has_permission(user_id, "repo", "write"):
    # Allow the operation
    pass
```

## Extending the Agent

### Adding New Tools

1. Create a new tool module in `agent/tools/` or add to `agent/tools_ext.py`
2. Define Pydantic models for request and response
3. Implement the tool function
4. Register the tool using `@register_action`
5. Add appropriate permissions if needed

### Adding New Subagent Types

1. Define a new subagent configuration in `agent/subagents.py`
2. Specify the system prompt, tools, and permissions
3. Add the new type to the `SUBAGENT_TYPES` dictionary
4. The subagent can then be spawned via `!subagent spawn <type> <task>`

### Adding New API Endpoints

1. Add the endpoint to `agent/main.py`
2. Define Pydantic models for request/response
3. Implement the handler function
4. Register the endpoint using the appropriate decorator
5. Add OpenAPI documentation in the docstring
6. Update the `openapi.json` if needed (auto-generated from code)

## Development Setup

### Prerequisites

- Python 3.12+
- Docker and Docker Compose
- Git
- An LLM API key (OpenAI, Anthropic, or access to a vLLM server)

### Local Development

1. Fork and clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r agent/requirements.txt
   pip install -r agent/requirements-dev.txt
   ```
4. Set up environment variables in `.env`
5. Run the agent in development mode:
   ```bash
   uvicorn agent.main:app --reload --host 0.0.0.0 --port 8080
   ```
6. Run tests:
   ```bash
   pytest tests/unit/
   ```
7. Run linting:
   ```bash
   ruff check agent/ tests/
   ruff format --check agent/ tests/
   ```
8. Run type checking:
   ```bash
   mypy agent/ --strict
   ```

## Testing

### Unit Tests

Unit tests are located in the `tests/unit/` directory. Follow these conventions:

- Test files should be named `test_*.py`
- Use pytest fixtures for common setup
- Mock external dependencies when possible
- Keep tests focused and isolated

### Integration Tests

Integration tests verify the interaction between components and may require running services like Qdrant.

### Test Coverage

We aim for at least 80% code coverage. Run coverage with:
```bash
pytest --cov=agent --cov-report=term-missing
```

## Code Style

### Python

- Follow PEP 8 formatting
- Use type hints for all function parameters and return values
- Keep functions focused and under 50 lines when possible
- Write descriptive docstrings for all public functions and classes
- Use ruff for linting and formatting

### Documentation

- Keep documentation up to date with code changes
- Write clear, concise explanations
- Include examples where helpful
- Follow the existing documentation style

## Security Considerations

### Authentication

- Never hardcode secrets in the codebase
- Use environment variables for sensitive configuration
- Validate all input data
- Implement proper authentication and authorization checks

### Tool Safety

- All tools should validate their inputs
- Tools that modify the system should require appropriate permissions
- Consider sandboxing for potentially dangerous operations
- Log all tool executions for audit purposes

### Data Protection

- Encrypt sensitive data at rest when possible
- Minimize collection of personally identifiable information
- Follow data retention policies
- Securely delete data when no longer needed

## Deployment

### Docker

The agent is designed to run in Docker containers. See `docker-compose.yml` and `docker-compose.cpu.yml` for the production configuration.

### Kubernetes

For Kubernetes deployment, see the manifests in the `k8s/` directory (to be created).

### Environment Variables

All configuration should be done through environment variables. See `.env.example` for the complete list.

## Contributing

### Pull Request Process

1. Fork the repository
2. Create a feature branch from `main`
3. Make your changes
4. Add or update tests as needed
5. Ensure all tests pass
6. Update documentation if needed
7. Submit a pull request
8. Address any feedback from maintainers

### Code Review

All pull requests require review from at least one maintainer. Look for:

- Code correctness and clarity
- Adherence to coding standards
- Adequate test coverage
- Documentation updates
- Security considerations
- Performance implications

### Reporting Issues

Use the GitHub issue tracker to report bugs or suggest features. Include:

- Clear description of the issue
- Steps to reproduce (for bugs)
- Expected vs actual behavior
- Relevant logs or error messages
- Environment information

## License

This project is licensed under the MIT License - see the [LICENSE](../LICENSE) file for details.

## Contact

For questions or support, please open an issue on the GitHub repository or contact the maintainers directly.