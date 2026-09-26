Workflow (docs/archive/fable/W1_generate_offer.json): Fetch active template (getAll + where active=true + sort + limit 1) zamieniony na Get offer template — zwykły get po document_templates.Id odczytanym wprost z linka na wyzwalającym rekordzie oferty (document_templates.Id, tak jak wcześniej robiliśmy z leads.Id).

Do zrobienia po Twojej stronie:

make init-schema — idempotentny, doda tylko tę jedną nową relację (reszta tabel/pól już istnieje, zostanie pominięta).
make upgrade-links — też idempotentny, podniesie tylko tę nową relację do pełnego LinkToAnotherRecord (inaczej webhook nie osadzi linka w payloadzie tak jak dziś robi to dla leads).
Nazwa pola zwrotnego na offers jest niepewna — NocoDB nazywa je automatycznie i nie da się tego wymusić skryptem. Po kroku 1-2 sprawdź w UI (albo prościej: odpal make dump-crm-schema jeszcze raz i zobacz w docs/archive/fable/schema_map.json, jak nazywa się nowe pole na offers). Założyłem, że będzie się nazywać document_templates (tak jak leads/companies/meetings nazwały się po tytule tabeli-właściciela) — jeśli w dumpie wyjdzie inaczej, powiedz mi, poprawię wyrażenie id w Get offer template.
W NocoDB, na widoku offers, podepnij nowe pole Link i wybierz szablon dla rekordu offer #1 przed kolejnym testem — bez tego document_templates.Id będzie puste i Get offer template zwróci 404, tak jak wcześniej Update offer record na unknown.

---

2026-08-30 — offers ↔ package_variants + szkice AI na slajdy 5/6/7: dodałem w `scripts/init-schema.py` nową tabelę-łączącą `offer_packages` (analogicznie do `recommendation_packages`, NIE plain Links mm — patrz niżej dlaczego) między `offers` a `package_variants`. Tabela `package_variants` i jej dane (`warianty_slajd_4.txt`, 10 gotowych pakietów: Business English, English for IT, English + Business Skills: Facilitating/Negotiating/Dynamic Discussions/Presenting & Pitching/Bridging the Gap Between Cultures, Job Interview) już istnieją, ale nic ich dotąd nie łączyło z `offers`.

Powód tabeli-łączącej zamiast zwykłego pola Links: klientka opisała kolejny krok — po wyborze pakietu/pakietów na slajd 4 AI generuje dłuższy szkic tekstu na WŁASNY slajd każdego wybranego pakietu (5/6/7 — ile pakietów, tyle slajdów), człowiek go weryfikuje przed wysyłką. To wymaga miejsca na `generated_text`/`ai_status`/`sort_order` PER (offer, package_variant), a zwykły mm-link tego nie unosi. `offer_packages` ma: `package_name` (display value), `sort_order` (steruje kolejnością na slajdzie 4 i przypisaniem do slajdu 5/6/7), `generated_text` (LongText, szkic AI → tekst zweryfikowany), `ai_status` (konwencja none→pending→ai_draft_ready→ai_accepted/ai_rejected).

**Trigger generowania — ZMIENIONE, patrz notatka niżej:** pierwotnie ustaliłem JEDEN zbiorczy przycisk na `offers` ("Generuj opisy pakietów"). Po Twojej uwadze wróciliśmy do przycisku PER WIERSZ na `offer_packages` ("Generuj opis") — powód: zbiorczy klik nadpisywałby `ai_status` (i odpalał ponowne LLM) też dla pakietów już zaakceptowanych przez człowieka, nie tylko dla nowych. Button w `scripts/init-schema.py` (`BUTTONS`) jest już na `offer_packages`, `ai_status_field("Generuj opis")` na tej tabeli też to odzwierciedla.

**Uwaga o duplikatach w źródle klienta:** `warianty_slajd_4.txt` ma DWA wpisy "English + Business Skills: Facilitating" i DWA "...Negotiating" — każdy z innym opisem (import-packages.py traktuje to jako zamierzone, nie deduplikuje po nazwie). Warto potwierdzić z klientką, czy to naprawdę dwa różne warianty tekstu (pod różny kontekst/odbiorcę), czy wklejka z dwóch wersji dokumentu, zanim ktoś wybierze "zły" wiersz na ofercie.

