# Zasady dostępu do NocoDB

Wyprowadzone z `schema_map.json`, `Makefile` i historii w
`docs/archive/fable/README.md`. Doktryna ogólna w [common.md](common.md) §1;
mechanika flow w [n8n.md](n8n.md).

## 1. Nigdy nie zgaduj ID tabel/pól

Table ID (`m...`), field ID (`c...`), workspace/project ID nie są do
zgadywania ani przepisywania z pamięci. Źródło prawdy:
`docs/archive/fable/schema_map.json`, generowany przez:

```
make dump-crm-schema
```

(dumpuje live ID tabel/pól + relacje do `schema_map.json`, patrz
`scripts/dump-crm-schema.sh`). Jeśli potrzebnego ID nie ma w dumpie albo dump
jest stary — **poproś usera o ponowne odpalenie `make dump-crm-schema`**,
zamiast zgadywać wartość albo wpisywać placeholder na hurra (zgodnie z
istniejącą zasadą feedbacku o brakującym ID).

Przed importem/edycją flow z hardkodowanymi ID zawsze odśwież dump i
zdiffuj — ID drfyują przy zmianach schematu (zdarzyło się już z tabelą
`leads` po przebudowie i z nazwą pola zwrotnego `document_templates` —
NocoDB nazywa pola odwrotnych relacji automatycznie i nie da się tego
wymusić skryptem).

## 2. Natywny node NocoDB, HTTP Request tylko dla dziur w API node'a

Patrz `.claude/skills/n8n-flow/SKILL.md` §4. Dla relacji M2M/link używaj
`resource: linkrow`. HTTP Request tylko dla endpointów bez pokrycia w
nodzie (np. `/api/v2/storage/upload`) — nazwij taki node opisowo ("Upload
offer file"), nie "HTTP Request".

## 3. Dwie konwencje sourcowania ID — nie miksuj bez powodu

- **(a) Nowsza, obowiązkowa dla nowych flow**: node "Get one base" +
  wyrażenia do wszystkich innych node'ów (`.claude/skills/n8n-flow/SKILL.md`
  §1). Używana od W8.
- **(b) Starsza, tylko w istniejących flow (W1, W7, W10)**: `workspaceId`/
  `projectId` wklejone osobno w KAŻDYM nodzie `nocoDb`, wartość z
  `schema_map.json` z dnia pisania flow; pole `table` samo ID, bez `__rl__`
  wrapper. W tym wzorcu `workspaceId`/`projectId` bywają też celowo puste w
  nodach `update`/`create` — n8n dociąga je z credentiala po otwarciu noda
  w UI (wpisanie na sztywno wymaga 2-3 otwarć/zamknięć, żeby UI się
  odświeżył).

Nowy flow → zawsze (a). Edycja istniejącego flow → kontynuuj konwencję, w
której flow już jest, nie migruj bez wyraźnej zgody usera.

## 4. Tabele katalogowe vs tabele selekcji

Nie myl definicji z wybraną instancją:
- tabela **katalogowa** (np. `package_variants_cores/others`) — reużywalna
  definicja: nazwa, opis, domyślne godziny,
