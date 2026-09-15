"""
Security Hardening for Kovanica Agent.

Provides mTLS, audit logging, rate limiting, secret scanning, and security policies.
"""
from __future__ import annotations

import fnmatch
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import ssl
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Callable
from functools import wraps
import threading


@dataclass
class RateLimitRule:
    """Rate limiting rule."""
    path_pattern: str
    max_requests: int
    window_seconds: int
    methods: List[str] = field(default_factory=lambda: ["GET", "POST", "PUT", "DELETE", "PATCH"])
    scope: str = "ip"  # ip, user, global


@dataclass
class AuditEvent:
    """Security audit event."""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    event_type: str = ""  # auth, access, data, config, security
    action: str = ""  # login, logout, read, write, delete, create, update
    user_id: str = ""
    session_id: str = ""
    ip_address: str = ""
    user_agent: str = ""
    resource: str = ""
    result: str = "success"  # success, failure, blocked
    details: Dict[str, Any] = field(default_factory=dict)
    risk_level: str = "low"  # low, medium, high, critical


@dataclass
class SecretMatch:
    """Detected secret."""
    file_path: str
    line_number: int
    secret_type: str  # api_key, token, password, private_key, etc.
    matched_content: str
    severity: str = "high"  # low, medium, high, critical
    rule_id: str = ""


@dataclass
class SecurityPolicy:
    """Security policy configuration."""
    # Rate limiting
    rate_limits: List[RateLimitRule] = field(default_factory=list)
    
    # Authentication
    require_mtls: bool = False
    mtls_ca_cert: str = ""
    mtls_client_cert: str = ""
    mtls_client_key: str = ""
    jwt_issuer: str = ""
    jwt_audience: str = ""
    jwt_jwks_url: str = ""
    auth_dev_token: str = ""
    
    # Authorization
    default_role: str = "user"
    role_permissions: Dict[str, List[str]] = field(default_factory=dict)
    
    # Audit logging
    audit_enabled: bool = True
    audit_log_path: str = ""
    audit_retention_days: int = 90
    audit_events: List[str] = field(default_factory=lambda: ["auth", "access", "data", "config", "security"])
    
    # Secret scanning
    secret_scan_enabled: bool = True
    secret_scan_paths: List[str] = field(default_factory=lambda: ["."])
    secret_scan_exclude: List[str] = field(default_factory=lambda: [".git", "node_modules", "__pycache__", "venv", ".venv"])
    custom_patterns: List[Dict[str, str]] = field(default_factory=list)
    
    # Network security
    allowed_ips: List[str] = field(default_factory=list)  # CIDR notation
    blocked_ips: List[str] = field(default_factory=list)
    cors_origins: List[str] = field(default_factory=list)
    
    # Content security
    max_request_size: int = 10 * 1024 * 1024  # 10MB
    allowed_content_types: List[str] = field(default_factory=lambda: ["application/json", "text/plain"])
    
    # Session security
    session_timeout_minutes: int = 60
    max_sessions_per_user: int = 10
    csrf_protection: bool = True
    
    # Encryption
    encryption_enabled: bool = True
    encryption_key: str = ""
    encryption_algorithm: str = "AES-256-GCM"


