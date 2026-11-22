import json

import httpx
from pytest_bdd import given, parsers, scenarios, then, when

from conftest import cliente, piquete_id, sistema
from maneja.adaptadores.satelite import SateliteCopernicus

scenarios("ndvi.feature")


@given(parsers.parse("uma imagem com fração de nuvem {nuvem:f}"))
def imagem(ctx, nuvem):
    s = sistema(ctx)
    ctx["piquete"] = piquete_id(ctx, "Piquete Feijão")
    ctx["serie"] = list(s.repo.ndvi)

    def responder(requisicao):
        if requisicao.url.host == "identity.dataspace.copernicus.eu":
            return httpx.Response(200, json={"access_token": "teste", "expires_in": 3600})
        assert requisicao.headers["Authorization"] == "Bearer teste"
        dados = json.loads(requisicao.content)
        piquete = next(p for p in s.repo.piquetes if p.id == ctx["piquete"])
        if dados["input"]["bounds"]["geometry"] != piquete.geometria:
            return httpx.Response(200, json={"data": []})
        return httpx.Response(200, json={"data": [{"outputs": {
            "ndvi": {"bands": {"B0": {"stats": {"mean": 0.61}}}},
            "nuvem": {"bands": {"B0": {"stats": {"mean": nuvem}}}},
        }}]})

    s.satelite = SateliteCopernicus("cliente", "segredo", httpx.Client(transport=httpx.MockTransport(responder)))


@when("atualizo o NDVI pela API")
def atualizar(ctx):
    ctx["resposta"] = cliente(ctx).post("/ndvi/atualizar")


@then(parsers.parse("a leitura da imagem foi registrada: {registrada}"))
def conferir(ctx, registrada):
    assert ctx["resposta"].status_code == 200
    s = sistema(ctx)
    novas = ctx["resposta"].json()["leituras"]
    assert s.repo.ndvi[:len(ctx["serie"])] == ctx["serie"]
    if registrada == "sim":
        assert novas == [{"piquete_id": ctx["piquete"], "data": s.hoje(), "valor": 0.61}]
        assert cliente(ctx).post("/ndvi/atualizar").json()["leituras"] == []
    else:
        assert novas == []
        assert s.repo.ndvi == ctx["serie"]
