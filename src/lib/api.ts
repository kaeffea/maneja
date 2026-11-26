// Cliente da API do Maneja (backend/). Só é usado quando VITE_API_URL está definida;
// sem ela o front roda no modo demonstração (dados de demo.ts), como antes (decisão D7).

import type { Base } from "./demo";
import type {
  Cliente,
  Coleira,
  CultivarPiqueTech,
  Fazenda,
  FazendaPiqueTech,
  GeoJsonPolygon,
  Lotacao,
  Lote,
  Movimentacao,
  OcupacaoPiquete,
  PapelUsuario,
  Piquete,
  PlanoManejo,
  Rebanho,
  ResultadoExportacao,
  ResultadoImportacao,
  Usuario,
  Verificacao,
} from "./tipos";

export const API_URL: string = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");
export const USAR_API = API_URL !== "";

export class ErroApi extends Error {
  readonly status: number;
  readonly motivos: string[];

  constructor(status: number, motivos: string[]) {
    super(motivos.join("; "));
    this.status = status;
    this.motivos = motivos;
  }
}

// ---------- sessão (SPEC-009 / SPEC-017) ----------
const CHAVE_TOKEN = "maneja.token";
const CHAVE_FAZENDA = "maneja.fazenda_id";
let tokenEmMemoria: string | null = null;

export function lerToken(): string | null {
  try {
    return localStorage.getItem(CHAVE_TOKEN) ?? tokenEmMemoria;
  } catch {
    return tokenEmMemoria;
  }
}

export function guardarToken(token: string | null): void {
  tokenEmMemoria = token;
  try {
    if (token === null) localStorage.removeItem(CHAVE_TOKEN);
    else localStorage.setItem(CHAVE_TOKEN, token);
  } catch {
    // sem armazenamento: fica só em memória
  }
}

export function lerFazendaSalva(): string | null {
  try {
    return localStorage.getItem(CHAVE_FAZENDA);
  } catch {
    return null;
  }
}

export function guardarFazendaSalva(id: string | null): void {
  try {
    if (id === null) localStorage.removeItem(CHAVE_FAZENDA);
    else localStorage.setItem(CHAVE_FAZENDA, id);
  } catch {
    // ignora
  }
}

// Quem quiser saber que a sessão caiu (401) escuta este evento.
export const EVENTO_SESSAO_EXPIRADA = "maneja:sessao-expirada";

async function chamar<T>(metodo: string, caminho: string, corpo?: unknown): Promise<T> {
  let resposta: Response;
  const cabecalhos: Record<string, string> = {};
  if (corpo !== undefined) cabecalhos["Content-Type"] = "application/json";
  const token = lerToken();
  if (token) cabecalhos.Authorization = `Bearer ${token}`;
  try {
    resposta = await fetch(`${API_URL}${caminho}`, {
      method: metodo,
      headers: cabecalhos,
      body: corpo === undefined ? undefined : JSON.stringify(corpo),
    });
  } catch {
    throw new ErroApi(0, [`não foi possível falar com a API em ${API_URL}`]);
  }
  if (resposta.status === 401 && caminho !== "/auth/token") {
    guardarToken(null);
    guardarFazendaSalva(null);
    window.dispatchEvent(new Event(EVENTO_SESSAO_EXPIRADA));
  }
  if (resposta.status === 204) return undefined as T;
  const dados = await resposta.json().catch(() => null);
  if (!resposta.ok) {
    const detalhe = dados?.detail;
    const motivos = Array.isArray(detalhe)
      ? detalhe.map((d: unknown) => (typeof d === "string" ? d : JSON.stringify(d)))
      : [typeof detalhe === "string" ? detalhe : `erro ${resposta.status}`];
    throw new ErroApi(resposta.status, motivos);
  }
  return dados as T;
}

export interface BaseApi extends Base {
  plano: PlanoManejo | null;
  lotes: Lote[];
}

function baseFazenda(fazendaId: string): string {
  return `/fazendas/${encodeURIComponent(fazendaId)}`;
}

export async function carregarBase(fazendaId: string): Promise<BaseApi> {
  const b = baseFazenda(fazendaId);
  const [fazenda, piquetes, lotacao, lotes, ndvi, clima, historico] = await Promise.all([
    chamar<Fazenda>("GET", b),
    chamar<Piquete[]>("GET", `${b}/piquetes`),
    chamar<Lotacao[]>("GET", `${b}/lotacao`),
    chamar<Lote[]>("GET", `${b}/lotes`),
    chamar<Base["ndvi"]>("GET", `${b}/ndvi`),
    chamar<Base["clima"]>("GET", `${b}/clima`),
    chamar<Movimentacao[]>("GET", `${b}/historico`),
  ]);
  const plano = await chamar<PlanoManejo>("GET", `${b}/plano`).catch((e: unknown) => {
    if (e instanceof ErroApi && e.status === 404) return null;
    throw e;
  });
  return { fazenda, piquetes, lotacao, lotes, ndvi, clima, historico, plano };
}

export interface Sessao {
  access_token: string;
  expira_em: string;
  id: string;
  email: string;
  nome: string;
  papel: PapelUsuario;
  cliente_id: string | null;
}

export async function entrar(email: string, senha: string): Promise<Sessao> {
  const sessao = await chamar<Sessao>("POST", "/auth/token", { email, senha });
  guardarToken(sessao.access_token);
  guardarFazendaSalva(null);
  return sessao;
}

