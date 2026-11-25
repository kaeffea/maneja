import { useState } from "react";
import FormularioFazenda from "../componentes/ui/FormularioFazenda";
import { api, mensagemDeErro } from "../lib/api";
import { useFazenda } from "../lib/fazenda";

export default function Configuracoes() {
  const { modo, usuario, fazenda, salvarFazenda, recarregarFazendas } = useFazenda();
  const [sincronizando, setSincronizando] = useState(false);
  const [mensagem, setMensagem] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  async function atualizarPiqueTech() {
    setSincronizando(true);
    setMensagem(null);
    setErro(null);
    try {
      const r = await api.piquetechAtualizar(fazenda.id);
      await recarregarFazendas(fazenda.id);
      setMensagem(
        `Atualizado do PiqueTech: ${r.piquetes_importados} piquete(s), ${r.lotes_importados} lote(s)` +
        (r.piquetes_inativados > 0 ? `, ${r.piquetes_inativados} inativado(s).` : "."),
      );
    } catch (e) {
      setErro(mensagemDeErro(e));
    } finally {
      setSincronizando(false);
    }
  }

  return (
    <div className="pagina">
      <div className="pagina-cabecalho">
        <h1 className="pagina-titulo">Fazenda</h1>
      </div>

      <section className="cartao">
        <FormularioFazenda key={fazenda.id} inicial={fazenda} aoEnviar={salvarFazenda} />
      </section>

      {modo === "api" && (
        <section className="cartao formulario">
          <div className="pagina-cabecalho">
            <div>
              <h2 className="cartao-titulo">Integração com o PiqueTech</h2>
              <p className="cartao-subtitulo">
                {fazenda.seugado_id
                  ? `Vinculada ao PiqueTech (UUID ${fazenda.seugado_id}). O cadastro de piquetes e lotes vem do PiqueTech.`
                  : "Esta fazenda opera apenas no Maneja (sem vínculo com o PiqueTech)."}
              </p>
            </div>
            <span className={fazenda.seugado_id ? "selo selo-alta" : "selo selo-media"}>
              {fazenda.seugado_id ? "Integrada" : "Somente Maneja"}
            </span>
          </div>
          {erro ? <p className="aviso-erro" role="alert">{erro}</p> : null}
          {mensagem ? <p className="aviso-info" role="status">{mensagem}</p> : null}
          {usuario.papel === "admin" && fazenda.seugado_id ? (
            <div>
              <button
                className="botao botao-secundario"
                type="button"
                disabled={sincronizando}
                onClick={() => void atualizarPiqueTech()}
              >
                {sincronizando ? "Atualizando…" : "Atualizar do PiqueTech"}
              </button>
            </div>
          ) : null}
        </section>
      )}
    </div>
  );
}
