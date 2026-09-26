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
