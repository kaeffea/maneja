// Estado da aplicação. Com VITE_API_URL definida, tudo vem da API (backend/);
// sem ela, roda o modo demonstração em memória (decisão D7, SPEC-010, SPEC-017).
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router";
import {
  api,
  carregarBase,
  EVENTO_SESSAO_EXPIRADA,
  guardarFazendaSalva,
  lerFazendaSalva,
  lerToken,
  mensagemDeErro,
  sair,
  USAR_API,
} from "./api";
import Login from "../paginas/Login";
import { gerarRecomendacao } from "./agente";
import { hojeNaFazenda } from "./datas";
import { baseInicial, USUARIO, type Base } from "./demo";
import { areaHa } from "./geo";
import { ultimaLeitura } from "./ndvi";
import { lotacaoDe, totalAnimais } from "./rebanho";
import { validarMovimento } from "./regras";
import type { Cliente, Fazenda, GeoJsonPolygon, Lote, Movimentacao, PlanoManejo, Rebanho, Usuario } from "./tipos";

export interface EstadoDemo extends Base {
  plano: PlanoManejo | null;
  lotes: Lote[];
}

export type DadosFazenda = Pick<Fazenda, "nome">;

export interface NovoPiquete {
  nome: string;
  vegetacao: string;
  geometria: GeoJsonPolygon;
}

// As ações devolvem uma mensagem de erro (ou null) quando podem ser recusadas.
interface Contexto {
  modo: "api" | "demo";
  usuario: Usuario;
  estado: EstadoDemo;
  fazenda: Fazenda;
  fazendas: Fazenda[];
  clientes: Cliente[];
  lotes: Lote[];
  hoje: string;
  selecionarFazenda: (fazendaId: string) => void;
  recarregarFazendas: (selecionarId?: string) => Promise<void>;
  salvarFazenda: (dados: DadosFazenda) => Promise<string | null>;
  criarPiquete: (dados: NovoPiquete) => Promise<string>;
  atualizarGeometria: (piqueteId: string, geometria: GeoJsonPolygon) => Promise<string | null>;
  desativarPiquete: (piqueteId: string) => Promise<string | null>;
  gerarPlano: () => Promise<PlanoManejo>;
  salvarLotacao: (piqueteId: string, rebanho: Rebanho) => Promise<string | null>;
  executarMovimentacao: (movimentacaoId: string, destinoId?: string) => Promise<string | null>;
  recusarMovimentacao: (movimentacaoId: string) => Promise<string | null>;
  sair?: () => void; // só no modo API
}

const ContextoFazenda = createContext<Contexto | null>(null);

const FUSO = "America/Maceio";
const espera = (ms: number) => new Promise((r) => setTimeout(r, ms));
const USUARIO_DEMO: Usuario = {
  id: "demo",
  email: "demo@maneja.app",
  nome: USUARIO.nome,
  papel: "cliente",
  cliente_id: null,
};

function recomendar(base: Base, hoje: string, agora?: Date): PlanoManejo {
  const { piquetes, ndvi, clima, lotacao, historico } = base;
  return gerarRecomendacao({ piquetes, ndvi, clima, lotacao, historico }, hoje, agora);
}

function comMovimentacao(plano: PlanoManejo, mov: Movimentacao): PlanoManejo {
  return { ...plano, movimentacoes: plano.movimentacoes.map((m) => (m.id === mov.id ? mov : m)) };
}

function estadoInicial(): EstadoDemo {
  const hoje = hojeNaFazenda(FUSO);
  const base = baseInicial(hoje);
  const geradoAs = new Date();
  geradoAs.setHours(7, 48, 0, 0);
  return { ...base, lotes: [], plano: recomendar(base, hoje, geradoAs) };
}

