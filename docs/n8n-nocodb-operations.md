# Katalog operacji n8n ↔ NocoDB

Lista standardowych "klocków" workflow, wyciągnięta z `docs/archive/fable/W*.json`
(zakres: tylko NocoDB i logika n8n; serwisy zewnętrzne — MailerLite, OpenRouter,
file-renderer, e-mail — poza zakresem). Cel: nowe WF składamy z tych operacji,
a ID (workspace/base/tabele/pola/widoki/credentiale) są placeholderami
podmienianymi przez `make fill-workflows` (`scripts/fill-workflow-placeholders.py`).

Reguła "Get one base" jest usunięta (skill `n8n-flow` §1) — jej rolę przejmuje
`make fill-workflows`. ID są "wypalone" w wygenerowanym JSON-ie, więc po zmianie
schematu trzeba go wygenerować ponownie.

## 1. Wejścia (triggery)

| Operacja | Node n8n | Użycie dziś | Co zapisujemy |
|---|---|---|---|
| **Webhook z przycisku NocoDB** | `webhook` POST (+ `responseMode: onReceived`) | W1, W14, W17, W18, W21, W8… | Payload wrzucasz Ty → zapisuję kształt (`body.data.rows[0]`, relacje jako `{Id, …}`, pola) per WF w sekcji "Payload" |
| **Webhook zdarzenia tabeli** (after insert/update) | `webhook` | W2, W5, W7, W4 | Jw.; dodatkowo `previous_rows` dla update (stage change) |
| **Webhook z zewnątrz (formularz)** | `webhook` | W4*, W13 | Surowy payload formularza → mapowanie na pola |
| **Harmonogram** | `scheduleTrigger` | W0, W11, W16, W19 | Cron |
| **Wywołanie z innego WF** | `executeWorkflowTrigger` / `executeWorkflow` | W3, W15, W20 | Kontrakt wejścia/wyjścia podworkflow; ID: `__Wnn_WORKFLOW_ID__` |

## 2. Odczyt

| Operacja | Node | Parametry |
|---|---|---|
| **R1. Jeden wiersz po Id** | `nocoDb` `get` | tabela, `id` (zwykle z payloadu webhooka) |
| **R2. Wiele wierszy z filtrem** | `nocoDb` `getAll` | tabela, `where` (`(pole,eq,wartość)`), `limit`, sort |
| **R3. Powiązane rekordy (link)** — reguła 1b | `nocoDb` v4 `linkrow` (get) | tabela-źródło, `id` wiersza, **pole relacji** (`__COL_<TABLE>__<FIELD>__`), lista pól do zwrócenia. Np. rekomendacje oferty, szanse sprzedaży leada, oceny uczestnika |
| **R4. Powiązane — przez HTTP** | `httpRequest` GET `/api/v2/tables/{tbl}/links/{field}/records/{id}` | tylko gdy `linkrow` nie wystarcza (np. paginacja, `where` na linkach) |
| **R5. Odczyt widoku** | `httpRequest` GET `/records?viewId=` | gdy filtr ma wynikać z widoku (`__VIEW_<TABLE>_ID__`) |
| **R8. Alias danych (Set)** — reguła 1c | `set` | grupowanie danych z triggera / "Get linked" pod aliasami; preferowany nad `code` do mapowania, warunków i sprawdzania pustych danych |
| **R6. Odczyt równoległy** — reguła 6 | rozgałęzienie + `merge` (v3, `numberInputs` = liczba ścieżek) | niezależne R1/R3 od jednego triggera, scalone `merge` (W1 ma 4 wejścia) |
| **R7. Wykrycie duplikatu** | `getAll` + `if` | reguły dedup: W4v2, W5 (email/domena/nazwa) |

## 3. Zapis

| Operacja | Node | Uwagi |
|---|---|---|
| **W1. Utwórz wiersz** | `nocoDb` `create` | najczęstsza (54×): `activities`, `tasks`, `sale_opportunities`, historia etapów |
| **W2. Zaktualizuj wiersz po Id** | `nocoDb` `update` | statusy (`convert_status`, `generation status`), wyniki AI |
| **W3. Upsert** | `nocoDb` v4 `upsert` | klucz naturalny (np. `campaign_id`, W11) |
| **W4. Podłącz relację** | `httpRequest` POST `/tables/{tbl}/links/{field}/records/{id}` | body `[{Id}]`; `nocoDb` nie ma "link", stąd HTTP (nazwać "Link X to Y") |
| **W5. Odłącz relację** | jw. DELETE | W18 (`method` dynamiczne) |
| **W6. Komentarz do rekordu** | `httpRequest` POST `/api/v2/meta/comments` | W4v2/W5/W6b |
| **W7. Załącznik** | `httpRequest` POST `/api/v2/storage/upload` → PATCH rekord | W1; bez AI, status `creating file` |
| **W8. Wpis do `activities`** | `create` | każdy flow z leadem/ofertą: `summary,type,flow,triggered_by,payload` |
| **W9. Task dla człowieka** | `create` w `tasks` | `title,status,priority,assignee,created_by_flow,description`; po błędzie i do review |

## 4. Wzorce (kompozycje)

