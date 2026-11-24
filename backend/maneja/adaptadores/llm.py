"""Modelos de linguagem usados para explicar as movimentações: o Gemini real (SPEC-005) e as versões sem rede."""

from __future__ import annotations

import logging
from datetime import date
from threading import Lock
from time import monotonic

import httpx

from ..dominio import CotaEsgotada

logger = logging.getLogger(__name__)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
GEMINI_TIMEOUT_S = 15  # SPEC-005 (chamada única)
GEMINI_TIMEOUT_FALLBACK_S = 8.0  # timeout por tentativa quando há modelos de reserva (cabe nos 30 s da Vercel)
GEMINI_ORCAMENTO_FALLBACK_S = 22.0


class GeminiLLM:
    """Google Gemini pela API REST. Só escreve texto: quem decide é a regra (agente.py).

    Aceita uma sequência opcional de `modelos_reserva` (plano gratuito): se o modelo
    principal falhar por 404, 429, 5xx, timeout ou resposta vazia, tenta o próximo dentro
    do orçamento de tempo. HTTP 401/403 (chave inválida) interrompe na hora.
    As mensagens de erro e os logs nunca levam a URL nem a chave.
    """

    def __init__(self, chave: str, modelo: str, cliente_http: httpx.Client | None = None,
                 modelos_reserva: tuple[str, ...] = ()) -> None:
        self._chave, self.modelo = chave, modelo
        self.modelos: tuple[str, ...] = tuple(dict.fromkeys(m for m in (modelo, *modelos_reserva) if m))
        self._http = cliente_http or httpx.Client(timeout=GEMINI_TIMEOUT_S)
        self.ultimo_modelo: str | None = None

    def _chamar_modelo(self, modelo: str, prompt: str, timeout: float) -> str:
        try:
            resposta = self._http.post(
                GEMINI_URL.format(modelo=modelo),
                params={"key": self._chave},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=timeout,
            )
        except httpx.TimeoutException as e:
            raise RuntimeError(f"Gemini ({modelo}) não respondeu em {timeout:g} s") from e
        except httpx.HTTPError as e:
            raise RuntimeError(f"falha de conexão com o Gemini ({modelo}): {type(e).__name__}") from e
        if resposta.status_code == 429:
            raise CotaEsgotada(f"cota do Gemini esgotada em {modelo} (HTTP 429)")
        if resposta.status_code != 200:
            raise RuntimeError(f"Gemini ({modelo}) respondeu HTTP {resposta.status_code}")
        try:
            texto = resposta.json()["candidates"][0]["content"]["parts"][0]["text"]
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"resposta do Gemini ({modelo}) sem texto") from e
        if not isinstance(texto, str) or not texto.strip():
            raise RuntimeError(f"resposta do Gemini ({modelo}) sem texto")
        return texto

    def gerar_texto(self, prompt: str) -> str:
        if len(self.modelos) == 1:
            texto = self._chamar_modelo(self.modelo, prompt, GEMINI_TIMEOUT_S)
            self.ultimo_modelo = self.modelo
            return texto

        prazo = monotonic() + GEMINI_ORCAMENTO_FALLBACK_S
        ultimo_erro: Exception | None = None
        todos_cota = True
        for modelo in self.modelos:
            restante = prazo - monotonic()
            if restante <= 0.5:
                break
            timeout = min(GEMINI_TIMEOUT_FALLBACK_S, restante)
            try:
                texto = self._chamar_modelo(modelo, prompt, timeout)
                self.ultimo_modelo = modelo
                return texto
            except CotaEsgotada as e:
                ultimo_erro = e
                logger.warning("Gemini fallback: %s", e)
            except RuntimeError as e:
                ultimo_erro = e
                todos_cota = False
                logger.warning("Gemini fallback: %s", e)
                if "HTTP 401" in str(e) or "HTTP 403" in str(e):
                    raise
        if ultimo_erro is None:
            raise RuntimeError("orçamento de tempo esgotado ao consultar o Gemini")
        if todos_cota:
            raise ultimo_erro
        raise ultimo_erro


class LLMFixo:
    """Responde sempre o mesmo texto. Usado nos testes do validador (risco R3)."""

    def __init__(self, resposta: str) -> None:
        self.resposta = resposta

    def gerar_texto(self, prompt: str) -> str:
        return self.resposta


class ControleDeCota:
    """Risco R7: conta as chamadas do dia e lança CotaEsgotada ao passar do limite."""

    def __init__(self, llm, limite: int) -> None:
        self._llm, self.limite, self.usado = llm, limite, 0
        self._dia = date.today()
        self._trava = Lock()

    def gerar_texto(self, prompt: str) -> str:
        with self._trava:
            dia = date.today()
            if dia != self._dia:
                self._dia, self.usado = dia, 0
            if self.usado >= self.limite:
                raise CotaEsgotada(f"cota de {self.limite} chamadas esgotada")
            self.usado += 1
        return self._llm.gerar_texto(prompt)