Do zrobienia po Twojej stronie:

`make init-schema` — idempotentny, doda tabelę `offer_packages`, jej dwie relacje `hm` i przycisk `offer_packages`."Generuj opis" (reszta już istnieje, zostanie pominięta).
`make upgrade-links` (albo ręczne "Upgrade Link Field" w UI) — jak przy document_templates wyżej, inaczej webhook nie osadzi wybranych pakietów w payloadzie.
Jeśli jeszcze nie zaimportowane: `./scripts/import-packages.sh --dry-run` → bez flagi, żeby wgrać 10 pakietów z `warianty_slajd_4.txt` do `package_variants`.
Po `make init-schema`: otwórz pole `offer_packages`."Generuj opis" w UI, zmień akcję z placeholder "Open URL" na "Run Webhook" — dopiero po zaimportowaniu workflowa (teraz już napisany jako DRAFT, patrz niżej).

**2026-08-30 (później tego samego dnia) — workflow napisany, potem PRZEBUDOWANY DWA RAZY:** `docs/archive/fable/W9_offer_package_texts.json`.
- Wersja 1: surowy `httpRequest`/wywołanie OpenRouter API wprost — poprawiona po Twojej uwadze, że konwencja to node'y `nocoDb`/`AI Agent`.
- Wersja 2 (ta poprawka): node'y `nocoDb`, `AI Agent`, `responseMode: lastNode`, ale wciąż zbiorczy przycisk na `offers` z fan-outem na N pakietów naraz.
- **Wersja 3, aktualna:** po Twojej uwadze, że przycisk zbiorczy na `offers` nadpisywałby też już zaakceptowane pakiety, przycisk przeniesiony na `offer_packages` (per wiersz) — to ROZWIĄZAŁO ryzyko nadpisywania i JEDNOCZEŚNIE bardzo uprościło graf: nie ma już "ile pakietów wybrano" (zawsze dokładnie 1 — ten, którego wiersz kliknięto), więc zniknęły: `Fan out packages`, `Gather offer packages`/IF-czy-są-pakiety, agregacja wielu wyników w jeden task. **25 node'ów** (było 27), kształt niemal identyczny z W8 (jeden rekord wchodzi, jeden wychodzi):

Button (`responseMode: lastNode`) → `Set ai_status = pending` (DRUGI node, na surowym payloadzie — dokładnie jak w W8, bo teraz Id jest znane od razu) → `Guard` → `Get package_variant` / `Get offer` → `Get lead` → `Get company` → IF `Wariant uzupelniony?` →
- **TAK:** `Assemble prompt` (tylko dane z CRM; sam prompt metodyczny siedzi STALE w polu System Message noda `AI Agent`, jak w W8 — edytowalny bez znajomości JS) → `AI Agent` (+ `OpenRouter Chat Model`) → sukces: `Parse LLM response` → `nocoDb update` (`generated_text`+`ai_status=ai_draft_ready`) → task weryfikacji → activity; błąd: task NAJPIERW → dopiero potem `nocoDb update` wpisuje w `generated_text` komunikat + link do TEGO taska (`ai_status` wraca na `none` — transient, klikalne od razu) → activity.
- **NIE** (brak wybranego wariantu na wierszu): task "uzupełnij wariant" → link w `generated_text` → `ai_status='ai_rejected'` (wymaga akcji człowieka, w odróżnieniu od `none` przy błędzie LLM) → activity.

Błędy konsekwentnie wpisane w POLE WYNIKOWE (`generated_text`) + link do taska w OBU gałęziach błędu — teraz możliwe we WSZYSTKICH trzech gałęziach (sukces/błąd LLM/brak wariantu), bo w odróżnieniu od poprzedniej (zbiorczej) wersji wiersz `offer_packages` zawsze już istnieje, zanim przycisk w ogóle mógł zostać kliknięty.

Opisane też w `.ai/PRD.md` §12 i `docs/archive/fable/README.md` (tabela + sekcje 1/2/3/4).

