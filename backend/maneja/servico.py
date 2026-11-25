"""Sistema: liga o repositório, os adaptadores e os componentes do domínio (a montagem do DC)."""

from __future__ import annotations

import functools
import uuid
from datetime import datetime, timedelta, timezone

from . import agente as agente_mod
from .adaptadores.coleiras import SimuladorColeiras
from .adaptadores.satelite import ISatelite, SateliteSimulado
from .adaptadores.seugado import ISeuGado, SeuGadoApi, SeuGadoDesligado
from .autenticacao import ConfigAuth, SessaoUsuario, hash_senha, verificar_senha
from .datas import hoje_na_fazenda
from .dominio import (
    CATEGORIAS,
    Cliente,
    Coleira,
    Fazenda,
    Lotacao,
    Lote,
    Movimentacao,
    OcupacaoPiquete,
    Piquete,
    PlanoManejo,
    Posicao,
    PrevisaoClima,
    RegraViolada,
    ResumoPiquete,
    Usuario,
    Verificacao,
)
from .geo import area_ha, centro, poligono_valido
from .monitoramento import ocupacao, piquete_da_posicao, ultimas_posicoes, validar_posicoes
from .ndvi import lotacao_de, resumo_piquetes
from .regras import validar_movimento
from .repositorio import RepositorioMemoria
from .verificacao import coleiras_do_grupo, movimentacoes_externas, verificar

_UNSET = object()

CATEGORIAS_COLEIRA = ("boi", "vaca", "bezerro")

# Mapeamento de categorias PiqueTech (7) ↔ Maneja (3) conforme SPEC-018
_PIQUETECH_PARA_MANEJA = {
    "boi": "bois",
    "touro": "bois",
    "novilho": "bois",
    "vaca": "vacas",
    "novilha": "vacas",
    "bezerro": "bezerros",
    "bezerra": "bezerros",
}


def persiste(metodo):
    """Depois de uma operação que muda dados, grava o estado (se o repositório for persistente)."""
    @functools.wraps(metodo)
    def envolto(self, *args, **kwargs):
        resultado = metodo(self, *args, **kwargs)
        self.persistir()
        return resultado
    return envolto


INTERVALO_COLEIRA_MIN = 10  # a validar com a ficha técnica da coleira


class Conflito(Exception):
    """A operação não vale para o estado atual (por exemplo, aceitar o que já foi aceito)."""


class Relogio:
    """Hora real mais um deslocamento que o simulador avança."""

    def __init__(self, inicio: datetime | None = None) -> None:
        self._inicio = inicio
        self.deslocamento = timedelta()

    def agora(self) -> datetime:
        base = self._inicio or datetime.now(timezone.utc)
        return base + self.deslocamento

    def avancar(self, horas: float) -> None:
        self.deslocamento += timedelta(hours=horas)


