#!/usr/bin/env python3
"""
Prometheus metrics for Kovanica Agent.
"""

from __future__ import annotations

import time
from typing import Dict

from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST

# === Metrics Definitions ===

# Request metrics
REQUEST_COUNT = Counter(
    "kovanica_agent_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "http_status"]
)

REQUEST_LATENCY = Histogram(
    "kovanica_agent_request_latency_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"]
)

# Agent-specific metrics
AGENT_SESSIONS_ACTIVE = Gauge(
    "kovanica_agent_sessions_active",
    "Number of active agent sessions"
)

AGENT_MESSAGES_PROCESSED = Counter(
    "kovanica_agent_messages_processed_total",
    "Total number of messages processed by the agent",
    ["session_id", "message_type"]
)

AGENT_TOOL_USAGE = Counter(
    "kovanica_agent_tool_usage_total",
    "Total usage of agent tools",
    ["tool_name", "success"]
)

AGENT_SUBAGENT_SPAWNED = Counter(
    "kovanica_agent_subagent_spawned_total",
    "Total number of subagents spawned",
    ["agent_type"]
)

AGENT_PATCHES_PROPOSED = Counter(
    "kovanica_agent_patches_proposed_total",
    "Total number of patches proposed by the agent"
)

AGENT_PATCHES_APPROVED = Counter(
    "kovanica_agent_patches_approved_total",
    "Total number of patches approved by users"
)

AGENT_PATCHES_REJECTED = Counter(
    "kovanica_agent_patches_rejected_total",
    "Total number of patches rejected by users"
)

# LLM metrics
LLM_REQUEST_LATENCY = Histogram(
    "kovanica_agent_llm_request_latency_seconds",
    "Latency of LLM requests in seconds",
    ["model", "provider"]
)

LLM_TOKEN_USAGE = Counter(
    "kovanica_agent_llm_token_usage_total",
    "Total number of tokens used by LLM",
    ["model", "provider", "token_type"]  # token_type: prompt, completion
)

# RAG metrics
RAG_QUERY_LATENCY = Histogram(
    "kovanica_agent_rag_query_latency_seconds",
    "Latency of RAG queries in seconds",
    ["query_type"]
)

RAG_CACHE_HITS = Counter(
    "kovanica_agent_rag_cache_hits_total",
    "Total number of RAG cache hits"
)

RAG_CACHE_MISSES = Counter(
    "kovanica_agent_rag_cache_misses_total",
    "Total number of RAG cache misses"
)

# System metrics
AGENT_UPTIME_SECONDS = Gauge(
    "kovanica_agent_uptime_seconds",
    "Uptime of the agent in seconds"
)

# Start time for uptime calculation
_START_TIME = time.time()


def update_uptime() -> None:
    """Update the uptime gauge."""
    AGENT_UPTIME_SECONDS.set(time.time() - _START_TIME)


def get_metrics() -> bytes:
    """Generate Prometheus metrics payload."""
    update_uptime()
    return generate_latest()


def get_metrics_response() -> Dict[str, object]:
    """Get metrics as a dictionary for potential use in other contexts."""
    update_uptime()
    # In a real implementation, we might return a dict, but for Prometheus we use the bytes.
    # This function is kept for compatibility if needed.
    return {"format": "prometheus", "data": get_metrics().decode('utf-8')}