class RateLimiter:
    """Rate limiter with multiple strategies."""
    
    def __init__(self, rules: List[RateLimitRule] = None):
        self.rules = rules or []
        self.counters: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()
    
    def add_rule(self, rule: RateLimitRule) -> None:
        self.rules.append(rule)
    
    def check_rate_limit(self, identifier: str, path: str, method: str) -> tuple[bool, Dict[str, Any]]:
        """Check if request is within rate limits."""
        now = time.time()
        matched_rules = [r for r in self.rules if self._match_rule(r, path, method)]
        
        if not matched_rules:
            return True, {"allowed": True, "remaining": -1, "reset": 0}
        
        with self._lock:
            for rule in matched_rules:
                key = f"{rule.scope}:{identifier}:{rule.path_pattern}"
                timestamps = self.counters[key]
                
                # Clean old timestamps
                cutoff = now - rule.window_seconds
                timestamps[:] = [ts for ts in timestamps if ts > cutoff]
                
                if len(timestamps) >= rule.max_requests:
                    oldest = min(timestamps)
                    reset_time = int(oldest + rule.window_seconds)
                    return False, {
                        "allowed": False,
                        "limit": rule.max_requests,
                        "remaining": 0,
                        "reset": reset_time,
                        "retry_after": int(reset_time - now) + 1,
                    }
                
                # Add current request
                timestamps.append(now)
                remaining = rule.max_requests - len(timestamps)
                reset_time = int(now + rule.window_seconds)
                
                return True, {
                    "allowed": True,
                    "limit": rule.max_requests,
                    "remaining": remaining,
                    "reset": reset_time,
                }
        
        return True, {"allowed": True, "remaining": -1, "reset": 0}
    
    def _match_rule(self, rule: RateLimitRule, path: str, method: str) -> bool:
        if method not in rule.methods:
            return False
        # Simple pattern matching (could use fnmatch or regex)
        if rule.path_pattern == "*" or rule.path_pattern == path:
            return True
        if rule.path_pattern.endswith("*"):
            prefix = rule.path_pattern[:-1]
            return path.startswith(prefix)
        return False
    
    def reset(self, identifier: str = None) -> None:
        """Reset rate limit counters."""
        with self._lock:
            if identifier:
                keys_to_remove = [k for k in self.counters if identifier in k]
                for k in keys_to_remove:
                    del self.counters[k]
            else:
                self.counters.clear()


class AuditLogger:
    """Security audit logger."""
    
    def __init__(self, policy: SecurityPolicy):
        self.policy = policy
        self.log_file = Path(policy.audit_log_path) if policy.audit_log_path else Path.home() / ".kovanica" / "logs" / "audit.jsonl"
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
    
    def log(self, event: AuditEvent) -> None:
        """Log an audit event."""
        if not self.policy.audit_enabled:
            return
        
        if event.event_type not in self.policy.audit_events:
            return
        
        with self._lock:
            with open(self.log_file, "a") as f:
                f.write(json.dumps(asdict(event)) + "\n")
    
    def log_auth(self, action: str, user_id: str, session_id: str, ip: str, 
                 user_agent: str, success: bool, details: Dict = None) -> None:
        """Log authentication event."""
        self.log(AuditEvent(
            event_type="auth",
            action=action,
            user_id=user_id,
            session_id=session_id,
            ip_address=ip,
            user_agent=user_agent,
            result="success" if success else "failure",
            details=details or {},
            risk_level="high" if not success else "low",
        ))
    
    def log_access(self, action: str, user_id: str, session_id: str, ip: str,
                   resource: str, success: bool, details: Dict = None) -> None:
        """Log resource access event."""
        self.log(AuditEvent(
            event_type="access",
            action=action,
            user_id=user_id,
            session_id=session_id,
            ip_address=ip,
            resource=resource,
            result="success" if success else "failure",
            details=details or {},
            risk_level="medium" if not success else "low",
        ))
    
    def log_security(self, action: str, user_id: str, session_id: str, ip: str,
                     details: Dict = None, risk_level: str = "high") -> None:
        """Log security event."""
        self.log(AuditEvent(
            event_type="security",
            action=action,
            user_id=user_id,
            session_id=session_id,
            ip_address=ip,
            result="blocked" if risk_level == "critical" else "warning",
            details=details or {},
            risk_level=risk_level,
        ))
    
    def query_logs(self, start_time: datetime = None, end_time: datetime = None,
                   event_type: str = None, user_id: str = None, limit: int = 100) -> List[AuditEvent]:
        """Query audit logs."""
        events = []
        if not self.log_file.exists():
            return events
        
        with open(self.log_file) as f:
            for line in f:
                try:
                    event = json.loads(line)
                    event_time = datetime.fromisoformat(event["timestamp"])
                    
                    if start_time and event_time < start_time:
                        continue
                    if end_time and event_time > end_time:
                        continue
                    if event_type and event["event_type"] != event_type:
                        continue
                    if user_id and event["user_id"] != user_id:
                        continue
                    
                    events.append(AuditEvent(**event))
                    if len(events) >= limit:
                        break
                except Exception:
                    pass
        
        return events


