# Demonstração final da AB2 · qui 26/11/2026 (presencial)

- **Slides (12 slides, 16:9, PDF pronto para projetor):** [Maneja-Apresentacao-Final-AB2.pdf](apresentacao/Maneja-Apresentacao-Final-AB2.pdf) (fonte em [slides.html](apresentacao/slides.html)).
- **Produção:** https://maneja.tech (front) · https://api.maneja.tech (API) · https://api.maneja.tech/docs (OpenAPI).

## Preparação antes de entrar em sala

1. *(Opcional — para começar a demo com o gado ainda no Piquete Abóbora)* No **SQL Editor** do Supabase, rode:
   ```sql
   TRUNCATE fazenda, movimentacao, plano_atual, coleira, posicao, grupo_externo, parametro CASCADE;
   ```
   Ao abrir `https://maneja.tech`, o backend recria automaticamente os 5 piquetes e as 10 coleiras (`MANEJA_SEMEAR=1`).
2. Deixe abertas duas abas no navegador: `https://maneja.tech` (já autenticado) e o repositório no GitHub (`CLAUDE.md`, `specs/` e `docs/uml/`).
3. Tenha um terminal aberto em `maneja/backend` pronto para rodar `uv run pytest` (105 testes, ~4 s, 100% sem rede).
4. *(Plano B offline, caso falte internet na sala)* A mesma aplicação roda localmente com `cd backend && MANEJA_PERDA_SINAL=0 uv run uvicorn maneja.api:app` + `VITE_API_URL=http://localhost:8000 VITE_MODO_DEMO=1 npm run dev`, ou com `MANEJA_SEUGADO_MODO=arquivo` para demonstrar o contrato do SeuGado.

## Roteiro ao vivo

1. **Mapa (`https://maneja.tech/mapa`):** mostre os 5 piquetes na escala de NDVI e ligue **Mostrar coleiras GPS**.
2. **Plano (`https://maneja.tech/plano`):** mostre a previsão real (**Open-Meteo**), clique em **Gerar plano**, apresente a recomendação `Piquete Abóbora → Piquete Macarrão`, a regra determinística (descarte do Jerimum por capacidade) e a explicação com o selo **IA** (Gemini com validador R3 e fallback gratuito).
3. **Persistência:** clique em **Confirmar movimentação** e recarregue a página (`F5`) para provar a gravação transacional no Supabase.
4. **Campo — Cumprida (`https://maneja.tech/campo`):** selecione a movimentação e **Piquete Macarrão** no simulador, clique em **Levar gado no campo** e mostre **Cumprida (100% no destino)** e **Confere** na tabela de ocupação.
5. **Campo — Divergente:** mova as mesmas coleiras para **Piquete Feijão**, clique em **Avançar 1 dia** duas vezes e mostre **Divergente (0% no destino)**, **Diverge** na tabela e as bordas vermelhas no **Mapa**.
6. **SDD + BDD + Conjunto-Ouro:** mostre `CLAUDE.md`, uma spec (`specs/SPEC-011-telas-coleiras-verificacao.md`), os diagramas em `docs/uml/` e rode `uv run pytest` (**105 passed**, incluindo o conjunto-ouro 27/30 = 90% e 0 violações).
