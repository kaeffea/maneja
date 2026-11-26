import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import { useFazenda } from "../lib/fazenda";
import { Icone } from "./ui/Icones";
import "./SeletorContexto.css";

const SEM_CLIENTE = "__sem_cliente__";

export default function SeletorContexto() {
  const { modo, usuario, fazenda, fazendas, clientes, selecionarFazenda } = useFazenda();
  const [aberto, setAberto] = useState(false);
  const [clienteSelecionado, setClienteSelecionado] = useState<string>("");
  const raizRef = useRef<HTMLDivElement>(null);

  const ehAdmin = modo === "api" && usuario.papel === "admin";
  const podeTrocar = ehAdmin ? fazendas.length > 0 : fazendas.length > 1;

  // Agrupa fazendas por cliente para navegação Cliente → Fazenda (admin)
  const grupos = useMemo(() => {
    const mapa = new Map<string, { id: string; nome: string; contato: string; fazendas: typeof fazendas }>();
    for (const c of clientes) {
      mapa.set(c.id, { id: c.id, nome: c.nome, contato: c.contato, fazendas: [] });
    }
    for (const f of fazendas) {
      const cid = f.cliente_id ?? SEM_CLIENTE;
      if (!mapa.has(cid)) {
        mapa.set(cid, {
          id: cid,
          nome: cid === SEM_CLIENTE ? "Sem cliente vinculado" : "Cliente",
          contato: "",
          fazendas: [],
        });
      }
      mapa.get(cid)!.fazendas.push(f);
    }
    return [...mapa.values()].filter((g) => g.fazendas.length > 0 || g.id !== SEM_CLIENTE);
  }, [clientes, fazendas]);

  const clienteAtivo = useMemo(() => {
    if (!fazenda.cliente_id) return null;
    return clientes.find((c) => c.id === fazenda.cliente_id) ?? null;
  }, [clientes, fazenda.cliente_id]);

  useEffect(() => {
    if (!aberto) return;
    const inicial = fazenda.cliente_id ?? (grupos[0]?.id ?? SEM_CLIENTE);
    setClienteSelecionado(inicial);

    const aoClicarFora = (e: MouseEvent) => {
      if (raizRef.current && !raizRef.current.contains(e.target as Node)) {
        setAberto(false);
      }
    };
    const aoTeclar = (e: KeyboardEvent) => {
      if (e.key === "Escape") setAberto(false);
    };
    document.addEventListener("mousedown", aoClicarFora);
    document.addEventListener("keydown", aoTeclar);
    return () => {
      document.removeEventListener("mousedown", aoClicarFora);
      document.removeEventListener("keydown", aoTeclar);
    };
  }, [aberto, fazenda.cliente_id, grupos]);

  if (!fazenda.id && !ehAdmin) return null;

  if (!podeTrocar) {
    return (
      <div className="contexto-estatico" title={fazenda.nome}>
        <span className="contexto-fazenda-nome">{fazenda.nome}</span>
      </div>
    );
  }

  const grupoAtual = grupos.find((g) => g.id === clienteSelecionado) ?? grupos[0] ?? null;

  return (
    <div ref={raizRef} className={`contexto${aberto ? " aberto" : ""}`}>
      <button
        type="button"
        className="contexto-gatilho"
        aria-expanded={aberto}
        aria-haspopup="dialog"
        aria-label="Selecionar cliente e fazenda"
        onClick={() => setAberto((v) => !v)}
      >
        <span className="contexto-labels">
          {ehAdmin && clienteAtivo ? <span className="contexto-cliente">{clienteAtivo.nome}</span> : null}
          <span className="contexto-fazenda">{fazenda.nome}</span>
        </span>
        <span className="contexto-seta" aria-hidden="true">
          <Icone nome="seta-baixo" />
        </span>
      </button>

      {aberto && (
        <div className={`contexto-painel${ehAdmin ? " dois-niveis" : ""}`} role="dialog" aria-label="Trocar fazenda">
          {ehAdmin ? (
            <>
              <div className="contexto-coluna">
                <div className="contexto-coluna-titulo">1. Cliente</div>
                <ul className="contexto-lista">
                  {grupos.map((g) => {
                    const ativo = grupoAtual?.id === g.id;
                    return (
                      <li key={g.id}>
                        <button
                          type="button"
                          className={`contexto-item${ativo ? " selecionado" : ""}`}
                          onClick={() => setClienteSelecionado(g.id)}
                        >
                          <span className="contexto-item-texto">
                            <strong>{g.nome}</strong>
                            <small>{g.fazendas.length} {g.fazendas.length === 1 ? "fazenda" : "fazendas"}</small>
                          </span>
                          <span className="contexto-item-icone" aria-hidden="true">
                            <Icone nome="seta" />
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>

              <div className="contexto-coluna">
                <div className="contexto-coluna-titulo">
                  2. Fazendas{grupoAtual ? ` · ${grupoAtual.nome}` : ""}
                </div>
                {grupoAtual && grupoAtual.fazendas.length > 0 ? (
                  <ul className="contexto-lista">
                    {grupoAtual.fazendas.map((f) => {
                      const ativa = f.id === fazenda.id;
                      return (
                        <li key={f.id}>
                          <button
                            type="button"
                            className={`contexto-item${ativa ? " ativa" : ""}`}
                            onClick={() => {
                              selecionarFazenda(f.id);
                              setAberto(false);
                            }}
                          >
                            <span className="contexto-item-texto">
                              <strong>{f.nome}</strong>
                              <small>{f.seugado_id ? "Integrada ao PiqueTech" : "Somente Maneja"}</small>
                            </span>
                            {ativa ? (
                              <span className="contexto-check" aria-hidden="true">
                                <Icone nome="check" />
                              </span>
                            ) : null}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                ) : (
                  <p className="contexto-vazio">Este cliente ainda não possui fazendas cadastradas.</p>
                )}
              </div>

              <div className="contexto-rodape">
                <Link to="/admin" className="contexto-rodape-link" onClick={() => setAberto(false)}>
                  Gerenciar clientes e fazendas →
                </Link>
              </div>
            </>
          ) : (
            <div className="contexto-coluna">
              <div className="contexto-coluna-titulo">Suas fazendas</div>
              <ul className="contexto-lista">
                {fazendas.map((f) => {
                  const ativa = f.id === fazenda.id;
                  return (
                    <li key={f.id}>
                      <button
                        type="button"
                        className={`contexto-item${ativa ? " ativa" : ""}`}
                        onClick={() => {
                          selecionarFazenda(f.id);
                          setAberto(false);
                        }}
                      >
                        <span className="contexto-item-texto">
                          <strong>{f.nome}</strong>
                          <small>{f.timezone}</small>
                        </span>
                        {ativa ? (
                          <span className="contexto-check" aria-hidden="true">
                            <Icone nome="check" />
                          </span>
                        ) : null}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
