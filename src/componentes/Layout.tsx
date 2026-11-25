import { Link, Outlet, useLocation } from "react-router";
import { useFazenda } from "../lib/fazenda";
import { Icone, Marca, type NomeIcone } from "./ui/Icones";
import "./Layout.css";

const LINKS: { para: string; texto: string; icone: NomeIcone }[] = [
  { para: "/mapa", texto: "Mapa", icone: "mapa" },
  { para: "/plano", texto: "Plano", icone: "plano" },
  { para: "/campo", texto: "Campo", icone: "fazenda" },
  { para: "/rebanho", texto: "Rebanho", icone: "clientes" },
  { para: "/historico", texto: "Histórico", icone: "relogio" },
  { para: "/dashboard", texto: "Dashboard", icone: "painel" },
  { para: "/fazenda", texto: "Fazenda", icone: "fazenda" },
];

export default function Layout() {
  const { modo, usuario, fazenda, fazendas, selecionarFazenda, sair } = useFazenda();
  const localizacao = useLocation();
  const ehAdmin = modo === "api" && usuario.papel === "admin";
  const emAdmin = localizacao.pathname === "/admin";

  return (
    <div className="layout">
      <header className="barra">
        <Link to="/mapa" className="barra-marca">
          <Marca />
          <span>Maneja</span>
        </Link>
        <nav className="barra-links" aria-label="Navegação principal">
          {LINKS.map((item) => {
            const ativo = localizacao.pathname === item.para;
            return (
              <Link
                key={item.para}
                to={item.para}
                aria-current={ativo ? "page" : undefined}
                className={ativo ? "barra-link ativo" : "barra-link"}
              >
                <Icone nome={item.icone} />
                <span>{item.texto}</span>
              </Link>
            );
          })}
        </nav>
        <div className="barra-usuario">
          {fazendas.length > 1 ? (
            <select
              className="barra-seletor-fazenda"
              aria-label="Selecionar fazenda"
              value={fazenda.id}
              onChange={(e) => selecionarFazenda(e.target.value)}
            >
              {fazendas.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.nome}
                </option>
              ))}
            </select>
          ) : null}
          {ehAdmin ? (
            <Link
              to="/admin"
              className={emAdmin ? "barra-admin ativo" : "barra-admin"}
              aria-current={emAdmin ? "page" : undefined}
            >
              Admin
            </Link>
          ) : null}
          <span className="barra-avatar" aria-hidden="true" title={usuario.email}>
            {(usuario.nome || usuario.email).charAt(0).toUpperCase()}
          </span>
          <span className="barra-usuario-texto">
            <span className="barra-usuario-nome">{usuario.nome || usuario.email}</span>
            <span className="barra-usuario-fazenda">{fazenda.nome}</span>
          </span>
          {sair ? (
            <button className="barra-sair" type="button" onClick={sair}>
              Sair
            </button>
          ) : null}
        </div>
      </header>
      <main className={localizacao.pathname === "/mapa" ? "conteudo conteudo-cheio" : "conteudo"}>
        <Outlet />
      </main>
    </div>
  );
}