class SecretScanner:
    """Scans codebase for secrets."""
    
    # Built-in secret patterns
    PATTERNS = {
        "api_key": [
            (r"(?i)(api[_-]?key|apikey)\s*[:=]\s*[\"']?([a-zA-Z0-9_\-]{20,})[\"']?", "Generic API Key"),
            (r"(?i)(aws[_-]?access[_-]?key(?:[_-]?id)?|aws[_-]?secret[_-]?access[_-]?key)\s*[:=]\s*[\"']?([A-Za-z0-9/+=]{20,40})[\"']?", "AWS Access Key"),
            (r"(?i)(github[_-]?token|gh[_-]?token)\s*[:=]\s*[\"']?(gh[ps]_[a-zA-Z0-9]{36})[\"']?", "GitHub Token"),
            (r"(?i)(slack[_-]?token|slack[_-]?bot[_-]?token)\s*[:=]\s*[\"']?(xox[baprs]-[a-zA-Z0-9-]{10,})[\"']?", "Slack Token"),
            (r"(?i)(discord[_-]?token|discord[_-]?bot[_-]?token)\s*[:=]\s*[\"']?([a-zA-Z0-9._-]{50,})[\"']?", "Discord Token"),
            (r"(?i)(stripe[_-]?key|stripe[_-]?secret)\s*[:=]\s*[\"']?(sk_live_[a-zA-Z0-9]{24,})[\"']?", "Stripe Secret Key"),
            (r"(?i)(sendgrid[_-]?key|sendgrid[_-]?api[_-]?key)\s*[:=]\s*[\"']?(SG\.[a-zA-Z0-9_-]{20,})[\"']?", "SendGrid API Key"),
            (r"(?i)(twilio[_-]?sid|twilio[_-]?token)\s*[:=]\s*[\"']?(AC[a-zA-Z0-9]{32})[\"']?", "Twilio SID"),
            (r"(?i)(jwt[_-]?secret|jwt[_-]?key)\s*[:=]\s*[\"']?([a-zA-Z0-9_\-]{32,})[\"']?", "JWT Secret"),
        ],
        "private_key": [
            (r"-----BEGIN (RSA|EC|DSA|OPENSSH) PRIVATE KEY-----", "Private Key"),
            (r"-----BEGIN PRIVATE KEY-----", "Private Key (PKCS#8)"),
        ],
        "password": [
            (r"(?i)(password|passwd|pwd)\s*[:=]\s*[\"']([^\"']{8,})[\"']", "Password in config"),
            (r"(?i)(database[_-]?url|db[_-]?url)\s*[:=]\s*[\"']?[^\"']*://[^:]+:([^@\"']{8,})@", "Password in DB URL"),
        ],
        "connection_string": [
            (r"(?i)(connection[_-]?string|conn[_-]?str)\s*[:=]\s*[\"']([^\"']{20,})[\"']", "Connection String"),
            (r"(?i)(database[_-]?url|db[_-]?url)\s*[:=]\s*[\"']?[^\"']*://[^@\"']+@[^\"']+", "Database Connection String"),
        ],
    }
    
    def __init__(self, policy: SecurityPolicy):
        self.policy = policy
        self.custom_patterns = policy.custom_patterns
    
    def scan_file(self, file_path: Path) -> List[SecretMatch]:
        """Scan a single file for secrets."""
        matches = []
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
        except Exception:
            return matches
        
        for line_num, line in enumerate(lines, 1):
            # Check built-in patterns
            for category, patterns in self.PATTERNS.items():
                for pattern, secret_type in patterns:
                    matches_iter = re.finditer(pattern, line)
                    for match in matches_iter:
                        matched = match.group(0)
                        # Redact the secret in output
                        redacted = self._redact_secret(matched)
                        matches.append(SecretMatch(
                            file_path=str(file_path),
                            line_number=line_num,
                            secret_type=f"{category}:{secret_type}",
                            matched_content=redacted,
                            severity=self._get_severity(category),
                            rule_id=f"{category}:{secret_type}",
                        ))
            
            # Check custom patterns
            for custom in self.custom_patterns:
                pattern = custom.get("pattern", "")
                secret_type = custom.get("type", "custom")
                severity = custom.get("severity", "medium")
                try:
                    matches_iter = re.finditer(pattern, line)
                    for match in matches_iter:
                        matched = match.group(0)
                        redacted = self._redact_secret(matched)
                        matches.append(SecretMatch(
                            file_path=str(file_path),
                            line_number=line_num,
                            secret_type=f"custom:{secret_type}",
                            matched_content=redacted,
                            severity=severity,
                            rule_id=f"custom:{secret_type}",
                        ))
                except re.error:
                    pass
        
        return matches
    
    def _redact_secret(self, secret: str) -> str:
        """Redact secret for safe display."""
        if len(secret) <= 8:
            return "*" * len(secret)
        return secret[:4] + "*" * (len(secret) - 8) + secret[-4:]
    
    def _get_severity(self, category: str) -> str:
        severity_map = {
            "api_key": "high",
            "private_key": "critical",
            "password": "high",
            "connection_string": "high",
        }
        return severity_map.get(category, "medium")
    
    def scan_directory(self, root_path: Path, exclude_patterns: List[str] = None) -> List[SecretMatch]:
        """Scan directory recursively for secrets."""
        all_matches = []
        exclude = exclude_patterns or self.policy.secret_scan_exclude
        
        for file_path in root_path.rglob("*"):
            if not file_path.is_file():
                continue
            
            # Check exclude patterns
            rel_path = file_path.relative_to(root_path)
            if any(fnmatch.fnmatch(str(rel_path), pat) for pat in exclude):
                continue
            
            # Skip binary files
            if self._is_binary(file_path):
                continue
            
            matches = self.scan_file(file_path)
            all_matches.extend(matches)
        
        return all_matches
    
    def _is_binary(self, file_path: Path) -> bool:
        """Check if file is binary."""
        try:
            with open(file_path, 'rb') as f:
                chunk = f.read(1024)
                return b'\x00' in chunk
        except Exception:
            return True