0. **Start po webhooku** (reguła 1a): webhook → `update` tego samego wiersza, tylko `completion_status` → `collecting data`; dopiero potem odczyty.
1. **Status flow** (reguła 3 skilla): `collecting data → [generating | creating file] → done`, gałąź błędu → `error` + komunikat + task + `activities` (operacje W2, W8, W9).
2. **Wzbogacenie wiersza z powiązań**: R1 (wiersz) ∥ R3 (relacje) → `merge` → `set` ("Assemble …") → dalej. Dane z relacji N:M w pętli: R3 → `set` tagujący id rodzica → `code`.
3. **Guard**: `code`/`if` sprawdza warunki wejściowe (np. brak primary person) → gałąź odmowy: W2 (`error`+note) + W8.
4. **Reguła przypisania/zadań**: `executeWorkflow` do W15 (resolve assignee), potem W9.

## 5. Payloady webhooków

### Wspólna koperta (przycisk NocoDB, `records.manual.trigger`)

```
body.type       "records.manual.trigger"
body.base_id    id bazy                     -> __PROJECT_ID__
body.version    "v3"
body.data.table_id / table_name              (tabela z przyciskiem)
body.data.rows[]  wiersze (przy przycisku zwykle 1 -> rows[0])
headers / query / params / webhookUrl / executionMode  (standard n8n)
```

Zasady odczytu wiersza w `rows[i]`:
- pola skalarne: wprost (`title`, `status`, `hours`, `total_price`…), puste = `null`;
- relacja do jednego rekordu (np. `sale_opportunity`, `document_templates`): `null` albo obiekt (`.Id`) — **do potwierdzenia kształtu**, w payloadzie były `null`;
- relacje do wielu: tablica `[{Id, title}]` (tylko Id + pole wyświetlane — np. `recommendations: [{Id:1, title:"rekomendacja dla miłosza"}]`); więcej pól → "Get linked …" (reguła 1b). Obok są techniczne `_nc_m2m_<tabela>_<tabela>` z pełnymi rekordami powiązanymi (`{recommendations_id, offers_id, recommendations:{…wszystkie pola…}}`) — **nie polegamy na nich**: nazwa jest przycinana (`_nc_m2m_sale_opportunit_offers`) i zależy od tabeli łączącej;
- pola-przyciski są obiektami `{type:"webhook", label, fk_webhook_id}` / `{type:"url", …}`;
- `Id`, `CreatedAt`, `UpdatedAt` zawsze.

### Wyniki node'ów (kształty, z żywego wykonania 2026-10-21)

- "Get linked recommendations" (`linkrow`): `[{ "id": 1, "id_fields": {"Id": 1}, "fields": {"title": "…"} }]` — dla wielu powiązań wiele itemów.
- Set "offer": `[{ "offer": { …cały wiersz z `rows[0]` jak w tabeli niżej… } }]`.

### W1 — przycisk "generuj ofertę" na `offers`

Webhook path `W1-generate-offer-v12`. Wiersz oferty (`rows[0]`):

| Pole | Typ / przykład |
|---|---|
| `Id`, `CreatedAt`, `UpdatedAt` | 1, daty |
| `title` | "Oferta dla Miłosza" |
| `status` | `draft` (draft/sent/accepted/rejected) |
| `hours`, `product_type`, `version`, `file`, `data_json`, `warnings`, `sent_at`, `valid_until`, `approved_total`, `version_status`, `version_note` | `null` |
| `total_price` | 0 (rollup/formuła, tylko do odczytu) |
| `generuj ofertę`, `Utwórz nową wersję` | pola-przyciski |
| `sale_opportunity`, `document_templates` | relacje 1 → `null` |
| `selected_testimonials`, `pricing`, `recommendations`, `tasks` | relacje N → `[]` |

**Rozjazd z obecnym W1** (wymaga poprawki przy migracji): W1 czyta
`rows[0].leads.Id`, `cover_style`, `logo_wall_style` i pole `generation status` —
żadnego z nich nie ma w payloadzie (schema v4: lead jest przez
`sale_opportunity`, nie `leads`). Do ustalenia: skąd brać lead i style okładki;
inaczej W1 przerwie się na pierwszym `leads.Id`.

| Pozostałe WF | Payload |
|---|---|
| W14, W17, W18, W21, W8… | brak, czekam na wklejki |

## 6. Przy migracji istniejących JSON-ów — do poprawy

- W1 ma twarde ID `wpgg1mff/p6w78auzu6sjdoo/m…` w ~40 miejscach i URL `back-office.coaction.pl` → `__WORKSPACE_ID__`, `__PROJECT_ID__`, `__TBL_*__`, `__NOCODB_BASE_URL__`.
- W1 "Get linked assesments": trzykrotnie zduplikowane `cefr_communication` (id `ckk5i6zlaqos6jo`) w liście pól — prawdopodobnie brakuje `cefr_…` pól (np. 2 inne kryteria).
- W4/W4v2/W5/W6b mają zaszyty host `back-office-coaction-test.giemza.dev` oraz skrócone ID linków (`ca2g6r4n` itd.) → `__COL_*__` .
- W9 ma webhook path `w12-…` — niespójne z numerem WF.

## Do decyzji

1. Skąd W1 ma brać leada, `cover_style`, `logo_wall_style` po zmianie schematu (patrz rozjazd w §5)?
