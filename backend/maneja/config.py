"""Configuração por variável de ambiente e montagem do sistema."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .adaptadores.clima import ClimaSimulado
from .adaptadores.coleiras import PERDA_SINAL_PADRAO, SimuladorColeiras
from .adaptadores.llm import GEMINI_COTA_DIARIA_PADRAO, GEMINI_MODELO_PADRAO, ControleDeCota, GeminiLLM
from .adaptadores.seugado import ISeuGado, SeuGadoApi, SeuGadoArquivo, SeuGadoDesligado
from .autenticacao import ConfigAuth, hash_senha
from .datas import hoje_na_fazenda
from .demo import repositorio_demo
from .servico import Relogio, Sistema

EXEMPLO_PLANO_SEUGADO = Path(__file__).resolve().parent.parent / "exemplos" / "plano-seugado.json"

# Valores só para desenvolvimento e demonstração. Em produção, defina as variáveis (SPEC-013).
EMAIL_PADRAO = "tecnico@maneja.app"
SENHA_PADRAO = "maneja123"
SEGREDO_PADRAO = "maneja-segredo-de-desenvolvimento"


def auth_do_ambiente() -> ConfigAuth:
    e = os.environ
    senha_hash = e.get("MANEJA_USUARIO_SENHA_HASH") or hash_senha(e.get("MANEJA_USUARIO_SENHA", SENHA_PADRAO))
    return ConfigAuth(
        email=e.get("MANEJA_USUARIO_EMAIL", EMAIL_PADRAO),
        senha_hash=senha_hash,
        segredo=e.get("MANEJA_JWT_SEGREDO", SEGREDO_PADRAO),
        token_integracao=e.get("MANEJA_TOKEN_INTEGRACAO", ""),
    )


@dataclass
class Config:
    seugado_modo: str = "desligado"
    seugado_arquivo: str = str(EXEMPLO_PLANO_SEUGADO)
    seugado_url: str = ""
    seugado_email: str = ""
    seugado_senha: str = ""
    seugado_fazenda_id: str = ""
    perda_sinal: float = PERDA_SINAL_PADRAO
    semente: int | None = None
    database_url: str = ""  # vazio = memória (SPEC-008)
    sem_estado: bool = False  # carrega do banco a cada requisição (Vercel, SPEC-013)
    cors_origens: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    semear: bool = True  # banco vazio recebe a fazenda de demonstração
    gemini_api_key: str = field(default="", repr=False)  # vazio = explicação só da regra (SPEC-005)
    gemini_modelo: str = GEMINI_MODELO_PADRAO
    gemini_cota_diaria: int = GEMINI_COTA_DIARIA_PADRAO

    @classmethod
    def do_ambiente(cls) -> Config:
        e = os.environ
        semente = e.get("MANEJA_SEMENTE")
        return cls(
            seugado_modo=e.get("MANEJA_SEUGADO_MODO", "desligado"),
            seugado_arquivo=e.get("MANEJA_SEUGADO_ARQUIVO", str(EXEMPLO_PLANO_SEUGADO)),
            seugado_url=e.get("MANEJA_SEUGADO_URL", ""),
            seugado_email=e.get("MANEJA_SEUGADO_EMAIL", ""),
            seugado_senha=e.get("MANEJA_SEUGADO_SENHA", ""),
            seugado_fazenda_id=e.get("MANEJA_SEUGADO_FAZENDA_ID", ""),
            perda_sinal=float(e.get("MANEJA_PERDA_SINAL", PERDA_SINAL_PADRAO)),
            semente=int(semente) if semente else None,
            database_url=e.get("DATABASE_URL", ""),
            semear=e.get("MANEJA_SEMEAR", "1") == "1",
            sem_estado=e.get("MANEJA_SEM_ESTADO", "1" if e.get("VERCEL") else "0") == "1",
            cors_origens=tuple(o.strip() for o in e.get(
                "MANEJA_CORS_ORIGENS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()),
            gemini_api_key=e.get("MANEJA_GEMINI_API_KEY", "").strip(),
            gemini_modelo=e.get("MANEJA_GEMINI_MODELO", "").strip() or GEMINI_MODELO_PADRAO,
            gemini_cota_diaria=int(e.get("MANEJA_GEMINI_COTA_DIARIA") or GEMINI_COTA_DIARIA_PADRAO),
        )


def adaptador_seugado(config: Config) -> ISeuGado:
    if config.seugado_modo == "arquivo":
        return SeuGadoArquivo(config.seugado_arquivo)
    if config.seugado_modo == "api":
        return SeuGadoApi(config.seugado_url, config.seugado_email, config.seugado_senha, config.seugado_fazenda_id)
    return SeuGadoDesligado()


def adaptador_llm(config: Config) -> ControleDeCota | None:
    """Sem chave do Gemini, o agente usa o texto da regra (SPEC-005, R3)."""
    if not config.gemini_api_key:
        return None
    return ControleDeCota(GeminiLLM(config.gemini_api_key, config.gemini_modelo), limite=config.gemini_cota_diaria)


def montar_sistema(config: Config | None = None, inicio: datetime | None = None, llm=None, clima=None) -> Sistema:
    """Sistema com a fazenda de demonstração e as primeiras posições das coleiras."""
    config = config or Config()
    relogio = Relogio(inicio)
    hoje = hoje_na_fazenda(relogio.agora() if inicio else datetime.now(timezone.utc), "America/Maceio")
    if config.database_url:
        from datetime import timedelta

        from .repositorio_pg import RepositorioPg

        repo = RepositorioPg.abrir(config.database_url, repositorio_demo(hoje) if config.semear else None)
        relogio.deslocamento = timedelta(seconds=repo.deslocamento_s)
    else:
        repo = repositorio_demo(hoje)
    simulador = SimuladorColeiras(repo.coleiras, repo.piquetes, config.perda_sinal, config.semente)
    if getattr(repo, "fisico", None):
        simulador.fisico.update(repo.fisico)
    llm = llm if llm is not None else adaptador_llm(config)
    sistema = Sistema(repo, clima or ClimaSimulado(), simulador, relogio, llm, adaptador_seugado(config))
    sistema.atualizar_coleiras()
    sistema.verificacoes()  # com a integração ligada, registra quem está na origem de cada movimentação do SeuGado
    return sistema