class MTLSManager:
    """Manages mTLS configuration and certificates."""
    
    def __init__(self, policy: SecurityPolicy):
        self.policy = policy
        self.ssl_context: Optional[ssl.SSLContext] = None
    
    def create_server_context(self) -> Optional[ssl.SSLContext]:
        """Create SSL context for server with mTLS."""
        if not self.policy.require_mtls:
            return None
        
        if not all([self.policy.mtls_ca_cert, self.policy.mtls_client_cert, self.policy.mtls_client_key]):
            raise ValueError("mTLS requires CA cert, client cert, and client key")
        
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_verify_locations(self.policy.mtls_ca_cert)
        context.load_cert_chain(self.policy.mtls_client_cert, self.policy.mtls_client_key)
        
        # Set minimum TLS version
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.maximum_version = ssl.TLSVersion.TLSv1_3
        
        # Set cipher suites
        context.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20')
        
        self.ssl_context = context
        return context
    
    def create_client_context(self) -> Optional[ssl.SSLContext]:
        """Create SSL context for client with mTLS."""
        if not self.policy.require_mtls:
            return None
        
        if not all([self.policy.mtls_ca_cert, self.policy.mtls_client_cert, self.policy.mtls_client_key]):
            raise ValueError("mTLS requires CA cert, client cert, and client key")
        
        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_verify_locations(self.policy.mtls_ca_cert)
        context.load_cert_chain(self.policy.mtls_client_cert, self.policy.mtls_client_key)
        
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.maximum_version = ssl.TLSVersion.TLSv1_3
        
        return context
    
    def verify_certificate(self, cert_pem: str) -> Dict[str, Any]:
        """Verify certificate details."""
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization
        
        cert = x509.load_pem_x509_certificate(cert_pem.encode())
        
        return {
            "subject": cert.subject.rfc4514_string(),
            "issuer": cert.issuer.rfc4514_string(),
            "serial_number": cert.serial_number,
            "not_valid_before": cert.not_valid_before_utc.isoformat(),
            "not_valid_after": cert.not_valid_after_utc.isoformat(),
            "is_expired": cert.not_valid_after_utc < datetime.utcnow(),
            "is_ca": cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca if cert.extensions.get_extension_for_class(x509.BasicConstraints) else False,
            "key_usage": [ku.name for ku in cert.extensions.get_extension_for_class(x509.KeyUsage).value] if cert.extensions.get_extension_for_class(x509.KeyUsage) else [],
            "subject_alt_names": [san.value for san in cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value] if cert.extensions.get_extension_for_class(x509.SubjectAlternativeName) else [],
        }