- tabela **selekcji** (np. `selected_package_variants_cores/others`) —
  konkretny wybór na konkretnej ofercie: linkuje do katalogu + może nadpisać
  godziny/dane wybraną instancją (`_hours` w node'ach "Tag ... with hours").

Render (faza 3, `common.md` §4) czyta z tabel selekcji, nie katalogowych —
katalog może zawierać opcje nigdy niewybrane do żadnej oferty.

## 5. `resource: linkrow` gubi kontekst rodzica po merge

Patrz [n8n.md](n8n.md) "Wzorzec Tag X with Y" — zawsze taguj wynik `linkrow`
ID rodzica w dedykowanym nodzie `Set` zaraz po fetchu, przed jakimkolwiek
`merge` z wynikami dla innych rodziców.

## 5. Model danych v4: osoby, leady, szanse (docs/archive/fable/nocodb_crm_schema_v4.md)

- **`persons`** to jedyna tabela ludzi spoza zespołu (klucz dedupu: `email`);
  zespół CoAction to `employees`. Dane osobowe nie żyją w innych tabelach.
- **`leads`** to zgłoszenie i kwalifikacja (osoba lub grupa osób w
  `leads.persons`, główny kontakt w `primary_person`); **`sale_opportunities`**
  to szansa z etapem, wartością i utratą (kupujący w `person`, lead tylko jako
  `source_lead`). Etapów nie zapisujemy na leadzie.
- Rola osoby wynika z powiązań: kupujący (`sale_opportunities.person`),
  attendee (`meetings.attendees`), do audytu (`to_be_audited`), po audycie
  (`audited`), uczestnik szkolenia (`participants`, dopiero po podpisaniu).
  Nie ma tabeli `participants` ani statusu roli na osobie.
- **Opcje `stage` mają polskie nazwy** („Nowa", „Audyt", „Umowa podpisana"…);
  flow porównują dokładnie te wartości (lista i mapowanie na klucze
  techniczne: sekcja „Nazwy etapów" w specyfikacji).
- Pola odpowiedzialności (`owner`, `assignee`, `assigned_methodologist`) to
  linki do `employees`, nie pola `User`.
- Osoby z `persons.sales_mode` = „Tylko spotkania" (puste = Standard) nigdy nie
  stają się leadem ani szansą: flow tworzące leady i szanse je pomijają.
- Schemat tworzy `make init-schema STAGE=N` (etapy 1-4, patrz plan migracji);
  dane testowe `make seed-test-data STAGE=N`.

## 6. Wyjątek: import/eksport CRM z/do pliku idzie przez PostgreSQL, nie przez NocoDB

Decyzja usera 2026-11-01, po próbie importu `docs/crm/crm-2026-10-30.csv`
(eksport z dotychczasowego CRM).

**Powód:** NocoDB (API i importer) nie pozwala ustawić systemowych pól
`created_at`/`CreatedAt` — zawsze wpisuje datę importu. Przy migracji
historycznych danych tracimy realną datę utworzenia leada/klienta/szansy z
dawnego CRM, a na niej opiera się raportowanie (czas w lejku, źródła w
czasie).

**Zasada:** hurtowy import danych z pliku CRM oraz eksport bazy do pliku CRM
wykonujemy bezpośrednio na PostgreSQL (schemat `crm`, kontener
`docker-postgres-1`, baza `$(APP_DB)`), nie przez API/importer/node NocoDB.
Dotyczy tylko tego jednego przypadku — zwykłe operacje flow (sekcja 1 w
[common.md](common.md)) nadal idą natywnym node'em NocoDB.

**Konsekwencje:**
- Import = skrypt zapisujący do tabel `crm.*` (SQL/psql lub Python z
  `psycopg`), z jawnie ustawianym `created_at` z pliku. Najpierw `--dry-run`,
  całość w jednej transakcji.
- Nazwy tabel/kolumn bierzemy z live schematu Postgresa (`\d crm.*`) lub
  `schema_map.json`, nie zgadujemy (zasada 1). Kolumny relacji/linków
  (FK, tabele łączące M2M) wypełniamy SQL-em samodzielnie.
- Po imporcie NocoDB widzi dane od razu (czyta ten sam schemat); w razie
  potrzeby odśwież metadane tabel w UI.
- Eksport do pliku CRM analogicznie: `COPY`/`SELECT` z `crm.*`, bez API NocoDB.
- Skrypt łączy się rolą z uprawnieniami zapisu do `crm` (nie rolą
  `NOCODB_CRM_USER`/`N8N_CRM_USER` bez sprawdzenia grantów).

Implementacja: `make import-crm-legacy CSV=docs/crm/crm-utf-8.csv` (dry-run;
`APPLY=1` zapisuje), kod w `scripts/import-crm-legacy.py`. Relacje (też
belongs-to) siedzą w tabelach łączących `_nc_m2m_*`: nazwy tabel z
`schema_map.json`, nazwy kolumn z kluczy obcych w bazie, nie z pamięci.
