# SPEC-005 · Ligar o Gemini real para escrever a explicação

Responsável: Leandro · Revisor: Kauê · Gantt: 7 · Camada DDD: core

## Contexto
O agente (SPEC-001) já decide por regras e aceita um `llm` com `gerar_texto(prompt) -> str`. Esta spec cria o adaptador real do Google Gemini. A regra continua decidindo. O texto do Gemini só é usado se passar no validador do risco R3 (`explicacao_valida` em `agente.py`), e a cota é controlada (risco R7).

## Arquivos
- ALTERAR `backend/maneja/adaptadores/llm.py` (criar `GeminiLLM`)
- ALTERAR `backend/maneja/config.py` (`MANEJA_GEMINI_API_KEY`, `MANEJA_GEMINI_MODELO`, `MANEJA_GEMINI_COTA_DIARIA`)
- CRIAR `backend/features/gemini.feature`, `backend/tests/test_gemini.py`

## Requisitos
- **R1.** `GeminiLLM(chave, modelo, cliente_http)`: faz `POST https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key=...` com `{"contents":[{"parts":[{"text": prompt}]}]}` e devolve `candidates[0].content.parts[0].text`. Timeout de 15 s.
- **R2.** Erro HTTP, timeout ou resposta sem texto: lança `CotaEsgotada` (status 429) ou `RuntimeError`. O agente já trata qualquer exceção do LLM usando o texto da regra (`agente.explicar`).
- **R3.** Sem `MANEJA_GEMINI_API_KEY`, o sistema sobe com `llm=None` (texto da regra). Com a chave, usa `ControleDeCota(GeminiLLM(...), limite=MANEJA_GEMINI_COTA_DIARIA)`.
- **R4.** Os testes nunca chamam a rede: o `cliente_http` é injetado (use `httpx.MockTransport`).

## Constantes
Modelo padrão `gemini-3.1-flash-lite`, substituindo o Gemini 2.0 Flash após sua desativação. O modelo pode ser configurado conforme o acesso da conta. Cota diária padrão de 50 por instância da aplicação. [Referência de modelos e desativações do Google](https://ai.google.dev/gemini-api/docs/deprecations).

## Cenários (BDD)
```gherkin
Funcionalidade: Gemini

  Cenário: Resposta válida vira a explicação
    Dado um Gemini que responde "Leve o gado do Piquete Abóbora para o Piquete Macarrão, que tem pasto melhor."
    Quando o agente gera o plano
    Então a explicação da movimentação vem do LLM

  Cenário: Gemini fora do ar não derruba o plano
    Dado um Gemini que responde com erro 500
    Quando o agente gera o plano
    Então a explicação da movimentação vem da regra

  Cenário: Cota esgotada
    Dado um Gemini com cota de 0 chamadas
    Quando o agente gera o plano
    Então a explicação da movimentação vem da regra
```

## Fora do escopo
O Gemini decidir destino. Chat livre com o usuário.

## Como ficou
- **Adaptador (`backend/maneja/adaptadores/llm.py`):** `GeminiLLM(chave, modelo, cliente_http)` faz o `POST` de R1 com timeout de 15 s. HTTP 429 vira `CotaEsgotada`. Outro erro HTTP, timeout, falha de conexão, JSON inválido ou resposta sem texto (bloqueio de segurança, `candidates` vazio) viram `RuntimeError`. As mensagens de erro não levam a URL, porque ela contém a chave.
- **Cota (R7):** o `ControleDeCota` zera o contador na virada do dia e usa uma trava para requisições simultâneas. `Config.llm` é uma `cached_property`, então no modo sem estado (Vercel) o mesmo contador vale para todas as requisições da instância.
- **Montagem (`backend/maneja/config.py`):** sem `MANEJA_GEMINI_API_KEY` (ou com ela em branco), `Config.llm` é `None` e a explicação vem da regra. Com a chave, `Config.llm` é `ControleDeCota(GeminiLLM(...), MANEJA_GEMINI_COTA_DIARIA)`. Variáveis vazias usam os padrões, e a chave não aparece no `repr` da `Config`.
- **Modelo:** conferido na conta em 20/11 e 22/11/2026. `gemini-1.5-flash`, `gemini-2.0-flash` e `gemini-2.5-flash` respondem 404. Com a fazenda de demonstração, `gemini-3.1-flash-lite` e `gemini-3.5-flash-lite` escreveram textos aceitos pelo validador R3 em 2 a 6 s na maioria das vezes. Nos horários de pico, algumas chamadas passaram dos 15 s e o plano saiu com o texto da regra, como previsto em R2.
- **Rodar local com o Gemini:** coloque as variáveis em `backend/.env` (já ignorado pelo git) e rode `uv run --env-file .env uvicorn maneja.api:app --reload`. O backend não lê `.env` sozinho.

## Limitações conhecidas
- A cota é por instância e fica em memória. Com várias instâncias na Vercel, cada uma tem o seu contador, e quem segura a cota real é o 429 do Google, que já cai no texto da regra.

## Situação
Feita em 20/11 (Leandro), integrada ao `main` em 22/11 e mesclada no `main` do fork em 24/11 (PR #2). Em 24/11 ganhou cadeia automática de fallback entre modelos ativos no plano gratuito (`gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`, `gemini-3.6-flash`, `gemini-3.8-flash`), logs sem expor a chave, diagnóstico em `/saude` e validador R3 insensível a maiúsculas/minúsculas. Suíte total em 104 testes verdes.
