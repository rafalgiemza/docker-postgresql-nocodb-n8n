# Zgłoszenie do NocoDB: v3 meta API nie pozwala wskazać źródła przy tworzeniu tabeli

Materiał do issue + PR w `nocodb/nocodb`. Treść zgłoszenia po **angielsku**
(projekt międzynarodowy) — komentarze i instrukcje tutaj po polsku.

## Dlaczego to nasza sprawa

`scripts/init-schema.py` musi tworzyć 16 tabel w bazie `appdata`
(schemat `crm`), podpiętej w NocoDB jako zewnętrzne źródło danych. To nasze
źródło prawdy — objęte `make backup`, dostępne dla `n8n_crm_user`, dumpowane
do `appdata/appdata_schema.sql`. Wewnętrzna baza NocoDB nie jest żadną z tych
rzeczy.

v3 tego nie potrafi, więc skrypt stoi na v2 — czyli na API zapowiedzianym do
wycofania. To dług, który sami sobie zapisaliśmy w nagłówku skryptu; zgłoszenie
jest próbą jego spłaty u źródła.

---

## Zanim otworzysz — odrób te trzy rzeczy

Maintainerzy zamykają zgłoszenia, które tego nie mają.

**1. Sprawdź wersję, na której to obserwujesz.** Wersja jest teraz literalnie
przypięta w `fragments/nocodb-compose.yml` (`image: nocodb/nocodb:...`,
zarządzana przez Dependabot — patrz `.github/dependabot.yml`).

Jeśli to nie jest najnowszy release — zaktualizuj i powtórz repro **przed**
zgłoszeniem. Bug zgłoszony na starej wersji dostaje "please retry on latest".

