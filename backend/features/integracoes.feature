# language: pt
Funcionalidade: Adaptadores externos

  Esquema do Cenário: Gemini explica o plano quando disponível e dentro da cota
    Dado um Gemini com HTTP <http> e cota <cota>
    Quando gero o plano de manejo
    Então a origem da explicação é "<origem>"

    Exemplos:
      | http | cota | origem |
      | 200  | 50   | llm    |
      | 500  | 50   | regra  |
      | 429  | 50   | regra  |
      | 200  | 0    | regra  |

  Esquema do Cenário: Open-Meteo mantém a previsão disponível
    Dado o Open-Meteo com HTTP <http> e cache <cache>
    Quando consulto o clima
    Então a fonte da previsão é "<fonte>"

    Exemplos:
      | http | cache | fonte      |
      | 200  | não   | open-meteo |
      | 500  | sim   | open-meteo |
      | 500  | não   | simulado   |

  Esquema do Cenário: SeuGado é uma fonte opcional
    Dado o SeuGado com HTTP <http> para o plano
    Quando verifico as movimentações
    Então o resultado do plano externo é "<resultado>"

    Exemplos:
      | http | resultado                  |
      | 200  | seugado                    |
      | 404  | sem_plano                  |
      | 503  | plano_externo_indisponivel |
