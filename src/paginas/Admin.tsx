import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router";
import Seletor, { type OpcaoSeletor } from "../componentes/ui/Seletor";
import { api, mensagemDeErro } from "../lib/api";
import { useFazenda } from "../lib/fazenda";
import type {
  Cliente,
  CultivarPiqueTech,
  Fazenda,
  FazendaPiqueTech,
  PapelUsuario,
  Usuario,
} from "../lib/tipos";
import "./Admin.css";

type Aba = "clientes" | "fazendas" | "usuarios" | "piquetech";

const OPCOES_PAPEL: OpcaoSeletor[] = [
  { valor: "cliente", rotulo: "Cliente", detalhe: "Acessa e edita apenas as próprias fazendas" },
  { valor: "admin", rotulo: "Administrador", detalhe: "Gerencia clientes, fazendas, usuários e integrações" },
];

export default function Admin() {
  const { modo, usuario, fazendas: fazendasCtx, selecionarFazenda, recarregarFazendas } = useFazenda();
  const navegar = useNavigate();
  const [aba, setAba] = useState<Aba>("clientes");

  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [fazendas, setFazendas] = useState<Fazenda[]>(fazendasCtx);
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [modoSeugado, setModoSeugado] = useState<string>("desligado");
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  // Novo cliente
  const [novoCliNome, setNovoCliNome] = useState("");
  const [novoCliContato, setNovoCliContato] = useState("");
  const [editCliId, setEditCliId] = useState<string | null>(null);
  const [editCliNome, setEditCliNome] = useState("");
  const [editCliContato, setEditCliContato] = useState("");

  // Fazendas (com filtro por cliente)
  const [filtroClienteId, setFiltroClienteId] = useState("");
  const [novaFazNome, setNovaFazNome] = useState("");
  const [novaFazCliId, setNovaFazCliId] = useState("");
  const [novaFazTz, setNovaFazTz] = useState("America/Maceio");
  const [editFazId, setEditFazId] = useState<string | null>(null);
  const [editFazNome, setEditFazNome] = useState("");
  const [editFazCliId, setEditFazCliId] = useState("");

  // Usuários
  const [novoUsrNome, setNovoUsrNome] = useState("");
  const [novoUsrEmail, setNovoUsrEmail] = useState("");
  const [novoUsrSenha, setNovoUsrSenha] = useState("");
  const [novoUsrPapel, setNovoUsrPapel] = useState<PapelUsuario>("cliente");
  const [novoUsrCliId, setNovoUsrCliId] = useState("");
  const [editUsrId, setEditUsrId] = useState<string | null>(null);
  const [editUsrNome, setEditUsrNome] = useState("");
  const [editUsrEmail, setEditUsrEmail] = useState("");
  const [editUsrSenha, setEditUsrSenha] = useState("");
  const [editUsrPapel, setEditUsrPapel] = useState<PapelUsuario>("cliente");
  const [editUsrCliId, setEditUsrCliId] = useState("");

  // PiqueTech
  const [fazendasPt, setFazendasPt] = useState<FazendaPiqueTech[]>([]);
  const [cultivaresPt, setCultivaresPt] = useState<CultivarPiqueTech[]>([]);
  const [cultivarId, setCultivarId] = useState("");
  const [ptCarregado, setPtCarregado] = useState(false);

  const carregarTudo = useCallback(async () => {
    const [clis, fazs, usrs, saude] = await Promise.all([
      api.clientes(),
      api.fazendas(),
      api.usuarios(),
      api.saude().catch(() => ({ status: "ok", modo_seugado: "desligado" })),
    ]);
    setClientes(clis);
    setFazendas(fazs);
    setUsuarios(usrs);
    setModoSeugado(saude.modo_seugado);
  }, []);

  useEffect(() => {
    if (modo !== "api" || usuario.papel !== "admin") return;
    setCarregando(true);
    carregarTudo()
      .catch((e: unknown) => setErro(mensagemDeErro(e)))
      .finally(() => setCarregando(false));
  }, [modo, usuario.papel, carregarTudo]);

  const opcoesClientes = useMemo<OpcaoSeletor[]>(
    () => clientes.map((c) => ({ valor: c.id, rotulo: c.nome, detalhe: c.contato || undefined })),
    [clientes],
  );

  const opcoesFiltroCliente = useMemo<OpcaoSeletor[]>(
    () => [
      { valor: "", rotulo: "Todos os clientes", detalhe: `${fazendas.length} fazenda(s)` },
      ...clientes.map((c) => ({
        valor: c.id,
        rotulo: c.nome,
        detalhe: `${fazendas.filter((f) => f.cliente_id === c.id).length} fazenda(s)`,
      })),
    ],
    [clientes, fazendas],
  );

  const opcoesClientesOpcional = useMemo<OpcaoSeletor[]>(
    () => [{ valor: "", rotulo: "Sem cliente vinculado" }, ...opcoesClientes],
    [opcoesClientes],
  );

  const opcoesCultivares = useMemo<OpcaoSeletor[]>(
    () =>
      cultivaresPt.map((c) => ({
        valor: c.id,
        rotulo: c.nome,
        detalhe: c.calibrada ? "Calibrada no PiqueTech" : "Em calibração",
      })),
    [cultivaresPt],
  );

  const fazendasFiltradas = useMemo(
    () => (filtroClienteId ? fazendas.filter((f) => f.cliente_id === filtroClienteId) : fazendas),
    [fazendas, filtroClienteId],
  );

  if (modo !== "api" || usuario.papel !== "admin") {
    return <Navigate to="/mapa" replace />;
  }

  const nomeCliente = (id?: string | null) =>
    clientes.find((c) => c.id === id)?.nome ?? "Sem cliente";

  async function executar(fn: () => Promise<void>, msgOk?: string) {
    setOcupado(true);
    setErro(null);
    setAviso(null);
    try {
      await fn();
      await carregarTudo();
      if (msgOk) setAviso(msgOk);
    } catch (e) {
      setErro(mensagemDeErro(e));
    } finally {
      setOcupado(false);
    }
  }

  // ---------- Clientes ----------
  async function criarCliente(e: FormEvent) {
    e.preventDefault();
    await executar(async () => {
      await api.criarCliente({ nome: novoCliNome.trim(), contato: novoCliContato.trim() });
      setNovoCliNome("");
      setNovoCliContato("");
      await recarregarFazendas();
    }, "Cliente criado.");
  }

  async function salvarCliente(e: FormEvent) {
    e.preventDefault();
    if (!editCliId) return;
    await executar(async () => {
      await api.atualizarCliente(editCliId, { nome: editCliNome.trim(), contato: editCliContato.trim() });
      setEditCliId(null);
      await recarregarFazendas();
    }, "Cliente atualizado.");
  }

  // ---------- Fazendas ----------
  async function criarFazenda(e: FormEvent) {
    e.preventDefault();
    if (!novaFazCliId) return;
    await executar(async () => {
      const criada = await api.criarFazenda({
        nome: novaFazNome.trim(),
        cliente_id: novaFazCliId,
        timezone: novaFazTz.trim() || "America/Maceio",
      });
      setNovaFazNome("");
      await recarregarFazendas(criada.id);
    }, "Fazenda criada.");
  }

  async function salvarFazenda(e: FormEvent) {
    e.preventDefault();
    if (!editFazId) return;
    await executar(async () => {
      await api.atualizarFazendaAdmin(editFazId, {
        nome: editFazNome.trim(),
        cliente_id: editFazCliId || null,
      });
      setEditFazId(null);
      await recarregarFazendas();
    }, "Fazenda atualizada.");
  }

  function abrirFazenda(id: string) {
    selecionarFazenda(id);
    navegar("/mapa");
  }

  // ---------- Usuários ----------
  async function criarUsuario(e: FormEvent) {
    e.preventDefault();
    if (novoUsrPapel === "cliente" && !novoUsrCliId) {
      setErro("Selecione o cliente vinculado para este usuário.");
      return;
    }
    await executar(async () => {
      await api.criarUsuario({
        nome: novoUsrNome.trim(),
        email: novoUsrEmail.trim(),
        senha: novoUsrSenha,
        papel: novoUsrPapel,
        cliente_id: novoUsrPapel === "cliente" ? novoUsrCliId : null,
      });
      setNovoUsrNome("");
      setNovoUsrEmail("");
      setNovoUsrSenha("");
    }, "Usuário criado.");
  }

  async function salvarUsuario(e: FormEvent) {
    e.preventDefault();
    if (!editUsrId) return;
    if (editUsrPapel === "cliente" && !editUsrCliId) {
      setErro("Selecione o cliente vinculado para este usuário.");
      return;
    }
    await executar(async () => {
      const dados: Parameters<typeof api.atualizarUsuario>[1] = {
        nome: editUsrNome.trim(),
        email: editUsrEmail.trim(),
        papel: editUsrPapel,
        cliente_id: editUsrPapel === "cliente" ? editUsrCliId : null,
      };
      if (editUsrSenha) dados.senha = editUsrSenha;
      await api.atualizarUsuario(editUsrId, dados);
      setEditUsrId(null);
      setEditUsrSenha("");
    }, "Usuário atualizado.");
  }

  // ---------- PiqueTech ----------
  async function carregarPiqueTech() {
    await executar(async () => {
      const [fazsPt, cults] = await Promise.all([api.piquetechFazendas(), api.piquetechCultivares()]);
      setFazendasPt(fazsPt);
      setCultivaresPt(cults);
      if (!cultivarId) {
        const padrao = cults.find((c) => c.calibrada) ?? cults[0];
        if (padrao) setCultivarId(padrao.id);
      }
      setPtCarregado(true);
    });
  }

  async function importarPiqueTech(seugadoId: string) {
    await executar(async () => {
      const res = await api.piquetechImportar(seugadoId);
      await recarregarFazendas(res.fazenda.id);
      const fazsPt = await api.piquetechFazendas();
      setFazendasPt(fazsPt);
      setAviso(
        `Fazenda "${res.fazenda.nome}" importada: ${res.piquetes_importados} piquete(s) e ${res.lotes_importados} lote(s).`,
      );
    });
  }

  async function atualizarDoPiqueTech(fazendaId: string) {
    await executar(async () => {
      const res = await api.piquetechAtualizar(fazendaId);
      await recarregarFazendas(res.fazenda.id);
      if (ptCarregado) setFazendasPt(await api.piquetechFazendas());
      setAviso(
        `Fazenda "${res.fazenda.nome}" atualizada: ${res.piquetes_importados} piquete(s), ` +
        `${res.lotes_importados} lote(s)` +
        (res.piquetes_inativados > 0 ? `, ${res.piquetes_inativados} inativado(s).` : "."),
      );
    });
  }

  async function exportarParaPiqueTech(fazendaId: string) {
    await executar(async () => {
      const res = await api.piquetechExportar(fazendaId, {
        cultivar_id: cultivarId || null,
        metodo_pastejo: "rotacionado",
      });
      await recarregarFazendas(res.fazenda.id);
      if (ptCarregado) setFazendasPt(await api.piquetechFazendas());
      setAviso(
        `Fazenda "${res.fazenda.nome}" criada no PiqueTech: ${res.piquetes_exportados} piquete(s) e ${res.lotes_exportados} lote(s).`,
      );
    });
  }

  return (
    <div className="pagina admin-pagina">
      <div className="pagina-cabecalho">
        <div>
          <h1 className="pagina-titulo">Administração</h1>
          <p className="cartao-subtitulo">Gerencie clientes, suas fazendas, acessos e a integração com o PiqueTech</p>
        </div>
      </div>

      <div className="admin-abas" role="tablist" aria-label="Seções administrativas">
        {([
          ["clientes", `Clientes (${clientes.length})`],
          ["fazendas", `Fazendas (${fazendas.length})`],
          ["usuarios", `Usuários (${usuarios.length})`],
          ["piquetech", "PiqueTech"],
        ] as [Aba, string][]).map(([id, rotulo]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={aba === id}
            className={aba === id ? "admin-aba ativo" : "admin-aba"}
            onClick={() => {
              setAba(id);
              setErro(null);
              setAviso(null);
            }}
          >
            {rotulo}
          </button>
        ))}
      </div>

      {erro ? <p className="aviso-erro" role="alert">{erro}</p> : null}
      {aviso ? <p className="aviso-info" role="status">{aviso}</p> : null}
      {carregando ? <p className="cartao-subtitulo">Carregando cadastros…</p> : null}

      {/* ---------- CLIENTES (com as fazendas de cada cliente) ---------- */}
      {!carregando && aba === "clientes" && (
        <>
          <form className="cartao admin-form" onSubmit={(e) => void criarCliente(e)}>
            <h2 className="cartao-titulo">Novo cliente</h2>
            <div className="admin-campos">
              <label className="campo">
                Nome
                <input className="campo-entrada" required value={novoCliNome}
                  onChange={(e) => setNovoCliNome(e.target.value)} placeholder="Ex.: João da Silva" />
              </label>
              <label className="campo">
                Contato (telefone ou e-mail)
                <input className="campo-entrada" value={novoCliContato}
                  onChange={(e) => setNovoCliContato(e.target.value)} placeholder="(82) 99999-0000" />
              </label>
            </div>
            <div>
              <button className="botao botao-primario" type="submit" disabled={ocupado}>Criar cliente</button>
            </div>
          </form>

          <section className="cartao">
            <h2 className="cartao-titulo">Clientes e suas fazendas</h2>
            {clientes.length === 0 ? (
              <p className="cartao-subtitulo" style={{ marginTop: 8 }}>Nenhum cliente cadastrado ainda.</p>
            ) : (
              <ul className="admin-lista">
                {clientes.map((c) => {
                  const fazendasDoCliente = fazendas.filter((f) => f.cliente_id === c.id);
                  const editando = editCliId === c.id;
                  return (
                    <li key={c.id} className="admin-item admin-item-cliente">
                      {editando ? (
                        <form className="admin-form-inline" onSubmit={(e) => void salvarCliente(e)}>
                          <input className="campo-entrada" required value={editCliNome}
                            onChange={(e) => setEditCliNome(e.target.value)} aria-label="Nome do cliente" />
                          <input className="campo-entrada" value={editCliContato}
                            onChange={(e) => setEditCliContato(e.target.value)} aria-label="Contato" placeholder="Contato" />
                          <div className="admin-acoes">
                            <button className="botao botao-primario" type="submit" disabled={ocupado}>Salvar</button>
                            <button className="botao botao-secundario" type="button" onClick={() => setEditCliId(null)}>Cancelar</button>
                          </div>
                        </form>
                      ) : (
                        <>
                          <div className="admin-item-cabecalho">
                            <div className="admin-item-info">
                              <strong>{c.nome}</strong>
                              <span className="cartao-subtitulo">
                                {c.contato || "Sem contato"} · {fazendasDoCliente.length} fazenda(s)
                              </span>
                            </div>
                            <div className="admin-acoes">
                              {c.seugado_id ? <span className="selo selo-alta">PiqueTech</span> : null}
                              <button
                                className="botao botao-secundario"
                                type="button"
                                onClick={() => {
                                  setFiltroClienteId(c.id);
                                  setNovaFazCliId(c.id);
                                  setAba("fazendas");
                                }}
                              >
                                + Fazenda
                              </button>
                              <button
                                className="botao botao-secundario"
                                type="button"
                                onClick={() => {
                                  setEditCliId(c.id);
                                  setEditCliNome(c.nome);
                                  setEditCliContato(c.contato);
                                }}
                              >
                                Editar
                              </button>
                            </div>
                          </div>

                          {fazendasDoCliente.length > 0 && (
                            <div className="admin-subfazendas">
                              {fazendasDoCliente.map((f) => (
                                <button
                                  key={f.id}
                                  type="button"
                                  className="admin-chip-fazenda"
                                  onClick={() => abrirFazenda(f.id)}
                                >
                                  <span>{f.nome}</span>
                                  {f.seugado_id ? <span className="selo selo-alta">PiqueTech</span> : null}
                                </button>
                              ))}
                            </div>
                          )}
                        </>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </>
      )}

      {/* ---------- FAZENDAS ---------- */}
      {!carregando && aba === "fazendas" && (
        <>
          <form className="cartao admin-form" onSubmit={(e) => void criarFazenda(e)}>
            <h2 className="cartao-titulo">Nova fazenda</h2>
            <div className="admin-campos">
              <label className="campo">
                Nome da fazenda
                <input className="campo-entrada" required value={novaFazNome}
                  onChange={(e) => setNovaFazNome(e.target.value)} placeholder="Ex.: Fazenda Boa Vista" />
              </label>
              <div className="campo">
                <span>Cliente</span>
                <Seletor
                  valor={novaFazCliId}
                  opcoes={opcoesClientes}
                  aoMudar={setNovaFazCliId}
                  placeholder="Selecione um cliente…"
                  ariaLabel="Cliente da nova fazenda"
                />
              </div>
              <label className="campo">
                Fuso horário
                <input className="campo-entrada" value={novaFazTz}
                  onChange={(e) => setNovaFazTz(e.target.value)} />
              </label>
            </div>
            <div>
              <button className="botao botao-primario" type="submit" disabled={ocupado || !novaFazCliId}>
                Criar fazenda
              </button>
            </div>
          </form>

          <section className="cartao">
            <div className="admin-lista-cabecalho">
              <h2 className="cartao-titulo">Fazendas cadastradas ({fazendasFiltradas.length})</h2>
              <div className="admin-filtro">
                <Seletor
                  valor={filtroClienteId}
                  opcoes={opcoesFiltroCliente}
                  aoMudar={setFiltroClienteId}
                  ariaLabel="Filtrar fazendas por cliente"
                />
              </div>
            </div>
            {fazendasFiltradas.length === 0 ? (
              <p className="cartao-subtitulo" style={{ marginTop: 12 }}>Nenhuma fazenda encontrada para este cliente.</p>
            ) : (
              <ul className="admin-lista">
                {fazendasFiltradas.map((f) => {
                  const editando = editFazId === f.id;
                  return (
                    <li key={f.id} className="admin-item">
                      {editando ? (
                        <form className="admin-form-inline" onSubmit={(e) => void salvarFazenda(e)}>
                          <input className="campo-entrada" required value={editFazNome}
                            onChange={(e) => setEditFazNome(e.target.value)} aria-label="Nome da fazenda" />
                          <div className="admin-seletor-inline">
                            <Seletor
                              valor={editFazCliId}
                              opcoes={opcoesClientesOpcional}
                              aoMudar={setEditFazCliId}
                              ariaLabel="Cliente da fazenda"
                            />
                          </div>
                          <div className="admin-acoes">
                            <button className="botao botao-primario" type="submit" disabled={ocupado}>Salvar</button>
                            <button className="botao botao-secundario" type="button" onClick={() => setEditFazId(null)}>Cancelar</button>
                          </div>
                        </form>
                      ) : (
                        <>
                          <div className="admin-item-info">
                            <strong>{f.nome}</strong>
                            <span className="cartao-subtitulo">
                              Cliente: {nomeCliente(f.cliente_id)} · {f.timezone}
                            </span>
                          </div>
                          <div className="admin-acoes">
                            <span className={f.seugado_id ? "selo selo-alta" : "selo selo-media"}>
                              {f.seugado_id ? "PiqueTech" : "Maneja"}
                            </span>
                            <button className="botao botao-primario" type="button" onClick={() => abrirFazenda(f.id)}>
                              Abrir
                            </button>
                            {f.seugado_id && modoSeugado === "api" ? (
                              <button className="botao botao-secundario" type="button" disabled={ocupado}
                                onClick={() => void atualizarDoPiqueTech(f.id)}>
                                Atualizar do PiqueTech
                              </button>
                            ) : null}
                            <button
                              className="botao botao-secundario"
                              type="button"
                              onClick={() => {
                                setEditFazId(f.id);
                                setEditFazNome(f.nome);
                                setEditFazCliId(f.cliente_id ?? "");
                              }}
                            >
                              Editar
                            </button>
                          </div>
                        </>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </>
      )}

      {/* ---------- USUÁRIOS ---------- */}
      {!carregando && aba === "usuarios" && (
        <>
          <form className="cartao admin-form" onSubmit={(e) => void criarUsuario(e)}>
            <h2 className="cartao-titulo">Novo usuário</h2>
            <div className="admin-campos">
              <label className="campo">
                Nome
                <input className="campo-entrada" required value={novoUsrNome}
                  onChange={(e) => setNovoUsrNome(e.target.value)} placeholder="Nome completo" />
              </label>
              <label className="campo">
                E-mail (login)
                <input className="campo-entrada" type="email" required value={novoUsrEmail}
                  onChange={(e) => setNovoUsrEmail(e.target.value)} placeholder="produtor@fazenda.com" />
              </label>
              <label className="campo">
                Senha inicial
                <input className="campo-entrada" type="password" required minLength={4} value={novoUsrSenha}
                  onChange={(e) => setNovoUsrSenha(e.target.value)} placeholder="Mínimo 4 caracteres" />
              </label>
              <div className="campo">
                <span>Papel</span>
                <Seletor
                  valor={novoUsrPapel}
                  opcoes={OPCOES_PAPEL}
                  aoMudar={(v) => setNovoUsrPapel(v as PapelUsuario)}
                  ariaLabel="Papel do usuário"
                />
              </div>
              {novoUsrPapel === "cliente" && (
                <div className="campo">
                  <span>Cliente vinculado</span>
                  <Seletor
                    valor={novoUsrCliId}
                    opcoes={opcoesClientes}
                    aoMudar={setNovoUsrCliId}
                    placeholder="Selecione um cliente…"
                    ariaLabel="Cliente vinculado"
                  />
                </div>
              )}
            </div>
            <div>
              <button className="botao botao-primario" type="submit" disabled={ocupado}>Criar usuário</button>
            </div>
          </form>

          <section className="cartao">
            <h2 className="cartao-titulo">Usuários cadastrados</h2>
            <p className="cartao-subtitulo" style={{ marginTop: 4, marginBottom: 12 }}>
              O administrador principal ({usuario.email}) sempre mantém acesso completo.
            </p>
            {usuarios.length === 0 ? (
              <p className="cartao-subtitulo">Nenhum usuário adicional cadastrado ainda.</p>
            ) : (
              <ul className="admin-lista">
                {usuarios.map((u) => {
                  const editando = editUsrId === u.id;
                  return (
                    <li key={u.id} className="admin-item">
                      {editando ? (
                        <form className="admin-form-inline" onSubmit={(e) => void salvarUsuario(e)}>
                          <input className="campo-entrada" required value={editUsrNome}
                            onChange={(e) => setEditUsrNome(e.target.value)} aria-label="Nome" />
                          <input className="campo-entrada" type="email" required value={editUsrEmail}
                            onChange={(e) => setEditUsrEmail(e.target.value)} aria-label="E-mail" />
                          <input className="campo-entrada" type="password" value={editUsrSenha}
                            onChange={(e) => setEditUsrSenha(e.target.value)} placeholder="Nova senha (opcional)" />
                          <div className="admin-seletor-inline">
                            <Seletor
                              valor={editUsrPapel}
                              opcoes={OPCOES_PAPEL}
                              aoMudar={(v) => setEditUsrPapel(v as PapelUsuario)}
                              ariaLabel="Papel"
                            />
                          </div>
                          {editUsrPapel === "cliente" && (
                            <div className="admin-seletor-inline">
                              <Seletor
                                valor={editUsrCliId}
                                opcoes={opcoesClientes}
                                aoMudar={setEditUsrCliId}
                                placeholder="Cliente…"
                                ariaLabel="Cliente"
                              />
                            </div>
                          )}
                          <div className="admin-acoes">
                            <button className="botao botao-primario" type="submit" disabled={ocupado}>Salvar</button>
                            <button className="botao botao-secundario" type="button" onClick={() => setEditUsrId(null)}>Cancelar</button>
                          </div>
                        </form>
                      ) : (
                        <>
                          <div className="admin-item-info">
                            <strong>{u.nome || u.email}</strong>
                            <span className="cartao-subtitulo">
                              {u.email}{u.papel === "cliente" ? ` · Cliente: ${nomeCliente(u.cliente_id)}` : ""}
                            </span>
                          </div>
                          <div className="admin-acoes">
                            <span className={u.papel === "admin" ? "selo selo-alta" : "selo selo-media"}>
                              {u.papel === "admin" ? "Admin" : "Cliente"}
                            </span>
                            <button
                              className="botao botao-secundario"
                              type="button"
                              onClick={() => {
                                setEditUsrId(u.id);
                                setEditUsrNome(u.nome);
                                setEditUsrEmail(u.email);
                                setEditUsrSenha("");
                                setEditUsrPapel(u.papel);
                                setEditUsrCliId(u.cliente_id ?? "");
                              }}
                            >
                              Editar
                            </button>
                          </div>
                        </>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </>
      )}

      {/* ---------- PIQUETECH (SPEC-018) ---------- */}
      {!carregando && aba === "piquetech" && (
        <>
          <section className="cartao admin-form">
            <div className="pagina-cabecalho">
              <div>
                <h2 className="cartao-titulo">Importar do PiqueTech</h2>
                <p className="cartao-subtitulo">
                  Status da conexão:{" "}
                  <strong>{modoSeugado === "api" ? "Conectado ao PiqueTech" : "Integração desligada"}</strong>.
                  {modoSeugado === "api"
                    ? " Busque as fazendas do PiqueTech para importar cliente, fazenda, piquetes e lotes com o mesmo UUID."
                    : " Ative a integração no ambiente da API para importar e exportar fazendas."}
                </p>
              </div>
              <button
                className="botao botao-primario"
                type="button"
                disabled={ocupado || modoSeugado !== "api"}
                onClick={() => void carregarPiqueTech()}
              >
                {ptCarregado ? "Recarregar do PiqueTech" : "Buscar fazendas do PiqueTech"}
              </button>
            </div>

            {ptCarregado && (
              fazendasPt.length === 0 ? (
                <p className="cartao-subtitulo">Nenhuma fazenda retornada pelo PiqueTech.</p>
              ) : (
                <ul className="admin-lista">
                  {fazendasPt.map((f) => (
                    <li key={f.seugado_id} className="admin-item">
                      <div className="admin-item-info">
                        <strong>{f.nome}</strong>
                        <span className="cartao-subtitulo">
                          Cliente: {f.cliente_nome || "Sem cliente"} · UUID {f.seugado_id}
                        </span>
                      </div>
                      <div className="admin-acoes">
                        {f.ja_importada && f.fazenda_local_id ? (
                          <>
                            <span className="selo selo-alta">Já importada</span>
                            <button className="botao botao-secundario" type="button" disabled={ocupado}
                              onClick={() => void atualizarDoPiqueTech(f.fazenda_local_id!)}>
                              Atualizar
                            </button>
                            <button className="botao botao-primario" type="button"
                              onClick={() => abrirFazenda(f.fazenda_local_id!)}>
                              Abrir
                            </button>
                          </>
                        ) : (
                          <button className="botao botao-primario" type="button" disabled={ocupado}
                            onClick={() => void importarPiqueTech(f.seugado_id)}>
                            Importar
                          </button>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              )
            )}
          </section>

          <section className="cartao admin-form">
            <h2 className="cartao-titulo">Criar no PiqueTech (exportar fazenda do Maneja)</h2>
            <p className="cartao-subtitulo">
              Envia cliente, fazenda, piquetes e lotes para o PiqueTech e guarda os UUIDs no Maneja.
            </p>
            {opcoesCultivares.length > 0 && (
              <div className="campo" style={{ maxWidth: 360 }}>
                <span>Cultivar para os piquetes criados</span>
                <Seletor
                  valor={cultivarId}
                  opcoes={opcoesCultivares}
                  aoMudar={setCultivarId}
                  ariaLabel="Cultivar"
                />
              </div>
            )}
            <ul className="admin-lista">
              {fazendas.filter((f) => !f.seugado_id).map((f) => (
                <li key={f.id} className="admin-item">
                  <div className="admin-item-info">
                    <strong>{f.nome}</strong>
                    <span className="cartao-subtitulo">Cliente: {nomeCliente(f.cliente_id)}</span>
                  </div>
                  <div className="admin-acoes">
                    <button
                      className="botao botao-primario"
                      type="button"
                      disabled={ocupado || modoSeugado !== "api"}
                      onClick={() => void exportarParaPiqueTech(f.id)}
                    >
                      Criar no PiqueTech
                    </button>
                  </div>
                </li>
              ))}
              {fazendas.every((f) => Boolean(f.seugado_id)) && (
                <li className="cartao-subtitulo">Todas as fazendas já estão vinculadas ao PiqueTech.</li>
              )}
            </ul>
          </section>
        </>
      )}
    </div>
  );
}
