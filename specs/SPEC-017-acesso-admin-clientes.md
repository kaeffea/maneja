# SPEC-017 · Acesso por papel (admin e cliente) e multi-fazenda

Responsável: Kauê · Camada DDD: Generic / Access Control

## Contexto

Até a SPEC-016 o Maneja tinha um único login de técnico e uma única fazenda por instância. Para operar como produto real (e sustentar a integração multi-fazenda com o PiqueTech), o sistema precisa separar **administradores** (que gerenciam vários clientes, fazendas e usuários) de **clientes** (que acessam e editam apenas as próprias fazendas), com verificação obrigatória no back-end em toda rota de fazenda.

## Arquivos

- ALTERAR `backend/maneja/dominio.py` (entidades `Cliente`, `Usuario`, `Lote`, campos `cliente_id` e `fazenda_id`)
- ALTERAR `backend/maneja/autenticacao.py` (`SessaoUsuario`, `emitir_token` com `papel`/`cliente_id`, `validar_sessao`)
- ALTERAR `backend/maneja/repositorio.py` e `backend/maneja/demo.py` (múltiplas fazendas, clientes e usuários mantendo compatibilidade com a fazenda de demonstração)
- ALTERAR `backend/db/schema.sql` e `backend/maneja/repositorio_pg.py` (tabelas `cliente`, `usuario`, `lote`, migração idempotente de bancos já em produção e `plano_atual` por fazenda)
- ALTERAR `backend/maneja/servico.py` (operações escopadas por `fazenda_id` e CRUD de clientes, fazendas, usuários e coleiras)
- ALTERAR `backend/maneja/api.py` (dependências `exigir_sessao`, `exigir_admin`, `exigir_acesso_fazenda`, rotas `/clientes`, `/usuarios`, `/fazendas` e `/fazendas/{fazenda_id}/...`)
- ALTERAR `src/lib/tipos.ts`, `src/lib/api.ts`, `src/lib/fazenda.tsx`, `src/App.tsx`, `src/componentes/Layout.tsx`, `src/componentes/Layout.css`, `src/paginas/Mapa.tsx`
- CRIAR `src/paginas/Admin.tsx` e `src/paginas/Admin.css`
- CRIAR `backend/features/acesso.feature` e `backend/tests/test_acesso.py`

## Requisitos

- **R1 (Modelo):**
  - `Cliente(id, nome, contato="", seugado_id=None)`
  - `Fazenda(id, nome, timezone="America/Maceio", cliente_id=None, seugado_id=None)`
  - `Usuario(id, email, senha_hash, papel: "admin" | "cliente", cliente_id=None, nome="")`
- **R2 (Admin padrão):** o login configurado por `MANEJA_USUARIO_EMAIL` / `MANEJA_USUARIO_SENHA` (ou `_HASH`) entra com `papel = "admin"` e `cliente_id = None`.
- **R3 (Autenticação de usuários do banco):** `POST /auth/token` autentica tanto o admin de ambiente quanto qualquer usuário cadastrado em `usuario`, devolvendo `access_token`, `token_type`, `expira_em`, `email`, `nome`, `papel`, `cliente_id`. `GET /me` devolve `id`, `email`, `nome`, `papel`, `cliente_id`.
- **R4 (Autorização no back-end):**
  - Rotas administrativas (`GET/POST/PUT /clientes`, `GET/POST/PUT /usuarios`, `POST /fazendas`) exigem `papel == "admin"`; cliente recebe `403`.
  - `GET /fazendas` lista todas as fazendas para `admin`, e apenas aquelas com `fazenda.cliente_id == sessao.cliente_id` para `cliente`.
  - Toda rota de fazenda (`/fazendas/{fazenda_id}/...` e os atalhos `/fazenda`, `/piquetes`, `/lotacao`, `/ndvi`, `/clima`, `/resumo`, `/plano`, `/movimentacoes/...`, `/historico`, `/coleiras`, `/ocupacao`, `/verificacoes`, `/simulador/...`) verifica no back-end: `admin` passa sempre; `cliente` passa somente se `fazenda.cliente_id == sessao.cliente_id`, recebendo `403` caso contrário (ou `404` se a fazenda não existir).
  - Rota sem token válido responde `401`.
- **R5 (Persistência e migração segura):** o `schema.sql` migra bancos PostgreSQL já existentes (como o Supabase de produção) de forma idempotente, sem perda dos dados já salvos.
- **R6 (Telas no front-end):**
  - **Admin:** página `/admin` para listar/criar/editar clientes, fazendas (vinculadas a um cliente) e usuários (incluindo login de cliente), além de seletor de fazenda ativa para navegar pelas telas operacionais.
  - **Cliente:** ao entrar, cai direto na própria fazenda (`/mapa`). Não vê `/admin`, lista de clientes nem fazendas de outros clientes; se tiver mais de uma fazenda, pode alternar apenas entre as suas.

## Cenários (BDD)

```gherkin
# language: pt
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
```

## Fora do escopo

- Recuperação de senha por e-mail ou convite automático.
- Papel intermediário de "técnico ligado a subconjunto de fazendas" (opcional futuro).

## Situação

Feita em 25/11 (`backend/features/acesso.feature`, `backend/tests/test_acesso.py`, migração PostgreSQL v1→v2 testada e UI `/admin` + isolamento de cliente).
