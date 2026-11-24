# Conjunto-ouro do agente de manejo

Gerado por `uv run python -m maneja.conjunto_ouro --relatorio` (SPEC-016). Não edite à mão: mude `backend/conjunto_ouro/casos.json` e rode de novo.

## Resultado

- **Plausíveis:** 27 de 30 (90%). Meta: 90%. Atingida.
- **Recomendações que violam as regras determinísticas:** 0. Meta: 0.
- **Data de referência dos casos:** 2026-11-22. Fazenda com os 5 piquetes da demonstração.

Cada caso traz a entrada (NDVI e idade da leitura, rebanho, chuva de 7 dias, recusas) e um gabarito escrito antes de rodar o agente: quem deve sair, para onde é plausível ir, em que dia e quando o certo é avisar que não há destino. Um caso é plausível quando o plano do agente cumpre todo o gabarito.

## Casos

| Caso | Situação | Gabarito | Agente recomendou | Resultado |
|---|---|---|---|---|
| C01 | Fazenda de demonstração: Abóbora esgotado | Piquete Abóbora → Piquete Macarrão | Piquete Abóbora → Piquete Macarrão (dia 0) | ✅ plausível |
| C02 | Pasto ainda bom não move | nenhuma movimentação | nenhuma movimentação | ✅ plausível |
| C03 | No limite de saída (0,35) fica | nenhuma movimentação | nenhuma movimentação | ✅ plausível |
| C04 | Logo abaixo do limite (0,34) sai | Piquete Abóbora → Piquete Macarrão ou Piquete Feijão | Piquete Abóbora → Piquete Macarrão (dia 0) | ✅ plausível |
| C05 | Rebanho pequeno cabe no melhor piquete | Piquete Abóbora → Piquete Jerimum | Piquete Abóbora → Piquete Jerimum (dia 0) | ✅ plausível |
| C06 | Todos os livres ainda em recuperação | Piquete Abóbora: alerta sem destino | alerta sem destino: Piquete Abóbora | ✅ plausível |
| C07 | Único livre degradado | Piquete Abóbora: alerta sem destino | alerta sem destino: Piquete Abóbora | ✅ plausível |
| C08 | Rebanho grande demais para qualquer piquete | Piquete Abóbora: alerta sem destino | alerta sem destino: Piquete Abóbora | ✅ plausível |
| C09 | Dois rebanhos saem, cada um para um piquete | Piquete Abóbora → Piquete Macarrão; Piquete Milho → Piquete Feijão ou Piquete Macarrão | Piquete Abóbora → Piquete Macarrão (dia 0); Piquete Milho → Piquete Feijão (dia 0) | ✅ plausível |
| C10 | Dois rebanhos, um só destino bom | Piquete Abóbora → Piquete Macarrão; Piquete Milho: alerta sem destino | Piquete Abóbora → Piquete Macarrão (dia 0); alerta sem destino: Piquete Milho | ✅ plausível |
| C11 | Rota recusada há 2 dias não volta | Piquete Abóbora → Piquete Feijão ou Piquete Milho | Piquete Abóbora → Piquete Feijão (dia 0) | ✅ plausível |
| C12 | Recusa antiga (10 dias) não bloqueia | Piquete Abóbora → Piquete Macarrão | Piquete Abóbora → Piquete Macarrão (dia 0) | ✅ plausível |
| C13 | Chuva forte hoje adia para amanhã | Piquete Abóbora → Piquete Macarrão (dia 1) | Piquete Abóbora → Piquete Macarrão (dia 1) | ✅ plausível |
| C14 | Três dias de chuva forte | Piquete Abóbora → Piquete Macarrão (dia 3) | Piquete Abóbora → Piquete Macarrão (dia 3) | ✅ plausível |
| C15 | Chuva forte a semana toda | nenhuma movimentação | Piquete Abóbora → Piquete Macarrão (dia 0) | ❌ movimentação marcada em dia de chuva forte (50 mm); moveu Piquete Abóbora para Piquete Macarrão, mas o gabarito não prevê essa saída |
| C16 | Semana seca ainda permite sair | Piquete Abóbora → Piquete Macarrão | Piquete Abóbora → Piquete Macarrão (dia 0) | ✅ plausível |
| C17 | Melhor NDVI com leitura de 40 dias | Piquete Abóbora → Piquete Feijão ou Piquete Milho | Piquete Abóbora → Piquete Macarrão (dia 0) | ❌ Piquete Abóbora foi para Piquete Macarrão, fora dos destinos plausíveis |
| C18 | Melhor piquete sem leitura | Piquete Abóbora → Piquete Feijão ou Piquete Milho | Piquete Abóbora → Piquete Feijão (dia 0) | ✅ plausível |
| C19 | Origem sem leitura de NDVI | nenhuma movimentação | nenhuma movimentação | ✅ plausível |
| C20 | Origem com leitura velha (30 dias) | nenhuma movimentação | Piquete Abóbora → Piquete Macarrão (dia 0) | ❌ moveu Piquete Abóbora para Piquete Macarrão, mas o gabarito não prevê essa saída |
| C21 | Livre passando do ponto recebe o gado | Piquete Abóbora → Piquete Feijão ou Piquete Macarrão | Piquete Abóbora → Piquete Feijão (dia 0) | ✅ plausível |
| C22 | Nenhum piquete ocupado | nenhuma movimentação | nenhuma movimentação | ✅ plausível |
| C23 | Linha de lotação zerada | nenhuma movimentação | nenhuma movimentação | ✅ plausível |
| C24 | Só bezerros (8 UA) | Piquete Abóbora → Piquete Jerimum | Piquete Abóbora → Piquete Jerimum (dia 0) | ✅ plausível |
| C25 | Empate entre destinos | Piquete Abóbora → Piquete Macarrão ou Piquete Milho | Piquete Abóbora → Piquete Macarrão (dia 0) | ✅ plausível |
| C26 | Piquete bom já ocupado não recebe | Piquete Abóbora → Piquete Macarrão; Piquete Feijão → Piquete Jerimum | Piquete Abóbora → Piquete Macarrão (dia 0); Piquete Feijão → Piquete Jerimum (dia 0) | ✅ plausível |
| C27 | Destino exatamente no mínimo (0,50) | Piquete Abóbora → Piquete Macarrão | Piquete Abóbora → Piquete Macarrão (dia 0) | ✅ plausível |
| C28 | Destino logo abaixo do mínimo (0,49) | Piquete Abóbora: alerta sem destino | alerta sem destino: Piquete Abóbora | ✅ plausível |
| C29 | Chuva forte só amanhã: move hoje | Piquete Abóbora → Piquete Macarrão (dia 0) | Piquete Abóbora → Piquete Macarrão (dia 0) | ✅ plausível |
| C30 | Rebanho no limite de capacidade do único livre | Piquete Abóbora → Piquete Feijão | Piquete Abóbora → Piquete Feijão (dia 0) | ✅ plausível |

