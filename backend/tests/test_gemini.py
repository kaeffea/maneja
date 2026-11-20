"""SPEC-005 · Gemini real escrevendo a explicação. Nenhum teste chama a rede (R4)."""

import json

import httpx
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from conftest import sistema, sistema_demo
from maneja.adaptadores.llm import (
    GEMINI_COTA_DIARIA_PADRAO,
    GEMINI_MODELO_PADRAO,
    GEMINI_TIMEOUT_S,
    ControleDeCota,
    GeminiLLM,
)
from maneja.config import Config, adaptador_llm, montar_sistema
from maneja.dominio import CotaEsgotada

scenarios("gemini.feature")

CHAVE = "chave-de-teste"


def resposta_gemini(texto: str) -> dict:
    return {"candidates": [{"content": {"parts": [{"text": texto}], "role": "model"}, "finishReason": "STOP"}]}


def gemini_falso(responder, chamadas: list | None = None, modelo: str = GEMINI_MODELO_PADRAO) -> GeminiLLM:
    """GeminiLLM com o HTTP trocado por um MockTransport; `chamadas` guarda as requisições feitas."""
    chamadas = [] if chamadas is None else chamadas

    def tratar(request: httpx.Request) -> httpx.Response:
        chamadas.append(request)
        return responder(request)

    return GeminiLLM(CHAVE, modelo, httpx.Client(transport=httpx.MockTransport(tratar)))


# ---------- cenários BDD ----------

@given(parsers.parse('um Gemini que responde "{texto}"'))
def gemini_responde(ctx, texto):
    ctx["texto_gemini"], ctx["chamadas"] = texto, []
    llm = gemini_falso(lambda r: httpx.Response(200, json=resposta_gemini(texto)), ctx["chamadas"])
    sistema(ctx).llm = ControleDeCota(llm, limite=GEMINI_COTA_DIARIA_PADRAO)


@given(parsers.parse("um Gemini que responde com erro {status:d}"))
def gemini_com_erro(ctx, status):
    ctx["chamadas"] = []
    llm = gemini_falso(lambda r: httpx.Response(status, json={"error": {"code": status}}), ctx["chamadas"])
    sistema(ctx).llm = ControleDeCota(llm, limite=GEMINI_COTA_DIARIA_PADRAO)


@given(parsers.parse("um Gemini com cota de {limite:d} chamadas"))
def gemini_com_cota(ctx, limite):
    ctx["chamadas"] = []
    texto = "Leve o gado do Piquete Abóbora para o Piquete Macarrão."
    llm = gemini_falso(lambda r: httpx.Response(200, json=resposta_gemini(texto)), ctx["chamadas"])
    sistema(ctx).llm = ControleDeCota(llm, limite=limite)


@when("o agente gera o plano")
def gera_plano(ctx):
    ctx["plano"] = sistema(ctx).gerar_plano()


@then("a explicação da movimentação vem do LLM")
def explicacao_do_llm(ctx):
    mov = ctx["plano"].movimentacoes[0]
    assert mov.explicacao_origem == "llm"
    assert mov.explicacao == ctx["texto_gemini"]
    assert len(ctx["chamadas"]) == len(ctx["plano"].movimentacoes)


@then("a explicação da movimentação vem da regra")
def explicacao_da_regra(ctx):
    assert ctx["plano"].movimentacoes, "esperava uma movimentação"
    mov = ctx["plano"].movimentacoes[0]
    assert mov.explicacao_origem == "regra"
    assert mov.explicacao == mov.motivo


# ---------- R1: a chamada ao Gemini ----------

def test_monta_a_requisicao_da_api_do_gemini():
    chamadas = []
    llm = gemini_falso(lambda r: httpx.Response(200, json=resposta_gemini("ok")), chamadas, modelo="gemini-teste")
    assert llm.gerar_texto("explique") == "ok"
    (req,) = chamadas
    assert req.method == "POST"
    assert req.url.host == "generativelanguage.googleapis.com"
    assert req.url.path == "/v1beta/models/gemini-teste:generateContent"
    assert req.url.params["key"] == CHAVE
    assert json.loads(req.content) == {"contents": [{"parts": [{"text": "explique"}]}]}
    assert req.extensions["timeout"] == {k: GEMINI_TIMEOUT_S for k in ("connect", "read", "write", "pool")}


def test_timeout_padrao_e_15_segundos():
    assert GEMINI_TIMEOUT_S == 15
    assert GeminiLLM(CHAVE)._http.timeout.read == 15


# ---------- R2: falhas viram exceção ----------

def test_429_vira_cota_esgotada():
    llm = gemini_falso(lambda r: httpx.Response(429, json={"error": {"status": "RESOURCE_EXHAUSTED"}}))
    with pytest.raises(CotaEsgotada):
        llm.gerar_texto("explique")


@pytest.mark.parametrize("status", [400, 403, 404, 500, 503])
def test_erro_http_vira_runtime_error(status):
    llm = gemini_falso(lambda r: httpx.Response(status, json={"error": {"code": status}}))
    with pytest.raises(RuntimeError, match=str(status)):
        llm.gerar_texto("explique")


@pytest.mark.parametrize("erro", [httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError])
def test_timeout_ou_sem_conexao_vira_runtime_error(erro):
    def falhar(request):
        raise erro("falhou", request=request)

    with pytest.raises(RuntimeError):
        gemini_falso(falhar).gerar_texto("explique")


