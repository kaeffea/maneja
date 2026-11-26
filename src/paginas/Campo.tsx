import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Icone } from "../componentes/ui/Icones";
import Seletor, { type OpcaoSeletor } from "../componentes/ui/Seletor";
import { api, mensagemDeErro } from "../lib/api";
import { dataCurta } from "../lib/datas";
import { useFazenda } from "../lib/fazenda";
import type { Coleira, OcupacaoPiquete, Verificacao } from "../lib/tipos";
import "./Campo.css";

const STATUS = {
  cumprida: "Cumprida",
  pendente: "Pendente",
  divergente: "Divergente",
  sem_dados: "Sem dados",
  sem_vinculo: "Sem vínculo",
};
const SITUACAO = { confere: "Confere", diverge: "Diverge", sem_coleiras: "Sem coleiras" };
const PERCENTUAL = new Intl.NumberFormat("pt-BR", { style: "percent" });

const OPCOES_CATEGORIA: OpcaoSeletor[] = [
  { valor: "boi", rotulo: "Boi" },
  { valor: "vaca", rotulo: "Vaca" },
  { valor: "bezerro", rotulo: "Bezerro" },
];

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

  // Cadastro / associação de coleiras GPS (admin)
  const [destinoColeira, setDestinoColeira] = useState("");
  const [categoriaColeira, setCategoriaColeira] = useState("boi");
  const [quantidadeColeira, setQuantidadeColeira] = useState(3);

  const nomes = useMemo(() => new Map(estado.piquetes.map((p) => [p.id, p.nome])), [estado.piquetes]);
  const nomesLote = useMemo(() => new Map(lotes.map((l) => [l.id, l.nome])), [lotes]);

  const opcoesDestino = useMemo<OpcaoSeletor[]>(() => {
    const lista: OpcaoSeletor[] = [];
    for (const l of lotes) {
      if (!l.piquete_atual_id) continue;
      lista.push({
        valor: `lote:${l.id}`,
        rotulo: `Lote ${l.nome}`,
        detalhe: `Em ${nomes.get(l.piquete_atual_id) ?? "piquete"}`,
      });
    }
    for (const p of estado.piquetes) {
      lista.push({
        valor: `piquete:${p.id}`,
        rotulo: p.nome,
        detalhe: "Piquete",
      });
    }
    return lista;
  }, [lotes, estado.piquetes, nomes]);

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
    setAvisoOk("");
    setDestinoColeira("");
    Promise.resolve()
      .then(consultar)
      .catch((falha: unknown) => setErro(mensagemDeErro(falha)))
      .finally(() => setCarregando(false));
  }, [modo, fazenda.id, consultar]);

  async function executarAcao(acao: () => Promise<void>) {
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
    await executarAcao(async () => {
      await api.criarColeiras(fazenda.id, {
        lote_id: tipo === "lote" ? id : null,
        piquete_id: tipo === "piquete" ? id : null,
        categoria: categoriaColeira,
        quantidade: quantidadeColeira,
      });
      setAvisoOk(`${quantidadeColeira} coleira(s) associada(s) com sucesso.`);
    });
  }

  async function removerColeira(coleiraId: string) {
    if (!fazenda.id) return;
    await executarAcao(async () => {
      await api.removerColeira(fazenda.id, coleiraId);
      setAvisoOk(`Coleira ${coleiraId} removida.`);
    });
  }

  return (
    <div className="pagina campo-pagina">
      <div className="pagina-cabecalho">
        <div>
          <h1 className="pagina-titulo">Campo</h1>
          <p className="cartao-subtitulo">{fazenda.nome} · acompanhamento de coleiras GPS e execução de manejos</p>
        </div>
      </div>

      {modo !== "api" ? (
        <p className="cartao cartao-subtitulo">Conecte a API do Maneja para acompanhar as coleiras e as movimentações.</p>
      ) : (
        <>
          {erro && <p role="alert" className="aviso-erro">{erro}</p>}
          {avisoOk && <p role="status" className="aviso-info">{avisoOk}</p>}
          {carregando && <p role="status" className="cartao-subtitulo">Consultando dados do campo…</p>}
          {avisos.includes("plano_externo_indisponivel") && (
            <p role="status" className="aviso-alerta">Plano do PiqueTech temporariamente indisponível.</p>
          )}

          <section className="cartao" aria-labelledby="ocupacao-titulo">
            <h2 className="cartao-titulo" id="ocupacao-titulo">Ocupação por piquete</h2>
            {ocupacao.length > 0 ? (
              <div className="tabela-rolagem">
                <table className="campo-tabela">
                  <thead>
                    <tr>
                      <th scope="col">Piquete</th>
                      <th scope="col" aria-label="Esperadas">
                        <span className="campo-coluna-longa">Esperadas</span>
                        <span className="campo-coluna-curta">Esp.</span>
                      </th>
                      <th scope="col" aria-label="Observadas">
                        <span className="campo-coluna-longa">Observadas</span>
                        <span className="campo-coluna-curta">Obs.</span>
                      </th>
                      <th scope="col">Sem sinal</th>
                      <th scope="col">Situação</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ocupacao.map((p) => (
                      <tr key={p.piquete_id}>
                        <th scope="row">{p.nome}</th>
                        <td>{p.coleiras_esperadas}</td>
                        <td>{p.coleiras_observadas}</td>
                        <td>{p.sem_sinal}</td>
                        <td>
                          <span className={`campo-status ${p.situacao}`}>{SITUACAO[p.situacao]}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : !carregando && <p className="cartao-subtitulo">Nenhum piquete cadastrado nesta fazenda.</p>}
          </section>

          <section className="cartao">
            <h2 className="cartao-titulo">Planejado × realizado</h2>
            {verificacoes.length > 0 ? (
              <ul className="campo-verificacoes">
                {verificacoes.map((v) => (
                  <li key={`${v.origem_plano}:${v.movimentacao_id}`}>
                    <strong>
                      {nomes.get(v.piquete_origem_id ?? "") ?? "Origem sem vínculo"} →{" "}
                      {nomes.get(v.piquete_destino_id ?? "") ?? "Destino sem vínculo"}
                    </strong>
                    <span className="cartao-subtitulo">
                      {v.origem_plano === "maneja" ? "Maneja" : "PiqueTech"} · {dataCurta(v.data)}
                    </span>
                    <span className={`campo-status ${v.status}`}>{STATUS[v.status]}</span>
                    <span className="cartao-subtitulo">
                      {v.fracao_no_destino === null
                        ? "Sem fração observada"
                        : `${PERCENTUAL.format(v.fracao_no_destino)} no destino`}
                    </span>
                  </li>
                ))}
              </ul>
            ) : !carregando && <p className="cartao-subtitulo">Nenhuma movimentação planejada para verificar no momento.</p>}
          </section>

          {usuario.papel === "admin" && estado.piquetes.length > 0 && (
            <form className="cartao campo-cadastro-coleiras" onSubmit={(e) => void associarColeiras(e)}>
              <h2 className="cartao-titulo">Associar coleiras GPS</h2>
              <p className="cartao-subtitulo campo-span-full">
                Vincule coleiras a um lote ou piquete desta fazenda para acompanhar ocupação e execução.
              </p>
              <div className="campo">
                <span>Lote ou piquete</span>
                <Seletor
                  valor={destinoColeira}
                  opcoes={opcoesDestino}
                  aoMudar={setDestinoColeira}
                  placeholder="Selecione um lote ou piquete…"
                  ariaLabel="Lote ou piquete"
                />
              </div>
              <div className="campo">
                <span>Categoria</span>
                <Seletor
                  valor={categoriaColeira}
                  opcoes={OPCOES_CATEGORIA}
                  aoMudar={setCategoriaColeira}
                  ariaLabel="Categoria"
                />
              </div>
              <label className="campo">
                Quantidade
                <input
                  className="campo-entrada"
                  type="number"
                  min={1}
                  max={50}
                  required
                  value={quantidadeColeira}
                  onChange={(e) => setQuantidadeColeira(Math.max(1, Number(e.target.value) || 1))}
                />
              </label>
              <button className="botao botao-primario" type="submit" disabled={ocupado || !destinoColeira}>
                Associar coleiras
              </button>
            </form>
          )}

          {coleiras.length > 0 && (
            <section className="cartao">
              <div className="pagina-cabecalho" style={{ marginBottom: 10 }}>
                <h2 className="cartao-titulo">Coleiras ativas ({coleiras.length})</h2>
                {lotes.length > 0 && (
                  <span className="cartao-subtitulo">
                    {lotes.map((l) => `${nomesLote.get(l.id)}: ${coleiras.filter((c) => c.lote_id === l.id).length}`).join(" · ")}
                  </span>
                )}
              </div>
              <ul className="campo-coleiras-lista">
                {coleiras.map((c) => (
                  <li key={c.id} className="campo-coleira-item">
                    <div className="campo-coleira-info">
                      <strong>{c.id}</strong>
                      <span className="cartao-subtitulo">
                        {c.categoria}
                        {c.lote_id && nomesLote.get(c.lote_id) ? ` · Lote ${nomesLote.get(c.lote_id)}` : ""}
                        {" · "}Cadastro: {nomes.get(c.piquete_cadastro_id) ?? "Sem piquete"}
                        {c.piquete_observado_id ? ` · Observado: ${nomes.get(c.piquete_observado_id) ?? "—"}` : " · Sem sinal recente"}
                      </span>
                    </div>
                    {usuario.papel === "admin" && (
                      <button
                        type="button"
                        className="campo-coleira-remover"
                        title={`Remover ${c.id}`}
                        aria-label={`Remover ${c.id}`}
                        disabled={ocupado}
                        onClick={() => void removerColeira(c.id)}
                      >
                        <Icone nome="lixeira" />
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  );
}
