"""
O.R.I.O.N — Local Ollama Provider (v0.3.0 Sprint 4)

Adaptador opcional e leve para modelos locais via Ollama.

CONTRATO DE HARDWARE — REGRAS INVIOLÁVEIS:
──────────────────────────────────────────
  1. ZERO auto-download: nunca baixa pesos de modelos automaticamente.
     Modelos devem estar pré-instalados manualmente pelo usuário.
  2. ZERO auto-start: nunca inicia o daemon Ollama automaticamente.
     O serviço deve estar rodando antes de ser utilizado.
  3. Opt-in explícito: este provedor só é instanciado se
     ``local_fallback_enabled=True`` na CircuitBreakerConfig.
  4. Checagem rápida de disponibilidade via ``/api/tags`` antes de qualquer
     inferência. Falha graciosa sem travar a máquina.

Referências: ADR-019 (Gateway com Fallback Local Leve).
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import aiohttp

from orion.gateway.models import (
    ContentBlock,
    LLMRequest,
    LLMResponse,
    LLMResponseChunk,
    ProviderName,
    TokenUsage,
)
from orion.gateway.providers.base import BaseLLMProvider
from orion.gateway.providers.openai_wire import (
    blocks_from_ollama_calls,
    map_finish_reason,
    serialize_messages,
    tools_to_openai,
)

logger = logging.getLogger(__name__)

# Porta padrão do Ollama
_DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"

# Timeout conservador para não travar a máquina em caso de sobrecarga local
_DEFAULT_TIMEOUT_S = 60.0
_CHECK_TIMEOUT_S = 3.0  # Timeout rápido para a checagem de disponibilidade

# Modelos que recusaram `tools`: lembrados no processo (o provider é recriado a cada chamada).
_MODELS_WITHOUT_TOOLS: set[str] = set()


class OllamaUnavailableError(Exception):
    """Levantada quando o daemon Ollama não está acessível.

    Indica que o serviço não está rodando ou não é acessível na URL
    configurada. O ORION não tentará iniciá-lo automaticamente.

    Attributes:
        base_url: URL onde o Ollama foi procurado.
        original_error: Exceção original (opcional).
    """

    def __init__(self, base_url: str, original_error: Exception | None = None) -> None:
        self.base_url = base_url
        self.original_error = original_error
        super().__init__(
            f"Ollama não está disponível em '{base_url}'. "
            f"Certifique-se de que o daemon está rodando (`ollama serve`). "
            f"O ORION nunca inicia o Ollama automaticamente. "
            + (f"Erro: {original_error}" if original_error else "")
        )


class OllamaModelNotFoundError(Exception):
    """Levantada quando o modelo solicitado não está instalado no Ollama.

    O ORION não baixará o modelo automaticamente. O usuário deve instalar
    manualmente com ``ollama pull <model>``.

    Attributes:
        model_id: ID do modelo não encontrado.
        available_models: Lista de modelos disponíveis (se conhecida).
    """

    def __init__(
        self,
        model_id: str,
        available_models: list[str] | None = None,
    ) -> None:
        self.model_id = model_id
        self.available_models = available_models or []
        models_str = (
            f"Disponíveis: {self.available_models}" if self.available_models else ""
        )
        super().__init__(
            f"Modelo '{model_id}' não encontrado no Ollama local. "
            f"O ORION NUNCA baixa modelos automaticamente. "
            f"Instale manualmente com: `ollama pull {model_id}`. "
            + models_str
        )


class LocalOllamaProvider(BaseLLMProvider):
    """Provedor de inferência local via Ollama (opt-in explícito).

    Conecta-se a um daemon Ollama já em execução na máquina local para
    inferência sem internet. Adequado para uso como fallback emergencial
    com modelos leves (ex: qwen2.5-coder:1.5b).

    IMPORTANTE: Este provedor NUNCA:
      - Baixa modelos automaticamente
      - Inicia o daemon Ollama
      - Consome recursos sem permissão explícita do usuário

    Exemplo de uso:
        >>> provider = LocalOllamaProvider(model_id="qwen2.5-coder:1.5b")
        >>> if await provider.is_available():
        ...     response = await provider.complete(request)

    Args:
        model_id: ID do modelo Ollama (ex: 'qwen2.5-coder:1.5b').
        base_url: URL base do daemon Ollama. Padrão: 'http://localhost:11434'.
        timeout_s: Timeout em segundos para chamadas de inferência.
    """

    def __init__(
        self,
        model_id: str = "qwen2.5-coder:1.5b",
        base_url: str = _DEFAULT_OLLAMA_BASE_URL,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
    ) -> None:
        self._model_id = model_id
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s

    @property
    def provider_name(self) -> str:
        return f"LocalOllama({self._model_id})"

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def base_url(self) -> str:
        return self._base_url

    # ── Verificação de Disponibilidade ───────────────────────────────────────

    async def is_available(self) -> bool:
        """Verifica se o daemon Ollama está acessível (sem timeout longo).

        Faz uma requisição rápida a ``/api/tags`` para confirmar que o
        serviço está rodando. Não verifica se o modelo específico está
        instalado — use ``check_model_available()`` para isso.

        Returns:
            True se o daemon está acessível; False caso contrário.
        """
        try:
            timeout = aiohttp.ClientTimeout(total=_CHECK_TIMEOUT_S)
            async with (
                aiohttp.ClientSession(timeout=timeout) as session,
                session.get(f"{self._base_url}/api/tags") as resp,
            ):
                return resp.status == 200
        except Exception:  # noqa: BLE001
            return False

    async def list_available_models(self) -> list[str]:
        """Lista os modelos instalados no Ollama local.

        Returns:
            Lista de IDs dos modelos disponíveis. Lista vazia se o daemon
            não está acessível.
        """
        try:
            timeout = aiohttp.ClientTimeout(total=_CHECK_TIMEOUT_S)
            async with (
                aiohttp.ClientSession(timeout=timeout) as session,
                session.get(f"{self._base_url}/api/tags") as resp,
            ):
                if resp.status != 200:
                    return []
                data = await resp.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception:  # noqa: BLE001
            return []

    async def check_model_available(self) -> bool:
        """Verifica se o modelo configurado está instalado localmente.

        Returns:
            True se o modelo está disponível; False caso contrário.
        """
        available = await self.list_available_models()
        # Ollama aceita tanto "model:tag" quanto "model" (usa :latest implícito)
        return any(
            m == self._model_id or m.startswith(f"{self._model_id}:")
            for m in available
        )

    # ── Inferência ────────────────────────────────────────────────────────────

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Executa inferência completa (não-streaming) via Ollama.

        Args:
            request: Requisição normalizada. O campo ``model`` é ignorado
                     em favor do ``model_id`` configurado no provedor.

        Returns:
            ``LLMResponse`` com conteúdo, uso de tokens e latência.

        Raises:
            OllamaUnavailableError: Se o daemon não está acessível.
            OllamaModelNotFoundError: Se o modelo não está instalado.
        """
        await self._assert_available()

        t0 = time.monotonic()
        data: dict[str, Any] = {}
        for _attempt in range(2):
            payload = self._build_payload(request, stream=False)
            try:
                timeout = aiohttp.ClientTimeout(total=self._timeout_s)
                async with aiohttp.ClientSession(timeout=timeout) as session, session.post(
                    f"{self._base_url}/api/chat",
                    json=payload,
                ) as resp:
                    if resp.status == 404:
                        available = await self.list_available_models()
                        raise OllamaModelNotFoundError(
                            model_id=self._model_id,
                            available_models=available,
                        )
                    if await self._tools_rejected(resp, payload):
                        continue
                    resp.raise_for_status()
                    data = await resp.json()
                    break
            except (OllamaUnavailableError, OllamaModelNotFoundError):
                raise
            except aiohttp.ClientConnectorError as exc:
                raise OllamaUnavailableError(self._base_url, exc) from exc
            except Exception:
                logger.exception("LocalOllamaProvider: erro na chamada de complete.")
                raise

        latency_ms = (time.monotonic() - t0) * 1000
        message = data.get("message", {})
        content = message.get("content", "")
        blocks = ([ContentBlock.of_text(content)] if content else []) + blocks_from_ollama_calls(
            message.get("tool_calls") or []
        )
        usage = self._usage(data)

        return LLMResponse(
            content=content,
            blocks=blocks,
            stop_reason=self._stop_reason(data, any(b.type == "tool_use" for b in blocks)),
            model=self._model_id,
            provider=ProviderName.OLLAMA,
            usage=usage,
            latency_ms=latency_ms,
            complexity_tier=request.complexity_tier,
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMResponseChunk]:
        """Streaming token a token via Ollama.

        Args:
            request: Requisição normalizada com ``stream=True``.

        Yields:
            ``LLMResponseChunk`` com delta de texto.

        Raises:
            OllamaUnavailableError: Se o daemon não está acessível.
            OllamaModelNotFoundError: Se o modelo não está instalado.
        """
        await self._assert_available()

        notice: str | None = None
        for _attempt in range(2):
            payload = self._build_payload(request, stream=True)
            if notice is not None:
                yield LLMResponseChunk(notice=notice)
            try:
                timeout = aiohttp.ClientTimeout(total=self._timeout_s)
                async with aiohttp.ClientSession(timeout=timeout) as session, session.post(
                    f"{self._base_url}/api/chat",
                    json=payload,
                ) as resp:
                    if resp.status == 404:
                        available = await self.list_available_models()
                        raise OllamaModelNotFoundError(
                            model_id=self._model_id,
                            available_models=available,
                        )
                    if await self._tools_rejected(resp, payload):
                        notice = self._degraded_notice()
                        continue
                    resp.raise_for_status()

                    completion_tokens = 0
                    has_calls = False
                    async for raw_line in resp.content:
                        line = raw_line.decode("utf-8").strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        message = data.get("message", {})
                        delta = message.get("content", "")
                        for block in blocks_from_ollama_calls(message.get("tool_calls") or []):
                            has_calls = True
                            yield LLMResponseChunk(block=block)

                        if data.get("done", False):
                            yield LLMResponseChunk(
                                delta=delta,
                                is_final=True,
                                usage=self._usage(data, completion_tokens),
                                stop_reason=self._stop_reason(data, has_calls),
                            )
                        else:
                            completion_tokens += 1
                            yield LLMResponseChunk(delta=delta, is_final=False)
                    return

            except (OllamaUnavailableError, OllamaModelNotFoundError):
                raise
            except aiohttp.ClientConnectorError as exc:
                raise OllamaUnavailableError(self._base_url, exc) from exc
            except Exception:
                logger.exception("LocalOllamaProvider: erro durante o streaming.")
                raise

    # ── Helpers internos ──────────────────────────────────────────────────────

    async def _assert_available(self) -> None:
        """Verifica disponibilidade e lança exceção se não disponível."""
        if not await self.is_available():
            raise OllamaUnavailableError(self._base_url)

    def _build_payload(self, request: LLMRequest, *, stream: bool) -> dict[str, Any]:
        """Constrói o payload para a API do Ollama (/api/chat).

        Com tools suportadas, envia ``tools`` e o histórico estruturado (``tool_calls``/``tool``);
        sem suporte (detectado em runtime), degrada para texto puro.

        Args:
            request: Requisição normalizada.
            stream: Se True, usa streaming; False para resposta completa.

        Returns:
            Dicionário com o payload JSON para o Ollama.
        """
        with_tools = bool(request.tools) and not self._tools_unsupported
        payload: dict[str, Any] = {
            "model": self._model_id,
            "messages": serialize_messages(
                request.messages, ollama=True, with_tools=not self._tools_unsupported
            ),
            "stream": stream,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }
        if with_tools:
            payload["tools"] = tools_to_openai(request.tools)
        return payload

    @property
    def _tools_unsupported(self) -> bool:
        return self._model_id in _MODELS_WITHOUT_TOOLS

    def _degraded_notice(self) -> str:
        return (
            f"O modelo local '{self._model_id}' não suporta tools: seguindo apenas em texto, "
            "sem ações no sistema."
        )

    async def _tools_rejected(self, resp: aiohttp.ClientResponse, payload: dict[str, Any]) -> bool:
        """True se o Ollama recusou ``tools`` (400); marca o provider para degradar a texto."""
        if resp.status != 400 or "tools" not in payload:
            return False
        body = await resp.text()
        if "does not support tools" not in body:
            return False
        logger.warning("Ollama: %s", self._degraded_notice())
        _MODELS_WITHOUT_TOOLS.add(self._model_id)
        return True

    @staticmethod
    def _usage(data: dict[str, Any], estimated_completion: int = 0) -> TokenUsage:
        """Uso do chunk final: campos nativos ``*_eval_count`` ou o legado ``usage``."""
        legacy = data.get("usage") or {}
        prompt = int(data.get("prompt_eval_count", legacy.get("prompt_tokens", 0)) or 0)
        completion = int(
            data.get("eval_count", legacy.get("completion_tokens", estimated_completion)) or 0
        )
        return TokenUsage(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
        )

    @staticmethod
    def _stop_reason(data: dict[str, Any], has_tool_calls: bool) -> str:
        reason = data.get("done_reason")
        return map_finish_reason(reason, has_tool_calls) or ("tool_use" if has_tool_calls else "end_turn")