**2. Poszukaj duplikatu.** W issues i discussions:
`is:issue source_id table create v3`, `external data source create table api`.
Sąsiednie, ale **to nie duplikaty** — warto je zalinkować jako kontekst:
- [#11309](https://github.com/nocodb/nocodb/issues/11309) — v3 meta endpoints rozjechane ze Swaggerem
- [#10178](https://github.com/nocodb/nocodb/issues/10178) — nie da się utworzyć source przez API
- [#9990](https://github.com/nocodb/nocodb/issues/9990) — dodanie źródła wymaga `CREATE DATABASE`
- [#3610](https://github.com/nocodb/nocodb/discussions/3610) — nieudokumentowany kontrakt kolumn Links

**3. Potwierdź, że v2 faktycznie działa na tej samej wersji.** To jest oś
całego zgłoszenia — bez tego to feature request, a z tym: regresja.

---

## Treść issue (do wklejenia)

**Tytuł:**

```
v3 meta API: cannot target a data source when creating a table (parity gap vs v2)
```

**Labels:** `bug` albo `enhancement` — zaproponuj `bug`, uzasadniając regresją
względem v2. Niech maintainer przeklasyfikuje, jeśli się nie zgodzi.

**Body:**

```markdown
### Summary

`POST /api/v3/meta/bases/{base_id}/tables` always creates the table in the
base's **default** source. There is no way to target a different (external)
data source — neither as a path segment nor as a request-body field.

The equivalent v2 endpoint supports this via an optional path segment:
`POST /api/v2/meta/bases/{baseId}/{sourceId}/tables`.

Since v3 is positioned to replace v2, this is a capability regression on the
migration path, not a missing nice-to-have.

### Environment

- NocoDB: <WERSJA>
- Deployment: self-hosted, Docker
- Metadata DB: PostgreSQL
- External data source: PostgreSQL (separate database, non-public schema)

### Steps to reproduce

1. Create a base.
2. Add an external PostgreSQL data source to it (Database `appdata`,
   Schema `crm`). The base now has two sources: the internal default one and
   the external one.
3. Get the external source id from `GET /api/v3/meta/bases/{base_id}`
   (`sources[]`).
4. Create a table, attempting to target that source:

```bash
curl -X POST -H "xc-token: $TOKEN" -H "Content-Type: application/json" \
  "$NC/api/v3/meta/bases/$BASE_ID/tables" \
  -d '{"title":"probe","source_id":"'"$SOURCE_ID"'",
       "fields":[{"title":"name","type":"SingleLineText"}]}'
```

5. Inspect where the physical table landed:

```sql
-- external database: empty
\dt crm.*
-- NocoDB metadata database: table is here, in a schema named after the base id
\dt "<base_id>".*
```

### Expected

The table is created in the specified data source (external PostgreSQL,
schema `crm`).

### Actual

- HTTP 200, table created successfully.
- `source_id` in the request body is silently ignored.
- The physical table is created in NocoDB's own metadata database, in a schema
  named after the base id.

No error or warning indicates that the requested source was not honoured —
this is the part that makes it costly to debug: the UI renders such a table
identically regardless of which database it physically lives in.

### Evidence from the spec

In `noco-apis-doc/meta-apis-v3/swagger-v3.json`:

- `POST /api/v3/meta/bases/{base_id}/tables` — request body has no
  source-related field; `source_id` appears only in the **response**.
- There is no path variant carrying a source id.
- There is no dedicated endpoint listing a base's sources (only the `sources`
  array inside `GET /api/v3/meta/bases/{baseId}`).

### Impact

Bootstrapping a schema into an external data source is only possible via v2.
Any project doing infrastructure-as-code against an external database is
therefore pinned to the API generation that is slated for removal.

Silent fallback makes this worse than an explicit rejection: a 400
"source_id not supported" would have cost minutes instead of hours.

### Proposed fix

Accept an optional source selector on v3 table creation, mirroring v2:

- preferred (v3 style): `source_id` in the request body,
- or: optional path segment, as in v2.

Behaviour when omitted stays as today (default source), so this is
backward-compatible. If the field cannot be honoured, reject with 400 rather
than ignoring it.

Also worth considering: `GET /api/v3/meta/bases/{base_id}/sources`, so callers
don't have to parse the whole base payload to discover source ids.
```

---

## Zakres PR

Nie czytałem kodu NocoDB, więc poniższe to **mapa do zweryfikowania**, nie
gotowy diff. Zacznij od znalezienia handlera v3 dla tabel i porównania go
z v2 — v2 już to robi, więc najprawdopodobniej wystarczy przeniesienie logiki,
a nie pisanie jej od zera.

**Co znaleźć:**

```bash
# route'y i kontrolery v3 dla tabel
rg -n "v3/meta/bases" --glob '!**/node_modules/**'
rg -n "tableCreate" --glob '!**/node_modules/**'
# jak v2 wybiera source - to jest wzorzec do skopiowania
rg -n "sourceId" packages/nocodb/src/controllers --glob '!**/node_modules/**'
```

**Czego prawdopodobnie dotknie zmiana:**

1. Kontroler v3 tabel — przyjęcie `source_id` z body i przekazanie dalej.
2. Warstwa serwisu — najpewniej wspólna z v2 i już parametryzowana źródłem;
   wtedy zmiana ogranicza się do kontrolera.
3. Walidacja — `source_id` musi należeć do tej bazy; obce id → 400, nie 500.
4. `swagger-v3.json` w `noco-apis-doc` (osobne repo — możliwe, że osobny PR).
5. Test: utworzenie tabeli w źródle innym niż domyślne i asercja, że
   `source_id` w odpowiedzi zgadza się z żądanym.

**Zakres, którego nie mieszaj do tego PR-a:**

- `GET /sources` dla v3 — osobne zgłoszenie, osobny PR (łatwiej przejdzie).
- Kolumny `Links` w v3 — inny temat, choć nas też dotyczy.

**Przed wysłaniem:** przeczytaj `CONTRIBUTING.md` w repo — NocoDB ma wymagania
co do formatu commitów i uruchomienia testów lokalnie.

---

## Czego NIE pisz w zgłoszeniu

- Nie opisuj naszego CRM-a ani procesu CoAction — maintainera interesuje
  minimalne repro, nie kontekst biznesowy.
- Nie wklejaj nazw naszych baz/hostów/tokenów. W repro używaj `appdata`/`crm`
  jako neutralnych przykładów (są generyczne) i zmiennych `$TOKEN`, `$NC`.
- Nie twierdź, że "v2 jest deprecated, więc musicie to naprawić" — to
  argument, ale podany jako żądanie działa przeciw Tobie. Wystarczy fakt
  parity gap.
