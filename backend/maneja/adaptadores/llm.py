"""Modelos de linguagem usados para explicar as movimentações."""

from __future__ import annotations

from datetime import date
from threading import Lock

import httpx

from ..dominio import CotaEsgotada


class GeminiLLM:
    def __init__(self, chave: str, modelo: str, cliente_http: httpx.Client | None = None) -> None:
        self.chave = chave
        self.modelo = modelo
        self.cliente_http = cliente_http or httpx.Client()

    def gerar_texto(self, prompt: str) -> str:
        try:
            resposta = self.cliente_http.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self.modelo}:generateContent",
                params={"key": self.chave},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=15,
            )
            if resposta.status_code == 429:
                raise CotaEsgotada("cota do Gemini esgotada")
            resposta.raise_for_status()
            texto = resposta.json()["candidates"][0]["content"]["parts"][0]["text"]
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            raise RuntimeError("Gemini indisponível ou resposta inválida") from None
        if not isinstance(texto, str) or not texto.strip():
            raise RuntimeError("Gemini respondeu sem texto")
        return texto


class LLMFixo:
    """Responde sempre o mesmo texto. Usado nos testes do validador (risco R3)."""

    def __init__(self, resposta: str) -> None:
        self.resposta = resposta

    def gerar_texto(self, prompt: str) -> str:
        return self.resposta


class ControleDeCota:
    """Risco R7: conta as chamadas e lança CotaEsgotada ao passar do limite."""

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
