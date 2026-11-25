"""Adaptador do SeuGado / PiqueTech (docs/02-integracao-seugado.md, SPEC-012 e SPEC-018).

Regra de independência: o Maneja nunca depende do SeuGado. O modo padrão é desligado,
e qualquer falha na consulta de plano vira um aviso, nunca um erro para o usuário.
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
TTL_PLANO_S = 600.0  # cache de 10 minutos por fazenda (SPEC-012 R3 / SPEC-018 R2)


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

    def plano_atual(self, fazenda_id: str | None = None) -> dict | None: ...


class SeuGadoDesligado:
    modo = "desligado"

    def plano_atual(self, fazenda_id: str | None = None) -> dict | None:
        return None


class SeuGadoArquivo:
    """Lê o plano vigente de um JSON no formato de GET /fazendas/{id}/plano/atual do SeuGado."""

    modo = "arquivo"

    def __init__(self, caminho: str | Path) -> None:
        self.caminho = Path(caminho)

    def plano_atual(self, fazenda_id: str | None = None) -> dict | None:
        return json.loads(self.caminho.read_text(encoding="utf-8"))


class SeuGadoApi:
    """Cliente HTTP real da API do PiqueTech / SeuGado (SPEC-012 e SPEC-018)."""

    modo = "api"

    def __init__(
        self,
        url: str,
        email: str,
        senha: str,
        fazenda_id: str = "",
        cliente_http: httpx.Client | None = None,
    ) -> None:
        self.url = url.rstrip("/")
        self.email = email
        self.senha = senha
        self.fazenda_id = fazenda_id  # opcional: mantido apenas por compatibilidade com testes antigos
        self.cliente_http = cliente_http or httpx.Client(timeout=15)
        self._token = ""
        self._token_ate = 0.0
        self._planos: dict[str, tuple[float, dict | None]] = {}
        self._trava = Lock()

    def _autenticar(self) -> str:
        if monotonic() >= self._token_ate:
            resposta = self.cliente_http.post(
                f"{self.url}/auth/token",
                data={"username": self.email, "password": self.senha},
            )
            resposta.raise_for_status()
            dados = resposta.json()
            self._token = dados["access_token"]
            self._token_ate = monotonic() + _ttl_token(self._token, dados)
        return self._token

    def _requisitar(self, metodo: str, caminho: str, *, json_body: dict | None = None) -> httpx.Response:
        def enviar() -> httpx.Response:
            headers = {"Authorization": f"Bearer {self._autenticar()}"}
            return self.cliente_http.request(metodo, f"{self.url}{caminho}", headers=headers, json=json_body)

        resposta = enviar()
        if resposta.status_code == 401:
            self._token_ate = 0.0
            resposta = enviar()
        return resposta

    def invalidar_cache_plano(self, fazenda_id: str | None = None) -> None:
        with self._trava:
            if fazenda_id is None:
                self._planos.clear()
            else:
                self._planos.pop(fazenda_id, None)

    def plano_atual(self, fazenda_id: str | None = None) -> dict | None:
        alvo = (fazenda_id or self.fazenda_id or "").strip()
        if not alvo:
            return None
        with self._trava:
            em_cache = self._planos.get(alvo)
            if em_cache is not None and monotonic() < em_cache[0]:
                return em_cache[1]
            fazenda_q = quote(alvo, safe="")
            resposta = self._requisitar("GET", f"/fazendas/{fazenda_q}/plano/atual")
            if resposta.status_code == 404:
                plano = None
            else:
                resposta.raise_for_status()
                plano = resposta.json()
                if not isinstance(plano, dict):
                    raise RuntimeError("Plano inválido do SeuGado")
            self._planos[alvo] = (monotonic() + TTL_PLANO_S, plano)
            return plano

    # ---------- leitura para importação / exportação (SPEC-018) ----------

    def _get_json(self, caminho: str):
        with self._trava:
            resposta = self._requisitar("GET", caminho)
            resposta.raise_for_status()
            return resposta.json()

    def _post_json(self, caminho: str, corpo: dict) -> dict:
        with self._trava:
            resposta = self._requisitar("POST", caminho, json_body=corpo)
            resposta.raise_for_status()
            dados = resposta.json()
            if not isinstance(dados, dict):
                raise RuntimeError(f"Resposta inesperada do PiqueTech em POST {caminho}")
            return dados

    def listar_clientes(self) -> list[dict]:
        return list(self._get_json("/clientes"))

    def listar_fazendas(self) -> list[dict]:
        return list(self._get_json("/fazendas"))

    def obter_fazenda(self, fazenda_id: str) -> dict:
        return dict(self._get_json(f"/fazendas/{quote(fazenda_id, safe='')}"))

    def listar_piquetes(self, fazenda_id: str) -> list[dict]:
        return list(self._get_json(f"/fazendas/{quote(fazenda_id, safe='')}/piquetes"))

    def listar_lotes(self, fazenda_id: str) -> list[dict]:
        return list(self._get_json(f"/fazendas/{quote(fazenda_id, safe='')}/lotes"))

    def listar_cultivares(self) -> list[dict]:
        return list(self._get_json("/cultivares"))

    # ---------- criação para exportação (SPEC-018) ----------

    def criar_cliente(self, dados: dict) -> dict:
        return self._post_json("/clientes", dados)

    def criar_fazenda(self, dados: dict) -> dict:
        return self._post_json("/fazendas", dados)

    def criar_piquete(self, fazenda_id: str, dados: dict) -> dict:
        return self._post_json(f"/fazendas/{quote(fazenda_id, safe='')}/piquetes", dados)

    def criar_lote(self, fazenda_id: str, dados: dict) -> dict:
        return self._post_json(f"/fazendas/{quote(fazenda_id, safe='')}/lotes", dados)
