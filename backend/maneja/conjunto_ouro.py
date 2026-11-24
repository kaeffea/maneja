"""Conjunto-ouro do agente de manejo (SPEC-016, critério de qualidade do pacote 1.1).

Roda o agente de verdade (`gerar_plano`) em 30 cenários escritos à mão e compara cada plano
com o gabarito do caso: quais piquetes devem sair, para quais destinos é plausível ir, em que dia,
e quando o certo é avisar que não há destino. O critério de aceite é ≥ 90% dos casos plausíveis
e nenhuma movimentação recomendada violando as regras determinísticas.

Uso:
    uv run python -m maneja.conjunto_ouro                 # mostra o resultado
    uv run python -m maneja.conjunto_ouro --relatorio     # reescreve docs/05-conjunto-ouro.md
    uv run python -m maneja.conjunto_ouro --gemini        # usa o Gemini real (MANEJA_GEMINI_API_KEY)
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .agente import CHUVA_FORTE_MM, EntradaAgente, ILLM, gerar_plano
from .datas import somar_dias
from .dominio import LeituraNdvi, Lotacao, Movimentacao, Piquete, PlanoManejo, PrevisaoClima, PrevisaoDia, Rebanho
from .regras import validar_movimento

BACKEND = Path(__file__).resolve().parent.parent
CASOS = BACKEND / "conjunto_ouro" / "casos.json"
RELATORIO = BACKEND.parent / "docs" / "05-conjunto-ouro.md"
META_PLAUSIVEIS = 0.9  # critério de aceite da atividade 7 do Gantt (≥ 90% das 30 recomendações)
FAZENDA = "faz-ouro"


@dataclass
class ResultadoCaso:
    id: str
    titulo: str
    plausivel: bool
    esperado: str
    recomendado: str
    problemas: list[str] = field(default_factory=list)
    violacoes: list[str] = field(default_factory=list)
    movimentacoes: int = 0
    explicacoes_llm: int = 0


def carregar(caminho: Path = CASOS) -> dict:
    return json.loads(caminho.read_text(encoding="utf-8"))


def _quadrado(i: int) -> dict:
    """Geometria de enfeite: o agente só usa a área, mas o Piquete exige um polígono."""
    x = i * 0.01
    return {"type": "Polygon", "coordinates": [[[x, 0], [x + 0.005, 0], [x + 0.005, 0.005], [x, 0.005], [x, 0]]]}


def montar_entrada(dados: dict, caso: dict) -> tuple[EntradaAgente, list[Piquete], str]:
    hoje = dados["hoje"]
    piquetes = [Piquete(p["id"], FAZENDA, p["nome"], _quadrado(i), p["area_ha"], "capim")
                for i, p in enumerate(dados["piquetes"])]
    idade = caso.get("idade_ndvi_dias", {})
    ndvi = [LeituraNdvi(pid, somar_dias(hoje, -idade.get(pid, dados["idade_ndvi_padrao_dias"])), valor)
            for pid, valor in caso["ndvi"].items()]
    lotacao = [Lotacao(pid, FAZENDA, b, v, z, somar_dias(hoje, -10)) for pid, (b, v, z) in caso["lotacao"].items()]
    clima = PrevisaoClima(FAZENDA, [PrevisaoDia(somar_dias(hoje, i), mm, 20, 30) for i, mm in enumerate(caso["chuva_mm"])])
    nomes = {p.id: p.nome for p in piquetes}
    historico = [
        Movimentacao(
            id=f"recusa-{i}", data=somar_dias(hoje, -r["dias_atras"]), rebanho=Rebanho(12, 6, 5),
            piquete_origem_id=r["origem"], piquete_origem_nome=nomes[r["origem"]],
            piquete_destino_id=r["destino"], piquete_destino_nome=nomes[r["destino"]],
            ndvi_origem=None, ndvi_destino=None, motivo="", confianca="alta", motivo_confianca="",
            status="recusada", destino_trocado=False, destino_recomendado_nome=nomes[r["destino"]],
        )
        for i, r in enumerate(caso.get("recusas", []))
    ]
    return EntradaAgente(piquetes, ndvi, clima, lotacao, historico), piquetes, hoje


def _descrever_esperado(caso: dict, nomes: dict[str, str]) -> str:
    esp = caso["esperado"]
    partes = []
    for m in esp["movimentos"]:
        destinos = " ou ".join(nomes[d] for d in m["destinos"])
        dia = f" (dia {m['dia']})" if "dia" in m else ""
        partes.append(f"{nomes[m['origem']]} → {destinos}{dia}")
    for o in esp.get("sem_destino", []):
        partes.append(f"{nomes[o]}: alerta sem destino")
    return "; ".join(partes) or "nenhuma movimentação"


def _descrever_plano(plano: PlanoManejo, hoje: str) -> str:
    from .datas import dias_entre

    partes = [f"{m.piquete_origem_nome} → {m.piquete_destino_nome} (dia {dias_entre(hoje, m.data)})"
              for m in plano.movimentacoes]
    partes += [f"alerta sem destino: {a.texto.split(' está com')[0]}" for a in plano.alertas if a.tipo == "sem_piquete_apto"]
    return "; ".join(partes) or "nenhuma movimentação"


def avaliar_caso(dados: dict, caso: dict, llm: ILLM | None = None) -> ResultadoCaso:
    entrada, piquetes, hoje = montar_entrada(dados, caso)
    nomes = {p.id: p.nome for p in piquetes}
    plano = gerar_plano(entrada, hoje, datetime(2026, 11, 22, 12, tzinfo=timezone.utc), llm)
    esp = caso["esperado"]
    chuva = {d.data: d.chuva_mm for d in entrada.clima.dias}
    problemas: list[str] = []

    esperados = {m["origem"]: m for m in esp["movimentos"]}
    feitos = {m.piquete_origem_id: m for m in plano.movimentacoes}
    for origem, m in feitos.items():
        if chuva.get(m.data, 0) >= CHUVA_FORTE_MM:
            problemas.append(f"movimentação marcada em dia de chuva forte ({chuva[m.data]:.0f} mm)")
        alvo = esperados.get(origem)
        if alvo is None:
            problemas.append(f"moveu {nomes[origem]} para {m.piquete_destino_nome}, mas o gabarito não prevê essa saída")
            continue
        if m.piquete_destino_id not in alvo["destinos"]:
            problemas.append(f"{nomes[origem]} foi para {m.piquete_destino_nome}, fora dos destinos plausíveis")
        if "dia" in alvo and m.data != somar_dias(hoje, alvo["dia"]):
            problemas.append(f"{nomes[origem]} marcado para {m.data}, esperado o dia {alvo['dia']}")
    for origem in esperados:
        if origem not in feitos:
            problemas.append(f"não recomendou a saída de {nomes[origem]}")
    alertas_sem_destino = " ".join(a.texto for a in plano.alertas if a.tipo == "sem_piquete_apto")
    for origem in esp.get("sem_destino", []):
        if nomes[origem] not in alertas_sem_destino:
            problemas.append(f"faltou o alerta de sem destino para {nomes[origem]}")

    # Critério: nenhuma recomendação viola as regras determinísticas (conferido de novo, de fora do agente).
    violacoes = []
    for m in plano.movimentacoes:
        outras = [l for l in entrada.lotacao if l.piquete_id != m.piquete_origem_id]
        for falha in validar_movimento(m.piquete_destino_id, m.rebanho, piquetes, entrada.ndvi, outras, hoje):
            violacoes.append(f"{m.piquete_origem_nome} → {m.piquete_destino_nome}: {falha}")

    return ResultadoCaso(
        id=caso["id"], titulo=caso["titulo"], plausivel=not problemas and not violacoes,
        esperado=_descrever_esperado(caso, nomes), recomendado=_descrever_plano(plano, hoje),
        problemas=problemas, violacoes=violacoes,
        movimentacoes=len(plano.movimentacoes),
        explicacoes_llm=sum(1 for m in plano.movimentacoes if m.explicacao_origem == "llm"),
    )


def avaliar(dados: dict | None = None, llm: ILLM | None = None) -> list[ResultadoCaso]:
    dados = dados or carregar()
    return [avaliar_caso(dados, caso, llm) for caso in dados["casos"]]


def taxa(resultados: list[ResultadoCaso]) -> float:
    return sum(r.plausivel for r in resultados) / len(resultados)


def relatorio(resultados: list[ResultadoCaso], dados: dict) -> str:
    plausiveis = sum(r.plausivel for r in resultados)
    violacoes = sum(len(r.violacoes) for r in resultados)
    justificativas = {c["id"]: c["justificativa"] for c in dados["casos"]}
    linhas = [
        "# Conjunto-ouro do agente de manejo",
        "",
        "Gerado por `uv run python -m maneja.conjunto_ouro --relatorio` (SPEC-016). Não edite à mão: "
        "mude `backend/conjunto_ouro/casos.json` e rode de novo.",
        "",
        "## Resultado",
        "",
        f"- **Plausíveis:** {plausiveis} de {len(resultados)} ({plausiveis / len(resultados):.0%}). "
        f"Meta: {META_PLAUSIVEIS:.0%}. {'Atingida.' if plausiveis / len(resultados) >= META_PLAUSIVEIS else 'Não atingida.'}",
        f"- **Recomendações que violam as regras determinísticas:** {violacoes}. Meta: 0.",
        f"- **Data de referência dos casos:** {dados['hoje']}. Fazenda com os 5 piquetes da demonstração.",
        "",
        "Cada caso traz a entrada (NDVI e idade da leitura, rebanho, chuva de 7 dias, recusas) e um gabarito "
        "escrito antes de rodar o agente: quem deve sair, para onde é plausível ir, em que dia e quando o certo "
        "é avisar que não há destino. Um caso é plausível quando o plano do agente cumpre todo o gabarito.",
        "",
        "## Casos",
        "",
        "| Caso | Situação | Gabarito | Agente recomendou | Resultado |",
        "|---|---|---|---|---|",
    ]
    for r in resultados:
        resultado = "✅ plausível" if r.plausivel else "❌ " + "; ".join(r.problemas + r.violacoes)
        linhas.append(f"| {r.id} | {r.titulo} | {r.esperado} | {r.recomendado} | {resultado} |")
    falhos = [r for r in resultados if not r.plausivel]
    linhas += ["", "## Casos não plausíveis", ""]
    if not falhos:
        linhas.append("Nenhum.")
    for r in falhos:
        linhas += [f"### {r.id} · {r.titulo}", "", f"- **Por que o gabarito é este:** {justificativas[r.id]}",
                   f"- **O que o agente fez:** {r.recomendado}.", f"- **Problema:** {'; '.join(r.problemas + r.violacoes)}.", ""]
    linhas += ["## Justificativa de cada gabarito", ""]
    linhas += [f"- **{r.id}.** {justificativas[r.id]}" for r in resultados]
    linhas.append("")
    return "\n".join(linhas)


def main() -> None:
    parser = argparse.ArgumentParser(description="Roda o conjunto-ouro do agente de manejo.")
    parser.add_argument("--relatorio", action="store_true", help=f"reescreve {RELATORIO.name}")
    parser.add_argument("--gemini", action="store_true", help="usa o Gemini real para as explicações")
    args = parser.parse_args()
    llm = None
    if args.gemini:
        from .config import Config

        llm = Config.do_ambiente().llm
        if llm is None:
            raise SystemExit("defina MANEJA_GEMINI_API_KEY para usar --gemini")
    dados = carregar()
    resultados = avaliar(dados, llm)
    for r in resultados:
        print(f"{r.id} {'OK ' if r.plausivel else 'NÃO'} {r.titulo}" + ("" if r.plausivel else f" -> {'; '.join(r.problemas + r.violacoes)}"))
    print(f"\nPlausíveis: {sum(r.plausivel for r in resultados)}/{len(resultados)} ({taxa(resultados):.0%}) · "
          f"violações de regra: {sum(len(r.violacoes) for r in resultados)}")
    if args.gemini:
        movs = sum(r.movimentacoes for r in resultados)
        print(f"Explicações do Gemini aceitas pelo validador R3: {sum(r.explicacoes_llm for r in resultados)} de {movs} movimentações")
    if args.relatorio:
        RELATORIO.write_text(relatorio(resultados, dados), encoding="utf-8")
        print(f"Relatório gravado em {RELATORIO.relative_to(BACKEND.parent)}")


if __name__ == "__main__":
    main()
