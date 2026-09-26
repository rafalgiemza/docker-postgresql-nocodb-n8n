# n8n workflows — CoAction CRM (NocoDB)

12 workflowów zgodnych ze schematem `nocodb_crm_schema_v2.md`
(model docelowy: `nocodb_crm_schema_v3.md`) — 10 importowalnych i
zweryfikowanych na żywo, plus `W9` i `W10` jako zaprojektowane drafty (patrz
ich wiersze w tabeli i uwagi o placeholderach/braku pola Button niżej):

| Plik | Trigger | Co robi |
|---|---|---|
| `W0_recurring_tasks.json` | cron 06:00 | taski cykliczne z `task_templates` (RRULE: DAILY / WEEKLY;BYDAY / MONTHLY;BYMONTHDAY), z guardem idempotencji |
| `W2_stage_change.json` | webhook: leads update | kamienie milowe + `state`, task "uzupełnij powód utraty", mail do ownera |
| `W3_task_notifications.json` | webhook: tasks insert **i** update | mail do assignee przy nowym tasku / zmianie assignee |
| `W4_new_lead_intake.json` | webhook: Tally | lead + task "Schedule discovery call" dla Przemka |
| `W5_company_dedup.json` | webhook: leads insert | dopasowanie firmy po domenie, `pending_confirmation`, komentarz, mail |
| `W6a_meeting_ai_pipeline.json` | webhook: meetings update | transkrypcja → OpenRouter → `ai_analysis` → task weryfikacji; akceptacja → task "cele" (routing B2B→Dorota / B2C→Aleksandra); odrzucenie / brak transkrypcji → task naprawczy |
| `W6b_offer_pipeline.json` | webhook: leads update | `goals_provided` → task referencji; `testimonials_provided` → walidacja linków → task "złóż ofertę" + `draft_ready` |
| `W1_generate_offer.json` | Button na leadzie | woła `file-renderer-service` (renderuje PPTX/DOCX z szablonu) → task review + activity, albo task błędu; patrz `file-renderer-service/README.md`. Pakiety (`data.packages[]`) czyta z `recommendations`→`recommendation_packages` (2026-09-07 — **NIE** `offer_packages`→`package_variants`, patrz uwaga niżej) |
| `W7_bookings_meetings_sync.json` | cron co 15 min | pobiera kalendarz p.fidzina@coaction.com (MS Bookings, przez Microsoft Graph `/me/calendarView`) → nowe wydarzenia wpisuje do `meetings`, dopasowuje kontakt po e-mailu do `leads`/`participants` i linkuje, jeśli się da; dedup po `external_id` |
| `W8_assessment_needs_summary.json` | Button na `assessments` ("Generuj needs summary") | ocena CEFR + `auditor_notes` (ten wiersz) + notatki Przemka z ostatniego spotkania `discovery` leada → prompt klienta (5 sekcji: audyt / kontekst biznesowy / dotychczasowa nauka / wnioski z audytu / rekomendacja) → OpenRouter → `needs_summary` (`ai_draft_ready`) + task weryfikacji dla metodyka (routing B2B→Dorota / B2C→Aleksandra); brak wypełnionych ocen CEFR → task "uzupełnij audyt" zamiast wołania LLM; błąd OpenRouter → `ai_status` wraca na `none` + task naprawczy |
| `W9_offer_package_texts.json` | Button na `offer_packages` ("Generuj opis") | dla TEGO JEDNEGO wiersza (pakiet ze slajdu 4 "NASZA REKOMENDACJA" wybrany do oferty) `AI Agent` → dłuższy tekst na jego własny slajd (5/6/7) → `generated_text` (`ai_draft_ready`) + task weryfikacji dla metodyka; brak wybranego wariantu na wierszu → `ai_status=ai_rejected` + task "uzupełnij wariant" zamiast wołania LLM; błąd LLM → `ai_status=none` (klikalne od razu ponownie) — w obu przypadkach błędu komunikat z linkiem do naprawczego taska wpisany wprost w `generated_text`, nie tylko cichy reset (wzorzec "Loguj błąd w polu needs_summary" z W8). **Status: zaprojektowany, NIE wdrożony/przetestowany na żywo** — patrz uwaga niżej i `.ai/PRD.md` §12. |
| `W10_recommendation_rationale.json` | Button na `recommendations` (nowe pole, patrz uwaga niżej) | sklejа `rationale` z wybranych pakietów `selected_cores`/`selected_others` (linki na TYM wierszu) — tytuł+opis z katalogu `package_variants_cores`/`package_variants_others`, godziny z konkretnej wybranej instancji (`selected_package_variants_cores/others.hours`); brak wybranego pakietu (oba puste) → task "uzupełnij pakiety" zamiast pustego zapisu; błąd zapisu → task naprawczy z surowym błędem w opisie. Czysto deterministyczne sklejanie tekstu, bez AI — **Status: zaprojektowany, NIE wdrożony/przetestowany na żywo.** |

