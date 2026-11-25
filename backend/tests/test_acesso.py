"""SPEC-017 · Acesso por papel (admin e cliente) e multi-fazenda."""

from datetime import datetime, timezone

import psycopg
import pytest
from fastapi.testclient import TestClient
from pytest_bdd import given, parsers, scenarios, then, when

from conftest import AUTH_TESTE, EMAIL_TESTE, INICIO, SENHA_TESTE, cliente_anonimo, sistema
from maneja.api import criar_app
from maneja.config import Config, montar_sistema
from maneja.geo import poligono_em_metros

scenarios("acesso.feature")


def _headers(client: TestClient, email: str, senha: str) -> dict[str, str]:
    r = client.post("/auth/token", json={"email": email, "senha": senha})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _poligono(dx: int = 0) -> dict:
    return poligono_em_metros((-9.6205, -35.9695), [(dx, 0), (dx + 120, 0), (dx + 120, 120), (dx, 120)])


@given("dois clientes com fazendas próprias")
def dois_clientes(ctx):
    c = cliente_anonimo(ctx)
    h_admin = _headers(c, EMAIL_TESTE, SENHA_TESTE)
    ctx["h_admin"] = h_admin

    cli_a = c.post("/clientes", json={"nome": "Cliente A", "contato": "82 99999-0001"}, headers=h_admin).json()
    cli_b = c.post("/clientes", json={"nome": "Cliente B", "contato": "82 99999-0002"}, headers=h_admin).json()
    faz_a = c.post("/fazendas", json={"nome": "Fazenda Alfa", "cliente_id": cli_a["id"]}, headers=h_admin).json()
    faz_b = c.post("/fazendas", json={"nome": "Fazenda Beta", "cliente_id": cli_b["id"]}, headers=h_admin).json()

    pq_a = c.post(
        f"/fazendas/{faz_a['id']}/piquetes",
        json={"nome": "Piquete A1", "vegetacao": "Marandu", "geometria": _poligono(0)},
        headers=h_admin,
    ).json()
    pq_b = c.post(
        f"/fazendas/{faz_b['id']}/piquetes",
        json={"nome": "Piquete B1", "vegetacao": "Mombaça", "geometria": _poligono(300)},
        headers=h_admin,
    ).json()

    r_ua = c.post(
        "/usuarios",
        json={"email": "a@fazenda.test", "senha": "senha-a", "papel": "cliente", "cliente_id": cli_a["id"], "nome": "Ana"},
        headers=h_admin,
    )
    assert r_ua.status_code == 201, r_ua.text
    r_ub = c.post(
        "/usuarios",
        json={"email": "b@fazenda.test", "senha": "senha-b", "papel": "cliente", "cliente_id": cli_b["id"], "nome": "Beto"},
        headers=h_admin,
    )
    assert r_ub.status_code == 201, r_ub.text

    ctx.update({
        "cli_a": cli_a, "cli_b": cli_b,
        "faz_a": faz_a, "faz_b": faz_b,
        "pq_a": pq_a, "pq_b": pq_b,
        "h_a": _headers(c, "a@fazenda.test", "senha-a"),
        "h_b": _headers(c, "b@fazenda.test", "senha-b"),
    })


@when(parsers.parse('eu consulto "{caminho}" sem token'))
def consulto_sem_token(ctx, caminho):
    ctx["resposta"] = cliente_anonimo(ctx).get(caminho)


@when("o admin lista fazendas e clientes")
def admin_lista(ctx):
    c = cliente_anonimo(ctx)
    ctx["fazendas_admin"] = c.get("/fazendas", headers=ctx["h_admin"]).json()
    ctx["clientes_admin"] = c.get("/clientes", headers=ctx["h_admin"]).json()


@then("o admin vê as duas fazendas e os dois clientes")
def admin_ve_tudo(ctx):
    fids = {f["id"] for f in ctx["fazendas_admin"]}
    cids = {c["id"] for c in ctx["clientes_admin"]}
    assert {ctx["faz_a"]["id"], ctx["faz_b"]["id"]}.issubset(fids)
    assert {ctx["cli_a"]["id"], ctx["cli_b"]["id"]}.issubset(cids)


@when(parsers.parse('o cliente A lista "{caminho}"'))
def cliente_a_lista(ctx, caminho):
    ctx["resposta"] = cliente_anonimo(ctx).get(caminho, headers=ctx["h_a"])


@then("o cliente A vê apenas a fazenda do cliente A")
def ve_apenas_a(ctx):
    assert ctx["resposta"].status_code == 200
    assert [f["id"] for f in ctx["resposta"].json()] == [ctx["faz_a"]["id"]]


