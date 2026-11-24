"""Modelos de linguagem usados para explicar as movimentações: o Gemini real (SPEC-005) e as versões sem rede."""

from __future__ import annotations

from datetime import date
from threading import Lock

import httpx

from ..dominio import CotaEsgotada

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
GEMINI_TIMEOUT_S = 15  # SPEC-005


class GeminiLLM:
    """Google Gemini pela API REST. Só escreve texto: quem decide é a regra (agente.py).

    Qualquer falha vira exceção (CotaEsgotada no 429, RuntimeError no resto), e o agente
    fica com o texto da regra. As mensagens de erro não levam a URL, que contém a chave.
    """

    def __init__(self, chave: str, modelo: str, cliente_http: httpx.Client | None = None) -> None:
        self._chave, self.modelo = chave, modelo
        self._http = cliente_http or httpx.Client(timeout=GEMINI_TIMEOUT_S)

    def gerar_texto(self, prompt: str) -> str:
        try:
            resposta = self._http.post(
                GEMINI_URL.format(modelo=self.modelo),
                params={"key": self._chave},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=GEMINI_TIMEOUT_S,
            )
        except httpx.TimeoutException as e:
            raise RuntimeError(f"Gemini não respondeu em {GEMINI_TIMEOUT_S} s") from e
        except httpx.HTTPError as e:
            raise RuntimeError(f"falha de conexão com o Gemini: {type(e).__name__}") from e
        if resposta.status_code == 429:
            raise CotaEsgotada("cota do Gemini esgotada (HTTP 429)")
        if resposta.status_code != 200:
            raise RuntimeError(f"Gemini respondeu HTTP {resposta.status_code}")
        try:
            texto = resposta.json()["candidates"][0]["content"]["parts"][0]["text"]
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise RuntimeError("resposta do Gemini sem texto") from e
        if not isinstance(texto, str) or not texto.strip():
            raise RuntimeError("resposta do Gemini sem texto")
        return texto


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
