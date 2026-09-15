#!/usr/bin/env python3
"""
Vault client for fetching secrets from HashiCorp Vault.
"""

import os
from typing import Optional

try:
    import hvac
except ImportError:
    hvac = None


def is_vault_available() -> bool:
    """Check if Vault dependencies are installed and configured."""
    if hvac is None:
        return False
    vault_addr = os.environ.get("VAULT_ADDR")
    vault_token = os.environ.get("VAULT_TOKEN")
    return bool(vault_addr and vault_token)


def get_secret_from_vault(
    vault_addr: str,
    vault_token: str,
    secret_path: str,
    secret_key: str = "value",
    verify: bool = True,
) -> Optional[str]:
    """
    Fetch a secret from HashiCorp Vault.

    Args:
        vault_addr: Vault server address (e.g., "https://vault.example.com:8200")
        vault_token: Vault token for authentication
        secret_path: Path to the secret (e.g., "secret/data/myapp")
        secret_key: Key within the secret data to fetch (default: "value")
        verify: Whether to verify SSL certificates (default: True)

    Returns:
        The secret value as a string, or None if not found or on error.
    """
    if hvac is None:
        return None

    try:
        client = hvac.Client(
            url=vault_addr,
            token=vault_token,
            verify=verify,
        )

        # Check if client is authenticated
        if not client.is_authenticated():
            return None

        # Read the secret
        response = client.secrets.kv.v2.read_secret_version(path=secret_path)
        secret_data = response.get("data", {}).get("data", {})
        return secret_data.get(secret_key)
    except Exception as e:
        # Log the error in a real application
        # For now, we just return None
        return None


def get_openai_api_key_from_vault(
    vault_addr: Optional[str] = None,
    vault_token: Optional[str] = None,
) -> Optional[str]:
    """
    Fetch the OpenAI API key from Vault.

    Uses environment variables for configuration if not provided:
        VAULT_ADDR: Vault server address
        VAULT_TOKEN: Vault token
        VAULT_OPENAI_SECRET_PATH: Path to the secret (default: "secret/data/openai")
        VAULT_OPENAI_SECRET_KEY: Key within the secret (default: "api_key")

    Args:
        vault_addr: Vault server address (overrides VAULT_ADDR if provided)
        vault_token: Vault token (overrides VAULT_TOKEN if provided)

    Returns:
        The OpenAI API key as a string, or None if not found or on error.
    """
    addr = vault_addr or os.environ.get("VAULT_ADDR")
    token = vault_token or os.environ.get("VAULT_TOKEN")
    secret_path = os.environ.get(
        "VAULT_OPENAI_SECRET_PATH", "secret/data/openai"
    )
    secret_key = os.environ.get("VAULT_OPENAI_SECRET_KEY", "api_key")

    if not addr or not token:
        return None

    return get_secret_from_vault(
        vault_addr=addr,
        vault_token=token,
        secret_path=secret_path,
        secret_key=secret_key,
    )


def get_dev_token_from_vault(
    vault_addr: Optional[str] = None,
    vault_token: Optional[str] = None,
) -> Optional[str]:
    """
    Fetch the agent dev token from Vault.

    Uses environment variables for configuration if not provided:
        VAULT_ADDR: Vault server address
        VAULT_TOKEN: Vault token
        VAULT_DEV_TOKEN_SECRET_PATH: Path to the secret (default: "secret/data/dev-token")
        VAULT_DEV_TOKEN_SECRET_KEY: Key within the secret (default: "token")

    Args:
        vault_addr: Vault server address (overrides VAULT_ADDR if provided)
        vault_token: Vault token (overrides VAULT_TOKEN if provided)

    Returns:
        The dev token as a string, or None if not found or on error.
    """
    addr = vault_addr or os.environ.get("VAULT_ADDR")
    token = vault_token or os.environ.get("VAULT_TOKEN")
    secret_path = os.environ.get(
        "VAULT_DEV_TOKEN_SECRET_PATH", "secret/data/dev-token"
    )
    secret_key = os.environ.get("VAULT_DEV_TOKEN_SECRET_KEY", "token")

    if not addr or not token:
        return None

    return get_secret_from_vault(
        vault_addr=addr,
        vault_token=token,
        secret_path=secret_path,
        secret_key=secret_key,
    )