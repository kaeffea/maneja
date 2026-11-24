# Rodada de testes e triagem · AB2

Verificação de 19/11/2026 na branch `codex/pendencias-ab2`.

| Verificação | Resultado |
|---|---|
| `uv run pytest` | 52 testes passaram, incluindo os cenários PostgreSQL e 13 novos cenários BDD com HTTP simulado. |
| Mapa e Campo com a API local | Gerou e aceitou Abóbora → Macarrão. Ao simular o destino correto, a verificação ficou **Cumprida** e mostrou 100%. Com Feijão como destino observado e após dois avanços de um dia, ficou **Divergente**, com 0% no destino. A camada GPS exibiu as coleiras e as bordas vermelhas no Feijão. |
| Dependências JavaScript | A triagem apontou dois alertas altos em Vite e source-map-js na cadeia de desenvolvimento. O lockfile atualizado passou no `npm audit` com zero alertas. |

Os testes executados não revelaram defeito funcional bloqueante de severidade 1 ou 2. O aceite da implantação ainda precisa ser executado na Vercel com o banco Supabase. As respostas de Gemini, SeuGado e Copernicus foram validadas com HTTP simulado, sem credenciais reais.

## Revalidação final · 24/11/2026 (estado unificado após PRs #1–#4)

| Verificação | Resultado |
|---|---|
| `cd backend && uv run pytest` | **97 testes passaram** (agente, API, autenticação, coleiras, persistência PostgreSQL, verificação, integrações Open-Meteo/Gemini/SeuGado, NDVI Copernicus e conjunto-ouro). |
| Conjunto-ouro (SPEC-016) | **27 de 30 plausíveis (90%)** e **0 violações** das regras determinísticas (detalhes em `docs/05-conjunto-ouro.md`). |
| `npx tsc -b && npm run build` | Sem erros de tipo nem de empacotamento. |
| `npm audit --audit-level=moderate` | **0 vulnerabilidades**. |
| Navegador (API + simulador e modo demonstração offline) | Fluxo completo da apresentação validado em `1280×800`, `720×800` e `360×740`: login, coleiras no mapa, gerar e aceitar plano, `Campo` (**Cumprida** em 100% e **Divergente** após 2 avanços), 7 abas na barra inferior em `360 px` sem truncamento nem rolagem horizontal, e mensagem offline em `/campo`. |

Defeitos encontrados e corrigidos na rodada de 24/11 (todos severidade 3/4):
- Truncamento de `"Dashboard"` na barra inferior em `360 px` com 7 abas e aperto da barra superior em `720 px` (`src/componentes/Layout.css`).
- Alinhamento e estilização da página `Campo` fora do container `.pagina` (`src/paginas/Campo.tsx` e `Campo.css`).
- Reaproveitamento do token em `SeuGadoApi` quando `POST /auth/token` não retorna `expires_in`, alinhado ao contrato real do SeuGado (`backend/maneja/adaptadores/seugado.py`).

Pendências externas ao código: publicar na Vercel + Supabase (SPEC-013), fechar slides e vídeo de reserva da apresentação (SPEC-014) e abrir o PR final do fork para `joaopedrosss/maneja`.