@pytest.mark.parametrize("corpo", [
    {},
    {"candidates": []},
    {"candidates": [{"content": {"parts": []}}]},
    {"candidates": [{"content": {"parts": [{"text": "   "}]}}]},
    {"candidates": [{"finishReason": "SAFETY"}]},
    {"promptFeedback": {"blockReason": "SAFETY"}},
    [],
])
def test_resposta_sem_texto_vira_runtime_error(corpo):
    llm = gemini_falso(lambda r: httpx.Response(200, json=corpo))
    with pytest.raises(RuntimeError, match="sem texto"):
        llm.gerar_texto("explique")


def test_resposta_que_nao_e_json_vira_runtime_error():
    llm = gemini_falso(lambda r: httpx.Response(200, text="<html>erro</html>"))
    with pytest.raises(RuntimeError, match="sem texto"):
        llm.gerar_texto("explique")


@pytest.mark.parametrize("responder", [
    lambda r: httpx.Response(500),
    lambda r: httpx.Response(429),
    lambda r: httpx.Response(200, json={}),
])
def test_mensagem_de_erro_nao_expoe_a_chave(responder):
    with pytest.raises(Exception) as erro:
        gemini_falso(responder).gerar_texto("explique")
    assert CHAVE not in str(erro.value)


def test_gemini_fora_do_ar_por_timeout_nao_derruba_o_plano():
    def falhar(request):
        raise httpx.ReadTimeout("falhou", request=request)

    s = sistema_demo()
    s.llm = ControleDeCota(gemini_falso(falhar), limite=GEMINI_COTA_DIARIA_PADRAO)
    mov = s.gerar_plano().movimentacoes[0]
    assert (mov.explicacao_origem, mov.explicacao) == ("regra", mov.motivo)


def test_texto_do_gemini_que_nao_cita_origem_e_destino_e_descartado():
    s = sistema_demo()
    llm = gemini_falso(lambda r: httpx.Response(200, json=resposta_gemini("Mantenha o gado onde está.")))
    s.llm = ControleDeCota(llm, limite=GEMINI_COTA_DIARIA_PADRAO)
    assert s.gerar_plano().movimentacoes[0].explicacao_origem == "regra"


# ---------- cota (risco R7) ----------

def test_cota_esgotada_nao_chama_o_gemini():
    chamadas = []
    llm = ControleDeCota(gemini_falso(lambda r: httpx.Response(200, json=resposta_gemini("ok")), chamadas), limite=2)
    assert llm.gerar_texto("a") == llm.gerar_texto("b") == "ok"
    with pytest.raises(CotaEsgotada):
        llm.gerar_texto("c")
    assert len(chamadas) == 2


# ---------- R3: montagem pelo ambiente ----------

@pytest.fixture
def sem_gemini_no_ambiente(monkeypatch):
    for var in ("MANEJA_GEMINI_API_KEY", "MANEJA_GEMINI_MODELO", "MANEJA_GEMINI_COTA_DIARIA"):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def test_sem_chave_o_sistema_sobe_sem_llm(sem_gemini_no_ambiente):
    config = Config.do_ambiente()
    assert config.gemini_api_key == ""
    assert adaptador_llm(config) is None
    assert montar_sistema(Config(perda_sinal=0.0, semente=7)).llm is None


def test_chave_em_branco_conta_como_sem_chave(sem_gemini_no_ambiente):
    sem_gemini_no_ambiente.setenv("MANEJA_GEMINI_API_KEY", "   ")
    assert adaptador_llm(Config.do_ambiente()) is None


def test_com_chave_usa_gemini_com_controle_de_cota(sem_gemini_no_ambiente):
    sem_gemini_no_ambiente.setenv("MANEJA_GEMINI_API_KEY", CHAVE)
    sem_gemini_no_ambiente.setenv("MANEJA_GEMINI_MODELO", "gemini-teste")
    sem_gemini_no_ambiente.setenv("MANEJA_GEMINI_COTA_DIARIA", "7")
    llm = adaptador_llm(Config.do_ambiente())
    assert isinstance(llm, ControleDeCota)
    assert llm.limite == 7
    assert isinstance(llm._llm, GeminiLLM)
    assert llm._llm.modelo == "gemini-teste"


def test_padroes_de_modelo_e_cota(sem_gemini_no_ambiente):
    sem_gemini_no_ambiente.setenv("MANEJA_GEMINI_API_KEY", CHAVE)
    config = Config.do_ambiente()
    assert (config.gemini_modelo, config.gemini_cota_diaria) == (GEMINI_MODELO_PADRAO, GEMINI_COTA_DIARIA_PADRAO)
    assert GEMINI_COTA_DIARIA_PADRAO == 50


def test_montar_sistema_com_chave_liga_o_gemini_sem_chamar_a_rede():
    s = montar_sistema(Config(perda_sinal=0.0, semente=7, gemini_api_key=CHAVE))
    assert isinstance(s.llm, ControleDeCota) and s.llm.usado == 0


def test_llm_passado_explicitamente_tem_prioridade():
    fixo = ControleDeCota(gemini_falso(lambda r: httpx.Response(500)), limite=1)
    assert montar_sistema(Config(perda_sinal=0.0, semente=7, gemini_api_key=CHAVE), llm=fixo).llm is fixo


def test_chave_nao_aparece_no_repr_da_config():
    assert CHAVE not in repr(Config(gemini_api_key=CHAVE))
