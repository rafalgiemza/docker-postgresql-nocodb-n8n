            ---
            name: n8n-flow
            description: Rules for creating or editing n8n workflows/flows that use NocoDB in this project (CoAction CRM). Use when the user asks to build a new n8n flow, add/change a node in an existing workflow (W0...W10 style), or export/import workflow JSON under n8n/ or docs/archive/fable/.
            ---

            # Zasady flow n8n (CoAction CRM)

            Te zasady obowiązują przy **każdym** tworzeniu lub edycji flow n8n operującego
            na NocoDB w tym repo — ustalone z userem 2026-09-02. Nie odstępuj od nich bez
            wyraźnej zgody usera; jeśli któraś zasada koliduje z konkretnym przypadkiem,
            zapytaj zamiast improwizować.

            ## 1. Jeden node startowy niesie cały setup: "Get one base"

            Każdy flow zaczyna się od node'a **"Get one base"** (NocoDB, resource Base).
            Wszystkie pozostałe node'y — filtry, tabele, workspace — muszą czerpać ID
            z jego outputu przez expressions (`{{$node["Get one base"].json[...]}}`),
            **nie** z hardkodowanych ID wklejonych osobno w każdym nodzie.

            Cel: żeby podmiana serwera/klienta albo zmiana ID tabeli wymagała edycji
            wyłącznie tego jednego node'a. Przy tworzeniu/edycji flow zawsze sprawdź: czy
            gdybym teraz zmienił bazę w "Get one base", flow zadziałałby bez dotykania
            niczego innego? Jeśli nie — popraw referencje.

            ## 2. Nazwy node'ów w języku biznesowym

            Osoba nietechniczna (np. Dorota, Aleksandra — patrz `.ai/PRD.md` §7) musi
            zrozumieć flow patrząc na same nazwy node'ów. Nazywaj po efekcie, nie po
            mechanice:

            - ✅ "Get participant details", "Update lead status", "Notify auditor"
            - ❌ "NocoDB1", "HTTP Request", "Set2", "IF"

            Domyślne nazwy node'ów z n8n UI zawsze zmień przed zakończeniem pracy.

            ## 3. Status musi być widoczny dla non-technical usera

            Jedno, uniwersalne pole **`status`** (nie osobne pola per-typ jak starsze
            `ai_status`/`processing_status`/`offer_prep_status` z `.ai/PRD.md` §5/§7 —
            te zostają tam gdzie już są, ale nowe flow standaryzują się na `status`).
            Dozwolony zestaw wartości, zawsze ten sam, niezależnie od flow:

            | Wartość | Kiedy |
            |---|---|
            | `none` | stan spoczynkowy — nic się nie dzieje, trigger/przycisk gotowy do ponownego kliknięcia |
            | `collecting data` | flow właśnie zbiera/waliduje dane wejściowe (odczyty z powiązanych tabel) |
            | `creating file` | flow generuje plik (PPTX/DOCX itp.) **bez** udziału AI |
            | `generating` | flow woła **AI Agent** — ustaw ten status w nodzie tuż PRZED nodem AI Agent |
            | `done` | sukces, stan końcowy |
            | `error` | błąd, stan końcowy w gałęzi błędu |

            Minimum cztery momenty zapisu, bez względu na flow:

            1. **Na starcie** — `collecting data`, żeby user widział że coś się dzieje
            zanim skończy.
            2. **W środku** — `generating` tuż przed nodem AI Agent, albo `creating file`
            tuż przed krokiem generowania pliku bez AI. Flow może użyć obu po kolei
            (np. najpierw `generating` przy AI Agent, potem `creating file` przy
            renderze dokumentu z wygenerowanej treści).
            3. **Na końcu, przy sukcesie** — `done`.
            4. **W gałęzi błędu** — `error` (docelowo wracaj do `none`, żeby przycisk dało
            się kliknąć ponownie, wzorem W9 w `.ai/PRD.md` §12) + w miarę możliwości
            czytelny komunikat błędu w polu tekstowym, nie tylko w logach.

            Rozważ też wpis do tabeli `activities` (append-only log pisany wyłącznie
            przez n8n — istniejąca konwencja), jeśli flow dotyczy leada/oferty i wpis do
            historii ma wartość dla usera.

            ## 4. Node NocoDB zamiast HTTP Request

            Domyślnie używaj natywnego node'u **NocoDB** (Get/Get All/Create/Update/
            Delete). HTTP Request tylko gdy NocoDB node faktycznie czegoś nie potrafi
            (np. specyficzny endpoint API, którego nie pokrywa node) — w takim wypadku
            nazwij node tak, żeby było jasne dlaczego to HTTP, np. "Upload offer file", zgodnie z istniejącym wzorcem w W3/W5
            (`docs/pipeline.md`).

            ## 5. AI Agent zamiast HTTP Request we fragmentach AI

            Gałęzie wołające LLM buduj na nodzie **AI Agent**, nie przez HTTP Request do
            OpenRouter/Anthropic wprost — wzorem W9 (`.ai/PRD.md` §7: `AI Agent → dłuższy
            tekst...`). HTTP Request do providera LLM jest akceptowalne tylko w starszym,
            już istniejącym wzorcu (W3/W5), nie kopiuj go do nowych flow.

            ## 6. Równoległość pobierania danych

            Jeśli flow potrzebuje danych z kilku niezależnych tabel, pobieraj je
            równolegle (rozgałęzienie z jednego triggera / "Get one base"), a nie w
            sekwencji. Sekwencja tylko wtedy, gdy node B faktycznie potrzebuje outputu
            node'a A (np. ID zwrócone przez A jest parametrem filtra w B).

            ## 7. Checklist przed uznaniem flow za gotowy

            - [ ] Wszystkie ID base/workspace/table pochodzą z "Get one base", nie są
                  wklejone osobno w innych nodach.
            - [ ] Każdy node ma nazwę zrozumiałą dla non-technical usera.
            - [ ] Status pisany na starcie, przed/po kroku AI/zewnętrznym, na sukces i na
                  błąd.
            - [ ] Brak zbędnych node'ów HTTP Request tam, gdzie starczy node NocoDB.
            - [ ] Brak zbędnych node'ów HTTP Request tam, gdzie starczy AI Agent.
            - [ ] Niezależne odczyty z tabel są równoległe, nie sekwencyjne.
            - [ ] Gałąź błędu istnieje i coś realnie robi (status + komunikat), nie tylko
                  kończy execution.

            ## 8. Gdzie zapisać

            Eksportowany JSON flow trafia do `docs/archive/fable/` (aktualny model
            NocoDB-native, wzorem `W0_recurring_tasks.json`...`W9_offer_package_texts.json`)
            albo `n8n/` (przykłady dla `file-renderer-service`, wzorem
            `wf-docx-gen-example.json`) — zależnie od tego, do którego zbioru flow
            faktycznie należy. Jeśli dodajesz nowy plik, dopisz go też do odpowiedniego
            README (`n8n/README.md` albo `docs/archive/fable/README.md`) sekcją setup, tak
            jak istniejące przykłady.
