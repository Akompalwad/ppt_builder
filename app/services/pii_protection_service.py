"""Owner-scoped PII tokenisation for external provider boundaries."""
from __future__ import annotations

import json
import re
from copy import deepcopy

from app.config import get_settings
from app.models.database import PresentationPIIVault
from app.schemas.presentation import PresentationSpec


class PIIProtectionError(ValueError):
    """Raised when sensitive content cannot safely cross a provider boundary."""


class PIIProtectionService:
    _email=re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?![\w.-])")
    _phone=re.compile(r"(?<!\w)(?:\+?\d[\d .()\-]{7,}\d)(?!\w)")
    _credential=re.compile(
        r"(?i)\b(?:password|api[ _-]?key|secret|access[ _-]?token|private[ _-]?key)\s*[:=]\s*\S+"
    )

    @staticmethod
    def _fernet():
        key=get_settings().pii_vault_key.strip()
        if not key:
            raise PIIProtectionError("PII protection needs PII_VAULT_KEY before contact details can be restored.")
        try:
            from cryptography.fernet import Fernet
        except ImportError as exc:  # Deployment must install requirements.txt.
            raise PIIProtectionError("PII protection dependency is unavailable on this server.") from exc
        try:
            return Fernet(key.encode())
        except (TypeError, ValueError) as exc:
            raise PIIProtectionError("PII_VAULT_KEY is not a valid Fernet key.") from exc

    @classmethod
    def tokenize(cls, value: str | None) -> tuple[str | None, dict[str, str]]:
        if not value or not get_settings().pii_protection_enabled:
            return value, {}
        if cls._credential.search(value):
            raise PIIProtectionError("Credentials and secrets cannot be included in a presentation prompt.")
        tokens: dict[str, str]={}

        def replace(pattern: re.Pattern[str], prefix: str, source: str) -> str:
            def callback(match: re.Match[str]) -> str:
                original=match.group(0)
                existing=next((token for token, saved in tokens.items() if saved == original), None)
                if existing:
                    return existing
                token=f"{{{{PII_{prefix}_{sum(key.startswith(f'{{{{PII_{prefix}_') for key in tokens) + 1}}}}}"
                tokens[token]=original
                return token
            return pattern.sub(callback, source)

        redacted=replace(cls._email, "EMAIL", value)
        redacted=replace(cls._phone, "PHONE", redacted)
        return redacted, tokens

    @classmethod
    def save_tokens(cls, db, presentation_id: str, user_id: str, tokens: dict[str, str]) -> None:
        if not tokens:
            return
        encrypted=cls._fernet().encrypt(json.dumps(tokens, sort_keys=True).encode()).decode()
        vault=db.get(PresentationPIIVault, presentation_id)
        if vault:
            existing=cls.tokens_for(db, presentation_id, user_id)
            existing.update(tokens)
            vault.encrypted_tokens=cls._fernet().encrypt(json.dumps(existing, sort_keys=True).encode()).decode()
            return
        db.add(PresentationPIIVault(presentation_id=presentation_id, user_id=user_id, encrypted_tokens=encrypted))

    @classmethod
    def tokens_for(cls, db, presentation_id: str, user_id: str) -> dict[str, str]:
        vault=db.get(PresentationPIIVault, presentation_id)
        if not vault or vault.user_id != user_id:
            return {}
        try:
            return json.loads(cls._fernet().decrypt(vault.encrypted_tokens.encode()).decode())
        except Exception as exc:
            raise PIIProtectionError("The protected values for this presentation are unavailable.") from exc

    @staticmethod
    def restore_text(value: str | None, tokens: dict[str, str]) -> str | None:
        if not value or not tokens:
            return value
        restored=value
        for token, original in tokens.items():
            restored=restored.replace(token, original)
        return restored

    @classmethod
    def restore_spec(cls, spec: PresentationSpec, tokens: dict[str, str]) -> PresentationSpec:
        if not tokens:
            return spec
        def restore(value):
            if isinstance(value, str):
                return cls.restore_text(value, tokens)
            if isinstance(value, list):
                return [restore(item) for item in value]
            if isinstance(value, dict):
                return {key: restore(item) for key, item in value.items()}
            return value
        return PresentationSpec.model_validate(restore(deepcopy(spec.model_dump(mode="json"))))