## Casos não plausíveis

### C15 · Chuva forte a semana toda

- **Por que o gabarito é este:** Não há dia seguro para mover. O plausível é não marcar movimentação sob chuva forte e esperar a próxima previsão.
- **O que o agente fez:** Piquete Abóbora → Piquete Macarrão (dia 0).
- **Problema:** movimentação marcada em dia de chuva forte (50 mm); moveu Piquete Abóbora para Piquete Macarrão, mas o gabarito não prevê essa saída.

### C17 · Melhor NDVI com leitura de 40 dias

- **Por que o gabarito é este:** A leitura do Macarrão tem 40 dias: o pasto pode ter mudado. Pelo critério 1.1.1 só vale leitura de até 7 dias. Feijão tem leitura recente.
- **O que o agente fez:** Piquete Abóbora → Piquete Macarrão (dia 0).
- **Problema:** Piquete Abóbora foi para Piquete Macarrão, fora dos destinos plausíveis.

### C20 · Origem com leitura velha (30 dias)

- **Por que o gabarito é este:** A leitura do Abóbora tem 30 dias. Pelo critério 1.1.1 o piquete fica fora da análise e deve ser sinalizado, não movido às cegas.
- **O que o agente fez:** Piquete Abóbora → Piquete Macarrão (dia 0).
- **Problema:** moveu Piquete Abóbora para Piquete Macarrão, mas o gabarito não prevê essa saída.

