#!/usr/bin/env python3
r"""Tworzy w NocoDB 8 tabel `demo_*` do pokazu koncepcji schematu v4
(docs/crm-schema-v4-proposal.md): lead != szansa sprzedaży, jedna tabela osób,
role (kupujący / attendee / participant) jako powiązania, historia etapów.

NIE DOTYKA istniejących tabel CRM: tworzy wyłącznie tabele z prefiksem
`demo_` i relacje MIĘDZY nimi (stąd własna `demo_companies` zamiast linku do
`companies` - link dodałby pole zwrotne do produkcyjnej tabeli). Po pokazie
tabele `demo_*` usuwa się ręcznie w UI.

Reużywa kodu `scripts/init-schema.py` (połączenie, wykrywanie źródła, tworzenie
tabel, relacji, opcji SingleSelect) i `scripts/upgrade-links.py` (konwersja
pól Links v1 -> LinkToAnotherRecord, bez niej relacje pokazują tylko licznik),
więc ma te same wymagania co `make init-schema`: NC_API_TOKEN, NC_CRM_BASE_ID,
ewentualnie NC_LOCAL_URL / NC_CRM_SOURCE_ID oraz podłączone źródło appdata/crm
(docs/hard-reset.md, Krok 0).

Idempotentny: istniejące tabele i pola są pomijane, można puszczać wielokrotnie.

NIEZWERYFIKOWANE NA ŻYWO (brak instancji NocoDB przy pisaniu): cały kod
tworzenia tabel/relacji to ponowne użycie funkcji z init-schema.py, które
działają na produkcji, ale NOWY jest krok `rename_reverse()` - zmiana nazw
pól zwrotnych relacji (NocoDB nadaje im nazwy sam). Jeśli nie znajdzie
jednoznacznego pola do przemianowania, wypisze, co zmienić ręcznie; nic nie
psuje.

Usage:
  make demo-schema-init
  # albo bezpośrednio:
  set -a; source .env; set +a
  python3 scripts/demo-schema-init.py --dry-run
  python3 scripts/demo-schema-init.py
"""
import argparse
import importlib.util
from pathlib import Path

HERE = Path(__file__).parent


def _load(name, filename):
    # Nazwy plików mają myślnik, stąd loader po ścieżce (jak w upgrade-links.py).
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


core = _load("init_schema", "init-schema.py")
ul = _load("upgrade_links", "upgrade-links.py")
select = core.select

# Etapy z Excela klienta (nie z obecnego `leads.stage`), bo klient je rozpozna.
# Tylko na potrzeby demo - nie rozstrzyga pytania otwartego 1 z propozycji v4.
STAGES = ("Nowa", "Badanie potrzeb", "Audyt", "Demo", "Oferta wysłana",
          "Umowa wysłana", "Umowa podpisana", "Utracona")

