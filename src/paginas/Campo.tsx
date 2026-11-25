import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, mensagemDeErro } from "../lib/api";
import { dataCurta } from "../lib/datas";
import { useFazenda } from "../lib/fazenda";
import type { Coleira, OcupacaoPiquete, Verificacao } from "../lib/tipos";
import "./Campo.css";

const STATUS = {
  cumprida: "Cumprida", pendente: "Pendente", divergente: "Divergente",
  sem_dados: "Sem dados", sem_vinculo: "Sem vínculo",
};
const SITUACAO = { confere: "Confere", diverge: "Diverge", sem_coleiras: "Sem coleiras" };
const MOSTRAR_SIMULADOR = import.meta.env.VITE_MODO_DEMO === "1";
const PERCENTUAL = new Intl.NumberFormat("pt-BR", { style: "percent" });

export default function Campo() {
  const { modo, usuario, fazenda, estado, lotes } = useFazenda();
  const [ocupacao, setOcupacao] = useState<OcupacaoPiquete[]>([]);
  const [verificacoes, setVerificacoes] = useState<Verificacao[]>([]);
  const [coleiras, setColeiras] = useState<Coleira[]>([]);
  const [avisos, setAvisos] = useState<string[]>([]);
  const [erro, setErro] = useState("");
  const [avisoOk, setAvisoOk] = useState("");
  const [carregando, setCarregando] = useState(true);
  const [ocupado, setOcupado] = useState(false);
  const [movimento, setMovimento] = useState("");
  const [piquete, setPiquete] = useState("");

  // Formulário para associar coleiras GPS a lote ou piquete
  const [destinoColeira, setDestinoColeira] = useState("");
  const [categoriaColeira, setCategoriaColeira] = useState("boi");
  const [quantidadeColeira, setQuantidadeColeira] = useState(3);

  const nomes = new Map(estado.piquetes.map((p) => [p.id, p.nome]));
  const nomesLote = new Map(lotes.map((l) => [l.id, l.nome]));
  // Aceita movimentações tanto do Maneja quanto do PiqueTech/SeuGado no simulador (SPEC-018)
  const movimentos = verificacoes.filter((v) => v.status !== "sem_vinculo");

  const consultar = useCallback(async () => {
    if (!fazenda.id) return;
    const [posicoes, resultado, listaColeiras] = await Promise.all([
      api.ocupacao(fazenda.id),
      api.verificacoes(fazenda.id),
      api.coleiras(fazenda.id),
    ]);
    setOcupacao(posicoes);
    setVerificacoes(resultado.verificacoes);
    setAvisos(resultado.avisos);
    setColeiras(listaColeiras);
  }, [fazenda.id]);

  useEffect(() => {
    if (modo !== "api" || !fazenda.id) return;
    setCarregando(true);
    setErro("");
    setMovimento("");
    setPiquete("");
    setDestinoColeira("");
    Promise.resolve().then(consultar).catch((falha: unknown) => setErro(mensagemDeErro(falha)))
      .finally(() => setCarregando(false));
  }, [modo, fazenda.id, consultar]);

  async function simular(acao: () => Promise<unknown>) {
    setOcupado(true);
    setErro("");
    setAvisoOk("");
    try {
      await acao();
      await consultar();
    } catch (falha) {
      setErro(mensagemDeErro(falha));
    } finally {
      setOcupado(false);
    }
  }

  async function associarColeiras(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    if (!fazenda.id || !destinoColeira) return;
    const [tipo, id] = destinoColeira.split(":");
    await simular(async () => {
      await api.criarColeiras(fazenda.id, {
        lote_id: tipo === "lote" ? id : null,
        piquete_id: tipo === "piquete" ? id : null,
        categoria: categoriaColeira,
        quantidade: quantidadeColeira,
      });
      setAvisoOk(`${quantidadeColeira} coleira(s) associada(s) com sucesso.`);
    });
  }

  return (
    <div className="pagina campo-pagina">
      <div className="pagina-cabecalho">
        <div>
          <h1 className="pagina-titulo">Campo</h1>
          <p className="cartao-subtitulo">{fazenda.nome}</p>
        </div>
      </div>
      {modo !== "api" ? <p className="cartao cartao-subtitulo">Conecte a API do Maneja para acompanhar as coleiras e as movimentações.</p> : (
        <>
          {erro && <p role="alert" className="aviso-erro">{erro}</p>}
          {avisoOk && <p role="status" className="aviso-info">{avisoOk}</p>}
          {carregando && <p role="status" className="cartao-subtitulo">Consultando dados do campo…</p>}
          {avisos.includes("plano_externo_indisponivel") && <p role="status" className="aviso-alerta">Plano do PiqueTech indisponível.</p>}

          {MOSTRAR_SIMULADOR && (
            <form className="cartao campo-simulador" onSubmit={(evento) => {
              evento.preventDefault();
              void simular(() => api.moverColeiras(fazenda.id, movimento, piquete));
            }}>
              <h2 className="cartao-titulo">Simulador do campo</h2>
              <label className="campo">Movimentação
                <select className="campo-entrada" required value={movimento} onChange={(evento) => {
                  const id = evento.target.value;
                  setMovimento(id);
                  const selecionada = movimentos.find((m) => m.movimentacao_id === id);
                  if (selecionada?.piquete_destino_id) setPiquete(selecionada.piquete_destino_id);
                }}>
                  <option value="">Selecione</option>
                  {movimentos.map((v) => (
                    <option key={v.movimentacao_id} value={v.movimentacao_id}>
                      {v.origem_plano === "seugado" ? "[PiqueTech] " : ""}
                      {nomes.get(v.piquete_origem_id ?? "")} → {nomes.get(v.piquete_destino_id ?? "")}
                      {" · "}{dataCurta(v.data)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="campo">Piquete observado
                <select className="campo-entrada" required value={piquete} onChange={(evento) => setPiquete(evento.target.value)}>
                  <option value="">Selecione</option>
                  {estado.piquetes.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
                </select>
              </label>
              <button className="botao botao-primario" disabled={ocupado || !movimento || !piquete}>Levar gado no campo</button>
              <button className="botao botao-secundario" type="button" disabled={ocupado}
                onClick={() => void simular(() => api.avancarCampo(fazenda.id))}>Avançar 1 dia</button>
            </form>
          )}

          {usuario.papel === "admin" && estado.piquetes.length > 0 && (
            <form className="cartao campo-simulador" onSubmit={(e) => void associarColeiras(e)}>
              <h2 className="cartao-titulo">Associar coleiras GPS ({coleiras.length} ativas)</h2>
              <label className="campo">Lote ou piquete
                <select className="campo-entrada" required value={destinoColeira} onChange={(e) => setDestinoColeira(e.target.value)}>
                  <option value="">Selecione…</option>
                  {lotes.filter((l) => l.piquete_atual_id).map((l) => (
                    <option key={`lote:${l.id}`} value={`lote:${l.id}`}>
                      Lote: {l.nome} ({nomes.get(l.piquete_atual_id ?? "") ?? "sem piquete"})
                    </option>
                  ))}
                  {estado.piquetes.map((p) => (
                    <option key={`piquete:${p.id}`} value={`piquete:${p.id}`}>
                      Piquete: {p.nome}
                    </option>
                  ))}
                </select>
              </label>
              <label className="campo">Categoria
                <select className="campo-entrada" value={categoriaColeira} onChange={(e) => setCategoriaColeira(e.target.value)}>
                  <option value="boi">Boi</option>
                  <option value="vaca">Vaca</option>
                  <option value="bezerro">Bezerro</option>
                </select>
              </label>
              <label className="campo">Quantidade
                <input className="campo-entrada" type="number" min={1} max={50} required
                  value={quantidadeColeira} onChange={(e) => setQuantidadeColeira(Math.max(1, Number(e.target.value) || 1))} />
              </label>
              <button className="botao botao-primario" type="submit" disabled={ocupado || !destinoColeira}>
                Associar coleiras
              </button>
            </form>
          )}

          <section className="cartao" aria-labelledby="ocupacao-titulo">
            <h2 className="cartao-titulo" id="ocupacao-titulo">Ocupação por piquete</h2>
            {ocupacao.length > 0 ? (
              <table className="campo-tabela">
                <thead><tr>
                  <th scope="col">Piquete</th>
                  <th scope="col" aria-label="Esperadas">
                    <span className="campo-coluna-longa">Esperadas</span><span className="campo-coluna-curta">Esp.</span>
                  </th>
                  <th scope="col" aria-label="Observadas">
                    <span className="campo-coluna-longa">Observadas</span><span className="campo-coluna-curta">Obs.</span>
                  </th>
                  <th scope="col">Sem sinal</th><th scope="col">Situação</th>
                </tr></thead>
                <tbody>{ocupacao.map((p) => (
                  <tr key={p.piquete_id}>
                    <th scope="row">{p.nome}</th><td>{p.coleiras_esperadas}</td>
                    <td>{p.coleiras_observadas}</td><td>{p.sem_sinal}</td>
                    <td><span className={`campo-status ${p.situacao}`}>{SITUACAO[p.situacao]}</span></td>
                  </tr>
                ))}</tbody>
              </table>
            ) : !carregando && <p>Nenhuma ocupação disponível.</p>}
          </section>

          <section className="cartao">
            <h2 className="cartao-titulo">Planejado × realizado</h2>
            {verificacoes.length > 0 ? (
              <ul className="campo-verificacoes">{verificacoes.map((v) => (
                <li key={`${v.origem_plano}:${v.movimentacao_id}`}>
                  <strong>{nomes.get(v.piquete_origem_id ?? "") ?? "Origem sem vínculo"} → {nomes.get(v.piquete_destino_id ?? "") ?? "Destino sem vínculo"}</strong>
                  <span>{v.origem_plano === "maneja" ? "Maneja" : "PiqueTech"} · {dataCurta(v.data)}</span>
                  <span className={`campo-status ${v.status}`}>{STATUS[v.status]}</span>
                  <span>{v.fracao_no_destino === null ? "Sem fração observada" : `${PERCENTUAL.format(v.fracao_no_destino)} no destino`}</span>
                </li>
              ))}</ul>
            ) : !carregando && <p>Nenhuma movimentação para verificar.</p>}
          </section>

          {coleiras.length > 0 && lotes.length > 0 && (
            <section className="cartao">
              <h2 className="cartao-titulo">Coleiras associadas ({coleiras.length})</h2>
              <p className="cartao-subtitulo">
                {lotes.map((l) => {
                  const qtd = coleiras.filter((c) => c.lote_id === l.id).length;
                  return `${nomesLote.get(l.id)}: ${qtd} coleira(s)`;
                }).join(" · ")}
              </p>
            </section>
          )}
        </>
      )}
    </div>
  );
}
