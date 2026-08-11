# n8n workflows — CoAction CRM (NocoDB)

9 importowalnych workflowów zgodnych ze schematem `nocodb_crm_schema_v2.md`
(model docelowy: `nocodb_crm_schema_v3.md`):

| Plik | Trigger | Co robi |
|---|---|---|
| `W1_recurring_tasks.json` | cron 06:00 | taski cykliczne z `task_templates` (RRULE: DAILY / WEEKLY;BYDAY / MONTHLY;BYMONTHDAY), z guardem idempotencji |
| `W2_stage_change.json` | webhook: leads update | kamienie milowe + `state`, task "uzupełnij powód utraty", mail do ownera |
| `W3_task_notifications.json` | webhook: tasks insert **i** update | mail do assignee przy nowym tasku / zmianie assignee |
| `W4_new_lead_intake.json` | webhook: Tally | lead + task "Schedule discovery call" dla Przemka |
| `W5_company_dedup.json` | webhook: leads insert | dopasowanie firmy po domenie, `pending_confirmation`, komentarz, mail |
| `W6a_meeting_ai_pipeline.json` | webhook: meetings update | transkrypcja → OpenRouter → `ai_analysis` → task weryfikacji; akceptacja → task "cele" (routing B2B→Dorota / B2C→Aleksandra); odrzucenie / brak transkrypcji → task naprawczy |
| `W6b_offer_pipeline.json` | webhook: leads update | `goals_provided` → task referencji; `testimonials_provided` → walidacja linków → task "złóż ofertę" + `draft_ready` |
| `W9_generate_offer.json` | Button na leadzie | woła `file-renderer-service` (renderuje PPTX/DOCX z szablonu) → task review + activity, albo task błędu; patrz `file-renderer-service/README.md` |
| `W10_bookings_meetings_sync.json` | cron co 15 min | pobiera kalendarz p.fidzina@coaction.com (MS Bookings, przez Microsoft Graph `/me/calendarView`) → nowe wydarzenia wpisuje do `meetings`, dopasowuje kontakt po e-mailu do `leads`/`participants` i linkuje, jeśli się da; dedup po `external_id` |

Każdy workflow kończy się wpisem do `activities` (+ link do leada tam, gdzie lead jest znany).

