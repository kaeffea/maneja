# Demonstração final da AB2 · 26/11

## Preparação

- Abra a API com a fazenda de demonstração e o front com `VITE_API_URL=http://localhost:8000` e `VITE_MODO_DEMO=1`. Use uma instância de demonstração, com `MANEJA_PERDA_SINAL=0` para tornar a apresentação reproduzível.
- Comece com o SeuGado desligado. Deixe outra instância preparada com `MANEJA_SEUGADO_MODO=arquivo` para mostrar o contrato com o plano externo. O exemplo tem datas fixas de 19 e 21/11, então ensaie o vínculo e o status com antecedência.
- Abra o mapa, o plano e a tela Campo. Tenha o terminal em `backend/` com as dependências instaladas. Consulte o [guia de deploy](04-deploy.md) para a apresentação hospedada.

## Roteiro

1. No **Mapa**, mostre os piquetes e a escala de NDVI. Ative **Mostrar coleiras GPS** para ver as posições observadas.
2. Em **Plano**, clique em **Gerar plano**. Mostre a recomendação de Abóbora para Macarrão, a regra de destino e a origem do texto da explicação. Se o Gemini estiver indisponível, a explicação da regra mantém a demonstração utilizável.
3. Aceite a movimentação. Em **Campo**, mostre a verificação pendente e compare o piquete previsto com a posição observada antes da execução.
4. Selecione a movimentação e Macarrão em **Piquete observado**. Clique em **Levar gado no campo**. Mostre a verificação **Cumprida** e volte ao **Mapa** para localizar as coleiras.
5. Mova as mesmas coleiras para outro piquete pelo simulador. Avance dois dias, em dois cliques separados. Mostre **Divergente**, a fração no destino e a diferença entre esperado e observado na tabela.
6. Abra a instância em modo arquivo. Em **Campo**, mostre uma verificação identificada como **SeuGado**. Explique o vínculo dos piquetes e o aviso exibido quando o plano externo está indisponível.
7. Abra `CLAUDE.md`, uma [spec](../specs/SPEC-011-telas-coleiras-verificacao.md) e os [diagramas UML](uml/README.md). Rode `uv run pytest` em `backend/` e mostre como os cenários cobrem as regras e os caminhos de falha.

## Vídeo de reserva · 25/11

Grave o roteiro após o ensaio em uma instância com dados de demonstração. Deixe visíveis o retorno do simulador, os dois status de verificação, a origem SeuGado e o resultado do pytest. Revise a gravação e confira se ela pode ser reproduzida sem conexão.