function ProviderDemo({ children }: { children: ReactNode }) {
  const [estado, setEstado] = useState<EstadoDemo>(estadoInicial);
  const atual = useRef(estado);

  const fazenda = estado.fazenda;
  const fazendaId = fazenda.id;
  const hoje = hojeNaFazenda(fazenda.timezone);

  function alterar(transformar: (e: EstadoDemo) => EstadoDemo): void {
    atual.current = transformar(atual.current);
    setEstado(atual.current);
  }

  async function salvarFazenda(dados: DadosFazenda): Promise<string | null> {
    alterar((e) => ({ ...e, fazenda: { ...e.fazenda, ...dados } }));
    return null;
  }

  async function criarPiquete(dados: NovoPiquete): Promise<string> {
    const id = `pq-${Date.now().toString(36)}`;
    alterar((e) => ({
      ...e,
      piquetes: [
        ...e.piquetes,
        {
          id,
          fazenda_id: fazendaId,
          nome: dados.nome.trim(),
          vegetacao: dados.vegetacao.trim(),
          geometria: dados.geometria,
          area_ha: areaHa(dados.geometria),
        },
      ],
    }));
    return id;
  }

  async function atualizarGeometria(piqueteId: string, geometria: GeoJsonPolygon): Promise<string | null> {
    alterar((e) => ({
      ...e,
      piquetes: e.piquetes.map((p) =>
        p.id === piqueteId ? { ...p, geometria, area_ha: areaHa(geometria) } : p,
      ),
    }));
    return null;
  }

  async function desativarPiquete(piqueteId: string): Promise<string | null> {
    if (lotacaoDe(atual.current.lotacao, piqueteId)) return "Há gado neste piquete. Mova os animais antes de desativar.";
    alterar((e) => ({
      ...e,
      piquetes: e.piquetes.filter((p) => p.id !== piqueteId),
      ndvi: e.ndvi.filter((l) => l.piquete_id !== piqueteId),
      lotacao: e.lotacao.filter((l) => l.piquete_id !== piqueteId),
    }));
    return null;
  }

  async function salvarLotacao(piqueteId: string, rebanho: Rebanho): Promise<string | null> {
    alterar((e) => {
      const outras = e.lotacao.filter((l) => l.piquete_id !== piqueteId);
      if (totalAnimais(rebanho) === 0) return { ...e, lotacao: outras };
      const desde = lotacaoDe(e.lotacao, piqueteId)?.desde ?? hoje;
      return { ...e, lotacao: [...outras, { piquete_id: piqueteId, fazenda_id: fazendaId, ...rebanho, desde }] };
    });
    return null;
  }

  async function gerarPlano(): Promise<PlanoManejo> {
    await espera(1600);
    const plano = recomendar(atual.current, hoje);
    alterar((e) => ({ ...e, plano }));
    return plano;
  }

  async function executarMovimentacao(movimentacaoId: string, destinoId?: string): Promise<string | null> {
    const e = atual.current;
    const plano = e.plano;
    const mov = plano?.movimentacoes.find((m) => m.id === movimentacaoId);
    if (!plano || !mov) return "Movimentação não encontrada.";
    const origem = lotacaoDe(e.lotacao, mov.piquete_origem_id);
    if (!origem) return "O piquete de origem está sem animais. Gere um novo plano.";

    const destinoFinal = destinoId ?? mov.piquete_destino_id;
    const rebanho = { bois: origem.bois, vacas: origem.vacas, bezerros: origem.bezerros };
    const falhas = validarMovimento(destinoFinal, rebanho, { piquetes: e.piquetes, ndvi: e.ndvi, lotacao: e.lotacao, hoje });
    if (falhas.length > 0) return `Não dá para mover: ${falhas.join("; ")}.`;

    const destino = e.piquetes.find((p) => p.id === destinoFinal)!;
    const trocado = destino.id !== mov.piquete_destino_id;
    const registrada: Movimentacao = {
      ...mov,
      rebanho,
      status: trocado ? "trocada" : "aceita",
      destino_trocado: trocado,
      piquete_destino_id: destino.id,
      piquete_destino_nome: destino.nome,
      ndvi_destino: ultimaLeitura(e.ndvi, destino.id, hoje)!.valor,
    };
    alterar((s) => ({
      ...s,
      lotacao: s.lotacao.map((l) => (l === origem ? { ...l, piquete_id: destino.id, desde: hoje } : l)),
      historico: [{ ...registrada, data: hoje }, ...s.historico],
      plano: comMovimentacao(plano, registrada),
    }));
    return null;
  }

  async function recusarMovimentacao(movimentacaoId: string): Promise<string | null> {
    const plano = atual.current.plano;
    const mov = plano?.movimentacoes.find((m) => m.id === movimentacaoId);
    if (!plano || !mov) return "Movimentação não encontrada.";
    const recusada: Movimentacao = { ...mov, status: "recusada" };
    alterar((s) => ({
      ...s,
      historico: [{ ...recusada, data: hoje }, ...s.historico],
      plano: comMovimentacao(plano, recusada),
    }));
    return null;
  }

  return (
    <ContextoFazenda.Provider
      value={{
        modo: "demo",
        usuario: USUARIO_DEMO,
        estado,
        fazenda,
        fazendas: [fazenda],
        clientes: [],
        lotes: [],
        hoje,
        selecionarFazenda: () => undefined,
        recarregarFazendas: async () => undefined,
        salvarFazenda,
        criarPiquete,
        atualizarGeometria,
        desativarPiquete,
        gerarPlano,
        salvarLotacao,
        executarMovimentacao,
        recusarMovimentacao,
      }}
    >
      {children}
    </ContextoFazenda.Provider>
  );
}

