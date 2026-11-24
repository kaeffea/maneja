"""SPEC-002 · Coleiras simuladas e ocupação estimada."""

from datetime import timedelta

from pytest_bdd import given, parsers, scenarios, then, when

from conftest import INICIO, piquete_id, sistema
from maneja.adaptadores.coleiras import SimuladorColeiras
from maneja.demo import piquetes_demo
from maneja.dominio import Coleira, ColeiraDesconhecida, Posicao
from maneja.geo import contem

scenarios("coleiras.feature")


def test_simulador_move_coleira_sem_sinal_no_aceite(ctx):
    s = sistema(ctx)
    origem = piquete_id(ctx, "Piquete Abóbora")
    coleira = next(c for c in s.repo.coleiras if c.piquete_cadastro_id == origem)
    s.repo.posicoes[:] = [p for p in s.repo.posicoes if p.coleira_id != coleira.id]
    outro_piquete = {cid: pid for cid, pid in s.simulador.fisico.items() if pid != origem}

    plano = s.gerar_plano()
    mov = s.aceitar(next(m.id for m in plano.movimentacoes if m.piquete_origem_id == origem))
    assert coleira.id not in mov.coleiras

    s.simulador_executar(mov.id)

    observada = next(c for c in s.coleiras() if c["id"] == coleira.id)
    assert observada["piquete_observado_id"] == mov.piquete_destino_id
    assert s.repo.ultima_movimentacao_fisica[coleira.id] == s.agora()
    assert {cid: s.simulador.fisico[cid] for cid in outro_piquete} == outro_piquete
    assert _ocupacao(ctx, "Piquete Abóbora").coleiras_observadas == 0
    assert _ocupacao(ctx, "Piquete Macarrão").situacao == "confere"


@given(parsers.parse('uma coleira no "{nome}"'))
def uma_coleira(ctx, nome):
    piquetes = piquetes_demo()
    alvo = next(p for p in piquetes if p.nome == nome)
    ctx["alvo"] = alvo
    ctx["simulador"] = SimuladorColeiras([Coleira("col-teste", "boi", alvo.id)], piquetes, perda_sinal=0.0, semente=3)


@given(parsers.parse('as coleiras do "{origem}" levadas para o "{destino}" no campo'))
def coleiras_levadas(ctx, origem, destino):
    s = sistema(ctx)
    ids = [c.id for c in s.repo.coleiras if c.piquete_cadastro_id == piquete_id(ctx, origem)]
    s.simulador.mover(ids, piquete_id(ctx, destino))
    s.relogio.avancar(1)


@when(parsers.parse("o simulador gera {n:d} posições"))
def gera_n_posicoes(ctx, n):
    sim = ctx["simulador"]
    ctx["posicoes"] = [p for i in range(n) for p in sim.gerar_posicoes(INICIO + timedelta(minutes=i))]


@when(parsers.parse('chega uma posição da coleira "{coleira}"'))
def chega_posicao(ctx, coleira):
    try:
        sistema(ctx).registrar_posicoes([Posicao(coleira, INICIO, -9.62, -35.97)])
        ctx["erro"] = None
    except ColeiraDesconhecida as e:
        ctx["erro"] = e


@when("o simulador gera as posições de agora")
def gera_agora(ctx):
    sistema(ctx).gerar_posicoes()


@then(parsers.parse('pelo menos {pct:d}% delas estão dentro do "{nome}"'))
def dentro(ctx, pct, nome):
    posicoes = ctx["posicoes"]
    dentro = sum(1 for p in posicoes if contem(ctx["alvo"].geometria, p.lat, p.lon))
    assert len(posicoes) == 1000
    assert dentro / len(posicoes) >= pct / 100


@then("a leitura é rejeitada")
def rejeitada(ctx):
    assert isinstance(ctx["erro"], ColeiraDesconhecida)
    assert not any(p.coleira_id == "col-99" for p in sistema(ctx).repo.posicoes)


def _ocupacao(ctx, nome):
    return next(o for o in sistema(ctx).ocupacao() if o.nome == nome)


@then(parsers.parse('a ocupação do "{nome}" confere'))
def confere(ctx, nome):
    o = _ocupacao(ctx, nome)
    assert o.situacao == "confere", o
    assert o.coleiras_observadas == o.coleiras_esperadas > 0


@then(parsers.parse('a ocupação do "{nome}" diverge'))
def diverge(ctx, nome):
    assert _ocupacao(ctx, nome).situacao == "diverge"


@then(parsers.parse('o "{nome}" tem coleiras observadas sem rebanho cadastrado'))
def observadas_sem_cadastro(ctx, nome):
    o = _ocupacao(ctx, nome)
    assert o.coleiras_esperadas == 0 and o.coleiras_observadas > 0, o