@when("o cliente A tenta ler os piquetes da fazenda do cliente B")
def cliente_a_le_b(ctx):
    ctx["resposta"] = cliente_anonimo(ctx).get(f"/fazendas/{ctx['faz_b']['id']}/piquetes", headers=ctx["h_a"])


@when("o cliente A tenta criar um piquete na fazenda do cliente B")
def cliente_a_cria_em_b(ctx):
    ctx["resposta"] = cliente_anonimo(ctx).post(
        f"/fazendas/{ctx['faz_b']['id']}/piquetes",
        json={"nome": "Invasor", "vegetacao": "Marandu", "geometria": _poligono(600)},
        headers=ctx["h_a"],
    )


@when("o cliente A tenta editar um piquete da fazenda do cliente B")
def cliente_a_edita_b(ctx):
    ctx["resposta"] = cliente_anonimo(ctx).put(
        f"/piquetes/{ctx['pq_b']['id']}",
        json={"nome": "Alterado"},
        headers=ctx["h_a"],
    )


@when("o cliente A tenta alterar a lotação da fazenda do cliente B")
def cliente_a_lotacao_b(ctx):
    ctx["resposta"] = cliente_anonimo(ctx).put(
        f"/lotacao/{ctx['pq_b']['id']}",
        json={"bois": 10, "vacas": 0, "bezerros": 0},
        headers=ctx["h_a"],
    )


@when(parsers.parse('o cliente A tenta listar "{caminho}"'))
def cliente_a_tenta_admin_get(ctx, caminho):
    ctx["resposta"] = cliente_anonimo(ctx).get(caminho, headers=ctx["h_a"])


@when("o cliente A tenta criar um usuário")
def cliente_a_tenta_criar_usuario(ctx):
    ctx["resposta"] = cliente_anonimo(ctx).post(
        "/usuarios",
        json={"email": "outro@fazenda.test", "senha": "1234", "papel": "admin"},
        headers=ctx["h_a"],
    )


@when("o cliente A renomeia a própria fazenda e atualiza a lotação do próprio piquete")
def cliente_a_edita_propria(ctx):
    c = cliente_anonimo(ctx)
    ctx["r_faz"] = c.put(
        f"/fazendas/{ctx['faz_a']['id']}",
        json={"nome": "Fazenda Alfa Nova"},
        headers=ctx["h_a"],
    )
    ctx["r_lot"] = c.put(
        f"/fazendas/{ctx['faz_a']['id']}/lotacao/{ctx['pq_a']['id']}",
        json={"bois": 15, "vacas": 5, "bezerros": 2},
        headers=ctx["h_a"],
    )


@then("as alterações da fazenda do cliente A são salvas com sucesso")
def alteracoes_salvas(ctx):
    assert ctx["r_faz"].status_code == 200, ctx["r_faz"].text
    assert ctx["r_faz"].json()["nome"] == "Fazenda Alfa Nova"
    assert ctx["r_lot"].status_code == 200, ctx["r_lot"].text
    assert ctx["r_lot"].json()["bois"] == 15


# ---------- testes complementares de isolamento e migração PostgreSQL ----------


def test_atalhos_de_fazenda_tambem_respeitam_isolamento_de_cliente(ctx):
    dois_clientes(ctx)
    c = cliente_anonimo(ctx)
    # atalho /fazenda sem fazenda_id abre direto a fazenda do cliente A
    r = c.get("/fazenda", headers=ctx["h_a"])
    assert r.status_code == 200 and r.json()["id"] == ctx["faz_a"]["id"]
    # passar fazenda_id de outro cliente devolve 403
    assert c.get(f"/piquetes?fazenda_id={ctx['faz_b']['id']}", headers=ctx["h_a"]).status_code == 403
    assert c.get(f"/ndvi?piquete_id={ctx['pq_b']['id']}", headers=ctx["h_a"]).status_code == 403
    assert c.delete(f"/piquetes/{ctx['pq_b']['id']}", headers=ctx["h_a"]).status_code == 403
    # /me devolve papel e cliente_id
    me_a = c.get("/me", headers=ctx["h_a"]).json()
    assert me_a["papel"] == "cliente" and me_a["cliente_id"] == ctx["cli_a"]["id"]
    me_admin = c.get("/me", headers=ctx["h_admin"]).json()
    assert me_admin["papel"] == "admin" and me_admin["cliente_id"] is None


