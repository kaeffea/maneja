"""Repositório PostgreSQL (SPEC-008, SPEC-017 e SPEC-018).

Mesma interface do RepositorioMemoria: os dados ficam em memória enquanto o processo roda,
e `salvar()` grava o estado inteiro numa única transação. Assim, uma movimentação aceita
atualiza lotação, histórico e coleiras juntos ou não atualiza nada (critério 2.2.1).
As posições das coleiras só crescem: cada `salvar()` grava apenas as novas.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from .dominio import (
    Alerta,
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
    Rebanho,
    Usuario,
)
from .repositorio import RepositorioMemoria

SCHEMA = Path(__file__).resolve().parent.parent / "db" / "schema.sql"
POSICOES_CARREGADAS_H = 24  # só as posições recentes interessam (ocupação e verificação usam 6 h)
LOCK_TRANSACAO_ID = 77123456  # advisory lock por transação (seguro no pooler 6543 do Supabase)

_CHECK_SCHEMA_SQL = """
SELECT to_regclass('public.parametro') IS NULL
    OR to_regclass('public.cliente') IS NULL
    OR to_regclass('public.usuario') IS NULL
    OR to_regclass('public.lote') IS NULL
    OR NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'fazenda' AND column_name = 'seugado_id'
    )
    OR NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'piquete' AND column_name = 'ativo'
    )
    OR NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'coleira' AND column_name = 'lote_id'
    )
    OR EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'plano_atual' AND column_name = 'unico'
    )
