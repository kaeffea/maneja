import { Link, Outlet, useLocation } from "react-router";
import { useFazenda } from "../lib/fazenda";
import SeletorContexto from "./SeletorContexto";
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
  const { modo, usuario, sair } = useFazenda();
  const localizacao = useLocation();
  const ehAdmin = modo === "api" && usuario.papel === "admin";
  const emAdmin = localizacao.pathname === "/admin";

  return (
    <div className="layout">
      <header className="barra">
        <div className="barra-esquerda">
          <Link to="/mapa" className="barra-marca">
            <Marca />
            <span className="barra-marca-texto">Maneja</span>
          </Link>
          <span className="barra-divisor" aria-hidden="true" />
          <SeletorContexto />
        </div>

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
          {ehAdmin ? (
            <Link
              to="/admin"
              className={emAdmin ? "barra-admin ativo" : "barra-admin"}
              aria-current={emAdmin ? "page" : undefined}
            >
              <Icone nome="config" />
              <span>Admin</span>
            </Link>
          ) : null}
          <span
            className="barra-avatar"
            title={`${usuario.nome || usuario.email} (${usuario.email})`}
            aria-label={usuario.nome || usuario.email}
          >
            {(usuario.nome || usuario.email).charAt(0).toUpperCase()}
          </span>
          {sair ? (
            <button className="barra-sair" type="button" onClick={sair}>
              <Icone nome="sair" />
              <span>Sair</span>
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
