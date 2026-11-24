# language: pt
# Fonte: specs/SPEC-016-conjunto-ouro.md
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
