import { useCallback, useEffect, useState } from "react";
import { api, mensagemDeErro } from "../lib/api";
import { dataCurta } from "../lib/datas";
import { useFazenda } from "../lib/fazenda";
import type { OcupacaoPiquete, Verificacao } from "../lib/tipos";
import "./Campo.css";

const STATUS = {
  cumprida: "Cumprida", pendente: "Pendente", divergente: "Divergente",
  sem_dados: "Sem dados", sem_vinculo: "Sem vínculo",
};
const SITUACAO = { confere: "Confere", diverge: "Diverge", sem_coleiras: "Sem coleiras" };
const MOSTRAR_SIMULADOR = import.meta.env.VITE_MODO_DEMO === "1";
const PERCENTUAL = new Intl.NumberFormat("pt-BR", { style: "percent" });

export default function Campo() {
  const { modo, estado } = useFazenda();
  const [ocupacao, setOcupacao] = useState<OcupacaoPiquete[]>([]);
  const [verificacoes, setVerificacoes] = useState<Verificacao[]>([]);
  const [avisos, setAvisos] = useState<string[]>([]);
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(true);
  const [ocupado, setOcupado] = useState(false);
  const [movimento, setMovimento] = useState("");
  const [piquete, setPiquete] = useState("");
  const nomes = new Map(estado.piquetes.map((p) => [p.id, p.nome]));
  const movimentos = verificacoes.filter((v) => v.origem_plano === "maneja");

  const consultar = useCallback(async () => {
    const [posicoes, resultado] = await Promise.all([api.ocupacao(), api.verificacoes()]);
    setOcupacao(posicoes);
    setVerificacoes(resultado.verificacoes);
    setAvisos(resultado.avisos);
  }, []);

  useEffect(() => {
    if (modo !== "api") return;
    Promise.resolve().then(consultar).catch((falha: unknown) => setErro(mensagemDeErro(falha)))
      .finally(() => setCarregando(false));
  }, [modo, consultar]);

  async function simular(acao: () => Promise<unknown>) {
    setOcupado(true);
    setErro("");
    try {
      await acao();
      await consultar();
    } catch (falha) {
      setErro(mensagemDeErro(falha));
    } finally {
      setOcupado(false);
    }
  }

  return (
    <div className="campo">
      <h1>Campo</h1>
      {modo !== "api" ? <p>Conecte a API do Maneja para acompanhar as coleiras e as movimentações.</p> : (
        <>
          {erro && <p role="alert" className="mensagem-erro">{erro}</p>}
          {carregando && <p role="status">Consultando dados do campo…</p>}
          {avisos.includes("plano_externo_indisponivel") && <p role="status">Plano do SeuGado indisponível.</p>}
          {MOSTRAR_SIMULADOR && (
            <form className="cartao campo-simulador" onSubmit={(evento) => {
              evento.preventDefault();
              void simular(() => api.moverColeiras(movimento, piquete));
            }}>
              <h2 className="cartao-titulo">Simulador do campo</h2>
              <label>Movimentação
                <select required value={movimento} onChange={(evento) => setMovimento(evento.target.value)}>
                  <option value="">Selecione</option>
                  {movimentos.map((v) => (
                    <option key={v.movimentacao_id} value={v.movimentacao_id}>
                      {nomes.get(v.piquete_origem_id ?? "")} → {nomes.get(v.piquete_destino_id ?? "")}
                      {" · "}{dataCurta(v.data)}
                    </option>
                  ))}
                </select>
              </label>
              <label>Piquete observado
                <select required value={piquete} onChange={(evento) => setPiquete(evento.target.value)}>
                  <option value="">Selecione</option>
                  {estado.piquetes.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
                </select>
              </label>
              <button className="botao-acao" disabled={ocupado || !movimento || !piquete}>Levar gado no campo</button>
              <button className="botao-acao secundario" type="button" disabled={ocupado}
                onClick={() => void simular(api.avancarCampo)}>Avançar 1 dia</button>
            </form>
          )}
          <section className="cartao" aria-labelledby="ocupacao-titulo">
            <h2 className="cartao-titulo" id="ocupacao-titulo">Ocupação por piquete</h2>
            {ocupacao.length > 0 ? (
              <table className="campo-tabela">
                <thead><tr>
                  <th scope="col">Piquete</th><th scope="col">Esperadas</th>
                  <th scope="col">Observadas</th><th scope="col">Sem sinal</th><th scope="col">Situação</th>
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
                  <span>{v.origem_plano === "maneja" ? "Maneja" : "SeuGado"} · {dataCurta(v.data)}</span>
                  <span className={`campo-status ${v.status}`}>{STATUS[v.status]}</span>
                  <span>{v.fracao_no_destino === null ? "Sem fração observada" : `${PERCENTUAL.format(v.fracao_no_destino)} no destino`}</span>
                </li>
              ))}</ul>
            ) : !carregando && <p>Nenhuma movimentação para verificar.</p>}
          </section>
        </>
      )}
    </div>
  );
}