Każdy workflow kończy się wpisem do `activities` (+ link do leada tam, gdzie lead jest znany).

**W7 i W8 są zbudowane na schemacie v3** (credential *NocoDB Token account*,
`id: 9gq205HbXOk9D3Jm`) — w odróżnieniu od W0, W2–W6b, które są jeszcze na starym
schemacie i ID tabel/pól (patrz sekcja "Wdrożenie na pustej bazie" w
`nocodb_crm_schema_v3.md`; wymagają przeróbki przed użyciem). **W8 w całości
przez node `n8n-nodes-base.nocoDb`** (get/getAll/create/**update**) — zero
`httpRequest`, zero zaszytego `https://back-office.coaction.pl` w URL-ach.
To inaczej niż `W1_generate_offer.json` "Update offer record" (tam PATCH przez
`httpRequest` z `authentication: predefinedCredentialType` /
`nodeCredentialType: nocoDbApiToken`, bo tamten wzorzec powstał wcześniej) —
świadoma zmiana we W8: operacja `update` na nodzie `nocoDb` daje ten sam efekt
(id + "Fields to Send", jak przy `create`), bez URL-a do utrzymania i ze
spójnym auto-resolve `workspaceId`/`projectId` z credentiala (patrz akapit
wyżej o pustych ID). Jeśli kiedyś W1 dostanie podobne odświeżenie, ten sam
zabieg (PATCH-`httpRequest` → `nocoDb`/`update`) ma sens tam też.

**ID tabel w `W8_assessment_needs_summary.json` pochodzą z `schema_map.json`**
(`make dump-crm-schema`, ostatni pełny dump: 2026-08-09) — `assessments`,
`meetings`, `participants`, `leads`, `companies`, `tasks`, `activities`.
`workspaceId`/`projectId` są celowo puste w każdym nodzie `nocoDb` — n8n
uzupełnia je sam z credentiala po otwarciu noda (wpisane na sztywno wymagałoby
2-3-krotnego otwarcia/zamknięcia noda, żeby UI się odświeżyło do poprawnej
wartości). **Przed importem odpal `make dump-crm-schema` jeszcze raz i zdiffuj**
z `schema_map.json` — jeśli ID którejś tabeli się zmieniło od 08-09 (patrz
`TODO.md`, tam podobny problem z ID tabeli `leads` w W1 po przebudowie), popraw
`table` w pliku przed importem, tak jak przy każdym innym workflow z tej listy.

**W8 woła LLM przez `AI Agent` (`@n8n/n8n-nodes-langchain.agent`) + osobny
sub-node `OpenRouter Chat Model` (`@n8n/n8n-nodes-langchain.lmChatOpenRouter`),
NIE przez `httpRequest`** jak W6a/W1 — świadomie inaczej niż reszta pliku.
Node "Assemble context" (Code) składa TYLKO dane z CRM w jeden tekst
(wiadomość użytkownika); cały prompt metodyczny (FILOZOFIA COACTION, struktura
rekomendacji, styl) siedzi w polu "System Message" noda "AI Agent" jako zwykły
tekst w UI, nie jako string w kodzie — metodyk albo Przemek mogą go poprawić
sami w n8n, bez znajomości JS. Konsekwencja: po imporcie podepnij pod
"OpenRouter Chat Model" credential z sekcji 2 punkt 3 (inny typ niż Header Auth
używany gdzie indziej) i sprawdź dropdown modelu (`anthropic/claude-sonnet-4.5`)
— przy pierwszym otwarciu noda w UI n8n może wymagać przeklikania wyboru
modelu z listy, tak samo jak przy tabelach NocoDB opisanych wyżej.

**`W9_offer_package_texts.json` jest inny niż reszta: WSZYSTKIE ID w nim są
placeholderami** (`__TBL_...__`, `__WORKSPACE_ID__`, `__PROJECT_ID__`,
`__NOCODB_BASE_URL__`, `__NOCODB_CRED_ID__`, `__OPENROUTER_CRED_ID__`,
`__VIEW_TASKS_ID__`), nie realnymi wartościami ze starego dumpu jak w W1/W7/W8 —
tabele `offer_packages`/`package_variants`, których używa, nie istnieją
jeszcze w `schema_map.json` (dump z 2026-08-09, `package_variants` dodane
2026-08-11, `offer_packages` dopiero 2026-08-30 w `scripts/init-schema.py`,
patrz `TODO.md`). Zanim ten workflow da się zaimportować: `make init-schema`
(utworzy tabelę + relacje + przycisk) → `make dump-crm-schema` → podmień
placeholdery realnymi ID z nowego `schema_map.json` (ten sam mechanizm co
sekcja 1 niżej, tylko podmieniasz `__NAZWA__` zamiast losowego `m...`/`c...`).
**Ten plik jest projektem/draftem workflowu, NIE zweryfikowanym na żywym
n8n** — traktuj go jako punkt startowy do zbudowania w UI, nie jako gotowy do
kliknięcia "Import" bez przeglądu, w szczególności:
- zweryfikuj nazwy pól zwrotnych `offers`→`leads` (w kodzie node'a `Get lead`)
  i `offer_packages`→`offers`/`package_variants` (w `Guard`) — dokładnie ten
  sam rodzaj niepewności co przy `document_templates` w `TODO.md`;
- node'y `nocoDb` z `operation: update` (`Set ai_status = pending`, `Update
  offer_package (draft ready)`, `Update offer_package (error)`, `Update
  offer_package (missing variant)`) mają celowo pusty blok
  `fieldsMapper.schema` (cache pól do UI, czysto kosmetyczny) — n8n go sam
  odtworzy przy pierwszym otwarciu node'a po wybraniu prawdziwej tabeli z
  listy, tak jak przy `workspaceId`/`projectId` opisanym niżej.

**Trigger przeszedł przez dwie iteracje w tej samej sesji.** Pierwotnie jeden
zbiorczy przycisk na `offers`, generujący teksty dla WSZYSTKICH wybranych
pakietów jednym klikiem (fan-out po stronie n8n na N itemów, po jednym na
pakiet — działało by dzięki temu, że root node'y w n8n, w tym `AI Agent`,
wykonują się raz na każdy wchodzący item, w odróżnieniu od sub-node'ów jak
`OpenRouter Chat Model`, które zawsze rozwiązują wyrażenie do pierwszego
itemu — [docs.n8n.io](https://docs.n8n.io/integrations/builtin/cluster-nodes/root-nodes/n8n-nodes-langchain.agent/)).
Zmienione po przemyśleniu: taki zbiorczy klik nadpisywałby `ai_status`
(i odpalał ponowne, płatne wywołanie LLM) też dla pakietów już zaakceptowanych
przez człowieka, nie tylko dla nowych. **Ostatecznie: przycisk PER WIERSZ na
`offer_packages`** — klik dotyczy zawsze dokładnie jednego pakietu. Efekt
uboczny: workflow jest teraz prostszy i strukturalnie bliski W8 (jeden
rekord wchodzi, jeden wychodzi) — nie ma już fan-outu, IF-a "czy w ogóle są
wybrane pakiety" ani agregacji wielu wyników w jeden task.

**2026-09-06 — `W1_generate_offer.json` przełączony z `recommendations`/
`recommendation_packages`/`training_descriptions` na `offer_packages`/
`package_variants`.** Po `make init-schema` + `make init-data` dane trafiły
do `package_variants` (10 wierszy) i `pricing` (36 wierszy), NIE do
`recommendations`/`recommendation_packages` — te tabele zostają w schemacie
(user zdecydował nie usuwać ich teraz), ale są puste i żaden aktywny workflow
już ich nie czyta. W1 fetchował je wcześniej i budował `data.module[]`
per (uczestnik, moduł) — zawsze pusto, bo źródłowe tabele są puste. Teraz:
`Fetch offer packages` (`getAll` na `offer_packages`) + `Fetch package_variants`
(`getAll` na `package_variants`) zastępują trzy stare fetch-e; w "Assemble
render data" filtrowanie po `offers.Id`, sort po `sort_order`, join do
`package_variants` po `package_variants.Id` → `data.package[]` (jeden wiersz
na pakiet OFERTY, nie per uczestnik — pakiety nie są już przypisane do
konkretnej osoby, więc zniknęła potrzeba spłaszczania per-uczestnik jak przy
starym `module[]`). Pola: `sort_order`, `name` (z `package_variants.name`,
fallback `offer_packages.package_name`), `hours` (`default_hours`),
`short_description`, `generated_text` — to ostatnie tylko gdy
`offer_packages.ai_status === 'ai_accepted'` (draft niezaakceptowany przez
metodyka trafia do oferty jako pusty string), zgodnie z notatką z `TODO.md`
("`{{package.generated_text}}` na slajd własny — tylko gdy
`ai_status=ai_accepted`"). Usunięte z `participant[]`: pole `recommendation`
(`type`/`headline`/`rationale`/`priority`) — źródłowa tabela `recommendations`
jest pusta, więc renderowało się i tak puste; jeśli szablon PPTX ma
`{{participant.recommendation.*}}`, zamień je na odpowiedniki z `package.*`
albo usuń ten fragment slajdu. **Szablon PPTX prawdopodobnie wymaga
odświeżenia**: stary kontrakt to `repeat:module` (`{{module.title}}`,
`{{module.goal_statement}}`, `{{module.participant_name}}` — patrz
`nocodb_crm_schema_v3.md` §"Co się zmienia w W1"), nowy to `repeat:package`
(`{{package.name}}`, `{{package.hours}}`, `{{package.short_description}}` na
slajd 4, `{{package.generated_text}}` na własny slajd pakietu) — sprawdź to
w `szablon_testowy.pptx` przed pierwszym realnym testem W1 po tej zmianie.

**`W10_recommendation_rationale.json` (2026-09-24) — ID tabel/pól pochodzą z
`schema_map.json`, ale w odróżnieniu od W8/W9 NIE korzysta z node'a
"Get one base" opisanego w skill `n8n-flow` — świadomie, na wzór W1/W7/W8
(żaden istniejący workflow tego jeszcze nie robi), `workspaceId`/`projectId`
są wklejone osobno w każdym nodzie `nocoDb`, jak w W1.** Nie pisze żadnego
pola `status`/`ai_status` — `recommendations` ma `ai_status`, ale to pole
jest dziś nieużywane przez żaden aktywny workflow na tej tabeli i ma inną
semantykę (used gdzie indziej: `assessments`, `offer_packages`, wartości typu
`pending`/`ai_draft_ready`) niż generyczna konwencja `status` ze skilla;
flow jest krótki i deterministyczny (odczyt + sklejenie tekstu + zapis), więc
świadomie pominięto pisanie statusu — decyzja usera, nie domyślne zachowanie.
Dopisek `(2x60 min lub 1x90 min)` przy pakietach **core** to STAŁY tekst
zaszyty w kodzie noda "Build rationale", NIE pole w NocoDB — `package_variants_cores`
ma tylko `name`+`description`, bez pola na format sesji; dopisek celowo NIE
pojawia się przy pakietach **others** (jednorazowe dodatki, bez cyklu sesji).
Jeśli kiedyś dojdzie pole typu `session_format`, zamień hardkod w "Build
rationale" na wartość z niego. Kolejność w tekście: najpierw wszystkie
`selected_cores`, potem wszystkie `selected_others`, każdy jako dwie linie
(`✅ {name} – {hours} godzin[, dopisek]` + linia opisu), połączone `\n` bez
pustej linii między wpisami — zgodnie z przykładem od usera. **Nowe pole
Button na `recommendations` NIE istnieje jeszcze w NocoDB** — trzeba je
ręcznie dodać (typ Button → Webhook → `.../webhook/w10-recommendation-rationale`),
w odróżnieniu od W8/W9, które podmieniały już istniejący placeholder z
`scripts/init-schema.py`. **Status: zaprojektowany, NIE wdrożony/
przetestowany na żywo** — w szczególności nie zweryfikowano na żywym n8n
kształtu odpowiedzi `resource: linkrow` (czy `id_fields.Id`/`fields.*` to
faktycznie dokładny kształt zwracany przez tę wersję node'a NocoDB, tylko
wzorowany 1:1 na działających node'ach w W1) ani czy webhook payload
przycisku na `recommendations` rzeczywiście ma kształt
`body.data.rows[0].Id` jak w W1/W8/W9.

**2026-09-07 — powyższe dla W1 NIEAKTUALNE, wrócono do `recommendations`/
`recommendation_packages`.** User potwierdził że to `recommendations`→
`recommendation_packages` jest teraz źródłem prawdy dla pakietów w W1 (nie
`offer_packages`/`package_variants` jak opisano wyżej) — te tabele NIE są
puste, mają realne dane (real execution `recommendation_packages` z linkiem
`recomendation packages` na `recommendations`, pola bezpośrednio na wierszu:
`package_name`, `sort_order`, `hours`, `content` — bez pośredniego joina do
`training_descriptions`, w odróżnieniu od jeszcze starszego kontraktu). Węzły
`Fetch participants`/`Fetch assessments`/`Fetch recommendations`/`Fetch
recommendation_packages`/`Fetch training_descriptions`/`Fetch meetings` +
Code-node `Assemble render data` (oba opisane wyżej) zastąpione: node'y
resource `linkrow` (`Get linked participants` → równolegle `Get linked
assesments` / `Get linked recommendations` → `Get linked recomendation
packages`, bez pętli `Loop Over Items` — te node'y wykonują się z natury raz
na wchodzący item) + jeden Set/Edit Fields node `Assemble offer data`
(zamiast Code) budujący `data.*` przez `$('Node').all()`/`.item` zamiast
Merge+Code. Kontrakt szablonu (`szablon_brand_3.pptx`, notatki `repeat:` w
speaker notes, nie shape names!): `repeat:participants` (slajd 3, per
uczestnik: `assessment.needs_summary`, `a.{o,r,a,f,c}`), `repeat:packages`
(slajd 5, **UWAGA: marker liczby mnogiej, ale placeholdery `{{package.*}}`
liczby pojedynczej** — każdy element `data.packages[]` musi być owinięty
`{ package: {...} }`, nie płaskimi polami), statyczne (nie-repeat) slajdy 1/4
czytają `lead.contact_name`/`assessment.position`/`offer.date` i
`recomendation.headline`/`.rationale` (**pisownia z jednym "m"**, dokładnie
jak w szablonie) z top-level `data` — ustawione na dane PIERWSZEGO uczestnika
z `Get linked participants`. Pole `package.goal` nie ma dziś źródła (tabela
`recommendation_packages` nie ma kolumny `goal`/`learning_goal`) — zostaje
puste. `Get linked recommendations` ma teraz `options.fields` wyczyszczone
(zamiast wąskiej listy Id+headline), żeby dociągnąć `rationale` — nie
znaleziono ID pola `rationale` żeby zawęzić z powrotem, można to zrobić
ręcznie w UI. Korelacja assessment/recommendation → uczestnik: NocoDB
linkrow-get nie zwraca FK do rodzica w odpowiedzi, więc dwa nowe małe node'y
`Tag assessment with participant`/`Tag recommendation with participant`
(Set, `includeOtherFields: true`) doklejają `_participant_id` przez
`$('Get linked participants').item.json.id_fields.Id` (ta sama gałąź
wykonania, nie cross-branch). **Nie przetestowane na żywym n8n** — sprawdź
przy pierwszym imporcie, zwłaszcza sortowanie "najnowszy" assessment/
recommendation per uczestnik (brak pola daty w wybranych `options.fields`,
użyto `id_fields.Id` malejąco jako proxy).

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

## 2. Credentials w n8n (5 sztuk)

1. **NocoDB Token** — typ *Header Auth*: name `xc-token`, value = token z NocoDB (Account → Tokens). Przypisz do wszystkich node'ów HTTP po imporcie (n8n podpowie po nazwie).
2. **OpenRouter** — typ *Header Auth*: name `Authorization`, value `Bearer sk-or-...` (W6a, przez zwykły `httpRequest`).
3. **OpenRouter account** — typ natywny *OpenRouter API* (`openRouterApi`, pole `API Key` = `sk-or-...`), UŻYWANY TYLKO przez node "OpenRouter Chat Model" w W8. To inny typ credentiala niż punkt 2 (Header Auth) — nie da się go podmienić 1:1, trzeba dodać osobno w n8n UI → Credentials → New → wyszukaj "OpenRouter". Powód rozdziału: W8 woła LLM przez node **AI Agent** (`@n8n/n8n-nodes-langchain.agent`) zamiast ręcznego `httpRequest` do `openrouter.ai/api/v1/chat/completions` — łatwiejsze w utrzymaniu dla metodyka, bo system prompt siedzi jako zwykłe pole tekstowe "System Message" w UI noda "AI Agent" (edytowalne bez dotykania kodu), nie jako string zaszyty w JS Code node jak w W6a/W1.
4. **SMTP** — do node'ów Send Email (W2, W3, W5). Zamiana na Slack/Telegram = podmiana jednego node'a.
5. **Microsoft Outlook OAuth2 API** — connect jako `p.fidzina@coaction.com` (tylko W7). Node "Fetch Outlook events" woła `/me/calendarView`, więc konto, którym się łączysz, musi BYĆ tą skrzynką — jeśli zamiast tego masz konto z delegowanym dostępem do jego kalendarza, zmień URL na `/users/p.fidzina@coaction.com/calendarView` i dodaj uprawnienie `Calendars.Read.Shared`.

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

W1 nie jest webhookiem tabeli — to pole **Button** na `leads` (patrz
`file-renderer-service/README.md` krok 5), wywołujące bezpośrednio
`.../webhook/w1-generate-offer`. Wymaga uruchomionego serwisu
`file-renderer-service` (`docker compose up -d --build file-renderer-service`) i co
najmniej jednego rekordu `document_templates` z `active=true`
(w bazie testowej tabela nazywa się jeszcze `offer_templates` — patrz
`nocodb_crm_schema_v3.md` §12).

W8 jak W1 nie jest webhookiem tabeli — to placeholder pola **Button** `ai_status`
na `assessments`, już utworzony przez `scripts/init-schema.py` jako "Open URL" z
formułą `NOW()` (patrz komentarz `ai_status_field()` w tym skrypcie — świadomy
placeholder, "kliknij i zobacz co się stanie" zanim webhook istniał). Po imporcie
W8 podmień akcję tego przycisku w NocoDB UI (`assessments` → pole `ai_status` →
edytuj → *Button* → *Webhook*) na `.../webhook/w8-assessment-needs-summary` —
NIE twórz nowego pola, podmień istniejące (inaczej opis pola i pozycja w widoku
się rozjadą). Wymaga uzupełnionych `cefr_overall`/`cefr_range`/`cefr_accuracy`/
`cefr_fluency`/`cefr_communication` na wierszu PRZED kliknięciem — bez tego W8
tworzy task "uzupełnij oceny CEFR" zamiast wołać LLM (patrz kod `Guard`).

W9 jak W1/W8 nie jest webhookiem tabeli — to placeholder pola **Button**
"Generuj opis" na `offer_packages` (PER WIERSZ — decyzja 2026-08-30, zmieniona
tego samego dnia z pierwotnego zbiorczego przycisku na `offers`, patrz
`TODO.md`), tworzony przez `scripts/init-schema.py` (`BUTTONS`). Po imporcie
podmień jego akcję w NocoDB UI (`offer_packages` → pole "Generuj opis" →
edytuj → *Button* → *Webhook*) na `.../webhook/w9-offer-package-text`.
Zbudowany wg tego samego wzorca co żywy W8 (patrz akapity wyżej): webhook
`responseMode: lastNode` (nie odpowiada od razu), DRUGI node po webhooku
ustawia `ai_status=pending` PRZED wywołaniem AI — na surowym payloadzie, tak
jak w W8, bo Id wiersza jest znane od razu (nie trzeba już nic ustalać, bo
przycisk jest na konkretnym pakiecie) — zapisy przez node'y `nocoDb`/`update`
zamiast `httpRequest`, LLM przez `AI Agent`+`OpenRouter Chat Model` (credential
z sekcji 2 punkt 3 — `openRouterApi`, NIE Header Auth). Wymaga wybranego
`package_variant` NA TYM WIERSZU przed kliknięciem — bez tego W9 tworzy task
"uzupełnij wariant pakietu" (i `ai_status=ai_rejected`) zamiast wołać LLM
(patrz węzeł IF `Wariant uzupelniony?`). **System prompt w polu "System
Message" noda "AI Agent" jest DRAFTEM** — w odróżnieniu od W8, gdzie klientka
dostarczyła gotowy tekst 1:1, tego promptu jeszcze nie widziała (patrz
komentarz w kodzie i `.ai/PRD.md` §12) — pokaż jej kilka wygenerowanych
przykładów przed użyciem produkcyjnym.

W10 jak W1/W8/W9 nie jest webhookiem tabeli — to pole **Button** na
`recommendations`, ale w odróżnieniu od W8/W9 to pole jeszcze NIE ISTNIEJE
(nie ma go w `scripts/init-schema.py`) — dodaj je ręcznie w NocoDB UI:
`recommendations` → nowe pole → typ *Button* → akcja *Webhook* →
`.../webhook/w10-recommendation-rationale`.

W7 nie jest webhookiem ani buttonem — to **Schedule Trigger** (co 15 min, wbudowany
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

Włączaj po jednym: **W3 → W2 → W0 → W4 → W5 → W6a → W6b → W1 → W7 → W8 → W9 → W10** (powiadomienia najpierw). Po każdym: wykonaj akcję testową w NocoDB i sprawdź execution log w n8n + wpis w `activities`.

Smoke test W6 (scenariusz "Piotr"): utwórz testowy lead + spotkanie z linkiem do leada → wklej transkrypcję → `processing_status = analysis_pending` → sprawdź `ai_analysis`, task weryfikacji i activity → `ai_accepted` → sprawdź task celów u właściwej metodyczki → na leadzie `goals_provided` → task referencji → podlinkuj testimonial → `testimonials_provided` → task dla Przemka + `draft_ready` → kliknij **Generuj ofertę** → sprawdź rekord w `offers` (patrz `file-renderer-service/README.md`).

Smoke test W8: na leadzie testowym dodaj meeting `meeting_type=discovery` z wypełnionym `notes` → dodaj `participants` + `assessments` (uzupełnij `cefr_*`, `strengths`, `gaps`, `auditor_notes`) → kliknij **Generuj needs summary** → sprawdź w execution logu, że `ai_status` przeszło `pending` → `ai_draft_ready`, że `needs_summary` zawiera tekst po polsku odwołujący się do wpisanych danych (nie ogólnik), i że powstał task weryfikacji u właściwej metodyczki (Dorota dla `lead_type=B2B`, Aleksandra dla `B2C`) + wpis w `activities`. Osobno: kliknij przycisk na wierszu z pustym `cefr_overall` → powinien powstać tylko task "uzupełnij oceny CEFR", bez wywołania OpenRouter.

Smoke test W9 (dopiero po `make init-schema` + import + podmiana placeholderów, patrz uwaga wyżej): na testowej ofercie dodaj wiersz `offer_packages` wskazujący jakiś `package_variant` → kliknij **Generuj opis** na TYM wierszu → sprawdź w execution logu, że `ai_status` przeszło `pending` → `ai_draft_ready`, że `generated_text` zawiera tekst po polsku odwołujący się do danych pakietu/leada (nie ogólnik), i że powstał task weryfikacji u właściwej metodyczki (Dorota dla `lead_type=B2B`, Aleksandra dla `B2C`) + wpis w `activities`. Dodaj drugi wiersz `offer_packages` (inny pakiet, ta sama oferta) i powtórz — sprawdź, że pierwszy wiersz (już `ai_draft_ready`) NIE zmienił się przy generowaniu drugiego. Osobno: kliknij przycisk na wierszu bez wybranego `package_variant` → powinien powstać tylko task "uzupełnij wariant pakietu", `ai_status=ai_rejected`, `generated_text` z linkiem do taska, bez wywołania LLM. Osobno: zepsuj credential OpenRouter (błędny klucz) i kliknij ponownie na wierszu z wariantem → sprawdź, że `generated_text` dostał komunikat błędu z linkiem do naprawczego taska (nie zostaje pusty), a `ai_status` wrócił na `none` (klikalne od razu ponownie, w odróżnieniu od `ai_rejected` wyżej).

Smoke test W10 (dopiero po ręcznym dodaniu pola Button na `recommendations`, patrz uwaga wyżej): na testowej rekomendacji podlinkuj jeden `selected_package_variants_cores` (z wypełnionym `hours` i linkiem do jakiegoś `package_variants_cores`) i jeden `selected_package_variants_others` (analogicznie) → kliknij przycisk → sprawdź w execution logu, że `rationale` na tym wierszu zawiera dwa bloki `✅ {name} – {hours} godzin` + opis pod spodem, core z dopiskiem `(2x60 min lub 1x90 min)`, others bez. Osobno: kliknij przycisk na rekomendacji bez żadnego linku w `selected_cores`/`selected_others` → powinien powstać tylko task "Uzupełnij pakiety dla rekomendacji #...", `rationale` zostaje bez zmian.

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
- **W7 nie propaguje zmian ani anulowania.** Sync tylko DODAJE nowe wydarzenia (po `external_id`) — jeśli ktoś przesunie spotkanie w kalendarzu albo je anuluje, meeting w NocoDB zostaje ze starymi danymi / w ogóle nie znika. Wymaga ręcznej korekty do czasu, aż ktoś doda logikę update/cancel.
- **W7 nie stronicuje odpowiedzi Microsoft Graph** (`$top=999` bez obsługi `@odata.nextLink`) — przy oknie -7/+60 dni i kalendarzu, na którym są tylko rezerwacje z MS Bookings, nie powinno to być problemem, ale przy bardzo zapchanym kalendarzu część wydarzeń może nie trafić do syncu.
- **W7 dopasowuje lead/participant tylko po dokładnym e-mailu** (bez domeny / fuzzy match jak w W4v2) — jeśli klient zarezerwował spotkanie na inny adres niż ten w CRM, meeting powstanie bez linku i trzeba go podlinkować ręcznie.
- **Parser RRULE w W0** obsługuje DAILY, WEEKLY;BYDAY i MONTHLY;BYMONTHDAY. YEARLY/INTERVAL dopiszemy, gdy będą potrzebne.
- **Aktywność w `activities` linkuje leada przez `ca2g6r4nc84ru61`**; linki do task/meeting są w `payload` (JSON), nie jako Links — mniej wywołań API, timeline i tak czytelny.
- Node'y "Link/Close/Comment" mają `onError: continueRegularOutput` — kosmetyczne niepowodzenie (np. brak uprawnień do komentarzy) nie zatrzyma głównego flow.
