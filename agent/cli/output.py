"""
Output formatting for Kovanica CLI (JSON, stream-JSON, text).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from enum import Enum
from typing import Any, Optional, TextIO


class OutputFormat(Enum):
    TEXT = "text"
    JSON = "json"
    STREAM_JSON = "stream-json"


class OutputFormatter:
    """Formats output in various formats."""
    
    def __init__(self, format: OutputFormat = OutputFormat.TEXT, stream: TextIO = None):
        self.format = format
        self.stream = stream or sys.stdout
        self._first_stream_item = True
    
    def set_format(self, format: OutputFormat) -> None:
        self.format = format
        self._first_stream_item = True
    
    def print(self, data: Any, **kwargs) -> None:
        """Print data in the configured format."""
        if self.format == OutputFormat.JSON:
            self._print_json(data)
        elif self.format == OutputFormat.STREAM_JSON:
            self._print_stream_json(data)
        else:
            self._print_text(data, **kwargs)
    
    def _print_text(self, data: Any, **kwargs) -> None:
        """Print as human-readable text."""
        if isinstance(data, str):
            print(data, file=self.stream, **kwargs)
        elif isinstance(data, dict):
            for key, value in data.items():
                print(f"{key}: {value}", file=self.stream, **kwargs)
        elif isinstance(data, list):
            for item in data:
                print(item, file=self.stream, **kwargs)
        else:
            print(str(data), file=self.stream, **kwargs)
    
    def _print_json(self, data: Any) -> None:
        """Print as single JSON envelope."""
        envelope = {
            "timestamp": datetime.now().isoformat(),
            "data": data,
        }
        json.dump(envelope, self.stream, default=str)
        self.stream.write("\n")
        self.stream.flush()
    
    def _print_stream_json(self, data: Any) -> None:
        """Print as streaming JSON (one object per line)."""
        if self._first_stream_item:
            # Print opening marker
            self.stream.write(json.dumps({"type": "start", "timestamp": datetime.now().isoformat()}) + "\n")
            self._first_stream_item = False
        
        # Print data item
        item = {
            "type": "data",
            "timestamp": datetime.now().isoformat(),
            "data": data,
        }
        json.dump(item, self.stream, default=str)
        self.stream.write("\n")
        self.stream.flush()
    
    def print_end(self) -> None:
        """Print end marker for stream-json."""
        if self.format == OutputFormat.STREAM_JSON:
            self.stream.write(json.dumps({"type": "end", "timestamp": datetime.now().isoformat()}) + "\n")
            self.stream.flush()
    
    def print_error(self, error: str, code: int = 1) -> None:
        """Print error in configured format."""
        if self.format == OutputFormat.JSON:
            envelope = {
                "timestamp": datetime.now().isoformat(),
                "error": error,
                "code": code,
            }
            json.dump(envelope, sys.stderr, default=str)
            sys.stderr.write("\n")
            sys.stderr.flush()
        elif self.format == OutputFormat.STREAM_JSON:
            item = {
                "type": "error",
                "timestamp": datetime.now().isoformat(),
                "error": error,
                "code": code,
            }
            json.dump(item, sys.stderr, default=str)
            sys.stderr.write("\n")
            sys.stderr.flush()
        else:
            print(f"Error: {error}", file=sys.stderr)
    
    def print_result(self, result: "CommandResult") -> None:
        """Print a CommandResult."""
        if self.format in (OutputFormat.JSON, OutputFormat.STREAM_JSON):
            data = {
                "success": result.success,
                "output": result.output,
                "error": result.error,
                "data": result.data,
            }
            self.print(data)
        else:
            if result.output:
                print(result.output, file=self.stream)
            if result.error:
                print(f"Error: {result.error}", file=sys.stderr)


class CommandResult:
    """Result of a command execution."""
    
    def __init__(
        self,
        success: bool,
        output: str = "",
        error: str = "",
        data: Any = None,
        should_exit: bool = False,
    ):
        self.success = success
        self.output = output
        self.error = error
        self.data = data
        self.should_exit = should_exit