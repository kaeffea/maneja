"""Adaptador do SeuGado (docs/02-integracao-seugado.md).

Regra de independência: o Maneja nunca depende do SeuGado. O modo padrão é desligado,
e qualquer falha aqui vira um aviso, nunca um erro para o usuário.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from threading import Lock
from time import monotonic, time
from typing import Protocol
from urllib.parse import quote

import httpx

TTL_TOKEN_PADRAO_S = 3000.0  # usado quando /auth/token não devolve expires_in nem JWT com exp
MARGEM_TOKEN_S = 30.0
TTL_PLANO_S = 600.0  # cache de 10 minutos (SPEC-012 R3)


def _ttl_token(token: str, dados: dict) -> float:
    """Duração útil do token em segundos: prefere expires_in, depois exp do JWT, senão padrão."""
    if "expires_in" in dados and dados["expires_in"] is not None:
        return max(0.0, float(dados["expires_in"]) - MARGEM_TOKEN_S)
    partes = token.split(".")
    if len(partes) == 3:
        try:
            corpo = partes[1] + "=" * (-len(partes[1]) % 4)
            payload = json.loads(base64.urlsafe_b64decode(corpo))
            if isinstance(payload, dict) and isinstance(payload.get("exp"), (int, float)):
                return max(0.0, float(payload["exp"]) - time() - MARGEM_TOKEN_S)
        except (ValueError, json.JSONDecodeError):
            pass
    return TTL_TOKEN_PADRAO_S


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
            self._token_ate = monotonic() + _ttl_token(self._token, dados)
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
            self._plano_ate = monotonic() + TTL_PLANO_S
            return plano
