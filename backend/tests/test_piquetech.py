"""SPEC-018 · Integração bidirecional multi-fazenda com o PiqueTech (SeuGado)."""

import json
import uuid

import httpx
from pytest_bdd import given, parsers, scenarios, then, when

from conftest import EMAIL_TESTE, SENHA_TESTE, cliente, cliente_anonimo, sistema
from maneja.adaptadores.seugado import SeuGadoApi
from maneja.geo import poligono_em_metros

scenarios("piquetech.feature")

FAZENDA_AULA_ID = "67c6de92-0f00-4ab6-81cd-dc9a71c7e7a6"
FAZENDA_EXTRA_ID = "22222222-0f00-4ab6-81cd-dc9a71c7e7a6"
CLI_AULA_ID = "11111111-1111-4111-8111-111111111111"
PQ7_ID = "77777777-0000-4000-8000-000000000007"
PQ8_ID = "77777777-0000-4000-8000-000000000008"
PQ9_ID = "77777777-0000-4000-8000-000000000009"
LOTE_RECRIA_ID = "99999999-0000-4000-8000-000000000001"
MOV_AULA_ID = "aaaaaaaa-0000-4000-8000-000000000001"
MOV_EXTRA_ID = "bbbbbbbb-0000-4000-8000-000000000002"
CULTIVAR_MARANDU_ID = "cccccccc-0000-4000-8000-000000000001"


def _poly(dx: int) -> dict:
    return poligono_em_metros((-9.6205, -35.9695), [(dx, 0), (dx + 150, 0), (dx + 150, 150), (dx, 150)])


def _estado_piquetech_inicial() -> dict:
    return {
        "clientes": [{"id": CLI_AULA_ID, "nome": "Prof. Rafael", "telefone": "82 99999-1111", "observacoes": None}],
        "fazendas": {
            FAZENDA_AULA_ID: {
                "id": FAZENDA_AULA_ID,
                "cliente_id": CLI_AULA_ID,
                "cliente_nome": "Prof. Rafael",
                "nome": "Fazenda Aula",
                "timezone": "America/Maceio",
            },
        },
        "piquetes": {
            FAZENDA_AULA_ID: [
                {"id": PQ7_ID, "nome": "Piquete 7", "geometria": _poly(0), "area_ha": 2.25, "cultivar_nome": "Marandu"},
                {"id": PQ8_ID, "nome": "Piquete 8", "geometria": _poly(200), "area_ha": 2.25, "cultivar_nome": "Marandu"},
                {"id": PQ9_ID, "nome": "Piquete 9", "geometria": _poly(400), "area_ha": 2.25, "cultivar_nome": "Marandu"},
            ],
        },
        "lotes": {
            FAZENDA_AULA_ID: [
                {
                    "id": LOTE_RECRIA_ID,
                    "nome": "Recria",
                    "piquete_atual_id": PQ7_ID,
                    "desde": "2026-11-10",
                    "composicao": [
                        {"categoria": "novilho", "n_animais": 10},
                        {"categoria": "touro", "n_animais": 2},
                        {"categoria": "novilha", "n_animais": 5},
                        {"categoria": "bezerra", "n_animais": 3},
                    ],
                },
            ],
        },
        "planos": {
            FAZENDA_AULA_ID: {
                "id": "plano-aula-1",
                "movimentacoes": [
                    {
                        "id": MOV_AULA_ID,
                        "data": "2026-11-19",
                        "lote_id": LOTE_RECRIA_ID,
                        "lote_nome": "Recria",
                        "piquete_origem_id": PQ7_ID,
                        "piquete_origem_nome": "Piquete 7",
                        "piquete_destino_id": PQ9_ID,
                        "piquete_destino_nome": "Piquete 9",
                        "motivo": "Plano do PiqueTech",
                    },
                ],
            },
        },
        "cultivares": [
            {"id": CULTIVAR_MARANDU_ID, "slug": "marandu", "nome": "Marandu", "regimes_disponiveis": ["rotacionado"], "calibrada": True, "faltantes_calibracao": []},
        ],
        "criados": {"clientes": [], "fazendas": [], "piquetes": [], "lotes": []},
    }