## Justificativa de cada gabarito

- **C01.** Abóbora está esgotado. Jerimum tem mais pasto, mas é pequeno para 20 UA. Macarrão é o melhor que comporta o rebanho.
- **C02.** Com NDVI 0,55 o pasto ainda sustenta o rebanho. Mover agora só encurtaria o descanso dos outros.
- **C03.** Está no limite. Ficar mais alguns dias é aceitável e evita mudar cedo demais.
- **C04.** Pasto já abaixo do ponto de saída. Qualquer piquete descansado que comporte o rebanho serve.
- **C05.** 5 UA cabem no Jerimum, que tem o melhor pasto.
- **C06.** Nenhum piquete livre recuperou. Mandar o gado só esgotaria outro piquete: o certo é avisar para suplementar.
- **C07.** O único piquete livre (Feijão) também está ruim.
- **C08.** 59 UA não cabem nem no Macarrão (máx. 49 UA). Melhor avisar para dividir o lote.
- **C09.** Os dois piquetes estão esgotados. O pior escolhe primeiro (Macarrão) e o outro vai para o próximo bom que comporta (Feijão).
- **C10.** Só o Macarrão está pronto. O pior piquete tem prioridade; o outro rebanho precisa de alerta.
- **C11.** O produtor recusou o Macarrão há 2 dias. Insistir seria ignorar a decisão dele.
- **C12.** A recusa já tem mais de uma semana; a situação mudou.
- **C13.** Não se move gado sob chuva forte. Amanhã o tempo melhora.
- **C14.** Mover no primeiro dia sem chuva forte.
- **C15.** Não há dia seguro para mover. O plausível é não marcar movimentação sob chuva forte e esperar a próxima previsão.
- **C16.** Seca não impede a saída de um piquete esgotado; só o rebrote fica mais lento.
- **C17.** A leitura do Macarrão tem 40 dias: o pasto pode ter mudado. Pelo critério 1.1.1 só vale leitura de até 7 dias. Feijão tem leitura recente.
- **C18.** Sem leitura do Macarrão não dá para saber o pasto; escolher entre os conhecidos.
- **C19.** Sem dado do piquete ocupado não há base para mandar sair.
- **C20.** A leitura do Abóbora tem 30 dias. Pelo critério 1.1.1 o piquete fica fora da análise e deve ser sinalizado, não movido às cegas.
- **C21.** Aproveitar o Feijão, que está passando do ponto, ou o Macarrão: os dois servem.
- **C22.** Sem gado no pasto, não há o que mover.
- **C23.** Piquete com zero animais está livre.
- **C24.** 20 bezerros equivalem a 8 UA e cabem no Jerimum, o melhor pasto.
- **C25.** Com o mesmo NDVI, os dois são plausíveis.
- **C26.** Milho está ocupado e fica. Abóbora (20 UA) vai para o Macarrão; Feijão (10 UA) cabe no Jerimum.
- **C27.** Macarrão atingiu o ponto de entrada; dá para receber.
- **C28.** Nenhum piquete chegou ao ponto de entrada.
- **C29.** Hoje o tempo está bom; adiar faria o gado passar a chuva no pasto esgotado.
- **C30.** 28 UA cabem nos 4,73 ha do Feijão (máx. 28,4 UA).
