# Zasady sub-flow AI (CoAction CRM)

Zasady konkretnie dla flow, które wołają LLM — wyprowadzone z
`W8_assessment_needs_summary.json`, `W9_offer_package_texts.json` i zasad
usera z 2026-09-26. Doktryna ogólna w [common.md](common.md) §3; mechanika
non-AI w [n8n.md](n8n.md).

## 1. Osobny flow, nie krok w innym flow

Fragment wołający AI ma własny trigger (Button na konkretnej tabeli/wierszu,
webhook) i żyje jako odrębny plik/flow. Nie wplataj wywołania LLM w środek
flow, który zbiera dane albo renderuje plik — render (`W1`) czyta już
gotowy, zaakceptowany tekst; nie generuje go w locie.

## 2. Wejście: jeden blok tekstu, nie surowy JSON z NocoDB

Dedykowany node (Code, np. "Assemble context") składa dane z CRM w JEDEN
tekst — wiadomość użytkownika dla `AI Agent`. Nie podawaj AI Agentowi
surowych obiektów JSON z wielu node'ów NocoDB naraz.

## 3. Wywołanie modelu: `AI Agent` + sub-node modelu

Zawsze `@n8n/n8n-nodes-langchain.agent` + osobny sub-node modelu (np.
`OpenRouter Chat Model`), nigdy `httpRequest` prosto do providera LLM.
Wyjątek: istniejące starsze flow (W3/W5) — nie kopiuj tego wzorca do nowych.

Prompt metodyczny (ton, struktura, "filozofia" firmy) siedzi w polu
**System Message** noda `AI Agent` w UI n8n jako zwykły tekst — nie jako
string w kodzie Code node'a. Dzięki temu osoba nietechniczna (metodyk) może
poprawić prompt samodzielnie, bez znajomości JS.

## 4. Wyjście: dokładnie jedno pole tekstowe

AI zapisuje wynik do JEDNEGO pola tekstowego na wierszu (np. `needs_summary`,
`generated_text`). AI nie tworzy nowych wierszy, nie linkuje relacji, nie
zmienia innych pól poza swoim polem tekstowym i polem statusu (§5). Jeśli
proces wymaga też pomocniczych wpisów w bazie — to faza 2 z `common.md` §4,
osobna od tej faza treści.

## 5. Feedback: pole `ai_status`, odrębne od generycznego `status`

Tabele, na których AI pisze treść, mają własne pole SingleSelect `ai_status`
— to NIE jest to samo co generyczna konwencja `status` ze
`.claude/skills/n8n-flow/SKILL.md` §3 (inna semantyka, inny cykl życia).
Wartości opisują cykl recenzji przez człowieka, nie postęp mechaniki flow:

| Wartość (przykładowo) | Kiedy |
|---|---|
| `none` / `pending` | stan spoczynkowy, gotowe do kliknięcia |
| `ai_draft_ready` | LLM zwrócił tekst, czeka na recenzję metodyka |
| `ai_accepted` | człowiek zaakceptował — tylko wtedy render może użyć tego tekstu |
| `ai_rejected` | brakujące dane wejściowe (np. brak ocen CEFR, brak wybranego wariantu) — LLM NIE został wywołany |

## 6. Guard przed wywołaniem LLM

Jeśli wymagane dane wejściowe są niekompletne (np. brak wypełnionych ocen
CEFR, brak wybranego wariantu pakietu), NIE wołaj LLM. Ustaw `ai_status` na
wartość odrzucenia i stwórz task typu "uzupełnij X" — koszt i czas modelu nie
mogą iść na dane, które i tak nie wystarczą.

## 7. Błąd LLM: reset + komunikat w polu treści, nie tylko log

Gdy wywołanie LLM się nie powiedzie: `ai_status` wraca na stan
spoczynkowy (żeby przycisk dał się kliknąć ponownie) ORAZ komunikat błędu z
linkiem do naprawczego taska trafia wprost w pole tekstowe wyjściowe (np.
`needs_summary`), nie tylko do logów/activities. User nietechniczny czyta
wiersz w NocoDB, nie logi n8n.

## 8. Render używa tylko zaakceptowanej treści AI

Flow generujący finalny plik (faza 3 z `common.md` §4) musi sprawdzić
`ai_status` przed użyciem pola tekstowego AI: jeśli nie jest w stanie
zaakceptowanym (np. `ai_accepted`), traktuj pole jako puste w wyrenderowanym
dokumencie, zamiast wstawiać nierecenzowany draft do dokumentu klienckiego.
