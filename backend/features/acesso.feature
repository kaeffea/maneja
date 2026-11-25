# language: pt
# Fonte: specs/SPEC-017-acesso-admin-clientes.md
Funcionalidade: Acesso por papel (admin e cliente)

  Cenário: Rota protegida sem login devolve 401
    Quando eu consulto "/fazendas" sem token
    Então a resposta é 401

  Cenário: Admin vê todos os clientes e todas as fazendas
    Dado dois clientes com fazendas próprias
    Quando o admin lista fazendas e clientes
    Então o admin vê as duas fazendas e os dois clientes

  Cenário: Cliente vê apenas a própria fazenda
    Dado dois clientes com fazendas próprias
    Quando o cliente A lista "/fazendas"
    Então o cliente A vê apenas a fazenda do cliente A

  Cenário: Cliente não lê nem altera dados da fazenda de outro cliente
    Dado dois clientes com fazendas próprias
    Quando o cliente A tenta ler os piquetes da fazenda do cliente B
    Então a resposta é 403
    Quando o cliente A tenta criar um piquete na fazenda do cliente B
    Então a resposta é 403
    Quando o cliente A tenta editar um piquete da fazenda do cliente B
    Então a resposta é 403
    Quando o cliente A tenta alterar a lotação da fazenda do cliente B
    Então a resposta é 403

  Cenário: Cliente não acessa rotas de administração
    Dado dois clientes com fazendas próprias
    Quando o cliente A tenta listar "/clientes"
    Então a resposta é 403
    Quando o cliente A tenta criar um usuário
    Então a resposta é 403

  Cenário: Cliente edita a própria fazenda, piquetes e rebanho
    Dado dois clientes com fazendas próprias
    Quando o cliente A renomeia a própria fazenda e atualiza a lotação do próprio piquete
    Então as alterações da fazenda do cliente A são salvas com sucesso
