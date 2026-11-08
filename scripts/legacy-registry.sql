-- Rejestr ID importu/eksportu starego CRM (poza schematem crm - NocoDB go nie widzi).
-- Jeden wiersz = jeden wiersz Excela: export_id (kolumna ID w pliku), lead i szansa.
-- Numery z sekwencji nie wracaja nigdy, nawet po usunieciu rekordu.
-- Uruchamiane z `make grant-crm-legacy` (psql -v u=<rola>), idempotentne.
CREATE SCHEMA IF NOT EXISTS legacy;
CREATE SEQUENCE IF NOT EXISTS legacy.export_id_seq;
CREATE TABLE IF NOT EXISTS legacy.rows (
  export_id      bigint PRIMARY KEY,
  lead_id        bigint,
  opportunity_id bigint,
  source         text NOT NULL DEFAULT 'import',
  created_at     timestamptz NOT NULL DEFAULT now());
ALTER TABLE legacy.rows ADD COLUMN IF NOT EXISTS orig jsonb;  -- surowe niepuste komorki wiersza z importu
-- ustawienia eksportu: naglowek pliku wejsciowego ('header'), oryginalne zapisy handlowcow ('seller:<id>')
CREATE TABLE IF NOT EXISTS legacy.meta (key text PRIMARY KEY, value jsonb NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS rows_opportunity_uniq ON legacy.rows (opportunity_id)
  WHERE opportunity_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS rows_lead_idx ON legacy.rows (lead_id);
GRANT USAGE ON SCHEMA legacy TO :"u";
GRANT SELECT, INSERT, UPDATE, DELETE ON legacy.rows, legacy.meta TO :"u";
GRANT USAGE, SELECT, UPDATE ON SEQUENCE legacy.export_id_seq TO :"u";
