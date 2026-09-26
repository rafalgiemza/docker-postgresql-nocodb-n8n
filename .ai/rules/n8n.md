# Mechanika flow n8n — uzupełnienie do skilla n8n-flow

Ten plik NIE powtarza `.claude/skills/n8n-flow/SKILL.md` (nazewnictwo node'ów,
"Get one base", generyczne pole `status`, node NocoDB vs HTTP Request,
równoległość) — czytaj go najpierw. Tu są wzorce mechaniczne, których skill
jeszcze nie opisuje, wyprowadzone z analizy `W1_generate_offer.json`
(2026-09-26). Doktrynę "dlaczego tak dzielimy flow" opisuje
[common.md](common.md).

## Węzeł "Assemble X data" jako jedyna granica przed renderem

Flow renderujący plik ma jeden, i tylko jeden, node typu `Set`
(`executeOnce: true`), w którym cała wcześniej pobrana wiedza z NocoDB jest
spłaszczana do struktury zgodnej z placeholderami szablonu (`data.lead`,
`data.offer`, `data.participants[]`, `data.packages[]`...). Wzorzec:
"Assemble offer data" w `W1_generate_offer.json`. Nie rozpraszaj tego
mapowania po wielu node'ach — jeśli szablon się zmienia, powinieneś edytować
wyrażenia w jednym miejscu.

## Równoległe fetch + merge

Niezależne odczyty z linkowanych tabel (participants, assessments,
recommendations, packages...) idą równoległymi gałęziami z jednego triggera,
schodzą się w jednym nodzie `n8n-nodes-base.merge` (`numberInputs` = liczba
gałęzi) PRZED node'em "Assemble X data". Sekwencja tylko gdy node B faktycznie
potrzebuje ID zwróconego przez node A jako parametru filtra.

## Wzorzec "Tag X with Y" po `resource: linkrow`

`resource: linkrow` zwraca dzieci jednego rodzica bez informacji, do którego
rodzica należą — jak tylko wynik trafi do gałęzi równoległej i zostanie
zmergeowany z wynikami dla innych rodziców, kontekst rodzica jest utracony.
Dlatego bezpośrednio po każdym fetchu `linkrow` wstaw node `Set`
(`includeOtherFields: true`) tagujący każdy wiersz ID rodzica, np.:

```
_participant_id = {{ $('Get linked participants').item.json.id_fields.Id }}
```

Wzorce w repo: "Tag assessment with participant", "Tag recommendation with
participant", "Tag package slide with hours", "Tag package variant adon with
selection data". Bez tego tagowania node "Assemble X data" nie może
poprawnie pogrupować dzieci po rodzicu przy pomocy `.filter()`.

## Gałąź błędu: symetria z gałęzią sukcesu

Node'y, które mogą zawiść (wywołanie serwisu renderującego, upload pliku),
ustawiają `onError: continueErrorOutput` i prowadzą do PARY node'ów
analogicznej do sukcesu:

| Sukces | Błąd |
|---|---|
| Log activity (`type: offer_draft_ready`) | Log error (`type: automation_error`) |
| Task: review offer | Task: generation failed |

Obie gałęzie piszą do `activities` (append-only log) i tworzą task z
`assignee`, `priority: high` i opisem zawierającym ID oferty/leada — nie
kończ gałęzi błędu samym przerwaniem execution.

## Kontrakt wywołania `file-renderer-service`

`POST http://file-renderer-service:8000/render`, `multipart-form-data`:
- `template` — binarka szablonu (pobrana wcześniej przez `httpRequest` z
  `signedUrl`/`url` pola Attachment),
- `data` — `JSON.stringify(...)` spłaszczonej struktury z "Assemble X data".

Response: `fullResponse: true`, `responseFormat: file`. Serwis nie ma żadnej
wiedzy o NocoDB (patrz [common.md](common.md) §4) — jeśli render czegoś nie
ma, to znaczy, że nie zostało dostarczone w `data`, nie że serwis powinien to
sam dociągnąć.

## Wyjątki HTTP Request w tym flow (nie kopiuj bez potrzeby)

`W1_generate_offer.json` ma trzy node'y `httpRequest` poza tymi opisanymi w
skillu (upload szablonu do storage, PATCH rekordu oferty) — to starszy
wzorzec z czasów przed standaryzacją na `nocoDb`/`update` (patrz
`docs/archive/fable/README.md`, akapit o W8 vs W1). Przy nowym flow użyj
`nocoDb`/`update`; przy edycji W1 nie musisz tego migrować bez wyraźnej
potrzeby.