**W10 jest zbudowany na schemacie v3** (te same ID tabel co `W9_generate_offer.json`,
node `n8n-nodes-base.nocoDb` + credential *NocoDB Token account*) — w odróżnieniu od
W1–W6b, które są jeszcze na starym schemacie i ID tabel/pól (patrz sekcja "Wdrożenie
na pustej bazie" w `nocodb_crm_schema_v3.md`; wymagają przeróbki przed użyciem).

## 1. Podmień placeholdery (PRZED importem)

```bash
cd n8n
sed -i \
 -e 's|https://back-office-coaction-test.giemza.dev|https://noco.twojadomena.pl|g' \
 -e 's|mx00y54712018vc|m1a2b3...|g' \
 -e 's|mdqdz4zjmarhmmu|...|g' \
 -e 's|mxpjf61n00yokq8|...|g' \
 -e 's|m1d4hmx0ib4s77s|...|g' \
 -e 's|marzjzld5cynlfw|...|g' \
 -e 's|myvr4lq0k17je7t|...|g' \
 -e 's|ca2g6r4nc84ru61|c_...|g' \
 -e 's|cxpflgkmdp110b4|c_...|g' \
 -e 's|c2aeg1l0oemtwfz|c_...|g' \
 -e 's|coydw2dymwf0tkf|c_...|g' \
 -e 's|przemek.fidzina@coaction-test.pl|przemek@...|g' \
 -e 's|dorota@coaction.pl|dorota@...|g' \
 -e 's|aleksandra@coaction.pl|aleksandra@...|g' \
 -e 's|katarzyna@coaction.pl|...@...|g' \
 -e 's|info@coaction-test.pl|crm@twojadomena.pl|g' \
 -e 's|anthropic/claude-sonnet-4.5|anthropic/claude-sonnet-4.5|g' \
 *.json
```

ID tabel (`m...`) i ID pól linkujących (`c...`): w NocoDB otwórz tabelę → menu → *API Snippet* / *Swagger*, albo `GET /api/v2/meta/bases/{baseId}/tables`. ID pola linku znajdziesz w `GET /api/v2/meta/tables/{tableId}/columns` (szukaj typu `Links`).

## 2. Credentials w n8n (4 sztuki)

1. **NocoDB Token** — typ *Header Auth*: name `xc-token`, value = token z NocoDB (Account → Tokens). Przypisz do wszystkich node'ów HTTP po imporcie (n8n podpowie po nazwie).
2. **OpenRouter** — typ *Header Auth*: name `Authorization`, value `Bearer sk-or-...` (tylko W6a).
3. **SMTP** — do node'ów Send Email (W2, W3, W5). Zamiana na Slack/Telegram = podmiana jednego node'a.
4. **Microsoft Outlook OAuth2 API** — connect jako `p.fidzina@coaction.com` (tylko W10). Node "Fetch Outlook events" woła `/me/calendarView`, więc konto, którym się łączysz, musi BYĆ tą skrzynką — jeśli zamiast tego masz konto z delegowanym dostępem do jego kalendarza, zmień URL na `/users/p.fidzina@coaction.com/calendarView` i dodaj uprawnienie `Calendars.Read.Shared`.

## 3. Webhooki w NocoDB

Dla każdego workflow z triggerem webhook: tabela → *Details* → *Webhooks* → *Create*:

| Workflow | Tabela | Event | URL n8n |
|---|---|---|---|
| W2 | leads | after **update** | `https://n8n.../webhook/w2-stage-change` |
| W3 | tasks | after **insert** ORAZ drugi after **update** | `.../webhook/w3-task-notify` (oba na ten sam URL) |
| W5 | leads | after **insert** | `.../webhook/w5-company-dedup` |
| W6a | meetings | after **update** | `.../webhook/w6a-meeting-ai` |
| W6b | leads | after **update** | `.../webhook/w6b-offer-pipeline` |

**KRYTYCZNE:** w każdym webhooku NocoDB zaznacz **"Include previous record"** (send me everything / previous state). Bez tego guardy `rows` vs `previous_rows` nie mają czego porównywać i workflowy odpalą się przy KAŻDEJ edycji rekordu — w W6a oznacza to płatne wywołanie LLM przy każdej poprawce literówki w notatce.

W4: URL `.../webhook/w4-tally-intake` wklej w Tally → Integrations → Webhooks.

W9 nie jest webhookiem tabeli — to pole **Button** na `leads` (patrz
`file-renderer-service/README.md` krok 5), wywołujące bezpośrednio
`.../webhook/w9-generate-offer`. Wymaga uruchomionego serwisu
`file-renderer-service` (`docker compose up -d --build file-renderer-service`) i co
najmniej jednego rekordu `document_templates` z `active=true`
(w bazie testowej tabela nazywa się jeszcze `offer_templates` — patrz
`nocodb_crm_schema_v3.md` §12).

W10 nie jest webhookiem ani buttonem — to **Schedule Trigger** (co 15 min, wbudowany
w workflow). Nie wymaga konfiguracji webhooka w NocoDB, tylko:

1. **Nowe pole w `meetings`**: `external_id` (SingleLineText) — klucz dedupu po ID
   wydarzenia z Microsoft Graph. Dodaj ręcznie w NocoDB UI PRZED importem workflow,
   inaczej pierwsze uruchomienie zapisze meeting bez tego pola i każde kolejne
   uruchomienie utworzy duplikat.
2. Credential **Microsoft Outlook OAuth2 API** (patrz sekcja 2 punkt 4).
3. Po imporcie workflow jest `active: false` — włącz ręcznie dopiero po pierwszym
   udanym uruchomieniu z n8n UI (żeby zobaczyć execution log przed odpaleniem na
   automacie).

## 4. Kolejność uruchamiania i test

Włączaj po jednym: **W3 → W2 → W1 → W4 → W5 → W6a → W6b → W9 → W10** (powiadomienia najpierw). Po każdym: wykonaj akcję testową w NocoDB i sprawdź execution log w n8n + wpis w `activities`.

Smoke test W6 (scenariusz "Piotr"): utwórz testowy lead + spotkanie z linkiem do leada → wklej transkrypcję → `processing_status = analysis_pending` → sprawdź `ai_analysis`, task weryfikacji i activity → `ai_accepted` → sprawdź task celów u właściwej metodyczki → na leadzie `goals_provided` → task referencji → podlinkuj testimonial → `testimonials_provided` → task dla Przemka + `draft_ready` → kliknij **Generuj ofertę** → sprawdź rekord w `offers` (patrz `file-renderer-service/README.md`).

## 5. Test Runner (pytest)

```
pip install -r fable/requirements.txt
pytest fable/ -v
```

Wymaga zmiennych środowiskowych opisanych w `fable/conftest.py`
(`NC_URL`, `NC_TOKEN`, `NC_TEST_BASE`, `N8N_URL`, opcjonalnie `WH_PREFIX`).

## 6. Znane uproszczenia (do świadomej akceptacji)

- **Kształt payloadu webhooków NocoDB różni się między wersjami** (pole User: obiekt vs tablica; linki: licznik vs obiekt). Guardy piszą defensywnie oba warianty, ale po pierwszym realnym wywołaniu obejrzyj payload w execution logu i w razie czego popraw ścieżki w Code node'ach. To najbardziej prawdopodobne miejsce jednorazowej korekty.
- **Wiązanie tasków z pipeline'em** działa przez marker w opisie (`meeting:{id}` / `lead:{id}`), a nie przez pole Links — celowo, bo linki przez API to osobne wywołania per rekord. Nie edytuj tych markerów ręcznie.
- **W10 nie propaguje zmian ani anulowania.** Sync tylko DODAJE nowe wydarzenia (po `external_id`) — jeśli ktoś przesunie spotkanie w kalendarzu albo je anuluje, meeting w NocoDB zostaje ze starymi danymi / w ogóle nie znika. Wymaga ręcznej korekty do czasu, aż ktoś doda logikę update/cancel.
- **W10 nie stronicuje odpowiedzi Microsoft Graph** (`$top=999` bez obsługi `@odata.nextLink`) — przy oknie -7/+60 dni i kalendarzu, na którym są tylko rezerwacje z MS Bookings, nie powinno to być problemem, ale przy bardzo zapchanym kalendarzu część wydarzeń może nie trafić do syncu.
- **W10 dopasowuje lead/participant tylko po dokładnym e-mailu** (bez domeny / fuzzy match jak w W4v2) — jeśli klient zarezerwował spotkanie na inny adres niż ten w CRM, meeting powstanie bez linku i trzeba go podlinkować ręcznie.
- **Parser RRULE w W1** obsługuje DAILY, WEEKLY;BYDAY i MONTHLY;BYMONTHDAY. YEARLY/INTERVAL dopiszemy, gdy będą potrzebne.
- **Aktywność w `activities` linkuje leada przez `ca2g6r4nc84ru61`**; linki do task/meeting są w `payload` (JSON), nie jako Links — mniej wywołań API, timeline i tak czytelny.
- Node'y "Link/Close/Comment" mają `onError: continueRegularOutput` — kosmetyczne niepowodzenie (np. brak uprawnień do komentarzy) nie zatrzyma głównego flow.