class IPFilter:
    """IP address filtering for access control."""
    
    def __init__(self, allowed: List[str] = None, blocked: List[str] = None):
        self.allowed_networks = [ipaddress.ip_network(cidr) for cidr in (allowed or [])]
        self.blocked_networks = [ipaddress.ip_network(cidr) for cidr in (blocked or [])]
    
    def is_allowed(self, ip: str) -> bool:
        """Check if IP is allowed."""
        try:
            ip_addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        
        # Check blocked first
        for network in self.blocked_networks:
            if ip_addr in network:
                return False
        
        # If allowed list is empty, allow all (unless blocked)
        if not self.allowed_networks:
            return True
        
        # Check allowed
        for network in self.allowed_networks:
            if ip_addr in network:
                return True
        
        return False
    
    def add_allowed(self, cidr: str) -> None:
        self.allowed_networks.append(ipaddress.ip_network(cidr))
    
    def add_blocked(self, cidr: str) -> None:
        self.blocked_networks.append(ipaddress.ip_network(cidr))
    
    def remove_allowed(self, cidr: str) -> bool:
        try:
            network = ipaddress.ip_network(cidr)
            for i, existing in enumerate(self.allowed_networks):
                if existing == network:
                    self.allowed_networks.pop(i)
                    return True
            return False
        except ValueError:
            return False
    
    def remove_blocked(self, cidr: str) -> bool:
        try:
            network = ipaddress.ip_network(cidr)
            for i, existing in enumerate(self.blocked_networks):
                if existing == network:
                    self.blocked_networks.pop(i)
                    return True
            return False
        except ValueError:
            return False


