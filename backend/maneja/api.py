"""API REST do Maneja (SPEC-004, SPEC-009, SPEC-017 e SPEC-018).

O JSON usa os mesmos nomes de src/lib/tipos.ts.
Toda rota de fazenda verifica autorização no back-end: admin acessa tudo;
cliente acessa apenas fazendas cujo cliente_id é o dele.
"""

from __future__ import annotations

import secrets
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Body, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .autenticacao import ConfigAuth, SessaoUsuario, TokenInvalido, emitir_token, validar_sessao
from .config import Config, auth_do_ambiente, montar_sistema
from .dominio import ColeiraDesconhecida, Fazenda, Posicao, RegraViolada, Usuario
from .servico import Conflito, Sistema

Quantidade = Annotated[int, Field(ge=0, strict=True)]


class LoginIn(BaseModel):
    email: str
    senha: str


class ClienteIn(BaseModel):
    nome: str
    contato: str = ""


class ClienteEdicaoIn(BaseModel):
    nome: str | None = None
    contato: str | None = None


class FazendaIn(BaseModel):
    nome: str
    timezone: str | None = None
    cliente_id: str | None = None


class FazendaCriarIn(BaseModel):
    nome: str
    cliente_id: str | None = None
    timezone: str = "America/Maceio"


class UsuarioCriarIn(BaseModel):
    email: str
    senha: str
    papel: str = "cliente"
    cliente_id: str | None = None
    nome: str = ""


class UsuarioEdicaoIn(BaseModel):
    nome: str | None = None
    email: str | None = None
    senha: str | None = None
    papel: str | None = None
    cliente_id: str | None = None


class PiqueteIn(BaseModel):
    nome: str
    vegetacao: str = ""
    geometria: dict
    externo_id: str | None = None


class PiqueteEdicaoIn(BaseModel):
    nome: str | None = None
    vegetacao: str | None = None
    geometria: dict | None = None


class LotacaoIn(BaseModel):
    bois: Quantidade = 0
    vacas: Quantidade = 0
    bezerros: Quantidade = 0


class ColeiraCriarIn(BaseModel):
    piquete_id: str | None = None
    lote_id: str | None = None
    categoria: str = "boi"
    quantidade: int = Field(default=1, ge=1, le=50)


class AceiteIn(BaseModel):
    destino_id: str | None = None


class AvancoIn(BaseModel):
    horas: float = Field(gt=0, le=24 * 30)


class ExecucaoIn(BaseModel):
    piquete_id: str | None = None


class PosicaoIn(BaseModel):
    coleira_id: str
    instante: datetime
    lat: float
    lon: float


class ExportarPiqueTechIn(BaseModel):
    cultivar_id: str | None = None
    metodo_pastejo: str = "rotacionado"


def agora_real() -> datetime:
    return datetime.now(timezone.utc)


def _usuario_publico(u: Usuario) -> dict[str, Any]:
    return {
        "id": u.id,
        "email": u.email,
        "nome": u.nome,
        "papel": u.papel,
        "cliente_id": u.cliente_id,
    }


_sistema_da_requisicao: ContextVar[Sistema | None] = ContextVar("sistema_da_requisicao", default=None)