TABLES = [
    {
        "title": "demo_companies",
        "icon": "🏢",
        "description": "DEMO v4: firma.",
        "fields": [
            {"title": "name", "type": "SingleLineText"},
            {"title": "nip", "type": "SingleLineText"},
        ],
    },
    {
        "title": "demo_persons",
        "icon": "🧑",
        "description": "DEMO v4: JEDYNA tabela ludzi. Rola (kupujący, attendee, "
                       "participant) wynika z powiązań, nie ze statusu osoby.",
        "fields": [
            {"title": "full_name", "type": "SingleLineText"},
            {"title": "email", "type": "Email"},
            {"title": "position", "type": "SingleLineText"},
        ],
    },
    {
        "title": "demo_leads",
        "icon": "🎯",
        "description": "DEMO v4: zgłoszenie i jego kwalifikacja. Bez etapów "
                       "sprzedaży i wartości - to jest w szansie sprzedaży.",
        "fields": [
            {"title": "lead_name", "type": "SingleLineText"},
            {"title": "lead_type", "type": "SingleSelect", "options": select("B2C", "B2B")},
            {"title": "lead_source", "type": "SingleSelect",
             "options": select("Google", "Recommendation", "LinkedIn")},
            {"title": "qualification", "type": "SingleSelect",
             "options": select("unqualified", "MQL", "SQL", "non-SQL")},
            {"title": "received_at", "type": "Date"},
        ],
    },
    {
        "title": "demo_sale_opportunities",
        "icon": "💼",
        "description": "DEMO v4: szansa sprzedaży (kanban po `stage`). Należy do "
                       "osoby i firmy; lead to tylko źródło (`source_lead`). "
                       "`participants` = osoby szkolone, wypełniane po podpisaniu.",
        "fields": [
            {"title": "name", "type": "SingleLineText"},
            {"title": "segment", "type": "SingleSelect", "options": select("B2C", "B2B")},
            {"title": "stage", "type": "SingleSelect", "options": select(*STAGES)},
            {"title": "state", "type": "SingleSelect",
             "options": select("open", "won", "lost")},
            {"title": "deal_value", "type": "Currency",
             "options": {"locale": "pl-PL", "code": "PLN"}},
        ],
    },
    {
        "title": "demo_stage_history",
        "icon": "🕓",
        "description": "DEMO v4: jeden wiersz na każdą zmianę etapu szansy "
                       "(podstawa do liczenia prędkości lejka).",
        "fields": [
            {"title": "title", "type": "SingleLineText"},
            {"title": "from_stage", "type": "SingleSelect", "options": select(*STAGES)},
            {"title": "to_stage", "type": "SingleSelect", "options": select(*STAGES)},
            {"title": "changed_at", "type": "Date"},
        ],
    },
    {
        "title": "demo_meetings",
        "icon": "👋",
        "description": "DEMO v4: spotkania. Kto był: pole `attendees`.",
        "fields": [
            {"title": "title", "type": "SingleLineText"},
            {"title": "meeting_type", "type": "SingleSelect",
             "options": select("discovery", "audit", "demo")},
            {"title": "starts_at", "type": "DateTime"},
            {"title": "status", "type": "SingleSelect",
             "options": select("scheduled", "done")},
        ],
    },
    {
        "title": "demo_assessments",
        "icon": "📝",
        "description": "DEMO v4: ocena z audytu należy do OSOBY (i spotkania), "
                       "nie do tabeli pośredniej.",
        "fields": [
            {"title": "title", "type": "SingleLineText"},
            {"title": "cefr_overall", "type": "SingleSelect",
             "options": select("A2", "B1", "B2", "C1")},
            {"title": "needs_summary", "type": "LongText"},
        ],
    },
    {
        "title": "demo_tasks",
        "icon": "✅",
        "description": "DEMO v4: zadania - oś codziennej pracy handlowca i "
                       "metodyczek (np. jedno zadanie 'umów audyt' na osobę).",
        "fields": [
            {"title": "title", "type": "SingleLineText"},
            {"title": "assignee", "type": "User"},
            {"title": "status", "type": "SingleSelect", "options": select("todo", "done")},
            {"title": "due_date", "type": "Date"},
        ],
    },
]

# (właściciel, tytuł pola, typ relacji, tabela docelowa, tytuł pola ZWROTNEGO)
# Konwencja jak w init-schema.py: relację "wiele-do-jednego" tworzymy jako `hm`
# na tabeli "jedynej"; pole zwrotne na tabeli "wielu" to właśnie klucz obcy
# (np. demo_leads.person), dlatego ma dostać nazwę po roli, nie po tabeli.
REL_SPEC = [
    ("demo_companies", "persons", "hm", "demo_persons", "company"),
    ("demo_companies", "opportunities", "hm", "demo_sale_opportunities", "company"),
    ("demo_persons", "leads", "hm", "demo_leads", "person"),
    ("demo_persons", "bought_opportunities", "hm", "demo_sale_opportunities", "person"),
    ("demo_persons", "assessments", "hm", "demo_assessments", "person"),
    ("demo_persons", "tasks", "hm", "demo_tasks", "person"),
    ("demo_leads", "opportunities", "hm", "demo_sale_opportunities", "source_lead"),
    ("demo_sale_opportunities", "history", "hm", "demo_stage_history", "sale_opportunity"),
    ("demo_sale_opportunities", "meetings", "hm", "demo_meetings", "sale_opportunity"),
    ("demo_sale_opportunities", "tasks", "hm", "demo_tasks", "sale_opportunity"),
    ("demo_meetings", "assessments", "hm", "demo_assessments", "meeting"),
    # many-to-many: pola zwrotne lądują na demo_persons
    ("demo_sale_opportunities", "participants", "mm", "demo_persons", "participant_in"),
    ("demo_meetings", "attendees", "mm", "demo_persons", "attended_meetings"),
]
RELATIONS = [(o, f, t, tg) for o, f, t, tg, _rev in REL_SPEC]

# init-schema.py czyta TABLES/RELATIONS z globali modułu - podmieniamy je na
# zestaw demo i zerujemy resztę, żeby żadna jego funkcja nie sięgnęła po
# produkcyjne definicje.
core.TABLES = TABLES
core.RELATIONS = RELATIONS
core.COMPUTED_FIELDS = []
core.BUTTONS = []