class SecurityManager:
    """Central security manager."""
    
    def __init__(self, policy: SecurityPolicy = None):
        self.policy = policy or SecurityPolicy()
        self.rate_limiter = RateLimiter(self.policy.rate_limits)
        self.audit_logger = AuditLogger(self.policy)
        self.secret_scanner = SecretScanner(self.policy)
        self.mtls_manager = MTLSManager(self.policy)
        self.ip_filter = IPFilter(self.policy.allowed_ips, self.policy.blocked_ips)
        self._lock = threading.Lock()
    
    def check_request(self, request: Dict[str, Any]) -> tuple[bool, Dict[str, Any]]:
        """Check if request passes all security checks."""
        ip = request.get("ip", "")
        path = request.get("path", "/")
        method = request.get("method", "GET")
        user_id = request.get("user_id", "")
        
        # IP filtering
        if not self.ip_filter.is_allowed(ip):
            self.audit_logger.log_security(
                action="ip_blocked",
                user_id=user_id,
                session_id=request.get("session_id", ""),
                ip=ip,
                details={"path": path, "method": method},
                risk_level="high"
            )
            return False, {"error": "IP blocked", "code": 403}
        
        # Rate limiting
        allowed, rate_info = self.rate_limiter.check_rate_limit(ip, path, method)
        if not allowed:
            self.audit_logger.log_security(
                action="rate_limit_exceeded",
                user_id=user_id,
                session_id=request.get("session_id", ""),
                ip=ip,
                details={"path": path, "method": method, **rate_info},
                risk_level="medium"
            )
            return False, {"error": "Rate limit exceeded", "code": 429, **rate_info}
        
        # Request size check
        content_length = request.get("content_length", 0)
        if content_length > self.policy.max_request_size:
            return False, {"error": "Request too large", "code": 413}
        
        # Content type check
        content_type = request.get("content_type", "")
        if content_type and content_type not in self.policy.allowed_content_types:
            return False, {"error": "Unsupported content type", "code": 415}
        
        return True, {"rate_limit": rate_info}
    
    def scan_for_secrets(self, path: str = ".") -> List[SecretMatch]:
        """Scan codebase for secrets."""
        return self.secret_scanner.scan_directory(Path(path))
    
    def create_ssl_context(self, server: bool = True) -> Optional[ssl.SSLContext]:
        """Create SSL context with mTLS if configured."""
        if self.policy.require_mtls:
            return self.mtls_manager.create_server_context() if server else self.mtls_manager.create_client_context()
        return None
    
    def audit_auth(self, action: str, user_id: str, session_id: str, ip: str,
                   user_agent: str, success: bool, details: Dict = None) -> None:
        """Log authentication event."""
        self.audit_logger.log_auth(action, user_id, session_id, ip, user_agent, success, details)
    
    def audit_access(self, action: str, user_id: str, session_id: str, ip: str,
                     resource: str, success: bool, details: Dict = None) -> None:
        """Log access event."""
        self.audit_logger.log_access(action, user_id, session_id, ip, resource, success, details)
    
    def audit_security(self, action: str, user_id: str, session_id: str, ip: str,
                       details: Dict = None, risk_level: str = "high") -> None:
        """Log security event."""
        self.audit_logger.log_security(action, user_id, session_id, ip, details, risk_level)


# Default security policies
DEFAULT_POLICY = SecurityPolicy(
    rate_limits=[
        RateLimitRule(path_pattern="/chat", max_requests=30, window_seconds=60, methods=["POST"]),
        RateLimitRule(path_pattern="/confirm", max_requests=10, window_seconds=60, methods=["POST"]),
        RateLimitRule(path_pattern="/api/*", max_requests=100, window_seconds=60),
        RateLimitRule(path_pattern="*", max_requests=200, window_seconds=60),
    ],
    cors_origins=["https://kovanica.online", "https://www.kovanica.online", "http://localhost:3000"],
    max_request_size=10 * 1024 * 1024,
    allowed_content_types=["application/json", "text/plain"],
    session_timeout_minutes=60,
    max_sessions_per_user=10,
    audit_enabled=True,
    audit_log_path=str(Path.home() / ".kovanica" / "logs" / "audit.jsonl"),
    secret_scan_enabled=True,
    secret_scan_paths=["."],
    secret_scan_exclude=[".git", "node_modules", "__pycache__", "venv", ".venv", "target", "dist", "build"],
)


