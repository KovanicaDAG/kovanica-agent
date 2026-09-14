"""
Observability and Monitoring for Kovanica Agent.

Provides LangSmith/Langfuse integration, token tracking, performance metrics,
and structured logging.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
from functools import wraps
import threading


@dataclass
class TokenUsage:
    """Token usage for a single request."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    session_id: str = ""
    request_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    cost_usd: float = 0.0


@dataclass
class PerformanceMetric:
    """Performance metric for an operation."""
    operation: str
    duration_ms: float
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    session_id: str = ""
    request_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error: Optional[str] = None


@dataclass
class TraceEvent:
    """A single trace event for LangSmith/Langfuse."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    type: str = "span"  # span, generation, event
    start_time: str = field(default_factory=lambda: datetime.now().isoformat())
    end_time: Optional[str] = None
    duration_ms: Optional[float] = None
    input: Any = None
    output: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    parent_id: Optional[str] = None
    session_id: str = ""
    trace_id: str = ""
    level: str = "INFO"
    error: Optional[str] = None


class TokenTracker:
    """Tracks token usage across requests."""
    
    def __init__(self, log_dir: Path = None):
        self.log_dir = log_dir or Path.home() / ".kovanica" / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.usage_file = self.log_dir / "token_usage.jsonl"
        self._lock = threading.Lock()
        self.session_usage: Dict[str, List[TokenUsage]] = defaultdict(list)
        self.total_usage = TokenUsage()
    
    def track(self, usage: TokenUsage) -> None:
        """Record token usage."""
        with self._lock:
            self.session_usage[usage.session_id].append(usage)
            self.total_usage.prompt_tokens += usage.prompt_tokens
            self.total_usage.completion_tokens += usage.completion_tokens
            self.total_usage.total_tokens += usage.total_tokens
            self.total_usage.cost_usd += usage.cost_usd
            
            # Write to file
            with open(self.usage_file, "a") as f:
                f.write(json.dumps(asdict(usage)) + "\n")
    
    def get_session_usage(self, session_id: str) -> List[TokenUsage]:
        """Get token usage for a session."""
        return self.session_usage.get(session_id, [])
    
    def get_total_usage(self) -> TokenUsage:
        """Get total token usage."""
        return self.total_usage
    
    def estimate_cost(self, prompt_tokens: int, completion_tokens: int, model: str) -> float:
        """Estimate cost based on model pricing."""
        # Pricing per 1M tokens (approximate)
        pricing = {
            "gpt-4": {"prompt": 30.0, "completion": 60.0},
            "gpt-4-turbo": {"prompt": 10.0, "completion": 30.0},
            "gpt-3.5-turbo": {"prompt": 0.5, "completion": 1.5},
            "claude-3-opus": {"prompt": 15.0, "completion": 75.0},
            "claude-3-sonnet": {"prompt": 3.0, "completion": 15.0},
            "claude-3-haiku": {"prompt": 0.25, "completion": 1.25},
            "qwen2.5-coder": {"prompt": 0.0, "completion": 0.0},  # Local model
        }
        
        model_key = model.lower()
        for key in pricing:
            if key in model_key:
                p = pricing[key]
                return (prompt_tokens * p["prompt"] + completion_tokens * p["completion"]) / 1_000_000
        
        # Default pricing
        return (prompt_tokens * 1.0 + completion_tokens * 2.0) / 1_000_000


class PerformanceMonitor:
    """Monitors performance metrics."""
    
    def __init__(self, log_dir: Path = None):
        self.log_dir = log_dir or Path.home() / ".kovanica" / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.metrics_file = self.log_dir / "performance_metrics.jsonl"
        self._lock = threading.Lock()
        self.metrics: List[PerformanceMetric] = []
    
    @contextmanager
    def measure(self, operation: str, session_id: str = "", request_id: str = "", metadata: Dict = None):
        """Context manager to measure operation duration."""
        start_time = time.perf_counter()
        request_id = request_id or str(uuid.uuid4())[:8]
        metadata = metadata or {}
        error = None
        success = True
        
        try:
            yield
        except Exception as e:
            success = False
            error = str(e)
            raise
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            metric = PerformanceMetric(
                operation=operation,
                duration_ms=duration_ms,
                session_id=session_id,
                request_id=request_id,
                metadata=metadata,
                success=success,
                error=error,
            )
            self.record(metric)
    
    def record(self, metric: PerformanceMetric) -> None:
        """Record a performance metric."""
        with self._lock:
            self.metrics.append(metric)
            with open(self.metrics_file, "a") as f:
                f.write(json.dumps(asdict(metric)) + "\n")
    
    def get_metrics(self, operation: str = None, session_id: str = None, limit: int = 100) -> List[PerformanceMetric]:
        """Get metrics with optional filtering."""
        filtered = self.metrics
        if operation:
            filtered = [m for m in filtered if m.operation == operation]
        if session_id:
            filtered = [m for m in filtered if m.session_id == session_id]
        return filtered[-limit:]
    
    def get_stats(self, operation: str = None) -> Dict[str, Any]:
        """Get statistics for an operation."""
        metrics = self.get_metrics(operation=operation)
        if not metrics:
            return {}
        
        durations = [m.duration_ms for m in metrics if m.success]
        errors = [m for m in metrics if not m.success]
        
        return {
            "operation": operation or "all",
            "total_calls": len(metrics),
            "successful_calls": len(durations),
            "failed_calls": len(errors),
            "success_rate": len(durations) / len(metrics) if metrics else 0,
            "avg_duration_ms": sum(durations) / len(durations) if durations else 0,
            "min_duration_ms": min(durations) if durations else 0,
            "max_duration_ms": max(durations) if durations else 0,
            "p50_duration_ms": sorted(durations)[len(durations) // 2] if durations else 0,
            "p95_duration_ms": sorted(durations)[int(len(durations) * 0.95)] if durations else 0,
            "p99_duration_ms": sorted(durations)[int(len(durations) * 0.99)] if durations else 0,
        }


class LangSmithTracer:
    """LangSmith integration for tracing."""
    
    def __init__(self, api_key: str = None, project: str = "kovanica"):
        self.api_key = api_key or os.environ.get("LANGSMITH_API_KEY")
        self.project = project
        self.enabled = bool(self.api_key)
        self.traces: List[TraceEvent] = []
        self._lock = threading.Lock()
        
        if self.enabled:
            try:
                from langsmith import Client
                self.client = Client(api_key=self.api_key)
            except ImportError:
                self.enabled = False
                print("LangSmith not installed. Run: pip install langsmith")
    
    def create_trace(self, name: str, session_id: str = "", trace_id: str = None, 
                     input: Any = None, metadata: Dict = None, tags: List[str] = None) -> TraceEvent:
        """Create a new trace."""
        trace = TraceEvent(
            name=name,
            type="span",
            session_id=session_id,
            trace_id=trace_id or str(uuid.uuid4()),
            input=input,
            metadata=metadata or {},
            tags=tags or [],
        )
        with self._lock:
            self.traces.append(trace)
        return trace
    
    def end_trace(self, trace: TraceEvent, output: Any = None, error: str = None) -> None:
        """End a trace."""
        trace.end_time = datetime.now().isoformat()
        trace.output = output
        trace.error = error
        trace.duration_ms = (datetime.fromisoformat(trace.end_time) - 
                            datetime.fromisoformat(trace.start_time)).total_seconds() * 1000
        
        if self.enabled and hasattr(self, 'client'):
            try:
                self.client.create_run(
                    name=trace.name,
                    run_type=trace.type,
                    inputs=trace.input,
                    outputs=trace.output,
                    error=trace.error,
                    start_time=trace.start_time,
                    end_time=trace.end_time,
                    extra=trace.metadata,
                    tags=trace.tags,
                    session_id=trace.session_id,
                    trace_id=trace.trace_id,
                )
            except Exception as e:
                print(f"LangSmith error: {e}")
    
    @contextmanager
    def trace(self, name: str, session_id: str = "", input: Any = None, 
              metadata: Dict = None, tags: List[str] = None):
        """Context manager for tracing."""
        trace = self.create_trace(name, session_id, input=input, metadata=metadata, tags=tags)
        try:
            yield trace
            self.end_trace(trace)
        except Exception as e:
            self.end_trace(trace, error=str(e))
            raise


class LangfuseTracer:
    """Langfuse integration for tracing."""
    
    def __init__(self, public_key: str = None, secret_key: str = None, host: str = None):
        self.public_key = public_key or os.environ.get("LANGFUSE_PUBLIC_KEY")
        self.secret_key = secret_key or os.environ.get("LANGFUSE_SECRET_KEY")
        self.host = host or os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")
        self.enabled = bool(self.public_key and self.secret_key)
        self.traces: List[TraceEvent] = []
        self._lock = threading.Lock()
        
        if self.enabled:
            try:
                from langfuse import Langfuse
                self.client = Langfuse(
                    public_key=self.public_key,
                    secret_key=self.secret_key,
                    host=self.host,
                )
            except ImportError:
                self.enabled = False
                print("Langfuse not installed. Run: pip install langfuse")
    
    def create_trace(self, name: str, session_id: str = "", trace_id: str = None,
                     input: Any = None, metadata: Dict = None, tags: List[str] = None) -> TraceEvent:
        trace = TraceEvent(
            name=name,
            type="span",
            session_id=session_id,
            trace_id=trace_id or str(uuid.uuid4()),
            input=input,
            metadata=metadata or {},
            tags=tags or [],
        )
        with self._lock:
            self.traces.append(trace)
        return trace
    
    def end_trace(self, trace: TraceEvent, output: Any = None, error: str = None) -> None:
        trace.end_time = datetime.now().isoformat()
        trace.output = output
        trace.error = error
        trace.duration_ms = (datetime.fromisoformat(trace.end_time) - 
                            datetime.fromisoformat(trace.start_time)).total_seconds() * 1000
        
        if self.enabled and hasattr(self, 'client'):
            try:
                self.client.trace(
                    name=trace.name,
                    input=trace.input,
                    output=trace.output,
                    metadata=trace.metadata,
                    tags=trace.tags,
                    session_id=trace.session_id,
                    trace_id=trace.trace_id,
                    start_time=trace.start_time,
                    end_time=trace.end_time,
                )
            except Exception as e:
                print(f"Langfuse error: {e}")
    
    @contextmanager
    def trace(self, name: str, session_id: str = "", input: Any = None,
              metadata: Dict = None, tags: List[str] = None):
        trace = self.create_trace(name, session_id, input=input, metadata=metadata, tags=tags)
        try:
            yield trace
            self.end_trace(trace)
        except Exception as e:
            self.end_trace(trace, error=str(e))
            raise


class ObservabilityManager:
    """Central observability manager combining all providers."""
    
    def __init__(self, log_dir: Path = None):
        self.log_dir = log_dir or Path.home() / ".kovanica" / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.token_tracker = TokenTracker(self.log_dir)
        self.performance_monitor = PerformanceMonitor(self.log_dir)
        self.langsmith = LangSmithTracer()
        self.langfuse = LangfuseTracer()
        
        # Structured logging
        self.structured_log_file = self.log_dir / "structured_logs.jsonl"
        self._log_lock = threading.Lock()
    
    def log_structured(self, level: str, message: str, session_id: str = "",
                       request_id: str = "", operation: str = "",
                       metadata: Dict = None, error: str = None) -> None:
        """Log structured log entry."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message,
            "session_id": session_id,
            "request_id": request_id or str(uuid.uuid4())[:8],
            "operation": operation,
            "metadata": metadata or {},
            "error": error,
        }
        
        with self._log_lock:
            with open(self.structured_log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
    
    def log_info(self, message: str, **kwargs) -> None:
        self.log_structured("INFO", message, **kwargs)
    
    def log_warning(self, message: str, **kwargs) -> None:
        self.log_structured("WARNING", message, **kwargs)
    
    def log_error(self, message: str, error: str = None, **kwargs) -> None:
        self.log_structured("ERROR", message, error=error, **kwargs)
    
    def track_tokens(self, prompt_tokens: int, completion_tokens: int, model: str,
                     session_id: str = "", request_id: str = "") -> TokenUsage:
        """Track token usage for a request."""
        usage = TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            model=model,
            session_id=session_id,
            request_id=request_id or str(uuid.uuid4())[:8],
        )
        usage.cost_usd = self.token_tracker.estimate_cost(prompt_tokens, completion_tokens, model)
        self.token_tracker.track(usage)
        return usage
    
    @contextmanager
    def measure(self, operation: str, session_id: str = "", request_id: str = "", metadata: Dict = None):
        """Measure operation performance."""
        with self.performance_monitor.measure(operation, session_id, request_id, metadata) as ctx:
            yield ctx
    
    def trace(self, name: str, session_id: str = "", input: Any = None,
              metadata: Dict = None, tags: List[str] = None):
        """Create a trace using available provider (LangSmith > Langfuse > local)."""
        if self.langsmith.enabled:
            return self.langsmith.trace(name, session_id, input=input, metadata=metadata, tags=tags)
        elif self.langfuse.enabled:
            return self.langfuse.trace(name, session_id, input=input, metadata=metadata, tags=tags)
        else:
            # Local tracing
            trace = TraceEvent(
                name=name,
                session_id=session_id,
                input=input,
                metadata=metadata or {},
                tags=tags or [],
            )
            return trace
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get data for observability dashboard."""
        return {
            "token_usage": {
                "total": asdict(self.token_tracker.get_total_usage()),
                "by_session": {
                    sid: [asdict(u) for u in usages]
                    for sid, usages in self.token_tracker.session_usage.items()
                },
            },
            "performance": {
                "by_operation": {
                    op: self.performance_monitor.get_stats(op)
                    for op in set(m.operation for m in self.performance_monitor.metrics)
                },
            },
            "traces": {
                "langsmith": len(self.langsmith.traces),
                "langfuse": len(self.langfuse.traces),
            },
        }


# Decorators for easy instrumentation
def track_tokens(model: str = "", session_id: str = ""):
    """Decorator to track token usage for a function."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # This would need integration with the actual LLM client
            return func(*args, **kwargs)
        return wrapper
    return decorator