def rename_reverse(ids, dry_run):
    """Przemianowuje auto-nazwane pola zwrotne relacji na tytuł z REL_SPEC.

    Szuka na tabeli docelowej jedynego pola relacji, które (a) nie jest polem
    zdefiniowanym przez nas i (b) wskazuje z powrotem na właściciela relacji.
    Przy 0 lub >1 kandydatów NIC nie zmienia i prosi o ręczną zmianę nazwy.
    """
    own_titles = {}
    for owner, field, _t, _tg, _rev in REL_SPEC:
        own_titles.setdefault(owner, set()).add(field.lower())
    for t in TABLES:
        own_titles.setdefault(t["title"], set()).update(
            f["title"].lower() for f in t["fields"])

    for owner, field, _rel_type, target, reverse in REL_SPEC:
        owner_id, target_id = ids.get(owner), ids.get(target)
        if dry_run:
            print(f"~  {target}.<pole zwrotne po {owner}.{field}> -> {reverse}")
            continue
        cols = core.table_columns(target_id)
        if reverse.lower() in cols:
            print(f"=  {target}.{reverse}: już nazwane, pomijam")
            continue
        taken = own_titles.get(target, set())
        cands = [
            c for title, c in cols.items()
            if c.get("uidt") in ("LinkToAnotherRecord", "Links")
            and title not in taken
            and (c.get("colOptions") or {}).get("fk_related_model_id") == owner_id
        ]
        if len(cands) != 1:
            print(f"!  {target}: nie umiem jednoznacznie wskazać pola zwrotnego po "
                  f"{owner}.{field} ({len(cands)} kandydatów) - zmień nazwę RĘCZNIE "
                  f"na '{reverse}'")
            continue
        print(f"+  {target}.{cands[0]['title']} -> {reverse}")
        ul.rename_column(cands[0]["id"], reverse)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="pokaż plan, nie wywołuj API")
    args = ap.parse_args()

    print(f"NocoDB: {core.URL}, base: {core.BASE_ID}"
          f"{' [DRY RUN]' if args.dry_run else ''}")
    if args.dry_run and not core.SOURCE_ID:
        source_id = "<zrodlo-appdata>"
        print("źródło: wykryję przy realnym uruchomieniu (GET .../sources)\n")
    else:
        source_id = core.resolve_source()
        print()

    print(f"--- tabele ({len(TABLES)}) ---")
    ids = core.create_tables(args.dry_run, source_id)
    print("\n--- ikonki tabel ---")
    core.sync_table_icons(ids, args.dry_run)
    print(f"\n--- relacje ({len(RELATIONS)}) ---")
    core.create_relations(ids, args.dry_run)
    print("\n--- opcje SingleSelect ---")
    core.sync_select_options(ids, args.dry_run)

    if args.dry_run:
        print(f"\n--- upgrade relacji Links v1 -> v3 ({len(RELATIONS)}) ---")
        for owner, field, _t, _tg in RELATIONS:
            print(f"+  {owner}.{field}: upgrade (convertLinkToV2)")
    else:
        print(f"\n--- upgrade relacji Links v1 -> v3 ({len(RELATIONS)}) ---")
        workspace_id = ul.resolve_workspace_id()
        for owner, field, _t, _tg in RELATIONS:
            ul.upgrade_relation(ids[owner], field, workspace_id, False)

    print("\n--- nazwy pól zwrotnych ---")
    rename_reverse(ids, args.dry_run)

    print("\nSPRAWDŹ w UI przed pokazem:")
    print("  1. Tabele demo_* są w appdata (a nie w wewnętrznej bazie NocoDB) -")
    print("     jak w make init-schema: docker exec docker-postgres-1 psql -U postgres \\")
    print("       -d appdata -c \"\\dt crm.demo_*\"")
    print("  2. Pola relacji pokazują powiązane rekordy (nie sam licznik) i mają")
    print("     role-nazwy: demo_leads.person, demo_sale_opportunities.person /")
    print("     .company / .source_lead, demo_persons.company /")
    print("     .participant_in / .attended_meetings.")
    print("  3. Widoki do wyklikania: Kanban demo_sale_opportunities po `stage`;")
    print("     grid demo_leads z filtrem qualification != SQL; karta rekordu")
    print("     demo_persons (kupujący vs szkolony vs attendee).")
    print("  4. Po pokazie usuń tabele demo_* w UI (skrypt nie ma --drop).")