// ---------- modo API (multi-fazenda + papéis admin/cliente) ----------

function ProviderApi({ children }: { children: ReactNode }) {
  const navegar = useNavigate();
  const [logado, setLogado] = useState(() => lerToken() !== null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [fazendas, setFazendas] = useState<Fazenda[]>([]);
  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [fazendaAtivaId, setFazendaAtivaId] = useState<string | null>(() => lerFazendaSalva());
  const [estado, setEstado] = useState<EstadoDemo | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const deslogar = useCallback(() => {
    sair();
    setUsuario(null);
    setFazendas([]);
    setClientes([]);
    setFazendaAtivaId(null);
    setEstado(null);
    setLogado(false);
    navegar("/mapa", { replace: true });
  }, [navegar]);

  // 401 em qualquer chamada: volta para o login (critério de qualidade 4.2)
  useEffect(() => {
    const expirou = () => {
      deslogar();
      setAviso("Sua sessão expirou. Entre de novo.");
    };
    window.addEventListener(EVENTO_SESSAO_EXPIRADA, expirou);
    return () => window.removeEventListener(EVENTO_SESSAO_EXPIRADA, expirou);
  }, [deslogar]);

  const carregarSessaoEFazendas = useCallback(async (preferida?: string): Promise<string | null> => {
    const [me, lista] = await Promise.all([api.me(), api.fazendas()]);
    const listaClientes = me.papel === "admin" ? await api.clientes().catch(() => []) : [];
    setUsuario(me);
    setFazendas(lista);
    setClientes(listaClientes);
    const salva = preferida ?? lerFazendaSalva();
    const valida = salva && lista.some((f) => f.id === salva) ? salva : (lista[0]?.id ?? null);
    setFazendaAtivaId(valida);
    guardarFazendaSalva(valida);
    setErro(null);
    return valida;
  }, []);

  const recarregarFazendaAtiva = useCallback(async (id: string): Promise<EstadoDemo> => {
    const base = await carregarBase(id);
    setEstado(base);
    setErro(null);
    return base;
  }, []);

  useEffect(() => {
    if (!logado) return;
    carregarSessaoEFazendas().catch((e: unknown) => setErro(mensagemDeErro(e)));
  }, [logado, carregarSessaoEFazendas]);

  useEffect(() => {
    if (!logado || !fazendaAtivaId) return;
    recarregarFazendaAtiva(fazendaAtivaId).catch((e: unknown) => setErro(mensagemDeErro(e)));
  }, [logado, fazendaAtivaId, recarregarFazendaAtiva]);

  const selecionarFazenda = useCallback((id: string) => {
    guardarFazendaSalva(id);
    setFazendaAtivaId(id);
  }, []);

  const recarregarFazendas = useCallback(async (selecionarId?: string) => {
    const escolhida = await carregarSessaoEFazendas(selecionarId);
    if (escolhida) {
      await recarregarFazendaAtiva(escolhida);
    }
  }, [carregarSessaoEFazendas, recarregarFazendaAtiva]);

  if (!logado) {
    return (
      <Login
        aviso={aviso}
        aoEntrar={() => {
          setAviso(null);
          setErro(null);
          setLogado(true);
        }}
      />
    );
  }

  if (erro !== null && usuario === null) {
    return (
      <div className="pagina" style={{ margin: "40px auto", padding: "0 16px" }}>
        <section className="cartao formulario">
          <h1 className="cartao-titulo">Não foi possível conectar ao Maneja</h1>
          <p className="aviso-erro" role="alert">{erro}</p>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              className="botao botao-primario"
              type="button"
              onClick={() => {
                setErro(null);
                carregarSessaoEFazendas().catch((e: unknown) => setErro(mensagemDeErro(e)));
              }}
            >
              Tentar novamente
            </button>
            <button className="botao botao-secundario" type="button" onClick={deslogar}>
              Sair
            </button>
          </div>
        </section>
      </div>
    );
  }

  if (usuario === null) {
    return <p style={{ margin: 24 }}>Carregando sessão…</p>;
  }

  if (fazendas.length === 0 && usuario.papel !== "admin") {
    return (
      <div className="pagina" style={{ margin: "40px auto", padding: "0 16px" }}>
        <section className="cartao">
          <h1 className="pagina-titulo">Bem-vindo, {usuario.nome || usuario.email}</h1>
          <p className="cartao-subtitulo" style={{ marginTop: 8 }}>
            Nenhuma fazenda foi vinculada à sua conta ainda. Fale com o administrador para cadastrar ou vincular sua fazenda.
          </p>
          <div style={{ marginTop: 16 }}>
            <button className="botao botao-secundario" type="button" onClick={deslogar}>Sair</button>
          </div>
        </section>
      </div>
    );
  }

  if (fazendaAtivaId && estado === null) {
    if (erro !== null) {
      return (
        <div className="pagina" style={{ margin: "40px auto", padding: "0 16px" }}>
          <section className="cartao formulario">
            <h1 className="cartao-titulo">Erro ao carregar a fazenda</h1>
            <p className="aviso-erro" role="alert">{erro}</p>
            <div>
              <button
                className="botao botao-primario"
                type="button"
                onClick={() => {
                  setErro(null);
                  recarregarFazendaAtiva(fazendaAtivaId).catch((e: unknown) => setErro(mensagemDeErro(e)));
                }}
              >
                Tentar novamente
              </button>
            </div>
          </section>
        </div>
      );
    }
    return <p style={{ margin: 24 }}>Carregando dados da fazenda…</p>;
  }

  const fazendaVazia: Fazenda = { id: "", nome: "Sem fazenda", timezone: FUSO };
  const estadoSeguro: EstadoDemo = estado ?? {
    fazenda: fazendaVazia,
    piquetes: [],
    lotacao: [],
    lotes: [],
    ndvi: [],
    clima: { fazenda_id: "", dias: [] },
    historico: [],
    plano: null,
  };
  const fazenda = estadoSeguro.fazenda;

  async function acao(fazer: () => Promise<unknown>): Promise<string | null> {
    if (!fazenda.id) return "Nenhuma fazenda selecionada.";
    try {
      await fazer();
      await recarregarFazendaAtiva(fazenda.id);
      return null;
    } catch (e) {
      return mensagemDeErro(e);
    }
  }

  const valor: Contexto = {
    modo: "api",
    usuario,
    estado: estadoSeguro,
    fazenda,
    fazendas,
    clientes,
    lotes: estadoSeguro.lotes,
    hoje: hojeNaFazenda(fazenda.timezone),
    selecionarFazenda,
    recarregarFazendas,
    salvarFazenda: async (dados) => {
      const falha = await acao(() => api.salvarFazenda(fazenda.id, dados.nome));
      if (!falha) await carregarSessaoEFazendas(fazenda.id);
      return falha;
    },
    criarPiquete: async (dados) => {
      const piquete = await api.criarPiquete(fazenda.id, dados.nome.trim(), dados.vegetacao.trim(), dados.geometria);
      await recarregarFazendaAtiva(fazenda.id);
      return piquete.id;
    },
    atualizarGeometria: (id, geometria) => acao(() => api.atualizarGeometria(fazenda.id, id, geometria)),
    desativarPiquete: (id) => acao(() => api.removerPiquete(fazenda.id, id)),
    gerarPlano: async () => {
      const plano = await api.gerarPlano(fazenda.id);
      await recarregarFazendaAtiva(fazenda.id);
      return plano;
    },
    salvarLotacao: (id, rebanho) => acao(() => api.salvarLotacao(fazenda.id, id, rebanho)),
    executarMovimentacao: (id, destinoId) => acao(() => api.aceitar(fazenda.id, id, destinoId)),
    recusarMovimentacao: (id) => acao(() => api.recusar(fazenda.id, id)),
    sair: deslogar,
  };
  return <ContextoFazenda.Provider value={valor}>{children}</ContextoFazenda.Provider>;
}

export function FazendaProvider({ children }: { children: ReactNode }) {
  return USAR_API ? <ProviderApi>{children}</ProviderApi> : <ProviderDemo>{children}</ProviderDemo>;
}

export function useFazenda(): Contexto {
  const ctx = useContext(ContextoFazenda);
  if (ctx === null) throw new Error("useFazenda fora do FazendaProvider");
  return ctx;
}