def test_migracao_idempotente_banco_v1_e_login_cliente_sem_estado(tmp_path):
    """Garante que o banco v1 já em produção no Supabase migra sem perder dados e suporta login sem estado."""
    pgserver = pytest.importorskip("pgserver")
    servidor = pgserver.get_server(str(tmp_path / "pg-migracao"), cleanup_mode="stop")
    try:
        url = servidor.get_uri()
        # Cria exatamente o schema v1 anterior à SPEC-017
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute("""
                CREATE TABLE fazenda (id text PRIMARY KEY, nome text NOT NULL, timezone text NOT NULL);
                CREATE TABLE piquete (
                    id text PRIMARY KEY, fazenda_id text NOT NULL REFERENCES fazenda(id),
                    nome text NOT NULL, geometria jsonb NOT NULL, area_ha double precision NOT NULL,
                    vegetacao text NOT NULL DEFAULT '', externo_id text, ordem integer NOT NULL
                );
                CREATE TABLE lotacao (
                    piquete_id text PRIMARY KEY REFERENCES piquete(id) ON DELETE CASCADE,
                    fazenda_id text NOT NULL, bois integer NOT NULL, vacas integer NOT NULL,
                    bezerros integer NOT NULL, desde date
                );
                CREATE TABLE leitura_ndvi (
                    piquete_id text NOT NULL REFERENCES piquete(id) ON DELETE CASCADE,
                    data date NOT NULL, valor double precision NOT NULL, PRIMARY KEY (piquete_id, data)
                );
                CREATE TABLE movimentacao (id text PRIMARY KEY, ordem integer NOT NULL, dados jsonb NOT NULL);
                CREATE TABLE plano_atual (unico boolean PRIMARY KEY DEFAULT true CHECK (unico), dados jsonb NOT NULL);
                CREATE TABLE coleira (
                    id text PRIMARY KEY, categoria text NOT NULL, piquete_cadastro_id text NOT NULL,
                    piquete_fisico_id text NOT NULL, ordem integer NOT NULL
                );
                CREATE TABLE posicao (
                    id bigserial PRIMARY KEY, coleira_id text NOT NULL, instante timestamptz NOT NULL,
                    lat double precision NOT NULL, lon double precision NOT NULL
                );
                CREATE TABLE grupo_externo (externo_id text PRIMARY KEY, coleiras jsonb NOT NULL);
                CREATE TABLE parametro (chave text PRIMARY KEY, valor text NOT NULL);

                INSERT INTO fazenda VALUES ('faz-antiga', 'Fazenda Existente', 'America/Maceio');
                INSERT INTO piquete VALUES (
                    'pq-1', 'faz-antiga', 'Piquete 1',
                    '{"type":"Polygon","coordinates":[[[-35.97,-9.62],[-35.96,-9.62],[-35.96,-9.61],[-35.97,-9.62]]]}'::jsonb,
                    5.0, 'Marandu', NULL, 0
                );
                INSERT INTO plano_atual (unico, dados) VALUES (
                    true,
                    '{"id":"pl-1","fazenda_id":"faz-antiga","data_geracao":"2026-11-25T10:00:00+00:00","data_inicio":"2026-11-25","horizonte_dias":7,"movimentacoes":[],"alertas":[]}'::jsonb
                );
            """)

        cfg = Config(perda_sinal=0.0, semente=7, database_url=url, sem_estado=True)
        api = TestClient(criar_app(auth=AUTH_TESTE, config=cfg))
        h_admin = _headers(api, EMAIL_TESTE, SENHA_TESTE)

        # Dados existentes preservados após migração automática
        fazendas = api.get("/fazendas", headers=h_admin).json()
        assert [f["id"] for f in fazendas] == ["faz-antiga"]
        assert api.get("/fazendas/faz-antiga/plano", headers=h_admin).status_code == 200

        # Admin cria cliente, fazenda e usuário e cliente faz login em modo sem_estado=True
        cli = api.post("/clientes", json={"nome": "Produtor Novo"}, headers=h_admin).json()
        faz = api.post("/fazendas", json={"nome": "Fazenda Nova", "cliente_id": cli["id"]}, headers=h_admin).json()
        r_u = api.post(
            "/usuarios",
            json={"email": "produtor@campo.test", "senha": "segredo123", "papel": "cliente", "cliente_id": cli["id"]},
            headers=h_admin,
        )
        assert r_u.status_code == 201, r_u.text

        h_cli = _headers(api, "produtor@campo.test", "segredo123")
        assert [f["id"] for f in api.get("/fazendas", headers=h_cli).json()] == [faz["id"]]
        assert api.get("/fazendas/faz-antiga/piquetes", headers=h_cli).status_code == 403
    finally:
        servidor.cleanup()