def create_security_manager(policy: SecurityPolicy = None) -> SecurityManager:
    """Create security manager with default or custom policy."""
    return SecurityManager(policy or DEFAULT_POLICY)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Kovanica Security Tools")
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # scan
    scan_parser = subparsers.add_parser("scan", help="Scan for secrets")
    scan_parser.add_argument("--path", default=".", help="Path to scan")
    scan_parser.add_argument("--json", action="store_true", help="Output as JSON")
    scan_parser.add_argument("--fail-on-find", action="store_true", help="Exit with error if secrets found")
    
    # audit
    audit_parser = subparsers.add_parser("audit", help="Query audit logs")
    audit_parser.add_argument("--type", help="Event type filter")
    audit_parser.add_argument("--user", help="Filter by user ID")
    audit_parser.add_argument("--start", help="Start time (ISO format)")
    audit_parser.add_argument("--end", help="End time (ISO format)")
    audit_parser.add_argument("--limit", type=int, default=100)
    audit_parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    # rate-limit
    rl_parser = subparsers.add_parser("rate-limit", help="Check rate limit")
    rl_parser.add_argument("--ip", required=True, help="IP address")
    rl_parser.add_argument("--path", default="/", help="Request path")
    rl_parser.add_argument("--method", default="GET", help="HTTP method")
    
    # ip-filter
    ip_parser = subparsers.add_parser("ip-filter", help="Manage IP filters")
    ip_subparsers = ip_parser.add_subparsers(dest="ip_action")
    ip_allow = ip_subparsers.add_parser("allow", help="Allow IP/CIDR")
    ip_allow.add_argument("cidr", help="CIDR to allow")
    ip_block = ip_subparsers.add_parser("block", help="Block IP/CIDR")
    ip_block.add_argument("cidr", help="CIDR to block")
    ip_list = ip_subparsers.add_parser("list", help="List IP filters")
    
    # mTLS
    mtls_parser = subparsers.add_parser("mtls", help="mTLS management")
    mtls_subparsers = mtls_parser.add_subparsers(dest="mtls_action")
    mtls_create = mtls_subparsers.add_parser("create-context", help="Create mTLS context")
    mtls_create.add_argument("--server", action="store_true", help="Create server context")
    mtls_create.add_argument("--ca-cert", required=True, help="CA certificate path")
    mtls_create.add_argument("--client-cert", required=True, help="Client certificate path")
    mtls_create.add_argument("--client-key", required=True, help="Client key path")
    mtls_verify = mtls_subparsers.add_parser("verify", help="Verify certificate")
    mtls_verify.add_argument("cert", help="Certificate PEM file")
    
    args = parser.parse_args()
    
    manager = create_security_manager()
    
    if args.command == "scan":
        matches = manager.scan_for_secrets(args.path)
        if args.json:
            print(json.dumps([asdict(m) for m in matches], indent=2))
        else:
            if not matches:
                print("No secrets found")
            else:
                for m in matches:
                    print(f"{m.file_path}:{m.line_number} [{m.severity}] {m.secret_type}: {m.matched_content}")
        
        if args.fail_on_find and matches:
            sys.exit(1)
    
    elif args.command == "audit":
        start = datetime.fromisoformat(args.start) if args.start else None
        end = datetime.fromisoformat(args.end) if args.end else None
        events = manager.audit_logger.query_logs(start, end, args.type, args.user, args.limit)
        if args.json:
            print(json.dumps([asdict(e) for e in events], indent=2))
        else:
            for e in events:
                print(f"{e.timestamp} [{e.risk_level}] {e.event_type}:{e.action} user={e.user_id} ip={e.ip_address} result={e.result}")
    
    elif args.command == "rate-limit":
        allowed, info = manager.rate_limiter.check_rate_limit(args.ip, args.path, args.method)
        print(json.dumps({"allowed": allowed, **info}, indent=2))
    
    elif args.command == "ip-filter":
        if args.ip_action == "allow":
            manager.ip_filter.add_allowed(args.cidr)
            print(f"Allowed {args.cidr}")
        elif args.ip_action == "block":
            manager.ip_filter.add_blocked(args.cidr)
            print(f"Blocked {args.cidr}")
        elif args.ip_action == "list":
            print("Allowed:")
            for n in manager.ip_filter.allowed_networks:
                print(f"  {n}")
            print("Blocked:")
            for n in manager.ip_filter.blocked_networks:
                print(f"  {n}")
    
    elif args.command == "mtls":
        if args.mtls_action == "create-context":
            policy = SecurityPolicy(
                require_mtls=True,
                mtls_ca_cert=args.ca_cert,
                mtls_client_cert=args.client_cert,
                mtls_client_key=args.client_key,
            )
            manager = SecurityManager(policy)
            context = manager.mtls_manager.create_server_context() if args.server else manager.mtls_manager.create_client_context()
            if context:
                print("mTLS context created successfully")
            else:
                print("Failed to create mTLS context")
        elif args.mtls_action == "verify":
            manager = create_security_manager()
            with open(args.cert) as f:
                cert_pem = f.read()
            result = manager.mtls_manager.verify_certificate(cert_pem)
            print(json.dumps(result, indent=2))
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()