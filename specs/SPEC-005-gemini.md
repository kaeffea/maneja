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
Modelo padrão `gemini-2.0-flash` (conferir o nome disponível na conta), cota diária padrão 50.

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
- **Montagem (`backend/maneja/config.py`):** `adaptador_llm(config)` devolve `None` sem `MANEJA_GEMINI_API_KEY` (ou com ela em branco) e `ControleDeCota(GeminiLLM(...), limite=MANEJA_GEMINI_COTA_DIARIA)` com ela. `montar_sistema` usa esse adaptador quando não recebe um `llm`. A chave não aparece no `repr` da `Config`.
- **Modelo padrão:** `gemini-3.5-flash-lite`. Conferido na conta em 20/11/2026: `gemini-2.0-flash`, `gemini-1.5-flash` e `gemini-2.5-flash` respondem 404. Em teste real com a fazenda de demonstração, o `gemini-3.5-flash-lite` respondeu em cerca de 1 s e escreveu textos aceitos pelo validador R3. O `gemini-3.8-flash` passou dos 15 s em 2 de 3 tentativas, e o `gemini-3.5-flash` às vezes devolve markdown (`**`).
- **Rodar local com o Gemini:** coloque as variáveis em `backend/.env` (já ignorado pelo git) e rode `uv run --env-file .env uvicorn maneja.api:app --reload`. O backend não lê `.env` sozinho.

## Limitações conhecidas (para decidir em outra spec)
- O `ControleDeCota` conta chamadas desde que o sistema subiu e não zera à meia-noite.
- No modo sem estado (Vercel), o sistema é montado a cada requisição, então o contador recomeça a cada `POST /plano`. Na prática, o limite fica valendo por plano, e quem segura a cota real é o 429 do Google, que já cai no texto da regra.

## Situação
Implementada em 20/11 (Leandro), em revisão (Kauê). Os 3 cenários de `backend/features/gemini.feature` e mais 32 testes em `backend/tests/test_gemini.py` estão passando, e `uv run pytest` está verde com 74 testes, também com a rede externa bloqueada. Testada também com o Gemini real.
