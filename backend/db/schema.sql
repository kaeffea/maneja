-- Maneja · esquema do PostgreSQL (SPEC-008, SPEC-017, SPEC-018). Idempotente: pode rodar a cada subida.

CREATE TABLE IF NOT EXISTS cliente (
    id          text PRIMARY KEY,
    nome        text NOT NULL,
    contato     text NOT NULL DEFAULT '',
    seugado_id  text,
    ordem       integer NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS usuario (
    id          text PRIMARY KEY,
    email       text NOT NULL UNIQUE,
    senha_hash  text NOT NULL,
    papel       text NOT NULL CHECK (papel IN ('admin', 'cliente')),
    cliente_id  text REFERENCES cliente(id) ON DELETE SET NULL,
    nome        text NOT NULL DEFAULT '',
    ordem       integer NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS fazenda (
    id          text PRIMARY KEY,
    nome        text NOT NULL,
    timezone    text NOT NULL,
    cliente_id  text REFERENCES cliente(id) ON DELETE SET NULL,
    seugado_id  text,
    ordem       integer NOT NULL DEFAULT 0
);
ALTER TABLE fazenda ADD COLUMN IF NOT EXISTS cliente_id text REFERENCES cliente(id) ON DELETE SET NULL;
ALTER TABLE fazenda ADD COLUMN IF NOT EXISTS seugado_id text;
ALTER TABLE fazenda ADD COLUMN IF NOT EXISTS ordem integer NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS piquete (
    id          text PRIMARY KEY,
    fazenda_id  text NOT NULL REFERENCES fazenda(id) ON DELETE CASCADE,
    nome        text NOT NULL,
    geometria   jsonb NOT NULL,
    area_ha     double precision NOT NULL,
    vegetacao   text NOT NULL DEFAULT '',
    externo_id  text,
    ordem       integer NOT NULL,
    ativo       boolean NOT NULL DEFAULT true
);
ALTER TABLE piquete ADD COLUMN IF NOT EXISTS ativo boolean NOT NULL DEFAULT true;

CREATE TABLE IF NOT EXISTS lote (
    id                text PRIMARY KEY,
    fazenda_id        text NOT NULL REFERENCES fazenda(id) ON DELETE CASCADE,
    nome              text NOT NULL,
    piquete_atual_id  text REFERENCES piquete(id) ON DELETE SET NULL,
    bois              integer NOT NULL DEFAULT 0 CHECK (bois >= 0),
    vacas             integer NOT NULL DEFAULT 0 CHECK (vacas >= 0),
    bezerros          integer NOT NULL DEFAULT 0 CHECK (bezerros >= 0),
    desde             date,
    seugado_id        text,
    ordem             integer NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS lotacao (
    piquete_id  text PRIMARY KEY REFERENCES piquete(id) ON DELETE CASCADE,
    fazenda_id  text NOT NULL,
    bois        integer NOT NULL CHECK (bois >= 0),
    vacas       integer NOT NULL CHECK (vacas >= 0),
    bezerros    integer NOT NULL CHECK (bezerros >= 0),
    desde       date
);

CREATE TABLE IF NOT EXISTS leitura_ndvi (
    piquete_id  text NOT NULL REFERENCES piquete(id) ON DELETE CASCADE,
    data        date NOT NULL,
    valor       double precision NOT NULL,
    PRIMARY KEY (piquete_id, data)
);

-- histórico de movimentações (mais recente = ordem 0); o JSON tem os campos de src/lib/tipos.ts
CREATE TABLE IF NOT EXISTS movimentacao (
    id          text PRIMARY KEY,
    ordem       integer NOT NULL,
    dados       jsonb NOT NULL,
    fazenda_id  text NOT NULL DEFAULT ''
);
ALTER TABLE movimentacao ADD COLUMN IF NOT EXISTS fazenda_id text NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS plano_atual (
    fazenda_id  text PRIMARY KEY REFERENCES fazenda(id) ON DELETE CASCADE,
    dados       jsonb NOT NULL
);

-- migração segura da tabela plano_atual v1 (coluna unico boolean) para v2 (fazenda_id text)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'plano_atual' AND column_name = 'unico'
    ) THEN
        ALTER TABLE plano_atual ADD COLUMN IF NOT EXISTS fazenda_id text;
        UPDATE plano_atual
           SET fazenda_id = COALESCE(dados->>'fazenda_id', (SELECT id FROM fazenda ORDER BY ordem, id LIMIT 1))
         WHERE fazenda_id IS NULL;
        ALTER TABLE plano_atual DROP CONSTRAINT IF EXISTS plano_atual_pkey;
        ALTER TABLE plano_atual DROP CONSTRAINT IF EXISTS plano_atual_unico_check;
        ALTER TABLE plano_atual DROP COLUMN IF EXISTS unico;
        DELETE FROM plano_atual WHERE fazenda_id IS NULL;
        ALTER TABLE plano_atual ADD PRIMARY KEY (fazenda_id);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS coleira (
    id                   text PRIMARY KEY,
    categoria            text NOT NULL,
    piquete_cadastro_id  text NOT NULL,
    piquete_fisico_id    text NOT NULL,  -- onde o simulador diz que o animal está de fato
    ordem                integer NOT NULL,
    fazenda_id           text NOT NULL DEFAULT '',
    lote_id              text
);
ALTER TABLE coleira ADD COLUMN IF NOT EXISTS fazenda_id text NOT NULL DEFAULT '';
ALTER TABLE coleira ADD COLUMN IF NOT EXISTS lote_id text;

CREATE TABLE IF NOT EXISTS posicao (
    id         bigserial PRIMARY KEY,
    coleira_id text NOT NULL,
    instante   timestamptz NOT NULL,
    lat        double precision NOT NULL,
    lon        double precision NOT NULL
);
CREATE INDEX IF NOT EXISTS posicao_instante ON posicao (instante);

CREATE TABLE IF NOT EXISTS grupo_externo (
    externo_id  text PRIMARY KEY,
    coleiras    jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS parametro (
    chave  text PRIMARY KEY,
    valor  text NOT NULL
);