def measure_performance(operation: str = "", session_id: str = ""):
    """Decorator to measure function performance."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            observability = get_observability_manager()
            with observability.measure(operation or func.__name__, session_id):
                return func(*args, **kwargs)
        return wrapper
    return decorator


def trace_operation(name: str = "", session_id: str = "", tags: List[str] = None):
    """Decorator to trace a function."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            observability = get_observability_manager()
            with observability.trace(name or func.__name__, session_id=session_id, tags=tags) as trace:
                trace.input = {"args": str(args)[:200], "kwargs": str(kwargs)[:200]}
                try:
                    result = func(*args, **kwargs)
                    trace.output = str(result)[:500]
                    return result
                except Exception as e:
                    trace.error = str(e)
                    raise
        return wrapper
    return decorator


# Global observability manager instance
_observability_manager: Optional[ObservabilityManager] = None


def get_observability_manager() -> ObservabilityManager:
    """Get or create the global observability manager."""
    global _observability_manager
    if _observability_manager is None:
        _observability_manager = ObservabilityManager()
    return _observability_manager


def init_observability(log_dir: Path = None, langsmith_key: str = None, 
                       langfuse_public: str = None, langfuse_secret: str = None) -> ObservabilityManager:
    """Initialize observability with configuration."""
    global _observability_manager
    _observability_manager = ObservabilityManager(log_dir)
    if langsmith_key:
        _observability_manager.langsmith = LangSmithTracer(langsmith_key)
    if langfuse_public and langfuse_secret:
        _observability_manager.langfuse = LangfuseTracer(langfuse_public, langfuse_secret)
    return _observability_manager


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Kovanica Observability")
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # metrics
    metrics_parser = subparsers.add_parser("metrics", help="Show performance metrics")
    metrics_parser.add_argument("--operation", help="Filter by operation")
    metrics_parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    # tokens
    tokens_parser = subparsers.add_parser("tokens", help="Show token usage")
    tokens_parser.add_argument("--session", help="Filter by session")
    tokens_parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    # logs
    logs_parser = subparsers.add_parser("logs", help="Show structured logs")
    logs_parser.add_argument("--level", choices=["INFO", "WARNING", "ERROR"], help="Filter by level")
    logs_parser.add_argument("--session", help="Filter by session")
    logs_parser.add_argument("--limit", type=int, default=50)
    
    # dashboard
    dashboard_parser = subparsers.add_parser("dashboard", help="Show observability dashboard")
    dashboard_parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    
    observability = get_observability_manager()
    
    if args.command == "metrics":
        stats = observability.performance_monitor.get_stats(args.operation)
        if args.json:
            print(json.dumps(stats, indent=2))
        else:
            for op, stat in stats.items():
                print(f"\n{op}:")
                for k, v in stat.items():
                    print(f"  {k}: {v}")
    
    elif args.command == "tokens":
        if args.session:
            usage = observability.token_tracker.get_session_usage(args.session)
            if args.json:
                print(json.dumps([asdict(u) for u in usage], indent=2))
            else:
                for u in usage:
                    print(f"  {u.timestamp} | {u.model} | {u.prompt_tokens}+{u.completion_tokens}={u.total_tokens} tokens | ${u.cost_usd:.6f}")
        else:
            total = observability.token_tracker.get_total_usage()
            if args.json:
                print(json.dumps(asdict(total), indent=2))
            else:
                print(f"Total: {total.prompt_tokens}+{total.completion_tokens}={total.total_tokens} tokens | ${total.cost_usd:.6f}")
    
    elif args.command == "logs":
        # Would read from structured log file
        print("Log viewing not yet implemented")
    
    elif args.command == "dashboard":
        data = get_observability_manager().get_dashboard_data()
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print(json.dumps(data, indent=2))
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()