class Sistema:
    def __init__(
        self,
        repo: RepositorioMemoria,
        clima,
        simulador: SimuladorColeiras,
        relogio: Relogio,
        llm=None,
        seugado: ISeuGado | None = None,
        satelite: ISatelite | None = None,
    ) -> None:
        self.repo, self.clima, self.simulador, self.relogio = repo, clima, simulador, relogio
        self.llm = llm
        self.seugado = seugado or SeuGadoDesligado()
        self.satelite = satelite or SateliteSimulado()

    def persistir(self) -> None:
        salvar = getattr(self.repo, "salvar", None)
        if salvar is None:  # repositório em memória
            return
        self.repo.fisico = dict(self.simulador.fisico)
        self.repo.deslocamento_s = self.relogio.deslocamento.total_seconds()
        salvar()

    # ---------- escopo por fazenda ----------

    def fazenda(self, fazenda_id: str | None = None) -> Fazenda:
        if fazenda_id is None:
            return self.repo.fazenda
        encontrada = next((f for f in self.repo.fazendas if f.id == fazenda_id), None)
        if encontrada is None:
            raise KeyError(fazenda_id)
        return encontrada

    def _piquetes(self, fazenda_id: str, *, apenas_ativos: bool = True) -> list[Piquete]:
        return [p for p in self.repo.piquetes if p.fazenda_id == fazenda_id and (not apenas_ativos or p.ativo)]

    def _lotacao(self, fazenda_id: str) -> list[Lotacao]:
        ativos = {p.id for p in self._piquetes(fazenda_id, apenas_ativos=True)}
        return [l for l in self.repo.lotacao if l.fazenda_id == fazenda_id and l.piquete_id in ativos]

    def _ndvi(self, fazenda_id: str) -> list:
        pids = {p.id for p in self._piquetes(fazenda_id, apenas_ativos=True)}
        return [l for l in self.repo.ndvi if l.piquete_id in pids]

    def _historico(self, fazenda_id: str) -> list[Movimentacao]:
        return [m for m in self.repo.historico if (m.fazenda_id or self.repo.fazenda.id) == fazenda_id]

    def _coleiras(self, fazenda_id: str) -> list[Coleira]:
        return [c for c in self.repo.coleiras if (c.fazenda_id or self.repo.fazenda.id) == fazenda_id]

    def _lotes(self, fazenda_id: str) -> list[Lote]:
        return [l for l in self.repo.lotes if l.fazenda_id == fazenda_id]

    def piquetes(self, fazenda_id: str | None = None, *, incluir_inativos: bool = False) -> list[Piquete]:
        f = self.fazenda(fazenda_id)
        return self._piquetes(f.id, apenas_ativos=not incluir_inativos)

    def lotacoes(self, fazenda_id: str | None = None) -> list[Lotacao]:
        return self._lotacao(self.fazenda(fazenda_id).id)

    def lotes(self, fazenda_id: str | None = None) -> list[Lote]:
        return self._lotes(self.fazenda(fazenda_id).id)

    def leituras_ndvi(self, fazenda_id: str | None = None, piquete_id: str | None = None):
        leituras = self._ndvi(self.fazenda(fazenda_id).id)
        if piquete_id is None:
            return leituras
        return [l for l in leituras if l.piquete_id == piquete_id]

    def historico(self, fazenda_id: str | None = None) -> list[Movimentacao]:
        return self._historico(self.fazenda(fazenda_id).id)

    def plano_atual(self, fazenda_id: str | None = None) -> PlanoManejo | None:
        fid = self.fazenda(fazenda_id).id
        if fid in self.repo.planos_por_fazenda:
            return self.repo.planos_por_fazenda[fid]
        if fid == self.repo.fazenda.id:
            return self.repo.plano_atual
        return None

    def dono_piquete(self, piquete_id: str) -> str:
        p = next((p for p in self.repo.piquetes if p.id == piquete_id), None)
        if p is None:
            raise KeyError(piquete_id)
        return p.fazenda_id

    def dono_coleira(self, coleira_id: str) -> str:
        c = next((c for c in self.repo.coleiras if c.id == coleira_id), None)
        if c is None:
            raise KeyError(coleira_id)
        return c.fazenda_id or self.repo.fazenda.id

    def dono_movimentacao(self, mov_id: str) -> str:
        for fid, plano in self.repo.planos_por_fazenda.items():
            if any(m.id == mov_id for m in plano.movimentacoes):
                return fid
        if self.repo.plano_atual and any(m.id == mov_id for m in self.repo.plano_atual.movimentacoes):
            return self.repo.fazenda.id
        for m in self.repo.historico:
            if m.id == mov_id:
                return m.fazenda_id or self.repo.fazenda.id
        if mov_id.startswith("seugado-"):
            ext_id = mov_id.removeprefix("seugado-")
            for f in self.repo.fazendas:
                plano = self.seugado_plano_seguro(f.id)
                if plano and any(str(m.get("id")) == ext_id for m in plano.get("movimentacoes", [])):
                    return f.id
        raise KeyError(mov_id)

    # ---------- clientes, fazendas e usuários (SPEC-017) ----------

    def listar_clientes(self) -> list[Cliente]:
        return list(self.repo.clientes)

    @persiste
    def criar_cliente(self, nome: str, contato: str = "", seugado_id: str | None = None) -> Cliente:
        if not nome.strip():
            raise RegraViolada(["o nome do cliente é obrigatório"])
        cliente = Cliente(f"cli-{uuid.uuid4().hex[:8]}", nome.strip(), contato.strip(), seugado_id)
        self.repo.clientes.append(cliente)
        return cliente

    @persiste
    def atualizar_cliente(self, cliente_id: str, nome: str | None = None, contato: str | None = None) -> Cliente:
        cliente = next((c for c in self.repo.clientes if c.id == cliente_id), None)
        if cliente is None:
            raise KeyError(cliente_id)
        if nome is not None:
            if not nome.strip():
                raise RegraViolada(["o nome do cliente é obrigatório"])
            cliente.nome = nome.strip()
        if contato is not None:
            cliente.contato = contato.strip()
        return cliente

    def listar_fazendas(self, cliente_id: str | None = None) -> list[Fazenda]:
        if cliente_id is None:
            return list(self.repo.fazendas)
        return [f for f in self.repo.fazendas if f.cliente_id == cliente_id]

    @persiste
    def criar_fazenda(
        self,
        nome: str,
        cliente_id: str | None,
        timezone_nome: str = "America/Maceio",
        seugado_id: str | None = None,
    ) -> Fazenda:
        if not nome.strip():
            raise RegraViolada(["o nome da fazenda é obrigatório"])
        if cliente_id is not None and not any(c.id == cliente_id for c in self.repo.clientes):
            raise RegraViolada([f"cliente não encontrado: {cliente_id}"])
        fazenda = Fazenda(
            id=f"faz-{uuid.uuid4().hex[:8]}",
            nome=nome.strip(),
            timezone=(timezone_nome or "America/Maceio").strip(),
            cliente_id=cliente_id,
            seugado_id=seugado_id,
        )
        self.repo.fazendas.append(fazenda)
        return fazenda

    @persiste
    def atualizar_fazenda(
        self,
        nome: str | None = None,
        fazenda_id: str | None = None,
        cliente_id: str | None | object = _UNSET,
        timezone_nome: str | None = None,
    ) -> Fazenda:
        faz = self.fazenda(fazenda_id)
        if nome is not None:
            if not nome.strip():
                raise RegraViolada(["o nome da fazenda é obrigatório"])
            faz.nome = nome.strip()
        if timezone_nome is not None and timezone_nome.strip():
            faz.timezone = timezone_nome.strip()
        if cliente_id is not _UNSET:
            if cliente_id is not None and not any(c.id == cliente_id for c in self.repo.clientes):
                raise RegraViolada([f"cliente não encontrado: {cliente_id}"])
            faz.cliente_id = cliente_id  # type: ignore[assignment]
        return faz

    def listar_usuarios(self) -> list[Usuario]:
        return list(self.repo.usuarios)

    @persiste
    def criar_usuario(
        self,
        email: str,
        senha: str,
        papel: str,
        cliente_id: str | None = None,
        nome: str = "",
        email_admin_env: str = "",
    ) -> Usuario:
        email_norm = email.strip().lower()
        if not email_norm or "@" not in email_norm:
            raise RegraViolada(["informe um e-mail válido"])
        if len(senha) < 4:
            raise RegraViolada(["a senha deve ter pelo menos 4 caracteres"])
        if papel not in ("admin", "cliente"):
            raise RegraViolada(["papel deve ser 'admin' ou 'cliente'"])
        if any(u.email.lower() == email_norm for u in self.repo.usuarios) or (
            email_admin_env and email_norm == email_admin_env.strip().lower()
        ):
            raise Conflito(f"já existe um usuário com o e-mail {email_norm}")
        if papel == "cliente":
            if not cliente_id or not any(c.id == cliente_id for c in self.repo.clientes):
                raise RegraViolada(["usuário cliente precisa estar vinculado a um cliente válido"])
        else:
            cliente_id = None
        usuario = Usuario(
            id=f"usr-{uuid.uuid4().hex[:8]}",
            email=email_norm,
            senha_hash=hash_senha(senha),
            papel=papel,  # type: ignore[arg-type]
            cliente_id=cliente_id,
            nome=nome.strip() or email_norm.split("@")[0],
        )
        self.repo.usuarios.append(usuario)
        return usuario

    @persiste
    def atualizar_usuario(
        self,
        usuario_id: str,
        *,
        nome: str | None = None,
        email: str | None = None,
        senha: str | None = None,
        papel: str | None = None,
        cliente_id: str | None | object = _UNSET,
        email_admin_env: str = "",
    ) -> Usuario:
        usuario = next((u for u in self.repo.usuarios if u.id == usuario_id), None)
        if usuario is None:
            raise KeyError(usuario_id)
        if email is not None:
            email_norm = email.strip().lower()
            if not email_norm or "@" not in email_norm:
                raise RegraViolada(["informe um e-mail válido"])
            if any(u.id != usuario_id and u.email.lower() == email_norm for u in self.repo.usuarios) or (
                email_admin_env and email_norm == email_admin_env.strip().lower()
            ):
                raise Conflito(f"já existe um usuário com o e-mail {email_norm}")
            usuario.email = email_norm
        if nome is not None:
            usuario.nome = nome.strip()
        if senha is not None and senha != "":
            if len(senha) < 4:
                raise RegraViolada(["a senha deve ter pelo menos 4 caracteres"])
            usuario.senha_hash = hash_senha(senha)
        novo_papel = papel if papel is not None else usuario.papel
        if novo_papel not in ("admin", "cliente"):
            raise RegraViolada(["papel deve ser 'admin' ou 'cliente'"])
        novo_cliente_id = usuario.cliente_id if cliente_id is _UNSET else cliente_id
        if novo_papel == "cliente":
            if not novo_cliente_id or not any(c.id == novo_cliente_id for c in self.repo.clientes):
                raise RegraViolada(["usuário cliente precisa estar vinculado a um cliente válido"])
            usuario.cliente_id = str(novo_cliente_id)
        else:
            usuario.cliente_id = None
        usuario.papel = novo_papel  # type: ignore[assignment]
        return usuario

    def autenticar_usuario(self, email: str, senha: str, cfg: ConfigAuth) -> SessaoUsuario | None:
        email_norm = email.strip().lower()
        for u in self.repo.usuarios:
            if u.email.lower() == email_norm:
                if verificar_senha(senha, u.senha_hash):
                    return SessaoUsuario(u.id, u.email, u.nome or u.email, u.papel, u.cliente_id)
                return None
        if email_norm == cfg.email.strip().lower() and verificar_senha(senha, cfg.senha_hash):
            return SessaoUsuario("admin", cfg.email, "Administrador", "admin", None)
        return None

    def resolver_sessao(self, sessao: SessaoUsuario, cfg: ConfigAuth) -> SessaoUsuario | None:
        email_norm = sessao.email.strip().lower()
        for u in self.repo.usuarios:
            if u.id == sessao.id or u.email.lower() == email_norm:
                return SessaoUsuario(u.id, u.email, u.nome or u.email, u.papel, u.cliente_id)
        if email_norm == cfg.email.strip().lower():
            return SessaoUsuario("admin", cfg.email, "Administrador", "admin", None)
        return None

    # ---------- tempo ----------

    def agora(self) -> datetime:
        return self.relogio.agora()

    def hoje(self, fazenda_id: str | None = None) -> str:
        return hoje_na_fazenda(self.agora(), self.fazenda(fazenda_id).timezone)

    # ---------- leitura ----------

    def atualizar_ndvi(self, fazenda_id: str | None = None) -> dict:
        fid = self.fazenda(fazenda_id).id
        hoje = self.hoje(fid)
        existentes = {l.piquete_id for l in self._ndvi(fid) if l.data == hoje}
        novas = []
        indisponiveis = []
        for piquete in self._piquetes(fid):
            if piquete.id in existentes:
                continue
            try:
                leitura = self.satelite.ndvi(piquete, hoje)
            except Exception:  # O histórico segue disponível durante falhas do provedor.
                indisponiveis.append(piquete.id)
                continue
            if leitura is not None:
                novas.append(leitura)
        if novas:
            self.repo.ndvi.extend(novas)
            self.persistir()
        return {"leituras": novas, "indisponiveis": indisponiveis}

    def previsao(self, fazenda_id: str | None = None) -> PrevisaoClima:
        fid = self.fazenda(fazenda_id).id
        centros = [centro(piquete.geometria) for piquete in self._piquetes(fid)]
        lat = sum(p[0] for p in centros) / len(centros) if centros else 0.0
        lon = sum(p[1] for p in centros) / len(centros) if centros else 0.0
        return self.clima.previsao(fid, lat, lon, self.hoje(fid))

    def resumo(self, fazenda_id: str | None = None) -> list[ResumoPiquete]:
        fid = self.fazenda(fazenda_id).id
        return resumo_piquetes(self._piquetes(fid), self._ndvi(fid), self._lotacao(fid), self.hoje(fid))

    # ---------- cadastros ----------

    @persiste
    def criar_piquete(
        self,
        nome: str,
        vegetacao: str,
        geometria: dict,
        externo_id: str | None = None,
        fazenda_id: str | None = None,
    ) -> Piquete:
        fid = self.fazenda(fazenda_id).id
        if not nome.strip():
            raise RegraViolada(["o nome do piquete é obrigatório"])
        if not poligono_valido(geometria):
            raise RegraViolada(["o polígono precisa de pelo menos 3 pontos distintos e área maior que zero"])
        piquete = Piquete(
            f"pq-{uuid.uuid4().hex[:8]}", fid, nome.strip(), geometria,
            area_ha(geometria), vegetacao, externo_id, ativo=True,
        )
        self.repo.piquetes.append(piquete)
        self.simulador.atualizar_piquetes(self.repo.piquetes)
        return piquete

    @persiste
    def atualizar_piquete(
        self,
        piquete_id: str,
        nome: str | None = None,
        vegetacao: str | None = None,
        geometria: dict | None = None,
    ) -> Piquete:
        piquete = next((p for p in self.repo.piquetes if p.id == piquete_id and p.ativo), None)
        if piquete is None:
            raise KeyError(piquete_id)
        if nome is not None:
            if not nome.strip():
                raise RegraViolada(["o nome do piquete é obrigatório"])
            piquete.nome = nome.strip()
        if vegetacao is not None:
            piquete.vegetacao = vegetacao.strip()
        if geometria is not None:
            if not poligono_valido(geometria):
                raise RegraViolada(["o polígono precisa de pelo menos 3 pontos distintos e área maior que zero"])
            piquete.geometria, piquete.area_ha = geometria, area_ha(geometria)
            self.simulador.atualizar_piquetes(self.repo.piquetes)
        return piquete

    @persiste
    def remover_piquete(self, piquete_id: str) -> None:
        if not any(p.id == piquete_id and p.ativo for p in self.repo.piquetes):
            raise KeyError(piquete_id)
        if lotacao_de(self.repo.lotacao, piquete_id) or any(
            c.piquete_cadastro_id == piquete_id for c in self.repo.coleiras
        ):
            raise Conflito("Há gado neste piquete. Mova os animais antes de desativar.")
        self.repo.piquetes = [p for p in self.repo.piquetes if p.id != piquete_id]
        self.repo.ndvi = [l for l in self.repo.ndvi if l.piquete_id != piquete_id]
        self.repo.lotacao = [l for l in self.repo.lotacao if l.piquete_id != piquete_id]
        self.simulador.atualizar_piquetes(self.repo.piquetes)

    @persiste
    def atualizar_lotacao(self, piquete_id: str, bois: int, vacas: int, bezerros: int) -> Lotacao:
        piquete = next((p for p in self.repo.piquetes if p.id == piquete_id and p.ativo), None)
        if piquete is None:
            raise KeyError(piquete_id)
        for nome_cat, qtd in zip(CATEGORIAS, (bois, vacas, bezerros)):
            if not isinstance(qtd, int) or isinstance(qtd, bool) or qtd < 0:
                raise RegraViolada([f"quantidade inválida de {nome_cat}: {qtd}"])
        atual = next((l for l in self.repo.lotacao if l.piquete_id == piquete_id), None)
        if atual is None:
            atual = Lotacao(piquete_id, piquete.fazenda_id, 0, 0, 0, None)
            self.repo.lotacao.append(atual)
        estava_vazio = atual.rebanho.total == 0
        atual.bois, atual.vacas, atual.bezerros = bois, vacas, bezerros
        if estava_vazio and atual.rebanho.total > 0:
            atual.desde = self.hoje(piquete.fazenda_id)
        return atual

    # ---------- agente ----------

    @persiste
    def gerar_plano(self, fazenda_id: str | None = None) -> PlanoManejo:
        fid = self.fazenda(fazenda_id).id
        entrada = agente_mod.EntradaAgente(
            self._piquetes(fid),
            self._ndvi(fid),
            self.previsao(fid),
            self._lotacao(fid),
            self._historico(fid),
        )
        plano = agente_mod.gerar_plano(entrada, self.hoje(fid), self.agora(), self.llm)
        for mov in plano.movimentacoes:
            mov.fazenda_id = fid
        self.repo.planos_por_fazenda[fid] = plano
        if fid == self.repo.fazenda.id:
            self.repo.plano_atual = plano
        return plano

    def _pendente(self, mov_id: str, fazenda_id: str) -> Movimentacao:
        plano = self.plano_atual(fazenda_id)
        mov = next((m for m in plano.movimentacoes if m.id == mov_id), None) if plano else None
        if mov is None:
            raise KeyError(mov_id)
        if mov.status != "pendente":
            raise Conflito(f"a movimentação já está {mov.status}")
        return mov

    @persiste
    def aceitar(self, mov_id: str, destino_id: str | None = None, fazenda_id: str | None = None) -> Movimentacao:
        fid = fazenda_id or self.dono_movimentacao(mov_id)
        mov = self._pendente(mov_id, fid)
        hoje = self.hoje(fid)
        piquetes_faz = self._piquetes(fid)
        lotacao_faz = self._lotacao(fid)
        ndvi_faz = self._ndvi(fid)
        coleiras_faz = self._coleiras(fid)

        origem_lot = lotacao_de(lotacao_faz, mov.piquete_origem_id)
        if origem_lot is None:
            raise RegraViolada([f"{mov.piquete_origem_nome} não tem mais rebanho cadastrado"])
        destino_id = destino_id or mov.piquete_destino_id
        falhas = validar_movimento(destino_id, origem_lot.rebanho, piquetes_faz, ndvi_faz, lotacao_faz, hoje)
        if falhas:
            raise RegraViolada(falhas)
        destino = next(p for p in piquetes_faz if p.id == destino_id)

        # coleiras do grupo: as que estão de fato na origem agora (base do planejado × realizado)
        mov.coleiras = coleiras_do_grupo(
            mov.piquete_origem_id, coleiras_faz, piquetes_faz,
            self.repo.posicoes_vigentes(), self.agora(), incluir_cadastro=False,
        )
        # o cadastro passa a dizer que o rebanho está no destino; o campo só muda quando o gado for levado
        rebanho = origem_lot.rebanho
        self.repo.lotacao = [
            l for l in self.repo.lotacao if l.piquete_id not in (mov.piquete_origem_id, destino_id)
        ]
        self.repo.lotacao.append(Lotacao(destino_id, fid, rebanho.bois, rebanho.vacas, rebanho.bezerros, hoje))
        for lote in self._lotes(fid):
            if lote.piquete_atual_id == mov.piquete_origem_id:
                lote.piquete_atual_id = destino_id
                lote.desde = hoje
        for c in coleiras_faz:
            if c.piquete_cadastro_id == mov.piquete_origem_id:
                c.piquete_cadastro_id = destino_id

        trocado = destino_id != mov.piquete_destino_id
        if trocado:
            leitura = next(
                (l for l in sorted(ndvi_faz, key=lambda l: l.data, reverse=True)
                 if l.piquete_id == destino_id and l.data <= hoje),
                None,
            )
            mov.piquete_destino_id, mov.piquete_destino_nome = destino.id, destino.nome
            mov.ndvi_destino = leitura.valor if leitura else None
            mov.explicacao = f"{mov.explicacao} Destino trocado pelo produtor para {destino.nome}."
        mov.status = "trocada" if trocado else "aceita"
        mov.destino_trocado = trocado
        mov.fazenda_id = fid
        self.repo.historico.insert(0, mov)
        return mov

    @persiste
    def recusar(self, mov_id: str, fazenda_id: str | None = None) -> Movimentacao:
        fid = fazenda_id or self.dono_movimentacao(mov_id)
        mov = self._pendente(mov_id, fid)
        mov.status = "recusada"
        mov.fazenda_id = fid
        self.repo.historico.insert(0, mov)
        return mov

    # ---------- coleiras ----------

    @persiste
    def criar_coleiras(
        self,
        fazenda_id: str,
        *,
        piquete_id: str | None = None,
        lote_id: str | None = None,
        categoria: str = "boi",
        quantidade: int = 1,
    ) -> list[Coleira]:
        fid = self.fazenda(fazenda_id).id
        if categoria not in CATEGORIAS_COLEIRA:
            raise RegraViolada([f"categoria inválida: {categoria} (use boi, vaca ou bezerro)"])
        if quantidade < 1 or quantidade > 50:
            raise RegraViolada(["quantidade deve estar entre 1 e 50"])
        if lote_id:
            lote = next((l for l in self._lotes(fid) if l.id == lote_id), None)
            if lote is None:
                raise KeyError(lote_id)
            if not lote.piquete_atual_id:
                raise RegraViolada([f"o lote {lote.nome} não está em nenhum piquete"])
            piquete_id = lote.piquete_atual_id
        if not piquete_id or not any(p.id == piquete_id for p in self._piquetes(fid)):
            raise RegraViolada(["selecione um piquete ou lote válido da fazenda"])
        self.simulador.atualizar_piquetes(self.repo.piquetes)
        criadas: list[Coleira] = []
        agora = self.agora()
        for _ in range(quantidade):
            col = Coleira(
                id=f"col-{uuid.uuid4().hex[:6]}",
                categoria=categoria,
                piquete_cadastro_id=piquete_id,
                fazenda_id=fid,
                lote_id=lote_id,
            )
            self.repo.coleiras.append(col)
            self.simulador.adicionar(col)
            pos = self.simulador.gerar_posicao_imediata(col.id, agora)
            if pos is not None:
                self.repo.posicoes.append(pos)
            criadas.append(col)
        return criadas

    @persiste
    def remover_coleira(self, coleira_id: str, fazenda_id: str | None = None) -> None:
        fid = fazenda_id or self.dono_coleira(coleira_id)
        col = next((c for c in self._coleiras(fid) if c.id == coleira_id), None)
        if col is None:
            raise KeyError(coleira_id)
        self.repo.coleiras = [c for c in self.repo.coleiras if c.id != coleira_id]
        self.simulador.fisico.pop(coleira_id, None)

    @persiste
    def registrar_posicoes(self, posicoes: list[Posicao], fazenda_id: str | None = None) -> int:
        alvo = self._coleiras(self.fazenda(fazenda_id).id) if fazenda_id is not None else self.repo.coleiras
        validar_posicoes(posicoes, alvo)
        self.repo.posicoes.extend(posicoes)
        return len(posicoes)

    def coleiras(self, fazenda_id: str | None = None) -> list[dict]:
        fid = self.fazenda(fazenda_id).id
        piquetes_faz = self._piquetes(fid)
        coleiras_faz = self._coleiras(fid)
        ultimas = ultimas_posicoes(self.repo.posicoes_vigentes(), self.agora())
        resultado = []
        for c in coleiras_faz:
            pos = ultimas.get(c.id)
            resultado.append({
                "id": c.id,
                "categoria": c.categoria,
                "piquete_cadastro_id": c.piquete_cadastro_id,
                "lote_id": c.lote_id,
                "piquete_observado_id": piquete_da_posicao(piquetes_faz, pos) if pos else None,
                "ultima_posicao": {"lat": pos.lat, "lon": pos.lon, "instante": pos.instante.isoformat()} if pos else None,
            })
        return resultado

    def ocupacao(self, fazenda_id: str | None = None) -> list[OcupacaoPiquete]:
        fid = self.fazenda(fazenda_id).id
        return ocupacao(self._piquetes(fid), self._coleiras(fid), self.repo.posicoes_vigentes(), self.agora())

    # ---------- planejado × realizado ----------

    def _alvo_seugado(self, fazenda: Fazenda) -> str | None:
        if self.seugado.modo == "desligado":
            return None
        if self.seugado.modo == "arquivo":
            return fazenda.seugado_id or (fazenda.id if fazenda.id == self.repo.fazenda.id else None)
        if fazenda.seugado_id:
            return fazenda.seugado_id
        # compatibilidade com testes unitários que passam fazenda_id diretamente em SeuGadoApi(...)
        padrao_adaptador = getattr(self.seugado, "fazenda_id", "")
        if padrao_adaptador and fazenda.id == self.repo.fazenda.id:
            return padrao_adaptador
        return None

    def verificacoes(self, fazenda_id: str | None = None) -> tuple[list[Verificacao], list[str]]:
        faz = self.fazenda(fazenda_id)
        fid = faz.id
        agora, hoje = self.agora(), self.hoje(fid)
        posicoes = self.repo.posicoes_vigentes()
        piquetes_todos = self._piquetes(fid, apenas_ativos=False)
        coleiras_faz = self._coleiras(fid)
        planejadas = [m for m in self._historico(fid) if m.status in ("aceita", "trocada") and m.coleiras]
        avisos: list[str] = []
        alvo_seugado = self._alvo_seugado(faz)
        plano = None
        if alvo_seugado is not None:
            try:
                plano = self.seugado.plano_atual(alvo_seugado)
            except Exception:  # noqa: BLE001 - o SeuGado nunca derruba o Maneja
                plano, avisos = None, ["plano_externo_indisponivel"]
        if plano:
            antes = {k: list(v) for k, v in self.repo.grupos_externos.items()}
            planejadas += movimentacoes_externas(
                plano, piquetes_todos, coleiras_faz, posicoes, agora,
                self.repo.grupos_externos, lotes=self._lotes(fid), fazenda_id=fid,
            )
            if self.repo.grupos_externos != antes:
                self.persistir()
        return [verificar(m, piquetes_todos, posicoes, agora, hoje) for m in planejadas], avisos

    def execucoes(self, desde: str) -> list[dict]:
        """Agrega as verificações de todas as fazendas integradas (SPEC-018 R6)."""
        if self.seugado.modo == "desligado":
            return []
        if self.seugado.modo == "arquivo":
            fazendas_alvo = [self.repo.fazenda]
        else:
            fazendas_alvo = [f for f in self.repo.fazendas if self._alvo_seugado(f) is not None]
        itens: list[dict] = []
        for f in fazendas_alvo:
            verificacoes, _ = self.verificacoes(f.id)
            for v in verificacoes:
                if v.origem_plano == "seugado" and v.data >= desde:
                    itens.append({
                        "movimentacao_externa_id": v.externo_id,
                        "piquete_origem_externo_id": v.piquete_origem_externo_id,
                        "piquete_destino_externo_id": v.piquete_destino_externo_id,
                        "status": v.status,
                        "fracao_no_destino": v.fracao_no_destino,
                        "coleiras_consideradas": v.coleiras_consideradas,
                        "observado_em": v.observado_em,
                    })
        return itens

    # ---------- integração bidirecional PiqueTech (SPEC-018) ----------

    def _exigir_piquetech_api(self) -> SeuGadoApi:
        if not isinstance(self.seugado, SeuGadoApi):
            raise RegraViolada([
                "integração com o PiqueTech não está ativa em modo api (configure MANEJA_SEUGADO_MODO=api)"
            ])
        return self.seugado

    def listar_fazendas_piquetech(self) -> list[dict]:
        api_pt = self._exigir_piquetech_api()
        por_seugado = {f.seugado_id: f for f in self.repo.fazendas if f.seugado_id}
        fazendas = api_pt.listar_fazendas()
        resultado = []
        for f in fazendas:
            fid_pt = str(f["id"])
            local = por_seugado.get(fid_pt)
            resultado.append({
                "seugado_id": fid_pt,
                "nome": f["nome"],
                "cliente_seugado_id": str(f["cliente_id"]) if f.get("cliente_id") else None,
                "cliente_nome": f.get("cliente_nome"),
                "timezone": f.get("timezone") or "America/Fortaleza",
                "ja_importada": local is not None,
                "fazenda_local_id": local.id if local else None,
            })
        return resultado

    def listar_cultivares_piquetech(self) -> list[dict]:
        return self._exigir_piquetech_api().listar_cultivares()

    @staticmethod
    def _somar_composicao_piquetech(composicao: list[dict]) -> tuple[int, int, int]:
        totais = {"bois": 0, "vacas": 0, "bezerros": 0}
        for item in composicao:
            chave = _PIQUETECH_PARA_MANEJA.get(str(item.get("categoria", "")).lower())
            if chave:
                totais[chave] += int(item.get("n_animais") or 0)
        return totais["bois"], totais["vacas"], totais["bezerros"]

    @staticmethod
    def _composicao_para_piquetech(bois: int, vacas: int, bezerros: int) -> list[dict]:
        itens = []
        if bois > 0:
            itens.append({"categoria": "boi", "n_animais": bois})
        if vacas > 0:
            itens.append({"categoria": "vaca", "n_animais": vacas})
        if bezerros > 0:
            itens.append({"categoria": "bezerro", "n_animais": bezerros})
        return itens

    @persiste
    def importar_fazenda_piquetech(self, seugado_fazenda_id: str) -> dict:
        """Importa ou atualiza (upsert por UUID) cliente, fazenda, piquetes e lotes do PiqueTech."""
        api_pt = self._exigir_piquetech_api()
        fazenda_pt = api_pt.obter_fazenda(seugado_fazenda_id)
        clientes_pt = api_pt.listar_clientes()
        piquetes_pt = api_pt.listar_piquetes(seugado_fazenda_id)
        lotes_pt = api_pt.listar_lotes(seugado_fazenda_id)

        # 1) Cliente (reaproveita pelo seugado_id)
        cli_pt_id = str(fazenda_pt["cliente_id"]) if fazenda_pt.get("cliente_id") else None
        cli_pt = next((c for c in clientes_pt if str(c["id"]) == cli_pt_id), None) if cli_pt_id else None
        cliente = next((c for c in self.repo.clientes if cli_pt_id and c.seugado_id == cli_pt_id), None)
        nome_cli = (
            (cli_pt.get("nome") if cli_pt else None)
            or fazenda_pt.get("cliente_nome")
            or f"Cliente {fazenda_pt['nome']}"
        )
        contato_cli = (cli_pt.get("telefone") or "") if cli_pt else ""
        if cliente is None:
            cliente = Cliente(f"cli-{uuid.uuid4().hex[:8]}", nome_cli, contato_cli, seugado_id=cli_pt_id)
            self.repo.clientes.append(cliente)
        else:
            cliente.nome = nome_cli
            if contato_cli:
                cliente.contato = contato_cli

        # 2) Fazenda (upsert pelo seugado_id)
        fid_pt = str(fazenda_pt["id"])
        fazenda = next((f for f in self.repo.fazendas if f.seugado_id == fid_pt), None)
        tz = fazenda_pt.get("timezone") or "America/Fortaleza"
        if fazenda is None:
            fazenda = Fazenda(f"faz-{uuid.uuid4().hex[:8]}", fazenda_pt["nome"], tz, cliente.id, seugado_id=fid_pt)
            self.repo.fazendas.append(fazenda)
        else:
            fazenda.nome = fazenda_pt["nome"]
            fazenda.timezone = tz
            fazenda.cliente_id = cliente.id

        # 3) Piquetes (upsert por externo_id; piquete que sumiu fica inativo)
        vistos_piquetes: set[str] = set()
        mapa_piquete: dict[str, Piquete] = {}
        for p_pt in piquetes_pt:
            ext_id = str(p_pt["id"])
            vistos_piquetes.add(ext_id)
            geometria = p_pt["geometria"]
            area = float(p_pt.get("area_ha") or area_ha(geometria))
            vegetacao = str(p_pt.get("cultivar_nome") or "")
            existente = next(
                (p for p in self.repo.piquetes if p.fazenda_id == fazenda.id and p.externo_id == ext_id), None
            )
            if existente is None:
                existente = Piquete(
                    id=f"pq-{uuid.uuid4().hex[:8]}",
                    fazenda_id=fazenda.id,
                    nome=p_pt["nome"],
                    geometria=geometria,
                    area_ha=area,
                    vegetacao=vegetacao,
                    externo_id=ext_id,
                    ativo=True,
                )
                self.repo.piquetes.append(existente)
            else:
                existente.nome = p_pt["nome"]
                existente.geometria = geometria
                existente.area_ha = area
                existente.vegetacao = vegetacao
                existente.ativo = True
            mapa_piquete[ext_id] = existente

        inativados = 0
        for p in self.repo.piquetes:
            if p.fazenda_id == fazenda.id and p.externo_id and p.externo_id not in vistos_piquetes and p.ativo:
                p.ativo = False
                inativados += 1

        # 4) Lotes (upsert por seugado_id) e lotação sincronizada
        vistos_lotes: set[str] = set()
        for l_pt in lotes_pt:
            l_ext_id = str(l_pt["id"])
            vistos_lotes.add(l_ext_id)
            bois, vacas, bezerros = self._somar_composicao_piquetech(l_pt.get("composicao") or [])
            pq_ext = str(l_pt["piquete_atual_id"]) if l_pt.get("piquete_atual_id") else None
            pq_local = mapa_piquete.get(pq_ext) if pq_ext else None
            pq_local_id = pq_local.id if pq_local else None
            desde = str(l_pt["desde"])[:10] if l_pt.get("desde") else None

            lote = next((l for l in self.repo.lotes if l.fazenda_id == fazenda.id and l.seugado_id == l_ext_id), None)
            if lote is None:
                lote = Lote(
                    id=f"lot-{uuid.uuid4().hex[:8]}",
                    fazenda_id=fazenda.id,
                    nome=l_pt["nome"],
                    piquete_atual_id=pq_local_id,
                    bois=bois,
                    vacas=vacas,
                    bezerros=bezerros,
                    desde=desde,
                    seugado_id=l_ext_id,
                )
                self.repo.lotes.append(lote)
            else:
                lote.nome = l_pt["nome"]
                lote.piquete_atual_id = pq_local_id
                lote.bois, lote.vacas, lote.bezerros = bois, vacas, bezerros
                lote.desde = desde

            # mantém o cadastro das coleiras do lote alinhado com o piquete atual do PiqueTech
            if pq_local_id:
                for c in self._coleiras(fazenda.id):
                    if c.lote_id == lote.id:
                        c.piquete_cadastro_id = pq_local_id

        # remove lotes externos que não existem mais no PiqueTech
        removidos_lotes = {
            l.id for l in self.repo.lotes if l.fazenda_id == fazenda.id and l.seugado_id and l.seugado_id not in vistos_lotes
        }
        if removidos_lotes:
            self.repo.lotes = [l for l in self.repo.lotes if l.id not in removidos_lotes]
            for c in self._coleiras(fazenda.id):
                if c.lote_id in removidos_lotes:
                    c.lote_id = None

        # recalcula lotação da fazenda a partir dos lotes importados
        self.repo.lotacao = [l for l in self.repo.lotacao if l.fazenda_id != fazenda.id]
        agrupado: dict[str, Lotacao] = {}
        for lote in self._lotes(fazenda.id):
            if not lote.piquete_atual_id or lote.rebanho.total == 0:
                continue
            atual = agrupado.get(lote.piquete_atual_id)
            if atual is None:
                agrupado[lote.piquete_atual_id] = Lotacao(
                    lote.piquete_atual_id, fazenda.id, lote.bois, lote.vacas, lote.bezerros, lote.desde,
                )
            else:
                atual.bois += lote.bois
                atual.vacas += lote.vacas
                atual.bezerros += lote.bezerros
        self.repo.lotacao.extend(agrupado.values())

        self.simulador.atualizar_piquetes(self.repo.piquetes)
        api_pt.invalidar_cache_plano(fid_pt)
        return {
            "cliente": cliente,
            "fazenda": fazenda,
            "piquetes_importados": len(piquetes_pt),
            "piquetes_inativados": inativados,
            "lotes_importados": len(lotes_pt),
        }

    def atualizar_fazenda_piquetech(self, fazenda_id: str) -> dict:
        faz = self.fazenda(fazenda_id)
        if not faz.seugado_id:
            raise RegraViolada(["esta fazenda ainda não está vinculada ao PiqueTech"])
        return self.importar_fazenda_piquetech(faz.seugado_id)

    def exportar_fazenda_piquetech(
        self,
        fazenda_id: str,
        cultivar_id: str | None = None,
        metodo_pastejo: str = "rotacionado",
    ) -> dict:
        """Cria cliente, fazenda, piquetes e lotes no PiqueTech e guarda todos os UUIDs."""
        api_pt = self._exigir_piquetech_api()
        faz = self.fazenda(fazenda_id)
        if faz.seugado_id:
            raise Conflito("esta fazenda já está vinculada ao PiqueTech")
        if metodo_pastejo not in ("rotacionado", "continuo"):
            raise RegraViolada(["metodo_pastejo deve ser 'rotacionado' ou 'continuo'"])
        cliente = next((c for c in self.repo.clientes if c.id == faz.cliente_id), None) if faz.cliente_id else None
        if cliente is None:
            raise RegraViolada(["vincule a fazenda a um cliente antes de exportar para o PiqueTech"])

        if not cultivar_id:
            cultivares = api_pt.listar_cultivares()
            preferida = next((c for c in cultivares if c.get("calibrada")), None) or (cultivares[0] if cultivares else None)
            if preferida is None:
                raise RegraViolada(["nenhuma cultivar disponível no PiqueTech"])
            cultivar_id = str(preferida["id"])

        criados_piquetes = 0
        criados_lotes = 0
        try:
            # 1) Cliente (pula se já tem seugado_id)
            if not cliente.seugado_id:
                resp_cli = api_pt.criar_cliente({
                    "nome": cliente.nome,
                    "telefone": cliente.contato or None,
                    "observacoes": "Criado pelo Maneja",
                })
                cliente.seugado_id = str(resp_cli["id"])

            # 2) Fazenda (padrões operacionais válidos no PiqueTech)
            resp_faz = api_pt.criar_fazenda({
                "cliente_id": cliente.seugado_id,
                "nome": faz.nome,
                "timezone": faz.timezone or "America/Maceio",
                "funcionarios_disponiveis": 1,
                "animais_por_funcionario_dia": 100,
                "dias_preferenciais_manejo": [0, 1, 2, 3, 4, 5, 6],
                "envio_plano_dia": 6,
                "envio_plano_hora": 18,
            })
            faz.seugado_id = str(resp_faz["id"])

            # 3) Piquetes ativos
            piquetes_faz = self._piquetes(faz.id)
            for p in piquetes_faz:
                resp_p = api_pt.criar_piquete(faz.seugado_id, {
                    "nome": p.nome,
                    "geometria": p.geometria,
                    "cultivar_id": cultivar_id,
                    "metodo_pastejo": metodo_pastejo,
                })
                p.externo_id = str(resp_p["id"])
                criados_piquetes += 1

            # 4) Lotes (dos lotes cadastrados ou, se não houver, de cada piquete ocupado)
            por_id = {p.id: p for p in piquetes_faz}
            lotes_exportar = [l for l in self._lotes(faz.id) if l.piquete_atual_id in por_id and l.rebanho.total > 0]
            if not lotes_exportar:
                for lot in self._lotacao(faz.id):
                    if lot.rebanho.total == 0 or lot.piquete_id not in por_id:
                        continue
                    novo_lote = Lote(
                        id=f"lot-{uuid.uuid4().hex[:8]}",
                        fazenda_id=faz.id,
                        nome=f"Lote {por_id[lot.piquete_id].nome}",
                        piquete_atual_id=lot.piquete_id,
                        bois=lot.bois,
                        vacas=lot.vacas,
                        bezerros=lot.bezerros,
                        desde=lot.desde,
                    )
                    self.repo.lotes.append(novo_lote)
                    lotes_exportar.append(novo_lote)

            for lote in lotes_exportar:
                composicao = self._composicao_para_piquetech(lote.bois, lote.vacas, lote.bezerros)
                pq = por_id.get(lote.piquete_atual_id or "")
                if not composicao or pq is None or not pq.externo_id:
                    continue
                payload_lote = {
                    "nome": lote.nome,
                    "composicao": composicao,
                    "piquete_atual_id": pq.externo_id,
                }
                if lote.desde:
                    payload_lote["desde"] = lote.desde
                resp_lote = api_pt.criar_lote(faz.seugado_id, payload_lote)
                lote.seugado_id = str(resp_lote["id"])
                criados_lotes += 1
        finally:
            # grava os UUIDs já criados mesmo em erro parcial para evitar duplicação na retentativa
            self.persistir()

        return {
            "cliente": cliente,
            "fazenda": faz,
            "piquetes_exportados": criados_piquetes,
            "lotes_exportados": criados_lotes,
        }

    # ---------- simulador do campo ----------

    def gerar_posicoes(self, fazenda_id: str | None = None, coleira_ids: set[str] | None = None) -> int:
        ids = coleira_ids
        if ids is None and fazenda_id is not None:
            ids = {c.id for c in self._coleiras(fazenda_id)}
        novas = self.simulador.gerar_posicoes(self.agora())
        if ids is not None:
            novas = [p for p in novas if p.coleira_id in ids]
        return self.registrar_posicoes(novas)

    def atualizar_coleiras(self) -> int:
        """As coleiras reportam a cada INTERVALO_COLEIRA_MIN: só gera para coleiras sem leitura recente."""
        agora = self.agora()
        corte = agora - timedelta(minutes=INTERVALO_COLEIRA_MIN)
        ultima_por_coleira: dict[str, datetime] = {}
        for p in self.repo.posicoes:
            if p.instante <= agora:
                ant = ultima_por_coleira.get(p.coleira_id)
                if ant is None or p.instante > ant:
                    ultima_por_coleira[p.coleira_id] = p.instante
        pendentes = {
            c.id for c in self.repo.coleiras
            if c.id not in ultima_por_coleira or ultima_por_coleira[c.id] <= corte
        }
        if not pendentes:
            return 0
        return self.gerar_posicoes(coleira_ids=pendentes)

    def simulador_avancar(self, horas: float, fazenda_id: str | None = None) -> int:
        self.relogio.avancar(horas)
        return self.gerar_posicoes(fazenda_id=fazenda_id)

    def simulador_executar(self, mov_id: str, piquete_id: str | None = None, fazenda_id: str | None = None) -> None:
        """O gado da movimentação é levado no campo (para o destino ou para outro piquete)."""
        fid = fazenda_id or self.dono_movimentacao(mov_id)
        piquetes_faz = self._piquetes(fid, apenas_ativos=False)
        coleiras_faz = self._coleiras(fid)
        ids_faz = {c.id for c in coleiras_faz}

        candidatas = list(self._historico(fid))
        plano = self.seugado_plano_seguro(fid)
        if plano:
            candidatas += movimentacoes_externas(
                plano, piquetes_faz, coleiras_faz, self.repo.posicoes_vigentes(),
                self.agora(), self.repo.grupos_externos, lotes=self._lotes(fid), fazenda_id=fid,
            )
        mov = next((m for m in candidatas if m.id == mov_id and m.status in ("aceita", "trocada")), None)
        if mov is None:
            raise KeyError(mov_id)
        alvo = piquete_id or mov.piquete_destino_id
        if not any(p.id == alvo for p in piquetes_faz):
            raise KeyError(alvo)
        grupo = (set(mov.coleiras) & ids_faz) | {
            cid for cid, piquete in self.simulador.fisico.items()
            if cid in ids_faz and piquete == mov.piquete_origem_id
        }
        movidas = {cid for cid in grupo if cid in self.simulador.fisico and self.simulador.fisico[cid] != alvo}
        agora = self.agora()
        # Em relógios fixos, separa a leitura nova de uma leitura anterior no mesmo instante.
        if any(p.coleira_id in movidas and p.instante == agora for p in self.repo.posicoes):
            self.relogio.deslocamento += timedelta(microseconds=1)
            agora = self.agora()
        self.repo.ultima_movimentacao_fisica.update(dict.fromkeys(movidas, agora))
        self.simulador.mover(sorted(grupo), alvo)
        self.gerar_posicoes(fazenda_id=fid)

    def seugado_plano_seguro(self, fazenda_id: str | None = None) -> dict | None:
        faz = self.fazenda(fazenda_id)
        alvo = self._alvo_seugado(faz)
        if alvo is None:
            return None
        try:
            return self.seugado.plano_atual(alvo)
        except Exception:  # noqa: BLE001
            return None
