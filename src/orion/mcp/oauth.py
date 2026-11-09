"""OAuth 2.1 (authorization code + PKCE S256) para servidores MCP remotos.

O SDK ``mcp`` faz a descoberta (PRM / metadados do servidor), o registro
dinâmico, o PKCE, o parâmetro ``resource`` e o refresh. Aqui ficam as peças do
ORION: armazenamento de tokens em ``~/.orion/mcp_auth/<servidor>.json`` (diretório
0700, arquivo 0600, escrita atômica) e o retorno do navegador por um servidor
HTTP em ``127.0.0.1`` (porta efêmera, só aceita ``/callback``).

Na inicialização o fluxo é **não interativo**: sem token válido o servidor fica
em erro com a instrução ``/mcp auth <servidor>``; o navegador só abre quando o
Senhor pede.
"""

from __future__ import annotations

import asyncio
import contextlib
import html
import logging
import re
import time
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.shared.auth import (
    AuthorizationCodeResult,
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthToken,
)

from orion.mcp.models import MCPServerConfig
from orion.settings.io import read_json_object, write_private_json

logger = logging.getLogger(__name__)

AUTH_DIR = "mcp_auth"
CALLBACK_TIMEOUT = 300.0
_SAFE = re.compile(r"[^A-Za-z0-9_.-]")


class AuthRequired(Exception):
    """O servidor exige login e o fluxo atual não pode abrir o navegador."""

    def __init__(self, server: str) -> None:
        super().__init__(f"autenticação necessária: use /mcp auth {server}")
        self.server = server


def auth_file(home: Path, server: str) -> Path:
    return home / AUTH_DIR / f"{_SAFE.sub('_', server)}.json"


class FileTokenStorage(TokenStorage):
    """Tokens e registro do cliente em arquivo privado (0600)."""

    def __init__(self, home: Path, server: str) -> None:
        self._path = auth_file(home, server)

    def _read(self) -> dict[str, Any]:
        return read_json_object(self._path) or {}

    def has_tokens(self) -> bool:
        return bool(self._read().get("tokens"))

    async def get_tokens(self) -> OAuthToken | None:
        data = self._read()
        raw = data.get("tokens")
        if not isinstance(raw, dict):
            return None
        token = OAuthToken.model_validate(raw)
        obtained = data.get("obtained_at")
        if token.expires_in is not None and isinstance(obtained, int | float):
            remaining = int(token.expires_in - (time.time() - obtained))
            token = token.model_copy(update={"expires_in": max(remaining, 0)})
        return token

    async def set_tokens(self, tokens: OAuthToken) -> None:
        data = self._read()
        data["tokens"] = tokens.model_dump(mode="json", exclude_none=True)
        data["obtained_at"] = time.time()
        write_private_json(self._path, data)

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        raw = self._read().get("client_info")
        return OAuthClientInformationFull.model_validate(raw) if isinstance(raw, dict) else None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        data = self._read()
        data["client_info"] = client_info.model_dump(mode="json", exclude_none=True)
        write_private_json(self._path, data)

    def forget_client_info(self) -> None:
        data = self._read()
        if data.pop("client_info", None) is not None:
            write_private_json(self._path, data)

    def preferred_port(self) -> int | None:
        """Porta do ``redirect_uri`` já registrado, para reutilizar o registro."""
        info = self._read().get("client_info")
        uris = info.get("redirect_uris") if isinstance(info, dict) else None
        if isinstance(uris, list) and uris:
            port = urlsplit(str(uris[0])).port
            return port
        return None

    def revoke(self) -> bool:
        """Apaga tokens e registro (``/mcp remove``)."""
        if self._path.exists():
            self._path.unlink()
            return True
        return False


