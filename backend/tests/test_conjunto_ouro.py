"""SPEC-016 · Conjunto-ouro do agente de manejo."""

import copy

from pytest_bdd import given, parsers, scenarios, then, when

from maneja.conjunto_ouro import META_PLAUSIVEIS, RELATORIO, avaliar, avaliar_caso, carregar, relatorio, taxa

scenarios("conjunto_ouro.feature")


@given(parsers.parse("o conjunto-ouro com {n:d} casos"))
def conjunto(ctx, n):
    ctx["dados"] = carregar()
    assert len(ctx["dados"]["casos"]) == n


@given(parsers.parse('o caso "{caso_id}" com o destino plausível trocado para "{nome}"'))
def caso_alterado(ctx, caso_id, nome):
    dados = copy.deepcopy(carregar())
    pid = next(p["id"] for p in dados["piquetes"] if p["nome"] == nome)
    caso = next(c for c in dados["casos"] if c["id"] == caso_id)
    caso["esperado"]["movimentos"][0]["destinos"] = [pid]
    ctx["dados"], ctx["caso"] = dados, caso


@when("o agente é avaliado em todos os casos")
def avaliar_todos(ctx):
    ctx["resultados"] = avaliar(ctx["dados"])


@when("o agente é avaliado nesse caso")
def avaliar_um(ctx):
    ctx["resultado"] = avaliar_caso(ctx["dados"], ctx["caso"])


@then("pelo menos 90% das recomendações são plausíveis")
def meta(ctx):
    falhos = [f"{r.id}: {r.problemas}" for r in ctx["resultados"] if not r.plausivel]
    assert taxa(ctx["resultados"]) >= META_PLAUSIVEIS, falhos


@then("nenhuma recomendação viola as regras determinísticas")
def sem_violacao(ctx):
    assert [v for r in ctx["resultados"] for v in r.violacoes] == []


@then("o caso não é plausível")
def nao_plausivel(ctx):
    assert not ctx["resultado"].plausivel
    assert ctx["resultado"].problemas


def test_casos_tem_ids_unicos_e_justificativa():
    casos = carregar()["casos"]
    assert len({c["id"] for c in casos}) == len(casos) == 30
    assert all(c["justificativa"].strip() for c in casos)


def test_relatorio_commitado_esta_em_dia():
    """Se este teste falhar, rode: uv run python -m maneja.conjunto_ouro --relatorio"""
    dados = carregar()
    assert RELATORIO.read_text(encoding="utf-8") == relatorio(avaliar(dados), dados)
