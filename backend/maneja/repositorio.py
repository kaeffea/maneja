"""Armazenamento em memória. A SPEC-008 troca por PostgreSQL mantendo a mesma interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .dominio import (
    Cliente,
    Coleira,
    Fazenda,
    LeituraNdvi,
    Lotacao,
    Lote,
    Movimentacao,
    Piquete,
    PlanoManejo,
    Posicao,
    Usuario,
)


@dataclass
class RepositorioMemoria:
    fazenda: Fazenda
    piquetes: list[Piquete] = field(default_factory=list)
    lotacao: list[Lotacao] = field(default_factory=list)
    ndvi: list[LeituraNdvi] = field(default_factory=list)
    historico: list[Movimentacao] = field(default_factory=list)  # mais recente primeiro
    coleiras: list[Coleira] = field(default_factory=list)
    posicoes: list[Posicao] = field(default_factory=list)
    plano_atual: PlanoManejo | None = None
    grupos_externos: dict[str, list[str]] = field(default_factory=dict)  # coleiras de cada movimentação do SeuGado
    ultima_movimentacao_fisica: dict[str, datetime] = field(default_factory=dict)
    clientes: list[Cliente] = field(default_factory=list)
    usuarios: list[Usuario] = field(default_factory=list)
    fazendas: list[Fazenda] = field(default_factory=list)
    lotes: list[Lote] = field(default_factory=list)
    planos_por_fazenda: dict[str, PlanoManejo] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.fazendas:
            self.fazendas = [self.fazenda]
        elif not any(f.id == self.fazenda.id for f in self.fazendas):
            self.fazendas.insert(0, self.fazenda)
        if self.plano_atual is not None and self.fazenda.id not in self.planos_por_fazenda:
            self.planos_por_fazenda[self.fazenda.id] = self.plano_atual
        elif self.plano_atual is None and self.fazenda.id in self.planos_por_fazenda:
            self.plano_atual = self.planos_por_fazenda[self.fazenda.id]
        fazenda_por_piquete = {p.id: p.fazenda_id for p in self.piquetes}
        for c in self.coleiras:
            if not c.fazenda_id:
                c.fazenda_id = fazenda_por_piquete.get(c.piquete_cadastro_id, self.fazenda.id)
        for m in self.historico:
            if not m.fazenda_id:
                m.fazenda_id = fazenda_por_piquete.get(m.piquete_origem_id, self.fazenda.id)

    def posicoes_vigentes(self) -> list[Posicao]:
        """Preserva o histórico e exclui leituras anteriores à última mudança física."""
        cortes = self.ultima_movimentacao_fisica
        return [p for p in self.posicoes if p.coleira_id not in cortes or p.instante >= cortes[p.coleira_id]]