class LoopbackCallback:
    """Recebe o redirect do navegador em ``http://127.0.0.1:<porta>/callback``."""

    def __init__(self) -> None:
        self._server: asyncio.Server | None = None
        self._result: asyncio.Future[AuthorizationCodeResult] | None = None
        self.port = 0

    @property
    def redirect_uri(self) -> str:
        return f"http://127.0.0.1:{self.port}/callback"

    async def start(self, preferred_port: int | None = None) -> None:
        self._result = asyncio.get_running_loop().create_future()
        for port in (preferred_port, 0) if preferred_port else (0,):
            try:
                self._server = await asyncio.start_server(self._handle, "127.0.0.1", port)
                break
            except OSError:
                continue
        if self._server is None:
            raise OSError("não foi possível abrir a porta de callback OAuth em 127.0.0.1")
        self.port = self._server.sockets[0].getsockname()[1]

    async def wait(self, timeout: float = CALLBACK_TIMEOUT) -> AuthorizationCodeResult:
        if self._result is None:
            raise RuntimeError("LoopbackCallback não iniciado")
        return await asyncio.wait_for(self._result, timeout)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            with contextlib.suppress(Exception):
                await self._server.wait_closed()
            self._server = None

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        status, body = "404 Not Found", "não encontrado"
        try:
            line = (await asyncio.wait_for(reader.readline(), 5.0)).decode("latin-1")
            parts = line.split()
            target = parts[1] if len(parts) >= 2 and parts[0] == "GET" else ""
            url = urlsplit(target)
            if url.path == "/callback":
                query = parse_qs(url.query)
                code = (query.get("code") or [""])[0]
                error = (query.get("error") or [""])[0]
                if code and self._result and not self._result.done():
                    self._result.set_result(
                        AuthorizationCodeResult(
                            code=code,
                            state=(query.get("state") or [""])[0] or None,
                            iss=(query.get("iss") or [""])[0] or None,
                        )
                    )
                    status, body = "200 OK", "ORION autorizado. Pode fechar esta aba."
                elif error and self._result and not self._result.done():
                    self._result.set_exception(
                        PermissionError(f"autorização negada: {html.escape(error)}")
                    )
                    status, body = "400 Bad Request", "Autorização negada."
        except Exception:  # noqa: BLE001 - rede hostil nunca derruba o ORION
            logger.debug("callback OAuth inválido", exc_info=True)
        payload = (
            f"<!doctype html><meta charset=utf-8><title>ORION</title><p>{html.escape(body)}</p>"
        ).encode()
        writer.write(
            f"HTTP/1.1 {status}\r\nContent-Type: text/html; charset=utf-8\r\n"
            f"Content-Length: {len(payload)}\r\nConnection: close\r\n\r\n".encode() + payload
        )
        with contextlib.suppress(Exception):
            await writer.drain()
        writer.close()


class OAuthSetup:
    """Provider pronto para uso mais a limpeza do callback (se interativo)."""

    def __init__(self, provider: OAuthClientProvider, callback: LoopbackCallback | None) -> None:
        self.provider = provider
        self.callback = callback

    async def close(self) -> None:
        if self.callback is not None:
            await self.callback.stop()


async def build_oauth(
    cfg: MCPServerConfig,
    home: Path,
    *,
    interactive: bool,
    notify: Callable[[str, str], None] | None = None,
    open_browser: Callable[[str], Any] = webbrowser.open,
    on_auth_required: Callable[[], None] | None = None,
) -> OAuthSetup:
    """Monta o ``OAuthClientProvider`` do SDK para *cfg*.

    ``interactive=False`` nunca abre o navegador: levanta :class:`AuthRequired`
    se for preciso autorizar. ``notify(server, url)`` mostra a URL ao Senhor.
    """
    storage = FileTokenStorage(home, cfg.name)
    callback: LoopbackCallback | None = None
    if interactive:
        callback = LoopbackCallback()
        preferred = storage.preferred_port()
        await callback.start(preferred)
        if preferred and callback.port != preferred:
            storage.forget_client_info()  # redirect_uri mudou: registra de novo
        redirect_uri = callback.redirect_uri
    else:
        info = await storage.get_client_info()
        redirect_uri = (
            str(info.redirect_uris[0]) if info and info.redirect_uris else "http://127.0.0.1/callback"
        )

    metadata = OAuthClientMetadata(
        redirect_uris=[redirect_uri],  # type: ignore[list-item]
        client_name="O.R.I.O.N",
        scope=cfg.scope,
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        token_endpoint_auth_method="none",
    )

    async def redirect_handler(url: str) -> None:
        if not interactive:
            if on_auth_required:
                on_auth_required()  # a exceção pode se perder no cancelamento do transporte
            raise AuthRequired(cfg.name)
        if notify:
            notify(cfg.name, url)
        with contextlib.suppress(Exception):
            open_browser(url)

    async def callback_handler() -> AuthorizationCodeResult:
        if callback is None:
            raise AuthRequired(cfg.name)
        return await callback.wait()

    provider = OAuthClientProvider(
        server_url=cfg.url or "",
        client_metadata=metadata,
        storage=storage,
        redirect_handler=redirect_handler,
        callback_handler=callback_handler,
    )
    return OAuthSetup(provider, callback)
