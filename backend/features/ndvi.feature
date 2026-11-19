# language: pt
Funcionalidade: NDVI por satélite

  Esquema do Cenário: Só imagens com nuvens dentro do limite entram na série
    Dado uma imagem com fração de nuvem <nuvem>
    Quando atualizo o NDVI pela API
    Então a leitura da imagem foi registrada: <registrada>

    Exemplos:
      | nuvem | registrada |
      | 0.05  | sim        |
      | 0.30  | sim        |
      | 0.80  | não        |
