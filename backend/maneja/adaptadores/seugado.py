"""Adaptador do SeuGado (docs/02-integracao-seugado.md).

Regra de independência: o Maneja nunca depende do SeuGado. O modo padrão é desligado,
e qualquer falha aqui vira um aviso, nunca um erro para o usuário.
"""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import Protocol
from urllib.parse import quote

import httpx


class ISeuGado(Protocol):
    modo: str

    def plano_atual(self) -> dict | None: ...


class SeuGadoDesligado:
    modo = "desligado"

    def plano_atual(self) -> dict | None:
        return None


class SeuGadoArquivo:
    """Lê o plano vigente de um JSON no formato de GET /fazendas/{id}/plano/atual do SeuGado."""

    modo = "arquivo"

    def __init__(self, caminho: str | Path) -> None:
        self.caminho = Path(caminho)

    def plano_atual(self) -> dict | None:
        return json.loads(self.caminho.read_text(encoding="utf-8"))


class SeuGadoApi:
    """Chamada real à API do SeuGado: SPEC-012."""

    modo = "api"

    def __init__(self, url: str, email: str, senha: str, fazenda_id: str,
                 cliente_http: httpx.Client | None = None) -> None:
        self.url, self.email, self.senha, self.fazenda_id = url.rstrip("/"), email, senha, fazenda_id
        self.cliente_http = cliente_http or httpx.Client(timeout=10)
        self._token = ""
        self._token_ate = 0.0
        self._plano = None
        self._plano_ate = 0.0
        self._trava = Lock()

    def _autenticar(self) -> str:
        if monotonic() >= self._token_ate:
            resposta = self.cliente_http.post(
                f"{self.url}/auth/token", data={"username": self.email, "password": self.senha},
            )
            resposta.raise_for_status()
            dados = resposta.json()
            self._token = dados["access_token"]
            self._token_ate = monotonic() + float(dados.get("expires_in", 0))
        return self._token

    def _consultar(self) -> httpx.Response:
        fazenda = quote(self.fazenda_id, safe="")
        return self.cliente_http.get(
            f"{self.url}/fazendas/{fazenda}/plano/atual",
            headers={"Authorization": f"Bearer {self._autenticar()}"},
        )

    def plano_atual(self) -> dict | None:
        with self._trava:
            if monotonic() < self._plano_ate:
                return self._plano
            resposta = self._consultar()
            if resposta.status_code == 401:
                self._token_ate = 0.0
                resposta = self._consultar()
            if resposta.status_code == 404:
                plano = None
            else:
                resposta.raise_for_status()
                plano = resposta.json()
                if not isinstance(plano, dict):
                    raise RuntimeError("Plano inválido do SeuGado")
            self._plano = plano
            self._plano_ate = monotonic() + 600
            return plano
