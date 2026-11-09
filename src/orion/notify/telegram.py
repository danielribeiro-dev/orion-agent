"""Canal Telegram do daemon via Bot API (ADR-032).

Nunca registra o token, nem em log nem em mensagens de exceção. Só o dono (``chat_id``) pode
responder um botão. Aprovação NUCLEAR remota é proibida e recusada antes, no roteador.
"""

from __future__ import annotations

import logging
import os
import stat
import time
from pathlib import Path
from typing import Any

import httpx

from orion.notify.models import Delivery, OutgoingMessage

logger = logging.getLogger(__name__)

_MAX_TEXT = 4000
_LONG_POLL_S = 25


def load_telegram_token(home: Path) -> str | None:
    """Token do env ``ORION_TELEGRAM_TOKEN`` ou de ``home/secrets/telegram_token`` (modo 0600)."""
    env = os.environ.get("ORION_TELEGRAM_TOKEN", "").strip()
    if env:
        return env
    path = Path(home) / "secrets" / "telegram_token"
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError:
        return None
    if mode & 0o077:
        logger.warning(
            "arquivo de token do Telegram ignorado: permissões %s (exigido 0600)", oct(mode)
        )
        return None
    try:
        token = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return token or None


class _RedactFilter(logging.Filter):
    """Remove o token de registros de ``httpx``/``httpcore`` (a URL da Bot API o contém)."""

    def __init__(self, token: str) -> None:
        super().__init__()
        self._token = token

    def filter(self, record: logging.LogRecord) -> bool:
        if self._token in record.getMessage():
            record.msg = record.getMessage().replace(self._token, "***")
            record.args = None
        return True


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


class TelegramNotifier:
    """Envio e aprovação por botões inline."""

    def __init__(
        self,
        token: str,
        chat_id: int,
        *,
        http: httpx.AsyncClient | None = None,
        base_url: str = "https://api.telegram.org",
    ) -> None:
        self._token = token
        self._chat_id = chat_id
        self._http = http or httpx.AsyncClient()
        self._owns_http = http is None
        self._base = f"{base_url.rstrip('/')}/bot{token}"
        self._offset = 0
        redact = _RedactFilter(token)
        for name in ("httpx", "httpcore"):
            logging.getLogger(name).addFilter(redact)

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def _call(
        self, method: str, payload: dict[str, Any], *, timeout_s: float = 15.0
    ) -> dict[str, Any] | None:
        """Chamada à Bot API; qualquer falha vira None (nunca levanta, nunca vaza o token)."""
        try:
            resp = await self._http.post(
                f"{self._base}/{method}", json=payload, timeout=timeout_s
            )
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("telegram %s falhou: %s", method, type(exc).__name__)
            return None
        if resp.status_code != 200 or not isinstance(data, dict) or not data.get("ok"):
            logger.warning("telegram %s recusado: HTTP %s", method, resp.status_code)
            return None
        return data

    @staticmethod
    def _text(msg: OutgoingMessage) -> str:
        text = msg.title if not msg.body else f"{msg.title}\n\n{msg.body}"
        return _truncate(text, _MAX_TEXT)

    async def send(self, msg: OutgoingMessage, delivery: Delivery) -> int | None:
        """Envia a mensagem; devolve o ``message_id`` do Telegram ou None em falha."""
        payload: dict[str, Any] = {
            "chat_id": self._chat_id,
            "text": self._text(msg),
            "disable_notification": delivery.silent,
        }
        if msg.actions:
            payload["reply_markup"] = {
                "inline_keyboard": [
                    [
                        {"text": a.label, "callback_data": f"{msg.id}:{a.id}"}
                        for a in msg.actions
                    ]
                ]
            }
        data = await self._call("sendMessage", payload)
        if data is None:
            return None
        result = data.get("result")
        if isinstance(result, dict) and isinstance(result.get("message_id"), int):
            return int(result["message_id"])
        return None

    async def ask(self, msg: OutgoingMessage, delivery: Delivery, timeout_s: float) -> str | None:
        """Envia e espera o toque do dono num botão; None no TTL ou em erro HTTP."""
        message_id = await self.send(msg, delivery)
        if message_id is None:
            return None
        deadline = time.monotonic() + timeout_s
        prefix = f"{msg.id}:"
        valid = {a.id: a for a in msg.actions}
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            poll = max(1, min(_LONG_POLL_S, int(remaining)))
            data = await self._call(
                "getUpdates",
                {
                    "offset": self._offset,
                    "timeout": poll,
                    "allowed_updates": ["callback_query"],
                },
                timeout_s=poll + 10,
            )
            if data is None:
                return None
            updates = data.get("result")
            for upd in updates if isinstance(updates, list) else []:
                if not isinstance(upd, dict):
                    continue
                uid = upd.get("update_id")
                if isinstance(uid, int):
                    self._offset = max(self._offset, uid + 1)
                cb = upd.get("callback_query")
                if not isinstance(cb, dict):
                    continue
                sender = cb.get("from")
                cb_data = cb.get("data")
                if (
                    not isinstance(sender, dict)
                    or sender.get("id") != self._chat_id
                    or not isinstance(cb_data, str)
                    or not cb_data.startswith(prefix)
                ):
                    continue
                action_id = cb_data[len(prefix) :]
                if action_id not in valid:
                    continue
                await self._call("answerCallbackQuery", {"callback_query_id": cb.get("id")})
                await self._call(
                    "editMessageText",
                    {
                        "chat_id": self._chat_id,
                        "message_id": message_id,
                        "text": _truncate(
                            f"{self._text(msg)}\n\nDecisão: {valid[action_id].label}", _MAX_TEXT
                        ),
                        "reply_markup": {"inline_keyboard": []},
                    },
                )
                return action_id
