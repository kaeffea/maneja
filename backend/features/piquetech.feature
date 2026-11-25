# language: pt
# Fonte: specs/SPEC-018-integracao-piquetech-bidirecional.md
Funcionalidade: Integração bidirecional multi-fazenda com o PiqueTech

  Cenário: Importar fazenda do PiqueTech cria cliente, fazenda, piquetes e lotes
    Dado uma API simulada do PiqueTech com a Fazenda Aula
    Quando o admin importa a Fazenda Aula pelo UUID
    Então o Maneja cria o cliente, a fazenda, 3 piquetes e o lote "Recria" vinculados por UUID

  Cenário: Atualizar do PiqueTech inativa piquete removido sem perder coleiras
    Dado uma fazenda já importada do PiqueTech com 3 piquetes
    Quando o PiqueTech remove um piquete e o admin atualiza a fazenda
    Então o piquete removido fica inativo e os demais são atualizados

  Cenário: Exportar fazenda do Maneja cria cliente, fazenda, piquetes e lotes no PiqueTech
    Dado uma API simulada do PiqueTech pronta para criação
    Quando o admin exporta a fazenda de demonstração para o PiqueTech usando a cultivar Marandu
    Então o PiqueTech recebe cliente, fazenda, piquetes e lotes e o Maneja guarda todos os UUIDs

  Cenário: Execuções agregam várias fazendas integradas no contrato v1
    Dado duas fazendas integradas ao PiqueTech com coleiras nos lotes
    Quando o gado da Fazenda Aula é levado ao destino no campo
    E o PiqueTech consulta "/integracao/v1/execucoes?desde=2026-11-01"
    Então a movimentação da Fazenda Aula aparece como "cumprida" junto com a outra fazenda