**Niepewność "czy AI Agent odpala się raz na item" — NIEAKTUALNA po wersji 3**: skoro teraz zawsze płynie dokładnie 1 item (jeden wiersz `offer_packages` per klik), pytanie "co się dzieje przy N>1" już się nie stosuje. Dla przyszłej referencji (gdyby kiedyś wrócił pomysł zbiorczego triggera): potwierdzone dokumentacją n8n, że `AI Agent` to *root node* i wykonuje się raz na każdy wchodzący item, `OpenRouter Chat Model` to *sub-node*, ale jego jedyny parametr (`model`) jest stały, więc rozróżnienie root/sub-node nie miało tu znaczenia ([docs.n8n.io](https://docs.n8n.io/integrations/builtin/cluster-nodes/root-nodes/n8n-nodes-langchain.agent/)).

To NIE jest gotowy do zaimportowania plik — do zrobienia najpierw:
1. Po `make init-schema` (tworzy `offer_packages` + przycisk `offer_packages`."Generuj opis") i `make dump-crm-schema`: podmień WSZYSTKIE placeholdery `__TBL_...__`/`__WORKSPACE_ID__`/`__PROJECT_ID__`/`__NOCODB_BASE_URL__`/`__NOCODB_CRED_ID__`/`__OPENROUTER_CRED_ID__`/`__VIEW_TASKS_ID__` w pliku realnymi ID (ten sam mechanizm co sekcja 1 w `docs/archive/fable/README.md`, ale tu placeholderów jest więcej, bo `offer_packages`/`package_variants` nie były jeszcze w żadnym dumpie).
2. Zweryfikuj zgadywane nazwy pól zwrotnych: `offers`→`leads` (w kodzie node'a `Get lead`) i `offer_packages`→`offers`/`package_variants` (w `Guard`) — dokładnie ta sama niepewność co przy `document_templates` wyżej w tym pliku.
3. **System prompt w node'ie "AI Agent" → System Message to mój draft, NIE tekst od klientki** (w odróżnieniu od W8, gdzie dostarczyła gotowy prompt 1:1) — pokaż jej instrukcje albo kilka wygenerowanych przykładów przed użyciem produkcyjnym.
4. Node'y `nocoDb` z `operation: update` mają celowo pusty `fieldsMapper.schema` (cache pól, kosmetyczny) — n8n go odtworzy przy pierwszym otwarciu noda po wybraniu prawdziwej tabeli.

Dopiero po tym: import do n8n, podpięcie webhooka pod przycisk `offer_packages`."Generuj opis", smoke test (opisany w `docs/archive/fable/README.md` sekcja 4).

**2026-09-06 — zrobione:** W1 (`docs/archive/fable/W1_generate_offer.json`, "Assemble render data") teraz czyta `offer_packages`→`package_variants` i zasila `data.package[]` (`sort_order`/`name`/`hours`/`short_description`/`generated_text`, to ostatnie tylko gdy `ai_status=ai_accepted`) — zastąpiło stare fetch-e `recommendations`/`recommendation_packages`/`training_descriptions`, które zostały w schemacie (nieusunięte, na żądanie usera) ale są puste i nieużywane. Szczegóły migracji w `docs/archive/fable/README.md` (notatka przy tabeli workflowów, sekcja przed "## 1. Podmień placeholdery"). **Nadal do zrobienia:** dopasowanie/weryfikacja szablonu PPTX pod `repeat:package` (był/mógł być jeszcze na starym `repeat:module`) — nie testowane na żywym renderze; ręczne uzupełnienie `lesson_frequency`/`lesson_minutes` na `package_variants` (import ich nie parsuje z pliku — patrz komentarz w `import-packages.py`).

**2026-09-07 — NIEAKTUALNE, cofnięte:** W1 wrócił do `recommendations`→
`recommendation_packages` dla pakietów (potwierdzone z userem — te tabele mają
realne dane, nie są puste jak opisano wyżej). Szczegóły w
`docs/archive/fable/README.md` (notatka 2026-09-07 przy tabeli workflowów).
`offer_packages`/`package_variants` zostają w schemacie dla `W9` (generowanie
AI tekstów per pakiet), ale W1 ich nie czyta.


HANDLE MISSING OFFFER TEMPLATE CASE