def criar_app(
    sistema: Sistema | None = None,
    auth: ConfigAuth | None = None,
    relogio=agora_real,
    config: Config | None = None,
) -> FastAPI:
    """`relogio` é a hora real usada nos tokens (o relógio do simulador não expira sessões).

    Modo sem estado (Vercel, SPEC-013): cada requisição monta o Sistema a partir do banco,
    e as operações que mudam dados gravam de volta antes de responder.
    """
    config = config or Config.do_ambiente()
    sem_estado = sistema is None and config.sem_estado
    if sem_estado and not config.database_url:
        raise RuntimeError("MANEJA_SEM_ESTADO exige DATABASE_URL")
    app = FastAPI(title="Maneja", version="0.4.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.cors_origens),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.sistema = None if sem_estado else (sistema or montar_sistema(config))
    app.state.auth = auth or auth_do_ambiente()

    if sem_estado:
        @app.middleware("http")
        async def sistema_por_requisicao(request: Request, call_next):
            if request.method == "OPTIONS":
                return await call_next(request)
            marca = _sistema_da_requisicao.set(await run_in_threadpool(montar_sistema, config))
            try:
                return await call_next(request)
            finally:
                _sistema_da_requisicao.reset(marca)

    def s() -> Sistema:
        return _sistema_da_requisicao.get() or app.state.sistema

    def executar(acao):
        try:
            return jsonable_encoder(acao())
        except HTTPException:
            raise
        except RegraViolada as e:
            raise HTTPException(status_code=422, detail=e.motivos) from e
        except ColeiraDesconhecida as e:
            raise HTTPException(status_code=422, detail=[str(e)]) from e
        except Conflito as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=f"não encontrado: {e.args[0]}") from e
        except httpx.HTTPStatusError as e:
            detalhe = e.response.text[:300] if e.response is not None else str(e)
            raise HTTPException(
                status_code=502,
                detail=f"erro do PiqueTech (HTTP {e.response.status_code}): {detalhe}",
            ) from e
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"não foi possível falar com o PiqueTech: {e}") from e

    # ---------- autenticação e autorização (SPEC-009 e SPEC-017) ----------

    def nao_autorizado(motivo: str) -> HTTPException:
        return HTTPException(status_code=401, detail=motivo, headers={"WWW-Authenticate": "Bearer"})

    def acesso_negado(motivo: str = "sem permissão para acessar este recurso") -> HTTPException:
        return HTTPException(status_code=403, detail=motivo)

    def token_do_cabecalho(authorization: str | None) -> str:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise nao_autorizado("faça login para continuar")
        return authorization.split(" ", 1)[1].strip()

    def exigir_sessao(authorization: str | None = Header(default=None)) -> SessaoUsuario:
        token = token_do_cabecalho(authorization)
        try:
            sessao_jwt = validar_sessao(token, app.state.auth.segredo, relogio())
        except TokenInvalido as e:
            raise nao_autorizado(f"sessão inválida: {e}") from e
        sessao = s().resolver_sessao(sessao_jwt, app.state.auth)
        if sessao is None:
            raise nao_autorizado("usuário não encontrado")
        return sessao

    def exigir_admin(sessao: SessaoUsuario = Depends(exigir_sessao)) -> SessaoUsuario:
        if sessao.papel != "admin":
            raise acesso_negado("acesso restrito a administradores")
        return sessao

    def exigir_usuario_ou_integracao(authorization: str | None = Header(default=None)) -> str:
        token = token_do_cabecalho(authorization)
        fixo = app.state.auth.token_integracao
        if fixo and secrets.compare_digest(token, fixo):
            return "integracao"
        return exigir_sessao(authorization).email

    def verificar_acesso_fazenda(fazenda_id: str, sessao: SessaoUsuario) -> Fazenda:
        try:
            faz = s().fazenda(fazenda_id)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=f"fazenda não encontrada: {fazenda_id}") from e
        if sessao.papel != "admin" and faz.cliente_id != sessao.cliente_id:
            raise acesso_negado("você não tem acesso a esta fazenda")
        return faz

    def resolver_fazenda(sessao: SessaoUsuario, fazenda_id: str | None = None) -> Fazenda:
        if fazenda_id is not None:
            return verificar_acesso_fazenda(fazenda_id, sessao)
        if sessao.papel == "admin":
            return s().fazenda()
        do_cliente = s().listar_fazendas(cliente_id=sessao.cliente_id)
        if not do_cliente:
            raise HTTPException(status_code=404, detail="nenhuma fazenda vinculada à sua conta")
        return do_cliente[0]

    def verificar_dono_piquete(piquete_id: str, sessao: SessaoUsuario) -> str:
        try:
            fid = s().dono_piquete(piquete_id)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=f"não encontrado: {piquete_id}") from e
        verificar_acesso_fazenda(fid, sessao)
        return fid

    def verificar_dono_movimentacao(mov_id: str, sessao: SessaoUsuario) -> str:
        try:
            fid = s().dono_movimentacao(mov_id)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=f"não encontrado: {mov_id}") from e
        verificar_acesso_fazenda(fid, sessao)
        return fid

    r = APIRouter(dependencies=[Depends(exigir_sessao)])
    admin = APIRouter(dependencies=[Depends(exigir_admin)])
    integracao = APIRouter(dependencies=[Depends(exigir_usuario_ou_integracao)])

    # ---------- saúde e login ----------

    @app.get("/saude")
    def saude() -> dict[str, Any]:
        llm = s().llm
        llm_info = None
        if llm is not None:
            interno = getattr(llm, "_llm", llm)
            modelos = getattr(interno, "modelos", None)
            llm_info = {
                "modelos": list(modelos) if modelos else [getattr(interno, "modelo", "desconhecido")],
                "cota_usada": getattr(llm, "usado", None),
                "cota_limite": getattr(llm, "limite", None),
            }
        return {
            "status": "ok",
            "modo_seugado": s().seugado.modo,
            "agora": s().agora().isoformat(),
            "banco": "postgresql" if config.database_url else "memoria",
            "sem_estado": sem_estado,
            "llm": llm_info,
        }

    @app.post("/auth/token")
    def login(corpo: LoginIn) -> dict[str, Any]:
        cfg = app.state.auth
        sessao = s().autenticar_usuario(corpo.email, corpo.senha, cfg)
        if sessao is None:
            raise nao_autorizado("e-mail ou senha incorretos")
        token, expira = emitir_token(
            sessao.email,
            cfg.segredo,
            relogio(),
            papel=sessao.papel,
            cliente_id=sessao.cliente_id,
            usuario_id=sessao.id,
            nome=sessao.nome,
        )
        return {
            "access_token": token,
            "token_type": "bearer",
            "expira_em": expira.isoformat(),
            "id": sessao.id,
            "email": sessao.email,
            "nome": sessao.nome,
            "papel": sessao.papel,
            "cliente_id": sessao.cliente_id,
        }

    @r.get("/me")
    def eu(sessao: SessaoUsuario = Depends(exigir_sessao)) -> dict[str, Any]:
        return {
            "id": sessao.id,
            "email": sessao.email,
            "nome": sessao.nome,
            "papel": sessao.papel,
            "cliente_id": sessao.cliente_id,
        }

    # ---------- administração (SPEC-017: somente admin) ----------

    @admin.get("/clientes")
    def listar_clientes():
        return jsonable_encoder(s().listar_clientes())

    @admin.post("/clientes", status_code=201)
    def criar_cliente(corpo: ClienteIn):
        return executar(lambda: s().criar_cliente(corpo.nome, corpo.contato))

    @admin.put("/clientes/{cliente_id}")
    def atualizar_cliente(cliente_id: str, corpo: ClienteEdicaoIn):
        return executar(lambda: s().atualizar_cliente(cliente_id, corpo.nome, corpo.contato))

    @admin.get("/usuarios")
    def listar_usuarios():
        return [_usuario_publico(u) for u in s().listar_usuarios()]

    @admin.post("/usuarios", status_code=201)
    def criar_usuario(corpo: UsuarioCriarIn):
        return executar(lambda: _usuario_publico(s().criar_usuario(
            corpo.email, corpo.senha, corpo.papel, corpo.cliente_id, corpo.nome,
            email_admin_env=app.state.auth.email,
        )))

    @admin.put("/usuarios/{usuario_id}")
    def atualizar_usuario(usuario_id: str, corpo: UsuarioEdicaoIn):
        campos = corpo.model_fields_set
        kwargs: dict[str, Any] = {"email_admin_env": app.state.auth.email}
        if "nome" in campos:
            kwargs["nome"] = corpo.nome
        if "email" in campos:
            kwargs["email"] = corpo.email
        if "senha" in campos:
            kwargs["senha"] = corpo.senha
        if "papel" in campos:
            kwargs["papel"] = corpo.papel
        if "cliente_id" in campos:
            kwargs["cliente_id"] = corpo.cliente_id
        return executar(lambda: _usuario_publico(s().atualizar_usuario(usuario_id, **kwargs)))

    @admin.post("/fazendas", status_code=201)
    def criar_fazenda(corpo: FazendaCriarIn):
        return executar(lambda: s().criar_fazenda(corpo.nome, corpo.cliente_id, corpo.timezone))

    # ---------- fazendas acessíveis pelo usuário ----------

    @r.get("/fazendas")
    def listar_fazendas(sessao: SessaoUsuario = Depends(exigir_sessao)):
        if sessao.papel == "admin":
            return jsonable_encoder(s().listar_fazendas())
        return jsonable_encoder(s().listar_fazendas(cliente_id=sessao.cliente_id))

    @r.get("/fazendas/{fazenda_id}")
    def obter_fazenda(fazenda_id: str, sessao: SessaoUsuario = Depends(exigir_sessao)):
        return jsonable_encoder(verificar_acesso_fazenda(fazenda_id, sessao))

    @r.put("/fazendas/{fazenda_id}")
    def editar_fazenda(fazenda_id: str, corpo: FazendaIn, sessao: SessaoUsuario = Depends(exigir_sessao)):
        verificar_acesso_fazenda(fazenda_id, sessao)
        kwargs: dict[str, Any] = {"nome": corpo.nome, "fazenda_id": fazenda_id, "timezone_nome": corpo.timezone}
        if sessao.papel == "admin" and "cliente_id" in corpo.model_fields_set:
            kwargs["cliente_id"] = corpo.cliente_id
        return executar(lambda: s().atualizar_fazenda(**kwargs))

    @r.get("/fazendas/{fazenda_id}/piquetes")
    def piquetes_da_fazenda(fazenda_id: str, sessao: SessaoUsuario = Depends(exigir_sessao)):
        verificar_acesso_fazenda(fazenda_id, sessao)
        return jsonable_encoder(s().piquetes(fazenda_id))

    @r.post("/fazendas/{fazenda_id}/piquetes", status_code=201)
    def criar_piquete_na_fazenda(fazenda_id: str, corpo: PiqueteIn, sessao: SessaoUsuario = Depends(exigir_sessao)):
        verificar_acesso_fazenda(fazenda_id, sessao)
        return executar(lambda: s().criar_piquete(
            corpo.nome, corpo.vegetacao, corpo.geometria, corpo.externo_id, fazenda_id=fazenda_id,
        ))

    @r.put("/fazendas/{fazenda_id}/piquetes/{piquete_id}")
    def atualizar_piquete_na_fazenda(
        fazenda_id: str, piquete_id: str, corpo: PiqueteEdicaoIn, sessao: SessaoUsuario = Depends(exigir_sessao),
    ):
        verificar_acesso_fazenda(fazenda_id, sessao)
        if verificar_dono_piquete(piquete_id, sessao) != fazenda_id:
            raise HTTPException(status_code=404, detail=f"não encontrado: {piquete_id}")
        return executar(lambda: s().atualizar_piquete(piquete_id, corpo.nome, corpo.vegetacao, corpo.geometria))

    @r.delete("/fazendas/{fazenda_id}/piquetes/{piquete_id}", status_code=204)
    def remover_piquete_na_fazenda(fazenda_id: str, piquete_id: str, sessao: SessaoUsuario = Depends(exigir_sessao)):
        verificar_acesso_fazenda(fazenda_id, sessao)
        if verificar_dono_piquete(piquete_id, sessao) != fazenda_id:
            raise HTTPException(status_code=404, detail=f"não encontrado: {piquete_id}")
        executar(lambda: s().remover_piquete(piquete_id))

    @r.get("/fazendas/{fazenda_id}/lotes")
    def lotes_da_fazenda(fazenda_id: str, sessao: SessaoUsuario = Depends(exigir_sessao)):
        verificar_acesso_fazenda(fazenda_id, sessao)
        return jsonable_encoder(s().lotes(fazenda_id))

    @r.get("/fazendas/{fazenda_id}/lotacao")
    def lotacao_da_fazenda(fazenda_id: str, sessao: SessaoUsuario = Depends(exigir_sessao)):
        verificar_acesso_fazenda(fazenda_id, sessao)
        return jsonable_encoder(s().lotacoes(fazenda_id))

    @r.put("/fazendas/{fazenda_id}/lotacao/{piquete_id}")
    def atualizar_lotacao_na_fazenda(
        fazenda_id: str, piquete_id: str, corpo: LotacaoIn, sessao: SessaoUsuario = Depends(exigir_sessao),
    ):
        verificar_acesso_fazenda(fazenda_id, sessao)
        if verificar_dono_piquete(piquete_id, sessao) != fazenda_id:
            raise HTTPException(status_code=404, detail=f"não encontrado: {piquete_id}")
        return executar(lambda: s().atualizar_lotacao(piquete_id, corpo.bois, corpo.vacas, corpo.bezerros))

    @r.get("/fazendas/{fazenda_id}/ndvi")
    def ndvi_da_fazenda(fazenda_id: str, piquete_id: str | None = None, sessao: SessaoUsuario = Depends(exigir_sessao)):
        verificar_acesso_fazenda(fazenda_id, sessao)
        if piquete_id is not None and verificar_dono_piquete(piquete_id, sessao) != fazenda_id:
            raise acesso_negado("piquete não pertence a esta fazenda")
        return jsonable_encoder(s().leituras_ndvi(fazenda_id, piquete_id))

    @r.post("/fazendas/{fazenda_id}/ndvi/atualizar")
    def atualizar_ndvi_da_fazenda(fazenda_id: str, sessao: SessaoUsuario = Depends(exigir_sessao)):
        verificar_acesso_fazenda(fazenda_id, sessao)
        return executar(lambda: s().atualizar_ndvi(fazenda_id))

    @r.get("/fazendas/{fazenda_id}/clima")
    def clima_da_fazenda(fazenda_id: str, sessao: SessaoUsuario = Depends(exigir_sessao)):
        verificar_acesso_fazenda(fazenda_id, sessao)
        return jsonable_encoder(s().previsao(fazenda_id))

    @r.get("/fazendas/{fazenda_id}/resumo")
    def resumo_da_fazenda(fazenda_id: str, sessao: SessaoUsuario = Depends(exigir_sessao)):
        verificar_acesso_fazenda(fazenda_id, sessao)
        return jsonable_encoder(s().resumo(fazenda_id))

    @r.post("/fazendas/{fazenda_id}/plano")
    def gerar_plano_da_fazenda(fazenda_id: str, sessao: SessaoUsuario = Depends(exigir_sessao)):
        verificar_acesso_fazenda(fazenda_id, sessao)
        return executar(lambda: s().gerar_plano(fazenda_id))

    @r.get("/fazendas/{fazenda_id}/plano")
    def plano_atual_da_fazenda(fazenda_id: str, sessao: SessaoUsuario = Depends(exigir_sessao)):
        verificar_acesso_fazenda(fazenda_id, sessao)
        plano = s().plano_atual(fazenda_id)
        if plano is None:
            raise HTTPException(status_code=404, detail="ainda não há plano")
        return jsonable_encoder(plano)

    @r.post("/fazendas/{fazenda_id}/movimentacoes/{mov_id}/aceitar")
    def aceitar_na_fazenda(
        fazenda_id: str, mov_id: str, corpo: AceiteIn | None = Body(default=None),
        sessao: SessaoUsuario = Depends(exigir_sessao),
    ):
        verificar_acesso_fazenda(fazenda_id, sessao)
        destino = corpo.destino_id if corpo else None
        return executar(lambda: s().aceitar(mov_id, destino, fazenda_id=fazenda_id))

    @r.post("/fazendas/{fazenda_id}/movimentacoes/{mov_id}/recusar")
    def recusar_na_fazenda(fazenda_id: str, mov_id: str, sessao: SessaoUsuario = Depends(exigir_sessao)):
        verificar_acesso_fazenda(fazenda_id, sessao)
        return executar(lambda: s().recusar(mov_id, fazenda_id=fazenda_id))

    @r.get("/fazendas/{fazenda_id}/historico")
    def historico_da_fazenda(fazenda_id: str, sessao: SessaoUsuario = Depends(exigir_sessao)):
        verificar_acesso_fazenda(fazenda_id, sessao)
        return jsonable_encoder(s().historico(fazenda_id))

    @r.get("/fazendas/{fazenda_id}/coleiras")
    def coleiras_da_fazenda(fazenda_id: str, sessao: SessaoUsuario = Depends(exigir_sessao)):
        verificar_acesso_fazenda(fazenda_id, sessao)
        return jsonable_encoder(s().coleiras(fazenda_id))

    @r.post("/fazendas/{fazenda_id}/coleiras", status_code=201)
    def criar_coleiras_na_fazenda(
        fazenda_id: str, corpo: ColeiraCriarIn, sessao: SessaoUsuario = Depends(exigir_sessao),
    ):
        verificar_acesso_fazenda(fazenda_id, sessao)
        return executar(lambda: s().criar_coleiras(
            fazenda_id, piquete_id=corpo.piquete_id, lote_id=corpo.lote_id,
            categoria=corpo.categoria, quantidade=corpo.quantidade,
        ))

    @r.delete("/fazendas/{fazenda_id}/coleiras/{coleira_id}", status_code=204)
    def remover_coleira_na_fazenda(
        fazenda_id: str, coleira_id: str, sessao: SessaoUsuario = Depends(exigir_sessao),
    ):
        verificar_acesso_fazenda(fazenda_id, sessao)
        executar(lambda: s().remover_coleira(coleira_id, fazenda_id=fazenda_id))

    @r.post("/fazendas/{fazenda_id}/coleiras/posicoes")
    def registrar_posicoes_na_fazenda(
        fazenda_id: str, corpo: list[PosicaoIn], sessao: SessaoUsuario = Depends(exigir_sessao),
    ):
        verificar_acesso_fazenda(fazenda_id, sessao)
        return executar(lambda: {"registradas": s().registrar_posicoes(
            [Posicao(p.coleira_id, p.instante, p.lat, p.lon) for p in corpo], fazenda_id=fazenda_id,
        )})

    @r.get("/fazendas/{fazenda_id}/ocupacao")
    def ocupacao_da_fazenda(fazenda_id: str, sessao: SessaoUsuario = Depends(exigir_sessao)):
        verificar_acesso_fazenda(fazenda_id, sessao)
        return jsonable_encoder(s().ocupacao(fazenda_id))

    @r.get("/fazendas/{fazenda_id}/verificacoes")
    def verificacoes_da_fazenda(fazenda_id: str, sessao: SessaoUsuario = Depends(exigir_sessao)):
        verificar_acesso_fazenda(fazenda_id, sessao)
        lista, avisos = s().verificacoes(fazenda_id)
        return jsonable_encoder({"verificacoes": lista, "avisos": avisos})

    @r.post("/fazendas/{fazenda_id}/simulador/avancar")
    def avancar_na_fazenda(fazenda_id: str, corpo: AvancoIn, sessao: SessaoUsuario = Depends(exigir_sessao)):
        verificar_acesso_fazenda(fazenda_id, sessao)
        return executar(lambda: {"posicoes_geradas": s().simulador_avancar(corpo.horas, fazenda_id), "agora": s().agora()})

    @r.post("/fazendas/{fazenda_id}/simulador/executar/{mov_id}")
    def executar_no_campo_da_fazenda(
        fazenda_id: str, mov_id: str, corpo: ExecucaoIn | None = Body(default=None),
        sessao: SessaoUsuario = Depends(exigir_sessao),
    ):
        verificar_acesso_fazenda(fazenda_id, sessao)
        destino = corpo.piquete_id if corpo else None
        return executar(lambda: s().simulador_executar(mov_id, destino, fazenda_id=fazenda_id) or {"ok": True})

    # ---------- atalhos de fazenda única (compatibilidade + checagem de acesso) ----------

    @r.get("/fazenda")
    def fazenda(fazenda_id: str | None = None, sessao: SessaoUsuario = Depends(exigir_sessao)):
        return jsonable_encoder(resolver_fazenda(sessao, fazenda_id))

    @r.put("/fazenda")
    def atualizar_fazenda(corpo: FazendaIn, fazenda_id: str | None = None, sessao: SessaoUsuario = Depends(exigir_sessao)):
        faz = resolver_fazenda(sessao, fazenda_id)
        return executar(lambda: s().atualizar_fazenda(corpo.nome, fazenda_id=faz.id, timezone_nome=corpo.timezone))

    @r.get("/piquetes")
    def piquetes(fazenda_id: str | None = None, sessao: SessaoUsuario = Depends(exigir_sessao)):
        faz = resolver_fazenda(sessao, fazenda_id)
        return jsonable_encoder(s().piquetes(faz.id))

    @r.post("/piquetes", status_code=201)
    def criar_piquete(corpo: PiqueteIn, fazenda_id: str | None = None, sessao: SessaoUsuario = Depends(exigir_sessao)):
        faz = resolver_fazenda(sessao, fazenda_id)
        return executar(lambda: s().criar_piquete(
            corpo.nome, corpo.vegetacao, corpo.geometria, corpo.externo_id, fazenda_id=faz.id,
        ))

    @r.put("/piquetes/{piquete_id}")
    def atualizar_piquete(piquete_id: str, corpo: PiqueteEdicaoIn, sessao: SessaoUsuario = Depends(exigir_sessao)):
        verificar_dono_piquete(piquete_id, sessao)
        return executar(lambda: s().atualizar_piquete(piquete_id, corpo.nome, corpo.vegetacao, corpo.geometria))

    @r.delete("/piquetes/{piquete_id}", status_code=204)
    def remover_piquete(piquete_id: str, sessao: SessaoUsuario = Depends(exigir_sessao)):
        verificar_dono_piquete(piquete_id, sessao)
        executar(lambda: s().remover_piquete(piquete_id))

    @r.get("/lotacao")
    def lotacao(fazenda_id: str | None = None, sessao: SessaoUsuario = Depends(exigir_sessao)):
        faz = resolver_fazenda(sessao, fazenda_id)
        return jsonable_encoder(s().lotacoes(faz.id))

    @r.put("/lotacao/{piquete_id}")
    def atualizar_lotacao(piquete_id: str, corpo: LotacaoIn, sessao: SessaoUsuario = Depends(exigir_sessao)):
        verificar_dono_piquete(piquete_id, sessao)
        return executar(lambda: s().atualizar_lotacao(piquete_id, corpo.bois, corpo.vacas, corpo.bezerros))

    @r.get("/ndvi")
    def ndvi(piquete_id: str | None = None, fazenda_id: str | None = None, sessao: SessaoUsuario = Depends(exigir_sessao)):
        if piquete_id is not None:
            fid = verificar_dono_piquete(piquete_id, sessao)
            return jsonable_encoder(s().leituras_ndvi(fid, piquete_id))
        faz = resolver_fazenda(sessao, fazenda_id)
        return jsonable_encoder(s().leituras_ndvi(faz.id))

    @r.post("/ndvi/atualizar")
    def atualizar_ndvi(fazenda_id: str | None = None, sessao: SessaoUsuario = Depends(exigir_sessao)):
        faz = resolver_fazenda(sessao, fazenda_id)
        return executar(lambda: s().atualizar_ndvi(faz.id))

    @r.get("/clima")
    def clima(fazenda_id: str | None = None, sessao: SessaoUsuario = Depends(exigir_sessao)):
        faz = resolver_fazenda(sessao, fazenda_id)
        return jsonable_encoder(s().previsao(faz.id))

    @r.get("/resumo")
    def resumo(fazenda_id: str | None = None, sessao: SessaoUsuario = Depends(exigir_sessao)):
        faz = resolver_fazenda(sessao, fazenda_id)
        return jsonable_encoder(s().resumo(faz.id))

    @r.post("/plano")
    def gerar_plano(fazenda_id: str | None = None, sessao: SessaoUsuario = Depends(exigir_sessao)):
        faz = resolver_fazenda(sessao, fazenda_id)
        return executar(lambda: s().gerar_plano(faz.id))

    @r.get("/plano")
    def plano_atual(fazenda_id: str | None = None, sessao: SessaoUsuario = Depends(exigir_sessao)):
        faz = resolver_fazenda(sessao, fazenda_id)
        plano = s().plano_atual(faz.id)
        if plano is None:
            raise HTTPException(status_code=404, detail="ainda não há plano")
        return jsonable_encoder(plano)

    @r.post("/movimentacoes/{mov_id}/aceitar")
    def aceitar(mov_id: str, corpo: AceiteIn | None = Body(default=None), sessao: SessaoUsuario = Depends(exigir_sessao)):
        fid = verificar_dono_movimentacao(mov_id, sessao)
        destino = corpo.destino_id if corpo else None
        return executar(lambda: s().aceitar(mov_id, destino, fazenda_id=fid))

    @r.post("/movimentacoes/{mov_id}/recusar")
    def recusar(mov_id: str, sessao: SessaoUsuario = Depends(exigir_sessao)):
        fid = verificar_dono_movimentacao(mov_id, sessao)
        return executar(lambda: s().recusar(mov_id, fazenda_id=fid))

    @r.get("/historico")
    def historico(fazenda_id: str | None = None, sessao: SessaoUsuario = Depends(exigir_sessao)):
        faz = resolver_fazenda(sessao, fazenda_id)
        return jsonable_encoder(s().historico(faz.id))

    @r.get("/coleiras")
    def coleiras(fazenda_id: str | None = None, sessao: SessaoUsuario = Depends(exigir_sessao)):
        faz = resolver_fazenda(sessao, fazenda_id)
        return jsonable_encoder(s().coleiras(faz.id))

    @r.post("/coleiras/posicoes")
    def registrar_posicoes(
        corpo: list[PosicaoIn], fazenda_id: str | None = None, sessao: SessaoUsuario = Depends(exigir_sessao),
    ):
        faz = resolver_fazenda(sessao, fazenda_id)
        return executar(lambda: {"registradas": s().registrar_posicoes(
            [Posicao(p.coleira_id, p.instante, p.lat, p.lon) for p in corpo], fazenda_id=faz.id,
        )})

    @r.get("/ocupacao")
    def ocupacao(fazenda_id: str | None = None, sessao: SessaoUsuario = Depends(exigir_sessao)):
        faz = resolver_fazenda(sessao, fazenda_id)
        return jsonable_encoder(s().ocupacao(faz.id))

    @r.get("/verificacoes")
    def verificacoes(fazenda_id: str | None = None, sessao: SessaoUsuario = Depends(exigir_sessao)):
        faz = resolver_fazenda(sessao, fazenda_id)
        lista, avisos = s().verificacoes(faz.id)
        return jsonable_encoder({"verificacoes": lista, "avisos": avisos})

    @r.post("/simulador/avancar")
    def avancar(corpo: AvancoIn, fazenda_id: str | None = None, sessao: SessaoUsuario = Depends(exigir_sessao)):
        faz = resolver_fazenda(sessao, fazenda_id)
        return executar(lambda: {"posicoes_geradas": s().simulador_avancar(corpo.horas, faz.id), "agora": s().agora()})

    @r.post("/simulador/executar/{mov_id}")
    def executar_no_campo(
        mov_id: str, corpo: ExecucaoIn | None = Body(default=None), sessao: SessaoUsuario = Depends(exigir_sessao),
    ):
        fid = verificar_dono_movimentacao(mov_id, sessao)
        destino = corpo.piquete_id if corpo else None
        return executar(lambda: s().simulador_executar(mov_id, destino, fazenda_id=fid) or {"ok": True})

    # ---------- integração bidirecional com o PiqueTech (SPEC-018) ----------

    @admin.get("/integracao/piquetech/fazendas")
    def piquetech_fazendas():
        return executar(lambda: s().listar_fazendas_piquetech())

    @admin.get("/integracao/piquetech/cultivares")
    def piquetech_cultivares():
        return executar(lambda: s().listar_cultivares_piquetech())

    @admin.post("/integracao/piquetech/importar/{seugado_fazenda_id}", status_code=201)
    def piquetech_importar(seugado_fazenda_id: str):
        return executar(lambda: s().importar_fazenda_piquetech(seugado_fazenda_id))

    @admin.post("/fazendas/{fazenda_id}/integracao/piquetech/atualizar")
    def piquetech_atualizar(fazenda_id: str):
        return executar(lambda: s().atualizar_fazenda_piquetech(fazenda_id))

    @admin.post("/fazendas/{fazenda_id}/integracao/piquetech/exportar")
    def piquetech_exportar(fazenda_id: str, corpo: ExportarPiqueTechIn | None = Body(default=None)):
        cultivar = corpo.cultivar_id if corpo else None
        metodo = corpo.metodo_pastejo if corpo else "rotacionado"
        return executar(lambda: s().exportar_fazenda_piquetech(fazenda_id, cultivar, metodo))

    @integracao.get("/integracao/v1/execucoes")
    def execucoes(desde: str = Query(pattern=r"^\d{4}-\d{2}-\d{2}$")):
        return jsonable_encoder(s().execucoes(desde))

    app.include_router(r)
    app.include_router(admin)
    app.include_router(integracao)
    return app


app = criar_app()
