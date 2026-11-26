import "./Interruptor.css";

interface Props {
  marcado: boolean;
  aoMudar: (marcado: boolean) => void;
  rotulo: string;
  descricao?: string;
  desabilitado?: boolean;
}

export default function Interruptor({ marcado, aoMudar, rotulo, descricao, desabilitado = false }: Props) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={marcado}
      disabled={desabilitado}
      className={`interruptor${marcado ? " ativo" : ""}`}
      onClick={() => aoMudar(!marcado)}
    >
      <span className="interruptor-texto">
        <span className="interruptor-rotulo">{rotulo}</span>
        {descricao ? <span className="interruptor-descricao">{descricao}</span> : null}
      </span>
      <span className="interruptor-trilho" aria-hidden="true">
        <span className="interruptor-bolinha" />
      </span>
    </button>
  );
}
