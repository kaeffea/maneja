import json

import httpx
from pytest_bdd import given, parsers, scenarios, then, when

from conftest import sistema
from maneja.adaptadores import clima as clima_mod
from maneja.adaptadores.llm import ControleDeCota, GeminiLLM
from maneja.adaptadores.seugado import SeuGadoApi
from maneja.config import EXEMPLO_PLANO_SEUGADO
from maneja.datas import somar_dias

scenarios("integracoes.feature")


@given(parsers.parse("um Gemini com HTTP {http:d} e cota {cota:d}"))
def gemini(ctx, http, cota):
    def responder(requisicao):
        assert cota > 0
        assert requisicao.method == "POST"
        assert requisicao.url.params["key"] == "teste"
        assert json.loads(requisicao.content)["contents"][0]["parts"][0]["text"]
        texto = "Leve o gado do Piquete Abóbora para o Piquete Macarrão, que tem pasto melhor."
        return httpx.Response(http, json={"candidates": [{"content": {"parts": [{"text": texto}]}}]})

    cliente = httpx.Client(transport=httpx.MockTransport(responder))
    sistema(ctx).llm = ControleDeCota(GeminiLLM("teste", "modelo-teste", cliente), cota)


@when("gero o plano de manejo")
def gerar_plano(ctx):
    ctx["plano"] = sistema(ctx).gerar_plano()


@then(parsers.parse('a origem da explicação é "{origem}"'))
def origem_explicacao(ctx, origem):
    assert ctx["plano"].movimentacoes[0].explicacao_origem == origem


@given(parsers.parse("o Open-Meteo com HTTP {http:d} e cache {cache}"))
def open_meteo(ctx, http, cache, monkeypatch):
    s = sistema(ctx)
    ctx["tempo"] = 0
    monkeypatch.setattr(clima_mod, "monotonic", lambda: ctx["tempo"])

    def responder(requisicao):
        assert requisicao.url.params["forecast_days"] == "7"
        codigo = 200 if cache == "sim" and ctx["tempo"] == 0 else http
        return httpx.Response(codigo, json={"daily": {
            "time": [somar_dias(s.hoje(), i) for i in range(7)],
            "precipitation_sum": [50, 0, 0, 0, 0, 0, 0],
            "temperature_2m_min": [20] * 7,
            "temperature_2m_max": [30] * 7,
        }})

    s.clima = clima_mod.ClimaOpenMeteo(httpx.Client(transport=httpx.MockTransport(responder)))
    if cache == "sim":
        ctx["anterior"] = s.previsao()
        ctx["tempo"] = 3 * 3600 + 1


@when("consulto o clima")
def consultar_clima(ctx):
    ctx["previsao"] = sistema(ctx).previsao()


@then(parsers.parse('a fonte da previsão é "{fonte}"'))
def fonte_previsao(ctx, fonte):
    previsao = ctx["previsao"]
    assert previsao.fonte == fonte
    assert len(previsao.dias) == 7
    if fonte == "open-meteo":
        assert previsao.dias[0].chuva_mm == 50
    if "anterior" in ctx:
        assert previsao is ctx["anterior"]


@given(parsers.parse("o SeuGado com HTTP {http:d} para o plano"))
def seugado(ctx, http):
    plano = json.loads(EXEMPLO_PLANO_SEUGADO.read_text(encoding="utf-8"))

    def responder(requisicao):
        if requisicao.url.path == "/auth/token":
            assert requisicao.method == "POST"
            assert requisicao.content == b"username=teste&password=senha"
            return httpx.Response(200, json={"access_token": "teste", "expires_in": 3600})
        assert requisicao.headers["Authorization"] == "Bearer teste"
        assert requisicao.url.path == "/fazendas/fazenda/plano/atual"
        return httpx.Response(http, json=plano)

    cliente = httpx.Client(transport=httpx.MockTransport(responder))
    sistema(ctx).seugado = SeuGadoApi("https://seugado.test", "teste", "senha", "fazenda", cliente)


@when("verifico as movimentações")
def verificar(ctx):
    ctx["verificacoes"] = sistema(ctx).verificacoes()


@then(parsers.parse('o resultado do plano externo é "{resultado}"'))
def resultado_externo(ctx, resultado):
    verificacoes, avisos = ctx["verificacoes"]
    assert any(v.origem_plano == "seugado" for v in verificacoes) == (resultado == "seugado")
    assert ("plano_externo_indisponivel" in avisos) == (resultado == "plano_externo_indisponivel")
