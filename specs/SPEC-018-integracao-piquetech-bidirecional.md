# SPEC-018 · Integração bidirecional multi-fazenda com o PiqueTech (SeuGado)

Responsável: Kauê · Camada DDD: Integration

## Contexto

Com a ADR-035 já em produção no PiqueTech (`api.piquetech.app`), o PiqueTech consulta `GET /integracao/v1/execucoes?desde=AAAA-MM-DD` a cada hora e confirma automaticamente movimentações cumpridas para qualquer fazenda integrada. Esta spec evolui a integração do Maneja (SPEC-012) de fazenda única por variável de ambiente para **múltiplas fazendas vinculadas por UUID**, com **importação (e atualização)** do PiqueTech para o Maneja, **exportação** do Maneja para o PiqueTech, associação de coleiras a lotes importados e cobertura de todas as fazendas integradas em `/integracao/v1/execucoes`.

## Arquivos

- ALTERAR `backend/maneja/dominio.py` (`seugado_id` em `Cliente`, `Fazenda`, `Lote`; `ativo` em `Piquete`; `lote_id` em `Coleira`)
- ALTERAR `backend/maneja/config.py` (remover dependência de `MANEJA_SEUGADO_FAZENDA_ID`)
- ALTERAR `backend/maneja/adaptadores/seugado.py` (cache de plano por `fazenda_id`, leitura de clientes/fazendas/piquetes/lotes/cultivares e criação via POST)
- ALTERAR `backend/maneja/verificacao.py` (grupo de coleiras por `lote_id` e não congelar grupo vazio antes da associação de coleiras)
- ALTERAR `backend/maneja/servico.py` e `backend/maneja/api.py` (importar, atualizar, exportar, associar coleiras a lote/piquete e `execucoes` agregando todas as fazendas integradas)
- ALTERAR `src/lib/tipos.ts`, `src/lib/api.ts`, `src/paginas/Admin.tsx`, `src/paginas/Campo.tsx`, `src/paginas/Configuracoes.tsx`
- ALTERAR `docs/02-integracao-seugado.md`
- CRIAR `backend/features/piquetech.feature` e `backend/tests/test_piquetech.py`

## Requisitos

- **R1 (Vínculo por UUID):** `cliente.seugado_id`, `fazenda.seugado_id`, `piquete.externo_id` e `lote.seugado_id` (todos opcionais). Fazenda com `seugado_id` é integrada; sem ele, opera apenas no Maneja. Sai `MANEJA_SEUGADO_FAZENDA_ID`.
- **R2 (Plano por fazenda):** em modo `api`, `SeuGadoApi.plano_atual(seugado_fazenda_id)` mantém cache de 10 minutos por fazenda e busca `GET /fazendas/{seugado_fazenda_id}/plano/atual`. Falha externa vira aviso `plano_externo_indisponivel` e nunca derruba o Maneja.
- **R3 (Importar e atualizar do PiqueTech):**
  - `GET /integracao/piquetech/fazendas` (admin): lista fazendas do PiqueTech indicando quais já existem no Maneja.
  - `POST /integracao/piquetech/importar/{seugado_fazenda_id}` e `POST /fazendas/{fazenda_id}/integracao/piquetech/atualizar` (admin): lê `/clientes`, `/fazendas`, `/fazendas/{id}/piquetes` e `/fazendas/{id}/lotes`; faz upsert por UUID de cliente, fazenda, piquetes (marcando como `ativo=False` piquetes que sumiram do PiqueTech sem apagar histórico de coleiras) e lotes (sincronizando `lotacao`).
  - Mapeamento de categorias na importação: `boi`, `touro`, `novilho` → `bois`; `vaca`, `novilha` → `vacas`; `bezerro`, `bezerra` → `bezerros`.
- **R4 (Exportar do Maneja para o PiqueTech):**
  - `GET /integracao/piquetech/cultivares` (admin): lista cultivares do PiqueTech (`GET /cultivares`).
  - `POST /fazendas/{fazenda_id}/integracao/piquetech/exportar` (admin, com `cultivar_id` e `metodo_pastejo="rotacionado"`): cria na ordem (1) cliente (pula se já tem `seugado_id`), (2) fazenda com padrões operacionais válidos, (3) piquetes ativos, (4) lotes ocupados (`bois → boi`, `vacas → vaca`, `bezerros → bezerro`), gravando todos os UUIDs retornados.
- **R5 (Coleiras em lotes importados e simulador):**
  - `POST /fazendas/{fazenda_id}/coleiras`: cria e associa `quantidade` coleiras a um `lote_id` ou `piquete_id`, posicionando-as no piquete atual com leitura GPS imediata.
  - No simulador da tela `Campo`, movimentações vindas do PiqueTech (`origem_plano == "seugado"`) também podem ser executadas no campo.
- **R6 (`/integracao/v1/execucoes` multi-fazenda):** mantém exatamente o contrato JSON atual, agregando as verificações de **todas** as fazendas integradas (`fazenda.seugado_id` preenchido) com `data >= desde`.

## Cenários (BDD)

```gherkin
# language: pt
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
    Dado uma fazenda do Maneja ainda sem vínculo externo
    Quando o admin exporta a fazenda para o PiqueTech usando a cultivar Marandu
    Então o PiqueTech recebe cliente, fazenda, piquetes e lotes e o Maneja guarda todos os UUIDs

  Cenário: Execuções agregam várias fazendas integradas no contrato v1
    Dado duas fazendas integradas ao PiqueTech com coleiras nos lotes
    Quando o gado da Fazenda Aula é levado ao destino no campo
    E o PiqueTech consulta "/integracao/v1/execucoes?desde=2026-11-01"
    Então a movimentação da Fazenda Aula aparece como "cumprida" junto com a outra fazenda
```

## Fora do escopo

- Copiar SAFER, régua de altura, motor de otimização ou bot do Telegram para o Maneja.
- Alterar `GET /plano/atual` ou `POST /auth/token` do PiqueTech.
- Envio automático de `piquete_observado_externo_id` para `divergente` (v1.1).

## Situação

Feita em 25/11 (`backend/features/piquetech.feature`, `backend/tests/test_piquetech.py`, importação/atualização/exportação bidirecional, coleiras em lotes e `/integracao/v1/execucoes` multi-fazenda).
