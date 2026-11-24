# language: pt
# Fonte: specs/SPEC-005-gemini.md
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