export function sair(): void {
  guardarToken(null);
  guardarFazendaSalva(null);
}

export const api = {
  saude: () => chamar<{ status: string; modo_seugado: string }>("GET", "/saude"),
  me: () => chamar<Usuario>("GET", "/me"),
  fazendas: () => chamar<Fazenda[]>("GET", "/fazendas"),

  // Operações da fazenda ativa
  coleiras: (fazendaId: string) => chamar<Coleira[]>("GET", `${baseFazenda(fazendaId)}/coleiras`),
  criarColeiras: (
    fazendaId: string,
    dados: { piquete_id?: string | null; lote_id?: string | null; categoria: string; quantidade: number },
  ) => chamar<Coleira[]>("POST", `${baseFazenda(fazendaId)}/coleiras`, dados),
  removerColeira: (fazendaId: string, coleiraId: string) =>
    chamar<void>("DELETE", `${baseFazenda(fazendaId)}/coleiras/${encodeURIComponent(coleiraId)}`),
  ocupacao: (fazendaId: string) => chamar<OcupacaoPiquete[]>("GET", `${baseFazenda(fazendaId)}/ocupacao`),
  verificacoes: (fazendaId: string) =>
    chamar<{ verificacoes: Verificacao[]; avisos: string[] }>("GET", `${baseFazenda(fazendaId)}/verificacoes`),
  gerarPlano: (fazendaId: string) => chamar<PlanoManejo>("POST", `${baseFazenda(fazendaId)}/plano`),
  aceitar: (fazendaId: string, id: string, destinoId?: string) =>
    chamar<Movimentacao>(
      "POST",
      `${baseFazenda(fazendaId)}/movimentacoes/${encodeURIComponent(id)}/aceitar`,
      destinoId ? { destino_id: destinoId } : undefined,
    ),
  recusar: (fazendaId: string, id: string) =>
    chamar<Movimentacao>("POST", `${baseFazenda(fazendaId)}/movimentacoes/${encodeURIComponent(id)}/recusar`),
  salvarFazenda: (fazendaId: string, nome: string) => chamar<Fazenda>("PUT", baseFazenda(fazendaId), { nome }),
  criarPiquete: (fazendaId: string, nome: string, vegetacao: string, geometria: GeoJsonPolygon) =>
    chamar<Piquete>("POST", `${baseFazenda(fazendaId)}/piquetes`, { nome, vegetacao, geometria }),
  atualizarGeometria: (fazendaId: string, id: string, geometria: GeoJsonPolygon) =>
    chamar<Piquete>("PUT", `${baseFazenda(fazendaId)}/piquetes/${encodeURIComponent(id)}`, { geometria }),
  removerPiquete: (fazendaId: string, id: string) =>
    chamar<void>("DELETE", `${baseFazenda(fazendaId)}/piquetes/${encodeURIComponent(id)}`),
  salvarLotacao: (fazendaId: string, piqueteId: string, r: Rebanho) =>
    chamar<Lotacao>("PUT", `${baseFazenda(fazendaId)}/lotacao/${encodeURIComponent(piqueteId)}`, r),

  // Administração (SPEC-017)
  clientes: () => chamar<Cliente[]>("GET", "/clientes"),
  criarCliente: (dados: { nome: string; contato: string }) => chamar<Cliente>("POST", "/clientes", dados),
  atualizarCliente: (id: string, dados: { nome?: string; contato?: string }) =>
    chamar<Cliente>("PUT", `/clientes/${encodeURIComponent(id)}`, dados),
  criarFazenda: (dados: { nome: string; cliente_id: string | null; timezone: string }) =>
    chamar<Fazenda>("POST", "/fazendas", dados),
  atualizarFazendaAdmin: (id: string, dados: { nome: string; cliente_id?: string | null; timezone?: string }) =>
    chamar<Fazenda>("PUT", baseFazenda(id), dados),
  usuarios: () => chamar<Usuario[]>("GET", "/usuarios"),
  criarUsuario: (dados: {
    email: string;
    senha: string;
    papel: PapelUsuario;
    cliente_id: string | null;
    nome: string;
  }) => chamar<Usuario>("POST", "/usuarios", dados),
  atualizarUsuario: (
    id: string,
    dados: { nome?: string; email?: string; senha?: string; papel?: PapelUsuario; cliente_id?: string | null },
  ) => chamar<Usuario>("PUT", `/usuarios/${encodeURIComponent(id)}`, dados),

  // Integração PiqueTech (SPEC-018)
  piquetechFazendas: () => chamar<FazendaPiqueTech[]>("GET", "/integracao/piquetech/fazendas"),
  piquetechCultivares: () => chamar<CultivarPiqueTech[]>("GET", "/integracao/piquetech/cultivares"),
  piquetechImportar: (seugadoId: string) =>
    chamar<ResultadoImportacao>("POST", `/integracao/piquetech/importar/${encodeURIComponent(seugadoId)}`),
  piquetechAtualizar: (fazendaId: string) =>
    chamar<ResultadoImportacao>("POST", `${baseFazenda(fazendaId)}/integracao/piquetech/atualizar`),
  piquetechExportar: (fazendaId: string, dados: { cultivar_id?: string | null; metodo_pastejo?: string }) =>
    chamar<ResultadoExportacao>("POST", `${baseFazenda(fazendaId)}/integracao/piquetech/exportar`, dados),
};

export function mensagemDeErro(e: unknown): string {
  return e instanceof ErroApi ? e.motivos.join("; ") : "erro inesperado";
}
