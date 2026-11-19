# Rodada de testes e triagem · AB2

Verificação de 19/11/2026 na branch `codex/pendencias-ab2`.

| Verificação | Resultado |
|---|---|
| `uv run pytest` | 52 testes passaram, incluindo os cenários PostgreSQL e 13 novos cenários BDD com HTTP simulado. |
| Mapa e Campo com a API local | Gerou e aceitou Abóbora → Macarrão. Ao simular o destino correto, a verificação ficou **Cumprida** e mostrou 100%. Com Feijão como destino observado e após dois avanços de um dia, ficou **Divergente**, com 0% no destino. A camada GPS exibiu as coleiras e as bordas vermelhas no Feijão. |
| Dependências JavaScript | A triagem apontou dois alertas altos em Vite e source-map-js na cadeia de desenvolvimento. O lockfile atualizado passou no `npm audit` com zero alertas. |

Os testes executados não revelaram defeito funcional bloqueante de severidade 1 ou 2. O aceite da implantação ainda precisa ser executado na Vercel com o banco Supabase. As respostas de Gemini, SeuGado e Copernicus foram validadas com HTTP simulado, sem credenciais reais.
