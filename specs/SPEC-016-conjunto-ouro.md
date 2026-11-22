# SPEC-016 · Conjunto-ouro do agente de manejo

Responsável: Leandro · Revisor: Leo Lima · Gantt: 7 · Camada DDD: core

## Contexto
O critério de aceitação da atividade 7 (agente inteligente) pede que **pelo menos 90% de 30 recomendações de um conjunto-ouro sejam plausíveis** e que **nenhuma recomendação viole as regras determinísticas**, reexecutando o conjunto a cada mudança de prompt ou de modelo. Nenhuma spec cobria isso. Esta spec cria o conjunto, o avaliador e o teste que cobra a meta.

O conjunto-ouro mede a **decisão** do agente (quem sai, para onde e quando), que é das regras. O Gemini só escreve a explicação (SPEC-005). Por isso o teste roda sem LLM, e a opção `--gemini` existe para conferir também as explicações quando o prompt ou o modelo mudar.

## Arquivos
- CRIAR `backend/conjunto_ouro/casos.json` (30 casos com entrada e gabarito)
- CRIAR `backend/maneja/conjunto_ouro.py` (avaliador e relatório)
- CRIAR `backend/features/conjunto_ouro.feature`, `backend/tests/test_conjunto_ouro.py`
- CRIAR `docs/05-conjunto-ouro.md` (relatório gerado)

## Requisitos
- **R1. Casos.** Cada caso tem a entrada (NDVI de cada piquete e idade da leitura, lotação por categoria, chuva dos 7 dias, rotas recusadas) e o gabarito: os piquetes que devem sair, os destinos plausíveis de cada um, o dia quando importa e as origens que devem gerar o alerta `sem_piquete_apto`. Cada gabarito tem uma justificativa em texto. Os gabaritos foram escritos antes de rodar o agente.
- **R2. Cobertura.** Os 30 casos cobrem: saída e permanência perto do limite de NDVI, capacidade do piquete (UA/ha), dois rebanhos disputando destinos, piquete ocupado, recusa recente e antiga, chuva forte (hoje, vários dias, semana toda, amanhã), semana seca, leitura de NDVI velha ou ausente (critério 1.1.1), destino no mínimo e logo abaixo, só bezerros, empate e fazenda sem gado.
- **R3. Avaliação.** Um caso é plausível quando: toda saída prevista acontece para um destino plausível, no dia previsto quando houver; nenhuma outra saída acontece; nenhuma movimentação cai em dia de chuva forte; os alertas de sem destino previstos aparecem; e `validar_movimento`, chamado de fora do agente, aprova cada movimentação.
- **R4. Meta.** O teste falha se menos de 90% dos casos forem plausíveis ou se houver qualquer violação de regra.
- **R5. Relatório.** `uv run python -m maneja.conjunto_ouro --relatorio` reescreve `docs/05-conjunto-ouro.md` com a taxa, a tabela dos 30 casos e a explicação dos não plausíveis.
- **R6. Gemini.** `--gemini` roda com o LLM configurado (`MANEJA_GEMINI_API_KEY`) e mostra quantas explicações passaram no validador R3. Os testes nunca usam rede.

## Cenários (BDD)
```gherkin
Funcionalidade: Conjunto-ouro do agente

  Cenário: O agente atinge a meta de plausibilidade
    Dado o conjunto-ouro com 30 casos
    Quando o agente é avaliado em todos os casos
    Então pelo menos 90% das recomendações são plausíveis
    E nenhuma recomendação viola as regras determinísticas

  Cenário: Um gabarito contrariado é marcado como não plausível
    Dado o caso "C01" com o destino plausível trocado para "Piquete Feijão"
    Quando o agente é avaliado nesse caso
    Então o caso não é plausível
```

## Fora do escopo
Mudar regras ou constantes do agente para "passar" nos casos. Os casos não plausíveis viram registro em `docs/05-conjunto-ouro.md` e, se a equipe decidir corrigir, uma nova spec.
