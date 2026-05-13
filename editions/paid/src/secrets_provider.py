"""Secrets provider abstraction with env and file backends."""

from __future__ import annotations

import json
import os
from pathlib import Path


def load_secret(name: str, *, provider: str = "env", secrets_file: str = "config/secrets.json") -> str | None:
    provider = (provider or "env").lower()
    if provider == "env":
        return os.getenv(name)
    if provider == "file":
        p = Path(secrets_file)
        if not p.exists():
            return None
        try:
            payload = json.loads(p.read_text())
        except Exception:
            return None
        value = payload.get(name)
        return str(value) if value is not None else None
    if provider in {"vault", "azure-keyvault"}:
        # 1) Simple env-map fallback: VAULT_SECRET_<NAME>
        mapped = os.getenv(f"VAULT_SECRET_{name}")
        if mapped:
            return mapped

        # 2) File-backed vault mock for local/dev parity
        vault_file = Path(os.getenv("VAULT_SECRETS_FILE", secrets_file))
        if vault_file.exists():
            try:
                payload = json.loads(vault_file.read_text())
                value = payload.get(name)
                if value is not None:
                    return str(value)
            except Exception:
                pass

        # 3) Optional Azure Key Vault path (enabled only when deps are installed)
        vault_url = os.getenv("AZURE_KEY_VAULT_URL")
        if vault_url:
            try:
                from azure.identity import DefaultAzureCredential  # type: ignore
                from azure.keyvault.secrets import SecretClient  # type: ignore

                client = SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())
                return client.get_secret(name).value
            except Exception:
                return None
        return None
    # Fallback to env for unknown providers
    return os.getenv(name)
