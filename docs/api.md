# Kovanica Agent API Documentation

This document provides an overview of the Kovanica Agent API endpoints.

## Base URL

The API is served at the root path (`/`) for the UI and at specific paths for programmatic access.

## Endpoints

### Health Checks

- `GET /healthz` - Liveness probe
  - Returns: `{"status": "ok", "name": "kovi"}`
  - Use for Kubernetes liveness probes

- `GET /readyz` - Readiness probe
  - Returns dependency status for Qdrant and LLM services
  - Example: `{"status": "ok", "name": "kovi", "deps": {"qdrant": "ok", "llm": "ok"}}`
  - Use for Kubernetes readiness probes

### Chat Interface

- `POST /chat` - Send a message to the agent
  - Requires: `session_id` (string) and `message` (string)
  - Returns: Either a successful response or a pending confirmation if the agent proposes changes

### Confirmation

- `POST /confirm` - Approve or reject a proposed change
  - Requires: `session_id` (string) and `approve` (boolean)
  - Returns: Status of the confirmation action

## Authentication

The API uses JWT-based authentication with two modes:

1. **JWKS Mode**: Production mode using a JWKS endpoint (set `AUTH_JWKS_URL`)
2. **Dev Token Mode**: Development mode with a simple token (default)

Include the `Authorization: Bearer <token>` header in all requests.

## Rate Limiting

- Default: 30 requests per 60 seconds per IP
- Configurable via `AGENT_RATE_LIMIT` and `AGENT_RATE_WINDOW_S` environment variables

## Error Responses

All endpoints may return standard HTTP error codes:
- 400 - Bad Request
- 401 - Unauthorized
- 403 - Forbidden
- 429 - Too Many Requests
- 500 - Internal Server Error
- 503 - Service Unavailable

## OpenAPI Specification

The full OpenAPI 3.1.0 specification is available at `/openapi.json` and can be viewed with tools like Swagger UI or Redoc.