"""Coleiras GPS simuladas (estratégia do MVP: sem compra de hardware).

O simulador guarda onde cada animal está DE FATO (piquete físico). O cadastro do sistema
pode discordar disso: é exatamente o que a ocupação estimada e o planejado × realizado medem.
"""

from __future__ import annotations

import random
from datetime import datetime

from ..dominio import Coleira, Piquete, Posicao
from ..geo import ponto_aleatorio

PERDA_SINAL_PADRAO = 0.1  # a validar com a ficha técnica da coleira


class SimuladorColeiras:
    def __init__(self, coleiras: list[Coleira], piquetes: list[Piquete],
                 perda_sinal: float = PERDA_SINAL_PADRAO, semente: int | None = None) -> None:
        self._piquetes = {p.id: p for p in piquetes}
        self.fisico = {c.id: c.piquete_cadastro_id for c in coleiras}
        self.perda_sinal = perda_sinal
        self._rng = random.Random(semente)

    def atualizar_piquetes(self, piquetes: list[Piquete]) -> None:
        self._piquetes = {p.id: p for p in piquetes}

    def adicionar(self, coleira: Coleira) -> None:
        self.fisico[coleira.id] = coleira.piquete_cadastro_id

    def mover(self, coleira_ids: list[str], piquete_id: str) -> None:
        """O gado foi levado no campo."""
        for cid in coleira_ids:
            if cid in self.fisico:
                self.fisico[cid] = piquete_id

    def gerar_posicoes(self, instante: datetime, coleira_ids: set[str] | None = None) -> list[Posicao]:
        posicoes = []
        for cid, pid in self.fisico.items():
            if coleira_ids is not None and cid not in coleira_ids:
                continue
            if pid not in self._piquetes:
                continue
            if self._rng.random() < self.perda_sinal:
                continue
            lat, lon = ponto_aleatorio(self._piquetes[pid].geometria, self._rng)
            posicoes.append(Posicao(cid, instante, lat, lon))
        return posicoes

    def gerar_posicao_imediata(self, coleira_id: str, instante: datetime) -> Posicao | None:
        pid = self.fisico.get(coleira_id)
        if not pid or pid not in self._piquetes:
            return None
        lat, lon = ponto_aleatorio(self._piquetes[pid].geometria, self._rng)
        return Posicao(coleira_id, instante, lat, lon)