def _mock_piquetech(estado: dict) -> SeuGadoApi:
    def responder(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path == "/auth/token":
            return httpx.Response(200, json={"access_token": "tok-pt", "token_type": "bearer"})
        assert req.headers.get("Authorization") == "Bearer tok-pt"

        if req.method == "GET":
            if path == "/clientes":
                return httpx.Response(200, json=estado["clientes"])
            if path == "/fazendas":
                return httpx.Response(200, json=list(estado["fazendas"].values()))
            if path == "/cultivares":
                return httpx.Response(200, json=estado["cultivares"])
            partes = path.strip("/").split("/")
            if len(partes) == 2 and partes[0] == "fazendas":
                f = estado["fazendas"].get(partes[1])
                return httpx.Response(200, json=f) if f else httpx.Response(404)
            if len(partes) == 3 and partes[0] == "fazendas" and partes[2] == "piquetes":
                return httpx.Response(200, json=estado["piquetes"].get(partes[1], []))
            if len(partes) == 3 and partes[0] == "fazendas" and partes[2] == "lotes":
                return httpx.Response(200, json=estado["lotes"].get(partes[1], []))
            if len(partes) == 4 and partes[0] == "fazendas" and partes[2] == "plano" and partes[3] == "atual":
                plano = estado["planos"].get(partes[1])
                return httpx.Response(200, json=plano) if plano else httpx.Response(404)

        if req.method == "POST":
            corpo = json.loads(req.content)
            novo_id = str(uuid.uuid4())
            if path == "/clientes":
                item = {"id": novo_id, **corpo}
                estado["criados"]["clientes"].append(item)
                estado["clientes"].append(item)
                return httpx.Response(201, json=item)
            if path == "/fazendas":
                item = {"id": novo_id, **corpo}
                estado["criados"]["fazendas"].append(item)
                estado["fazendas"][novo_id] = item
                return httpx.Response(201, json=item)
            partes = path.strip("/").split("/")
            if len(partes) == 3 and partes[0] == "fazendas" and partes[2] == "piquetes":
                item = {"id": novo_id, "fazenda_id": partes[1], **corpo}
                estado["criados"]["piquetes"].append(item)
                return httpx.Response(201, json=item)
            if len(partes) == 3 and partes[0] == "fazendas" and partes[2] == "lotes":
                item = {"id": novo_id, "fazenda_id": partes[1], **corpo}
                estado["criados"]["lotes"].append(item)
                return httpx.Response(201, json=item)

        return httpx.Response(404, json={"detail": f"rota não mockada: {req.method} {path}"})

    return SeuGadoApi(
        "https://api.piquetech.test",
        "servico@maneja.app",
        "segredo",
        cliente_http=httpx.Client(transport=httpx.MockTransport(responder)),
    )


@given("uma API simulada do PiqueTech com a Fazenda Aula")
@given("uma API simulada do PiqueTech pronta para criação")
def piquetech_mock(ctx):
    ctx["pt_estado"] = _estado_piquetech_inicial()
    sistema(ctx).seugado = _mock_piquetech(ctx["pt_estado"])


@when("o admin importa a Fazenda Aula pelo UUID")
def importar_aula(ctx):
    r = cliente(ctx).post(f"/integracao/piquetech/importar/{FAZENDA_AULA_ID}")
    assert r.status_code == 201, r.text
    ctx["importacao"] = r.json()


@then('o Maneja cria o cliente, a fazenda, 3 piquetes e o lote "Recria" vinculados por UUID')
def validar_importacao(ctx):
    imp = ctx["importacao"]
    assert imp["cliente"]["seugado_id"] == CLI_AULA_ID
    assert imp["fazenda"]["seugado_id"] == FAZENDA_AULA_ID
    assert imp["piquetes_importados"] == 3
    assert imp["lotes_importados"] == 1

    fid = imp["fazenda"]["id"]
    pqs = cliente(ctx).get(f"/fazendas/{fid}/piquetes").json()
    assert len(pqs) == 3
    assert {p["externo_id"] for p in pqs} == {PQ7_ID, PQ8_ID, PQ9_ID}

    lotes = cliente(ctx).get(f"/fazendas/{fid}/lotes").json()
    assert len(lotes) == 1
    recria = lotes[0]
    assert recria["nome"] == "Recria"
    assert recria["seugado_id"] == LOTE_RECRIA_ID
    # 10 novilhos + 2 touros = 12 bois; 5 novilhas = 5 vacas; 3 bezerras = 3 bezerros
    assert (recria["bois"], recria["vacas"], recria["bezerros"]) == (12, 5, 3)

    lotacao = cliente(ctx).get(f"/fazendas/{fid}/lotacao").json()
    assert len(lotacao) == 1 and lotacao[0]["bois"] == 12


@given("uma fazenda já importada do PiqueTech com 3 piquetes")
def fazenda_ja_importada(ctx):
    piquetech_mock(ctx)
    importar_aula(ctx)
    fid = ctx["importacao"]["fazenda"]["id"]
    lote_id = cliente(ctx).get(f"/fazendas/{fid}/lotes").json()[0]["id"]
    r = cliente(ctx).post(f"/fazendas/{fid}/coleiras", json={"lote_id": lote_id, "categoria": "boi", "quantidade": 3})
    assert r.status_code == 201, r.text


@when("o PiqueTech remove um piquete e o admin atualiza a fazenda")
def atualizar_com_piquete_removido(ctx):
    ctx["pt_estado"]["piquetes"][FAZENDA_AULA_ID] = [
        p for p in ctx["pt_estado"]["piquetes"][FAZENDA_AULA_ID] if p["id"] != PQ8_ID
    ]
    ctx["pt_estado"]["piquetes"][FAZENDA_AULA_ID][0]["nome"] = "Piquete 7 Renomeado"
    fid = ctx["importacao"]["fazenda"]["id"]
    r = cliente(ctx).post(f"/fazendas/{fid}/integracao/piquetech/atualizar")
    assert r.status_code == 200, r.text
    ctx["atualizacao"] = r.json()


@then("o piquete removido fica inativo e os demais são atualizados")
def conferir_inativacao(ctx):
    assert ctx["atualizacao"]["piquetes_inativados"] == 1
    fid = ctx["importacao"]["fazenda"]["id"]
    ativos = cliente(ctx).get(f"/fazendas/{fid}/piquetes").json()
    assert len(ativos) == 2
    assert any(p["nome"] == "Piquete 7 Renomeado" for p in ativos)
    # piquete removido continua no repositório como ativo=False (preserva histórico)
    todos = sistema(ctx).piquetes(fid, incluir_inativos=True)
    inativo = next(p for p in todos if p.externo_id == PQ8_ID)
    assert inativo.ativo is False
    # coleiras seguem intactas
    assert len(cliente(ctx).get(f"/fazendas/{fid}/coleiras").json()) == 3


@when("o admin exporta a fazenda de demonstração para o PiqueTech usando a cultivar Marandu")
def exportar_demo(ctx):
    r = cliente(ctx).post(
        "/fazendas/faz-marcinho/integracao/piquetech/exportar",
        json={"cultivar_id": CULTIVAR_MARANDU_ID, "metodo_pastejo": "rotacionado"},
    )
    assert r.status_code == 200, r.text
    ctx["exportacao"] = r.json()


@then("o PiqueTech recebe cliente, fazenda, piquetes e lotes e o Maneja guarda todos os UUIDs")
def conferir_exportacao(ctx):
    criados = ctx["pt_estado"]["criados"]
    exp = ctx["exportacao"]
    assert len(criados["clientes"]) == 1
    assert len(criados["fazendas"]) == 1
    assert len(criados["piquetes"]) == 5
    assert len(criados["lotes"]) == 2
    assert exp["cliente"]["seugado_id"] == criados["clientes"][0]["id"]
    assert exp["fazenda"]["seugado_id"] == criados["fazendas"][0]["id"]
    assert exp["piquetes_exportados"] == 5
    assert exp["lotes_exportados"] == 2
    # categorias convertidas para o padrão do PiqueTech
    cats = {item["categoria"] for lote in criados["lotes"] for item in lote["composicao"]}
    assert cats == {"boi", "vaca", "bezerro"}
    # todos os piquetes e lotes do Maneja têm UUID do PiqueTech gravado
    pqs = sistema(ctx).piquetes("faz-marcinho")
    assert {p.externo_id for p in pqs} == {p["id"] for p in criados["piquetes"]}
    lotes = sistema(ctx).lotes("faz-marcinho")
    assert {l.seugado_id for l in lotes} == {l["id"] for l in criados["lotes"]}


@given("duas fazendas integradas ao PiqueTech com coleiras nos lotes")
def duas_fazendas_integradas(ctx):
    piquetech_mock(ctx)
    # adiciona segunda fazenda no PiqueTech
    pq_e1 = "88888888-0000-4000-8000-000000000001"
    pq_e2 = "88888888-0000-4000-8000-000000000002"
    lote_e = "88888888-0000-4000-8000-000000000099"
    ctx["pt_estado"]["fazendas"][FAZENDA_EXTRA_ID] = {
        "id": FAZENDA_EXTRA_ID,
        "cliente_id": CLI_AULA_ID,
        "cliente_nome": "Prof. Rafael",
        "nome": "Fazenda Extra",
        "timezone": "America/Maceio",
    }
    ctx["pt_estado"]["piquetes"][FAZENDA_EXTRA_ID] = [
        {"id": pq_e1, "nome": "Piquete E1", "geometria": _poly(800), "area_ha": 2.25, "cultivar_nome": "Marandu"},
        {"id": pq_e2, "nome": "Piquete E2", "geometria": _poly(1000), "area_ha": 2.25, "cultivar_nome": "Marandu"},
    ]
    ctx["pt_estado"]["lotes"][FAZENDA_EXTRA_ID] = [
        {"id": lote_e, "nome": "Engorda", "piquete_atual_id": pq_e1, "desde": "2026-11-10", "composicao": [{"categoria": "boi", "n_animais": 20}]},
    ]
    ctx["pt_estado"]["planos"][FAZENDA_EXTRA_ID] = {
        "id": "plano-extra-1",
        "movimentacoes": [{
            "id": MOV_EXTRA_ID, "data": "2026-11-19", "lote_id": lote_e, "lote_nome": "Engorda",
            "piquete_origem_id": pq_e1, "piquete_origem_nome": "Piquete E1",
            "piquete_destino_id": pq_e2, "piquete_destino_nome": "Piquete E2", "motivo": "Rotação",
        }],
    }

    # importa as duas fazendas
    f_aula = cliente(ctx).post(f"/integracao/piquetech/importar/{FAZENDA_AULA_ID}").json()["fazenda"]
    f_extra = cliente(ctx).post(f"/integracao/piquetech/importar/{FAZENDA_EXTRA_ID}").json()["fazenda"]
    ctx["faz_aula_id"] = f_aula["id"]
    ctx["faz_extra_id"] = f_extra["id"]

    # verifica ANTES de associar coleiras (regressão: grupo vazio não pode congelar!)
    v_antes = cliente(ctx).get(f"/fazendas/{f_aula['id']}/verificacoes").json()["verificacoes"]
    assert v_antes[0]["status"] == "sem_dados"

    # associa 3 coleiras ao lote Recria e 3 ao lote Engorda
    lote_aula = cliente(ctx).get(f"/fazendas/{f_aula['id']}/lotes").json()[0]["id"]
    lote_extra = cliente(ctx).get(f"/fazendas/{f_extra['id']}/lotes").json()[0]["id"]
    assert cliente(ctx).post(f"/fazendas/{f_aula['id']}/coleiras", json={"lote_id": lote_aula, "quantidade": 3}).status_code == 201
    assert cliente(ctx).post(f"/fazendas/{f_extra['id']}/coleiras", json={"lote_id": lote_extra, "quantidade": 3}).status_code == 201


@when("o gado da Fazenda Aula é levado ao destino no campo")
def mover_aula(ctx):
    fid = ctx["faz_aula_id"]
    pqs = cliente(ctx).get(f"/fazendas/{fid}/piquetes").json()
    pq9 = next(p["id"] for p in pqs if p["externo_id"] == PQ9_ID)
    r = cliente(ctx).post(f"/fazendas/{fid}/simulador/executar/seugado-{MOV_AULA_ID}", json={"piquete_id": pq9})
    assert r.status_code == 200, r.text


@when(parsers.parse('o PiqueTech consulta "{caminho}"'))
def piquetech_consulta_execucoes(ctx, caminho):
    ctx["resposta"] = cliente_anonimo(ctx).get(caminho, headers={"Authorization": "Bearer token-do-seugado"})


@then('a movimentação da Fazenda Aula aparece como "cumprida" junto com a outra fazenda')
def conferir_execucoes_multi_fazenda(ctx):
    assert ctx["resposta"].status_code == 200, ctx["resposta"].text
    itens = {i["movimentacao_externa_id"]: i for i in ctx["resposta"].json()}
    assert set(itens) == {MOV_AULA_ID, MOV_EXTRA_ID}
    assert itens[MOV_AULA_ID]["status"] == "cumprida"
    assert itens[MOV_AULA_ID]["fracao_no_destino"] == 1.0
    assert itens[MOV_AULA_ID]["coleiras_consideradas"] == 3
    assert itens[MOV_AULA_ID]["piquete_destino_externo_id"] == PQ9_ID
    assert itens[MOV_EXTRA_ID]["status"] == "pendente"


def test_cliente_nao_pode_usar_rotas_piquetech_e_desligado_nao_quebra(ctx):
    # com PiqueTech desligado, listar fazendas devolve 422 claro sem quebrar o sistema
    assert cliente(ctx).get("/integracao/piquetech/fazendas").status_code == 422
    assert cliente(ctx).get("/integracao/v1/execucoes?desde=2026-01-01").json() == []

    # cliente comum recebe 403 nas rotas de integração PiqueTech
    cli = cliente(ctx).post("/clientes", json={"nome": "Cliente Comum"}).json()
    cliente(ctx).post(
        "/usuarios",
        json={"email": "comum@maneja.test", "senha": "senha", "papel": "cliente", "cliente_id": cli["id"]},
    )
    tok = cliente_anonimo(ctx).post("/auth/token", json={"email": "comum@maneja.test", "senha": "senha"}).json()["access_token"]
    assert cliente_anonimo(ctx).get("/integracao/piquetech/fazendas", headers={"Authorization": f"Bearer {tok}"}).status_code == 403
