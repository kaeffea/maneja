import { useEffect, useId, useRef, useState } from "react";
import { Icone } from "./Icones";
import "./Seletor.css";

export interface OpcaoSeletor {
  valor: string;
  rotulo: string;
  detalhe?: string;
}

interface Props {
  valor: string;
  opcoes: OpcaoSeletor[];
  aoMudar: (valor: string) => void;
  placeholder?: string;
  desabilitado?: boolean;
  ariaLabel?: string;
  className?: string;
}

export default function Seletor({
  valor,
  opcoes,
  aoMudar,
  placeholder = "Selecione…",
  desabilitado = false,
  ariaLabel,
  className = "",
}: Props) {
  const [aberto, setAberto] = useState(false);
  const [indiceAtivo, setIndiceAtivo] = useState(-1);
  const raizRef = useRef<HTMLDivElement>(null);
  const listaId = useId();

  const selecionada = opcoes.find((o) => o.valor === valor) ?? null;

  useEffect(() => {
    if (!aberto) return;
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
  }, [aberto]);

  function alternar() {
    if (desabilitado) return;
    setAberto((atual) => {
      const proximo = !atual;
      if (proximo) {
        const idx = opcoes.findIndex((o) => o.valor === valor);
        setIndiceAtivo(idx >= 0 ? idx : 0);
      }
      return proximo;
    });
  }

  function escolher(novoValor: string) {
    aoMudar(novoValor);
    setAberto(false);
  }

  function aoTeclarBotao(e: React.KeyboardEvent<HTMLButtonElement>) {
    if (desabilitado) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!aberto) {
        alternar();
        return;
      }
      const delta = e.key === "ArrowDown" ? 1 : -1;
      setIndiceAtivo((i) => (i + delta + opcoes.length) % Math.max(1, opcoes.length));
    } else if (e.key === "Enter" && aberto && indiceAtivo >= 0 && opcoes[indiceAtivo]) {
      e.preventDefault();
      escolher(opcoes[indiceAtivo].valor);
    }
  }

  return (
    <div ref={raizRef} className={`seletor ${aberto ? "aberto" : ""} ${className}`.trim()}>
      <button
        type="button"
        role="combobox"
        aria-expanded={aberto}
        aria-controls={listaId}
        aria-haspopup="listbox"
        aria-label={ariaLabel}
        disabled={desabilitado}
        className={`seletor-gatilho${selecionada ? "" : " vazio"}`}
        onClick={alternar}
        onKeyDown={aoTeclarBotao}
      >
        <span className="seletor-texto">{selecionada ? selecionada.rotulo : placeholder}</span>
        <span className="seletor-seta" aria-hidden="true">
          <Icone nome="seta-baixo" />
        </span>
      </button>

      {aberto && (
        <ul id={listaId} role="listbox" className="seletor-menu">
          {opcoes.length === 0 ? (
            <li className="seletor-vazio">Nenhuma opção disponível</li>
          ) : (
            opcoes.map((opcao, idx) => {
              const ativo = opcao.valor === valor;
              const focado = idx === indiceAtivo;
              return (
                <li
                  key={opcao.valor}
                  role="option"
                  aria-selected={ativo}
                  className={`seletor-opcao${ativo ? " selecionada" : ""}${focado ? " focada" : ""}`}
                  onMouseEnter={() => setIndiceAtivo(idx)}
                  onClick={() => escolher(opcao.valor)}
                >
                  <span className="seletor-opcao-conteudo">
                    <span className="seletor-opcao-rotulo">{opcao.rotulo}</span>
                    {opcao.detalhe ? <span className="seletor-opcao-detalhe">{opcao.detalhe}</span> : null}
                  </span>
                  {ativo ? (
                    <span className="seletor-check" aria-hidden="true">
                      <Icone nome="check" />
                    </span>
                  ) : null}
                </li>
              );
            })
          )}
        </ul>
      )}
    </div>
  );
}