"""


def conectar(url: str) -> psycopg.Connection:
    """prepare_threshold=None: o pooler do Supabase em modo transação (porta 6543) não aceita prepared statements."""
    return psycopg.connect(url, prepare_threshold=None)


def movimentacao_de_dict(d: dict) -> Movimentacao:
    d = dict(d)
    d["rebanho"] = Rebanho(**d["rebanho"])
    campos = {f.name for f in dataclasses.fields(Movimentacao)}
    return Movimentacao(**{k: v for k, v in d.items() if k in campos})


def plano_de_dict(d: dict) -> PlanoManejo:
    return PlanoManejo(
        id=d["id"], fazenda_id=d["fazenda_id"], data_geracao=d["data_geracao"], data_inicio=d["data_inicio"],
        horizonte_dias=d["horizonte_dias"],
        movimentacoes=[movimentacao_de_dict(m) for m in d["movimentacoes"]],
        alertas=[Alerta(**a) for a in d["alertas"]],
    )


class RepositorioPg(RepositorioMemoria):
    def __init__(self, url: str, **campos) -> None:
        super().__init__(**campos)
        self.url = url
        self.fisico: dict[str, str] = {}  # piquete físico de cada coleira (estado do simulador)
        self.deslocamento_s: float = 0.0  # relógio do simulador
        self._posicoes_gravadas = 0

    # ---------- abrir ----------

    @classmethod
    def abrir(cls, url: str, semente: RepositorioMemoria | None) -> RepositorioPg:
        """Cria/migra as tabelas, carrega o estado e, com o banco vazio, grava `semente` (a fazenda de demonstração)."""
        with conectar(url) as conn, conn.transaction():
            # aplica/migra o schema só se faltar tabela ou coluna (com lock transacional para evitar corrida no cold start)
            if conn.execute(_CHECK_SCHEMA_SQL).fetchone()[0]:
                conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_TRANSACAO_ID,))
                if conn.execute(_CHECK_SCHEMA_SQL).fetchone()[0]:
                    conn.execute(SCHEMA.read_text(encoding="utf-8"))
            vazio = conn.execute("SELECT count(*) FROM fazenda").fetchone()[0] == 0
        if vazio:
            base = semente or RepositorioMemoria(fazenda=Fazenda("fazenda", "Minha fazenda", "America/Maceio"))
            repo = cls(url, **{f.name: getattr(base, f.name) for f in dataclasses.fields(RepositorioMemoria)})
            repo.fisico = {c.id: c.piquete_cadastro_id for c in repo.coleiras}
            repo.salvar(apenas_se_vazio=True)
            return cls._carregar(url)
        repo = cls._carregar(url)
        # Se um banco já existente (migrado da v1) tem a fazenda exemplo sem nenhum usuário cliente cadastrado,
        # cria o cliente Marcinho e a conta exemplo cliente@maneja.app para acesso imediato.
        if semente is not None and not repo.usuarios:
            faz_demo = next((f for f in repo.fazendas if f.id == "faz-marcinho"), None)
            if faz_demo is not None:
                from .demo import CLIENTE_CONTATO, CLIENTE_ID, CLIENTE_NOME, usuario_cliente_exemplo

                if not any(c.id == CLIENTE_ID for c in repo.clientes):
                    repo.clientes.insert(0, Cliente(CLIENTE_ID, CLIENTE_NOME, CLIENTE_CONTATO))
                if faz_demo.cliente_id is None:
                    faz_demo.cliente_id = CLIENTE_ID
                repo.usuarios.append(usuario_cliente_exemplo())
                repo.salvar()
        return repo

    @classmethod
    def _carregar(cls, url: str) -> RepositorioPg:
        with conectar(url) as conn:
            desl = conn.execute("SELECT valor FROM parametro WHERE chave = 'deslocamento_relogio_s'").fetchone()
            deslocamento_s = float(desl[0]) if desl else 0.0

            clientes = [
                Cliente(r[0], r[1], r[2], r[3])
                for r in conn.execute("SELECT id, nome, contato, seugado_id FROM cliente ORDER BY ordem, id")
            ]
            usuarios = [
                Usuario(r[0], r[1], r[2], r[3], r[4], r[5])
                for r in conn.execute(
                    "SELECT id, email, senha_hash, papel, cliente_id, nome FROM usuario ORDER BY ordem, id"
                )
            ]
            fazendas = [
                Fazenda(r[0], r[1], r[2], r[3], r[4])
                for r in conn.execute("SELECT id, nome, timezone, cliente_id, seugado_id FROM fazenda ORDER BY ordem, id")
            ]
            fazenda_padrao = fazendas[0]

            piquetes = [
                Piquete(r[0], r[1], r[2], r[3], r[4], r[5], r[6], bool(r[7]))
                for r in conn.execute(
                    "SELECT id, fazenda_id, nome, geometria, area_ha, vegetacao, externo_id, ativo "
                    "FROM piquete ORDER BY ordem"
                )
            ]
            lotes = [
                Lote(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7].isoformat() if r[7] else None, r[8])
                for r in conn.execute(
                    "SELECT id, fazenda_id, nome, piquete_atual_id, bois, vacas, bezerros, desde, seugado_id "
                    "FROM lote ORDER BY ordem, id"
                )
            ]
            lotacao = [
                Lotacao(r[0], r[1], r[2], r[3], r[4], r[5].isoformat() if r[5] else None)
                for r in conn.execute("SELECT piquete_id, fazenda_id, bois, vacas, bezerros, desde FROM lotacao ORDER BY piquete_id")
            ]
            ndvi = [
                LeituraNdvi(r[0], r[1].isoformat(), r[2])
                for r in conn.execute("SELECT piquete_id, data, valor FROM leitura_ndvi ORDER BY piquete_id, data")
            ]
            fazenda_por_piquete = {p.id: p.fazenda_id for p in piquetes}
            historico = []
            for dados_mov, fid in conn.execute("SELECT dados, fazenda_id FROM movimentacao ORDER BY ordem"):
                mov = movimentacao_de_dict(dados_mov)
                if not mov.fazenda_id:
                    mov.fazenda_id = fid or fazenda_por_piquete.get(mov.piquete_origem_id, fazenda_padrao.id)
                historico.append(mov)

            planos_por_fazenda: dict[str, PlanoManejo] = {}
            for fid, dados_plano in conn.execute("SELECT fazenda_id, dados FROM plano_atual"):
                planos_por_fazenda[fid] = plano_de_dict(dados_plano)

            linhas = conn.execute(
                "SELECT id, categoria, piquete_cadastro_id, piquete_fisico_id, fazenda_id, lote_id "
                "FROM coleira ORDER BY ordem"
            ).fetchall()
            coleiras = [
                Coleira(
                    r[0],
                    r[1],
                    r[2],
                    fazenda_id=r[4] or fazenda_por_piquete.get(r[2], fazenda_padrao.id),
                    lote_id=r[5],
                )
                for r in linhas
            ]
            fisico = {r[0]: r[3] for r in linhas}

            cortes = conn.execute("SELECT valor FROM parametro WHERE chave = 'ultima_movimentacao_fisica'").fetchone()
            ultima_movimentacao_fisica = (
                {cid: datetime.fromisoformat(instante) for cid, instante in json.loads(cortes[0]).items()}
                if cortes
                else {}
            )
            limite = datetime.now(timezone.utc) + timedelta(seconds=deslocamento_s) - timedelta(hours=POSICOES_CARREGADAS_H)
            posicoes = [
                Posicao(*r)
                for r in conn.execute(
                    "SELECT coleira_id, instante, lat, lon FROM posicao WHERE instante >= %s ORDER BY id", (limite,)
                )
            ]
            grupos_externos = {r[0]: list(r[1]) for r in conn.execute("SELECT externo_id, coleiras FROM grupo_externo")}

        repo = cls(
            url,
            fazenda=fazenda_padrao,
            clientes=clientes,
            usuarios=usuarios,
            fazendas=fazendas,
            piquetes=piquetes,
            lotes=lotes,
            lotacao=lotacao,
            ndvi=ndvi,
            historico=historico,
            coleiras=coleiras,
            posicoes=posicoes,
            plano_atual=planos_por_fazenda.get(fazenda_padrao.id),
            planos_por_fazenda=planos_por_fazenda,
            grupos_externos=grupos_externos,
            ultima_movimentacao_fisica=ultima_movimentacao_fisica,
        )
        repo.fisico = fisico
        repo._posicoes_gravadas = len(repo.posicoes)
        repo.deslocamento_s = deslocamento_s
        return repo

    # ---------- salvar ----------

    def salvar(self, *, apenas_se_vazio: bool = False) -> None:
        """Grava o estado inteiro numa transação (tudo ou nada), serializada por advisory lock."""
        with conectar(self.url) as conn, conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_TRANSACAO_ID,))
            if apenas_se_vazio and conn.execute("SELECT count(*) FROM fazenda").fetchone()[0] > 0:
                return
            for tabela in (
                "lotacao", "leitura_ndvi", "movimentacao", "plano_atual", "coleira",
                "grupo_externo", "lote", "piquete", "fazenda", "usuario", "cliente",
            ):
                conn.execute(f"DELETE FROM {tabela}")  # noqa: S608 - nomes fixos
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO cliente (id, nome, contato, seugado_id, ordem) VALUES (%s, %s, %s, %s, %s)",
                    [(c.id, c.nome, c.contato, c.seugado_id, i) for i, c in enumerate(self.clientes)],
                )
                cur.executemany(
                    "INSERT INTO usuario (id, email, senha_hash, papel, cliente_id, nome, ordem) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    [(u.id, u.email, u.senha_hash, u.papel, u.cliente_id, u.nome, i) for i, u in enumerate(self.usuarios)],
                )
                fazendas = self.fazendas or [self.fazenda]
                cur.executemany(
                    "INSERT INTO fazenda (id, nome, timezone, cliente_id, seugado_id, ordem) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    [(f.id, f.nome, f.timezone, f.cliente_id, f.seugado_id, i) for i, f in enumerate(fazendas)],
                )
                cur.executemany(
                    "INSERT INTO piquete (id, fazenda_id, nome, geometria, area_ha, vegetacao, externo_id, ordem, ativo) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    [
                        (p.id, p.fazenda_id, p.nome, Jsonb(p.geometria), p.area_ha, p.vegetacao, p.externo_id, i, p.ativo)
                        for i, p in enumerate(self.piquetes)
                    ],
                )
                cur.executemany(
                    "INSERT INTO lote (id, fazenda_id, nome, piquete_atual_id, bois, vacas, bezerros, desde, seugado_id, ordem) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    [
                        (
                            l.id, l.fazenda_id, l.nome, l.piquete_atual_id, l.bois, l.vacas, l.bezerros,
                            date.fromisoformat(l.desde) if l.desde else None, l.seugado_id, i,
                        )
                        for i, l in enumerate(self.lotes)
                    ],
                )
                cur.executemany(
                    "INSERT INTO lotacao (piquete_id, fazenda_id, bois, vacas, bezerros, desde) VALUES (%s, %s, %s, %s, %s, %s)",
                    [
                        (l.piquete_id, l.fazenda_id, l.bois, l.vacas, l.bezerros, date.fromisoformat(l.desde) if l.desde else None)
                        for l in self.lotacao
                    ],
                )
                cur.executemany(
                    "INSERT INTO leitura_ndvi (piquete_id, data, valor) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                    [(l.piquete_id, date.fromisoformat(l.data), l.valor) for l in self.ndvi],
                )
                cur.executemany(
                    "INSERT INTO movimentacao (id, ordem, dados, fazenda_id) VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                    [(m.id, i, Jsonb(dataclasses.asdict(m)), m.fazenda_id) for i, m in enumerate(self.historico)],
                )
                planos = dict(self.planos_por_fazenda)
                if self.plano_atual is not None and self.fazenda.id not in planos:
                    planos[self.fazenda.id] = self.plano_atual
                cur.executemany(
                    "INSERT INTO plano_atual (fazenda_id, dados) VALUES (%s, %s)",
                    [(fid, Jsonb(dataclasses.asdict(plano))) for fid, plano in planos.items()],
                )
                cur.executemany(
                    "INSERT INTO coleira (id, categoria, piquete_cadastro_id, piquete_fisico_id, ordem, fazenda_id, lote_id) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    [
                        (c.id, c.categoria, c.piquete_cadastro_id, self.fisico.get(c.id, c.piquete_cadastro_id), i, c.fazenda_id, c.lote_id)
                        for i, c in enumerate(self.coleiras)
                    ],
                )
                novas = self.posicoes[self._posicoes_gravadas:]
                cur.executemany(
                    "INSERT INTO posicao (coleira_id, instante, lat, lon) VALUES (%s, %s, %s, %s)",
                    [(p.coleira_id, p.instante, p.lat, p.lon) for p in novas],
                )
                cur.executemany(
                    "INSERT INTO grupo_externo (externo_id, coleiras) VALUES (%s, %s)",
                    [(k, Jsonb(v)) for k, v in self.grupos_externos.items()],
                )
                cur.execute(
                    "INSERT INTO parametro VALUES ('deslocamento_relogio_s', %s) "
                    "ON CONFLICT (chave) DO UPDATE SET valor = excluded.valor",
                    (str(self.deslocamento_s),),
                )
                cur.execute(
                    "INSERT INTO parametro VALUES ('ultima_movimentacao_fisica', %s) "
                    "ON CONFLICT (chave) DO UPDATE SET valor = excluded.valor",
                    (json.dumps({cid: instante.isoformat() for cid, instante in self.ultima_movimentacao_fisica.items()}),),
                )
        self._posicoes_gravadas = len(self.posicoes)
