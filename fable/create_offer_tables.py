#!/usr/bin/env python3
r"""Tworzy CAŁY schemat CRM (16 tabel + relacje) w pustej bazie NocoDB przez
Meta API v3 — pod wdrożenie produkcji od zera.

Źródło prawdy: `fable/nocodb_crm_schema_v3.md` (decyzje projektowe i tabele
nowe/zmienione) + `fable/nocodb_crm_schema_v2.md` (pola tabel bazowych, których
v3 nie powtarza, bo opisuje wyłącznie różnice).

Trzy poziomy merytoryczne, patrz v3 "Architektura tabel":
    assessment     = CO JEST        (audyt)         per uczestnik
    recommendation = CO PROPONUJEMY (ścieżka)       per uczestnik
    offer          = ZA ILE         (cena, plik)    per lead

DLACZEGO v2, SKORO v3 JEST NOWSZE (i v2 kiedyś zniknie):
v3 **nie potrafi** utworzyć tabeli w zewnętrznym źródle danych. Sprawdzone
2026-08-03 w oficjalnym OpenAPI (github.com/nocodb/noco-apis-doc,
meta-apis-v3/swagger-v3.json): `POST /api/v3/meta/bases/{base_id}/tables`
nie przyjmuje id źródła ani w ścieżce, ani w body — `source_id` jest tylko
w ODPOWIEDZI, nadawane automatycznie. Nie ma też endpointu listującego
źródła (tylko `sources` w `GET /bases/{id}`). Skutek praktyczny: v3 zawsze
tworzy w źródle domyślnym, czyli w wewnętrznej bazie NocoDB — a nasze tabele
mają żyć w `appdata` (źródło prawdy, objęte `make backup`).

v2 ma źródło jako segment ścieżki i to działa (zweryfikowane na żywo, niżej).
KIEDY WRÓCIĆ DO v3: gdy w spec pojawi się sposób wskazania źródła przy
tworzeniu tabeli. Do tego czasu v2 jest jedyną opcją, niezależnie od jego
statusu. Kontekst: nieudokumentowany kontrakt kolumn Links w v2 był powodem,
dla którego pierwotnie celowaliśmy w v3 (nocodb/nocodb#3610).

ZWERYFIKOWANE NA ŻYWO 2026-08-03 (NocoDB `latest`, VPS-B) — ustalenia, których
NIE da się wyczytać z dokumentacji:

  1. `POST /api/v3/meta/bases/{base}/tables` z `source_id` W CIELE żądania
     zwraca 200, ale źródło jest IGNOROWANE — tabele lądują w wewnętrznej
     bazie NocoDB (`nocodb`), w schemacie o nazwie <base_id>.
  2. Ścieżkowy wariant v3 (`.../bases/{base}/{source}/tables`) → 404.
  3. DZIAŁA: `POST /api/v2/meta/bases/{base}/{source}/tables` — źródło jako
     segment ŚCIEŻKI, kontrakt v2 (`columns`/`uidt`, selecty w `dtxp`).
  4. Źródła NIE da się rozpoznać po `type`/`is_meta` — baza metadanych NocoDB
     sama stoi na Postgresie, więc jej wewnętrzne źródło też raportuje
     `type: pg, is_meta: false`. Rozróżnia je `alias` (wewnętrzne ma null).

WYMAGA RĘCZNEGO DOKOŃCZENIA: relacje `hm` powstają jako kolumny klucza obcego
(stary typ pola link), a nie jako tabele łączące. W UI NocoDB pokazuje przy
nich "Upgrade Link Field" — trzeba to kliknąć, bo webhooki NocoDB wystawiają
pełne rekordy powiązane tylko przez `_nc_m2m_*` (od tego zależy W9, patrz
`fable/W9_generate_offer.json`, node "Assemble render data"). Relacje `mm`
dostają tabelę łączącą od razu. TODO: znaleźć parametr API wymuszający nowy
typ od razu — inaczej ten sam klikany krok wraca przy każdym odtworzeniu.

GDZIE LĄDUJĄ TABELE (najważniejsze): baza NocoDB ma domyślne źródło = własna
baza metadanych NocoDB (`NC_DB`, czyli `nocodb`). `appdata` jest podpięta jako
OSOBNE źródło (`make wire-apps` / `scripts/crm-wire-init.sh`). Bez wskazania
`source_id` tabele powstają w bazie `nocodb` — poza źródłem prawdy, poza
`make backup` i poza zasięgiem `n8n_crm_user`. Skrypt wykrywa zewnętrzne
źródło automatycznie (`resolve_source()`); override: `NC_CRM_SOURCE_ID`.
WYMÓG: `make wire-apps` PRZED tym skryptem — inaczej nie ma czego wykryć.
Po uruchomieniu zweryfikuj w Postgresie (`\dt crm.*`), nie tylko w UI.

Alternatywa, której świadomie tu nie wybrano: napisać te 16 tabel jako SQL
w `appdata/appdata_schema.sql` i puścić `make migrate` + `meta-diff/apply`.
Byłoby deterministyczne i wersjonowane w gicie, ale kolumny `Links` to nie
czysty SQL — NocoDB trzyma dla nich własne metadane (i tabele `_nc_m2m_*`),
więc po samym SQL-u relacje trzeba by i tak odtwarzać w NocoDB. Stąd API.

CZEGO TEN SKRYPT NIE ROBI (do wyklikania ręcznie po uruchomieniu):
  1. Pól typu Button ("generuj ofertę" na `offers`, "generuj analizę" na
     `meetings`, "generuj needs summary" na `assessments`) — wymagają ID
     istniejącego webhooka, którego przed importem workflowów jeszcze nie ma.
  2. Widoków (Kanban/Calendar/Grid per osoba) — patrz v2 "Widoki".
  3. Nazw pól zwrotnych, które NocoDB samo nadaje dla relacji `hm` — nie są
     udokumentowane, sprawdź i popraw w UI.
  4. Display value: NocoDB bierze pierwsze pole z listy — dlatego w każdej
     tabeli pole "nazwowe" jest pierwsze. Zweryfikuj w UI.
  5. ZMIANY NA JUŻ WDROŻONEJ BAZIE (patrz `fable/feedback-tables-1.md`,
     nałożone na TABLES/RELATIONS 2026-08-06): `create_tables()` pomija CAŁĄ
     tabelę, jeśli tytuł już istnieje — nie ma diffa na poziomie pojedynczego
     pola. Jeśli baza z 16 tabelami już żyje w produkcji, ponowne uruchomienie
     tego skryptu NIE przemianuje `recommendation_items`→`recommendation_packages`,
     `training_modules`→`training_descriptions`, ani nie dopisze nowych
     opcji do istniejących SingleSelect/description — te tabele po prostu
     zostaną pominięte jako "już istnieje". Zmiany trzeba nanieść ręcznie w
     UI NocoDB (rename tabeli/pola zachowuje Id i dane) albo osobnym
     skryptem migracyjnym (PATCH po Id) — TABLES/RELATIONS niżej to teraz
     aktualny stan docelowy, nie automatyczny diff.

Idempotentny: tabele i pola-relacje o istniejącym tytule są pomijane.

Wymaga w środowisku (patrz .env.example): NC_API_TOKEN, NC_CRM_BASE_ID.
Opcjonalnie NC_LOCAL_URL (domyślnie http://localhost:8081).

Usage:
  set -a; source .env; set +a
  python3 fable/create_offer_tables.py --dry-run
  python3 fable/create_offer_tables.py
"""
import argparse
import os
import sys

import requests

URL = os.environ.get("NC_LOCAL_URL", "http://localhost:8081").rstrip("/")
TOKEN = os.environ.get("NC_API_TOKEN")
BASE_ID = os.environ.get("NC_CRM_BASE_ID")
# Opcjonalny override - normalnie wykrywany automatycznie, patrz resolve_source().
SOURCE_ID = os.environ.get("NC_CRM_SOURCE_ID")

if not TOKEN or not BASE_ID:
    sys.exit("Brak NC_API_TOKEN / NC_CRM_BASE_ID w środowisku - patrz .env.example.")

S = requests.Session()
S.headers.update({"xc-token": TOKEN, "Content-Type": "application/json"})


def api(method, path, raise_on_error=False, **kw):
    try:
        r = S.request(method, f"{URL}{path}", timeout=30, **kw)
    except requests.RequestException as e:
        sys.exit(f"Nie moge sie polaczyc z NocoDB ({URL}): {type(e).__name__}. "
                 f"Sprawdz NC_LOCAL_URL / czy kontener stoi.")
    if not r.ok:
        if raise_on_error:
            raise RuntimeError(f"{r.status_code}: {r.text[:200]}")
        sys.exit(f"NocoDB API error {r.status_code} on {method} {path}: {r.text[:500]}")
    return r.json() if r.text else {}


def resolve_source():
    """Zwraca id ZEWNĘTRZNEGO źródła (appdata/crm), nie wewnętrznej bazy NocoDB.

    KRYTYCZNE: baza NocoDB ma domyślne źródło = własna baza metadanych NocoDB
    (`NC_DB`, czyli `nocodb`). `appdata` jest podpięta jako OSOBNE źródło
    (`scripts/crm-wire-init.sh`: alias "appdata (crm)", type pg,
    searchPath ["crm"]). Tworzenie tabel bez wskazania source_id ląduje
    w bazie `nocodb` zamiast w `appdata` - czyli poza źródłem prawdy,
    poza `make backup` i poza zasięgiem `n8n_crm_user`.
    """
    if SOURCE_ID:
        print(f"źródło: {SOURCE_ID} (z NC_CRM_SOURCE_ID)")
        return SOURCE_ID
    for ver in ("v3", "v2"):          # v3 nie ma udokumentowanego /sources
        try:
            rows = api("GET", f"/api/{ver}/meta/bases/{BASE_ID}/sources",
                       raise_on_error=True).get("list", [])
        except RuntimeError:
            continue
        # Rozroznik: ZEWNETRZNE zrodlo ma nazwe (alias), domyslne/wewnetrzne ma
        # alias=null. NIE filtruj po `type`/`is_meta` - baza metadanych NocoDB
        # sama stoi na Postgresie, wiec jej wewnetrzne zrodlo tez raportuje
        # `type: pg, is_meta: false` i jest nieodroznialne od appdata.
        # (Zweryfikowane na zywo 2026-08-03: tabele utworzone przez takie
        # "wykryte" zrodlo wyladowaly w bazie `nocodb`, schemat <base_id>.)
        external = [s for s in rows if (s.get("alias") or "").strip()]
        if len(external) == 1:
            s = external[0]
            print(f"źródło: {s['id']} (alias={s.get('alias')!r}, type={s.get('type')})")
            return s["id"]
        if not external:
            sys.exit(
                f"Baza {BASE_ID} nie ma zewnętrznego źródła (żadne nie ma "
                f"aliasu) - tabele trafiłyby do wewnętrznej bazy NocoDB, "
                f"do schematu o nazwie <base_id>, a NIE do appdata.\n"
                f"Podepnij appdata w NocoDB UI: Base → Data Sources → New:\n"
                f"  Host=postgres  Port=5432  Database=appdata  Schema=crm\n"
                f"  User/Password = NOCODB_CRM_USER / NOCODB_CRM_PASSWORD\n"
                f"Database MUSI byc `appdata`, a `crm` idzie w pole Schema - "
                f"wpisanie `crm` jako Database konczy sie proba CREATE DATABASE "
                f"i bledem uprawnien.")
        sys.exit(f"Baza {BASE_ID} ma {len(external)} zewnętrznych źródeł "
                 f"({[s.get('alias') for s in external]}) - wskaż jednoznacznie "
                 f"przez NC_CRM_SOURCE_ID.")
    sys.exit("Nie moge odczytac listy zrodel bazy (ani v3, ani v2). "
             "Podaj NC_CRM_SOURCE_ID recznie - id znajdziesz w UI: "
             "Base → Data Sources.")


def select(*titles):
    return {"choices": [{"title": t} for t in titles]}


# --------------------------------------------------------------- wspólne słowniki
# Trzymane w stałych, bo v3 §11 wprost wymaga, żeby `pricing.product` ==
# `offers.product_type` i `pricing.training_group_size` ==
# `recommendation_packages.training_group_size` — inaczej automatyczne
# dopasowanie ceny nigdy nie będzie możliwe. Jedna definicja = listy nie
# mogą się rozjechać.
AI_STATUS = ("none", "pending", "ai_draft_ready", "ai_accepted", "ai_rejected")
MODE = ("1-1", "w_parach", "grupa")
# feedback-tables-1.md: offers.variant -> product_type (+ 3 nowe warianty),
# pricing.segment -> product - obie kolumny nadal musza dzielic te sama liste.
VARIANT = ("standard", "intensive_workshop", "oferta_specjalna",
           "audyt_jezykowy", "job_interview", "webinar")
# feedback-tables-1.md - pelna lista branz z excelowego CRM klienta (1:1,
# wlacznie z zapisem "E.commerce"/"Networks/Itadmin" itp. - to widoczne w
# dropdownie etykiety, nie wewnetrzne identyfikatory, wiec zostawione tak jak
# podala klientka, bez normalizacji wielkosci liter).
INDUSTRY = ("Agriculture", "AI", "Automation", "Automotive", "Banking", "Clothing",
            "Construction", "Data Solutions", "Design", "E.commerce", "Energy",
            "Entertainment", "Finance", "Food", "Furniture", "Home Appliances",
            "Hotels", "HR services", "Insurance", "Networks/Itadmin", "IT",
            "Medicine", "Law", "Machinery", "Marketing Agency", "Media", "Pharma",
            "Military", "Packaging", "Public sector", "Publishing", "Real Estate",
            "Retail", "Software Development", "Tech Product", "Telecommunication",
            "Tourism", "Training", "Transport/Logistics", "Housing", "Space",
            "Manufacturing", "Education", "CyberSec")


def ai_status_field(action=None):
    """`action` = etykieta przycisku, ktory faktycznie startuje generowanie w
    tej tabeli (patrz naglowek skryptu, sekcja "CZEGO TEN SKRYPT NIE ROBI" -
    Button na offers/meetings/assessments). feedback-tables-1.md prosil o
    opis "jak wygenerowac tresc" w description - NIE piszemy tu "zmien status
    i odswiez", bo to nieprawda: generowanie startuje przyciskiem, a zmiana
    samego ai_status niczego nie wywoluje.
    """
    base = ("Status tresci generowanej przez AI: none (nic nie generowano) -> "
            "pending (automatyzacja wlasnie generuje, czekaj) -> "
            "ai_draft_ready (jest szkic, czeka na weryfikacje czlowieka) -> "
            "ai_accepted / ai_rejected (decyzja czlowieka). Tylko ai_accepted "
            "moze zasilic oferte. Sama zmiana tego pola NIC nie generuje")
    if action:
        note = f' - uzupelnij pola powyzej, kliknij przycisk "{action}", potem odswiez'
    else:
        note = (" - przycisk/automatyzacja generujaca tresc dla tej tabeli nie "
                "jest jeszcze podpieta, do ustalenia")
    return {"title": "ai_status", "type": "SingleSelect", "options": select(*AI_STATUS),
            "description": base + note + "."}


# --------------------------------------------------------------- definicje tabel
# Kolejność pól ma znaczenie: pierwsze pole zostaje display value.
TABLES = [
    {
        "title": "companies",
        "description": "Firma jako byt trwaly - lead to pojedyncza szansa, "
                       "firma moze miec wiele leadow w czasie. Tylko B2B.",
        "fields": [
            {"title": "name", "type": "SingleLineText"},
            {"title": "domains", "type": "SingleLineText"},
            {"title": "nip", "type": "SingleLineText"},
            {"title": "industry", "type": "SingleSelect", "options": select(*INDUSTRY)},
            {"title": "size", "type": "SingleSelect",
             "options": select("<10", "10-50", "51-250", "250+")},
            {"title": "folder_url", "type": "URL"},
            {"title": "notes", "type": "LongText"},
            # v3 §10 - kontekst biznesowy z discovery
            {"title": "communication_processes", "type": "LongText",
             "description": "Jak w firmie przebiega komunikacja: kluczowe role, "
                            "z kim i o czym rozmawiaja pracownicy, kto jest "
                            "odbiorca komunikacji (np. klienci zagraniczni, "
                            "zespoly rozproszone). Wypelnia AI na podstawie "
                            "transkryptu spotkania discovery, czlowiek poprawia."},
            {"title": "business_impact", "type": "LongText",
             "description": "Jaki jest biznesowy skutek brakow jezykowych w tej "
                            "firmie (np. utracone kontrakty, wolniejsza obsluga "
                            "klienta zagranicznego). Wypelnia AI na podstawie "
                            "transkryptu spotkania discovery, czlowiek poprawia."},
        ],
    },
    {
        "title": "leads",
        "description": "Jedna szansa sprzedazy. Kanban po `stage`. UWAGA: "
                       "`deal_value` to PROGNOZA wartosci szansy - nie mylic z "
                       "`offers.total_price` (kwota na konkretnym dokumencie).",
        "fields": [
            # feedback-tables-1.md: contact_name -> lead_name (tabela miesza
            # firmy i klientow B2C, "contact_name" bylo mylace)
            {"title": "lead_name", "type": "SingleLineText"},
            {"title": "contact_email", "type": "Email"},
            {"title": "contact_phone", "type": "PhoneNumber"},
            # feedback-tables-1.md: type -> lead_type (za duzo pol "type" w
            # roznych tabelach w calej bazie, latwo pomylic)
            {"title": "lead_type", "type": "SingleSelect", "options": select("B2C", "B2B")},
            {"title": "owner", "type": "User"},
            # feedback-tables-1.md: source -> lead_source; lista zastapiona
            # tabelka podana przez klientke (zrodlo/kanal pozyskania leada)
            {"title": "lead_source", "type": "SingleSelect",
             "options": select("Google", "Outreach", "Existing client", "LinkedIn",
                               "Recommendation", "Webinar", "Facebook",
                               "Coming back Lead", "Coming back Client")},
            # feedback-tables-1.md: brakujace typy kontaktu - lista z excela
            # ("Uwzglednij wszystkie rodzaje contact_channel z excelowego crm")
            # + ta sama tabelka co lead_source (klientka: "do obu pol")
            {"title": "contact_channel", "type": "SingleSelect",
             "options": select("Bookings", "Telefon", "Linkedin CoAction", "Mail",
                               "Formularz", "Facebook Przemka", "Facebook CoAction",
                               "Linkedin Przemka", "Google", "Outreach",
                               "Existing client", "LinkedIn", "Recommendation",
                               "Webinar", "Facebook", "Coming back Lead",
                               "Coming back Client")},
            # feedback-tables-1.md: rozdzielenie non-MQL/non-SQL, zeby od razu
            # bylo widac NA JAKIM etapie lead zostal zdyskwalifikowany (tak
            # jak w excelu) - unqualified zostaje jako ogolny fallback
            {"title": "qualification", "type": "SingleSelect",
             "options": select("unqualified", "non-MQL", "MQL", "non-SQL", "SQL")},
            {"title": "disqualify_reason", "type": "SingleSelect",
             "options": select("brak_budzetu", "brak_potrzeby", "konkurencja",
                               "brak_kontaktu", "inne")},
            {"title": "disqualify_note", "type": "LongText"},
            {"title": "stage", "type": "SingleSelect",
             "options": select("new", "discovery_scheduled", "discovery_done",
                               "audit", "recommendation", "offer_sent",
                               "offer_discussed", "contract_sent",
                               "contract_signed", "lost", "archived")},
            {"title": "state", "type": "SingleSelect",
             "options": select("open", "won", "lost", "archived")},
            {"title": "loss_reason", "type": "SingleSelect",
             "options": select("cena", "brak_decyzji", "konkurencja",
                               "przesuniete_w_czasie", "inne")},
            {"title": "loss_note", "type": "LongText"},
            # feedback-tables-1.md: value -> deal_value + opis, zeby nie mylic
            # z offers.total_price (patrz opis tabeli wyzej: value to PROGNOZA)
            {"title": "deal_value", "type": "Currency",
             "options": {"locale": "pl-PL", "code": "PLN"},
             "description": "Wartosc szansy sprzedazy (prognoza pipeline'u, "
                            "szacowana zanim istnieje oferta). To NIE jest "
                            "kwota z konkretnego dokumentu ofertowego - tamta "
                            "jest w offers.total_price."},
            {"title": "label", "type": "SingleSelect",
             "options": select("hot", "oferta_specjalna")},
            # v3 §1 - dla B2C, gdzie nie ma rekordu firmy
            {"title": "industry", "type": "SingleSelect", "options": select(*INDUSTRY)},
            {"title": "notes", "type": "LongText"},
            {"title": "company_match_status", "type": "SingleSelect",
             "options": select("none", "pending_confirmation", "confirmed", "rejected")},
            {"title": "offer_prep_status", "type": "SingleSelect",
             "options": select("none", "waiting_goals", "goals_provided",
                               "testimonials_provided", "draft_ready")},
            {"title": "training_goals", "type": "LongText"},
            # kamienie milowe - pisze wylacznie n8n
            {"title": "offer_sent_at", "type": "Date"},
            {"title": "contract_sent_at", "type": "Date"},
            {"title": "closed_at", "type": "Date"},
            # v3 §1 - `lead_id` z v2 mialo mylaca nazwe (pole lead_id w tabeli leads)
            {"title": "legacy_id", "type": "SingleLineText"},
        ],
    },
    {
        "title": "participants",
        "description": "Osoba szkolona (!= kupujacy). v3 §3: tworzymy ZAWSZE, "
                       "takze dla B2C - inaczej nie ma gdzie trzymac oceny "
                       "i rekomendacji, a generator oferty wyrenderuje pusto. "
                       "Oceny CEFR mieszkaja w `assessments`, NIE tutaj.",
        "fields": [
            {"title": "full_name", "type": "SingleLineText"},
            {"title": "position", "type": "SingleLineText"},
            {"title": "linkedin_url", "type": "URL"},
            {"title": "email", "type": "Email"},
            # v3 §3 - "kontekst biznesowy" dla B2C, gdzie nie ma `companies`
            {"title": "role_context", "type": "LongText"},
            {"title": "frequency", "type": "SingleSelect",
             "options": select("codziennie", "kilka_razy_w_tyg", "rzadko")},
            {"title": "self_assessment", "type": "LongText"},
            {"title": "manager_needs", "type": "LongText"},
            {"title": "assigned_methodologist", "type": "User"},
        ],
    },
    {
        "title": "meetings",
        "description": "Tylko prawdziwe spotkania (Calendar view). v3 §2: pola "
                       "strukturalne zamiast jednego blobu - bo kazda rzecz, "
                       "ktora ma trafic na slajd, musi byc osobnym polem.",
        "fields": [
            {"title": "title", "type": "SingleLineText"},
            # feedback-tables-1.md: type -> meeting_type (jw., zeby nie mylic
            # z "type"/"variant" w innych tabelach)
            {"title": "meeting_type", "type": "SingleSelect",
             "options": select("discovery", "demo", "audit", "needs_analysis",
                               "offer_discussion", "inne")},
            {"title": "starts_at", "type": "DateTime"},
            {"title": "ends_at", "type": "DateTime"},
            {"title": "owner", "type": "User"},
            {"title": "status", "type": "SingleSelect",
             "options": select("scheduled", "done", "no_show", "cancelled")},
            # brudnopis
            {"title": "notes", "type": "LongText"},
            {"title": "transcript", "type": "LongText"},
            # draft AI -> czystopis (jeden prompt, jeden status) - opisy ponizej
            # wg nocodb_crm_schema_v3.md §2; goals/challenges leca wprost do
            # szablonu oferty jako {{meeting.goals}}/{{meeting.challenges}}
            # (v3 §"Co sie zmienia w W9 i szablonie oferty") - to jedyne dwa
            # pola z tej piatki ze zweryfikowanym miejscem docelowym w pliku.
            {"title": "goals", "type": "LongText",
             "description": "Cele klienta wzgledem szkolenia. Generowane przez "
                            "AI z transcript+notes, czlowiek poprawia po "
                            "ai_draft_ready. Trafia wprost na slajd oferty "
                            "jako {{meeting.goals}}."},
            {"title": "challenges", "type": "LongText",
             "description": "Wyzwania/problemy zglaszane podczas spotkania. "
                            "Generowane przez AI z transcript+notes, czlowiek "
                            "poprawia. Trafia wprost na slajd oferty jako "
                            "{{meeting.challenges}}."},
            {"title": "participant_types", "type": "LongText",
             "description": "Jacy ludzie / jakie role uczestnicza w szkoleniu "
                            "(skrot, nie lista imion - te sa w `participants`). "
                            "Generowane przez AI z transcript+notes, czlowiek "
                            "poprawia."},
            {"title": "business_context", "type": "LongText",
             "description": "Kontekst biznesowy firmy/klienta z rozmowy - "
                            "odpowiednik `companies.communication_processes` "
                            "dla tego konkretnego spotkania. Generowane przez "
                            "AI z transcript+notes, czlowiek poprawia."},
            {"title": "communication_situations", "type": "LongText",
             "description": "Konkretne sytuacje komunikacyjne po angielsku, w "
                            "ktorych klient bierze udzial (np. negocjacje z "
                            "dostawca, prezentacje dla zarzadu) - to one "
                            "bezposrednio zasilaja audyt jezykowy. Generowane "
                            "przez AI z transcript+notes, czlowiek poprawia."},
            ai_status_field("Generuj analizę"),
            # surowy blob z LLM - do wgladu/debugu, NIE zrodlo dla oferty
            {"title": "ai_analysis_raw", "type": "LongText"},
            {"title": "outcome", "type": "LongText"},
        ],
    },
    {
        "title": "assessments",
        "description": "Historia ocen CEFR: jeden wiersz na audyt. Najnowsza "
                       "ocena = sort=-UpdatedAt (pole systemowe), bez osobnej "
                       "flagi 'aktualna'. Zastepuje plaskie participants.cefr_*.",
        "fields": [
            {"title": "title", "type": "SingleLineText"},
            {"title": "assessed_at", "type": "Date"},
            # skala z czesciami dziesietnymi (B2.4) - text, nie number
            {"title": "cefr_overall", "type": "SingleLineText"},
            {"title": "cefr_range", "type": "SingleLineText"},
            {"title": "cefr_accuracy", "type": "SingleLineText"},
            {"title": "cefr_fluency", "type": "SingleLineText"},
            {"title": "cefr_communication", "type": "SingleLineText"},
            {"title": "strengths", "type": "LongText"},
            {"title": "gaps", "type": "LongText"},
            {"title": "needs_summary", "type": "LongText"},
            {"title": "auditor_notes", "type": "LongText"},
            ai_status_field("Generuj needs summary"),
            # v3 §12 - raport audytowy jako artefakt audytu, bez osobnej tabeli
            {"title": "report_file", "type": "Attachment"},
            {"title": "report_data_json", "type": "LongText"},
        ],
    },
    {
        "title": "recommendations",
        "description": "Co proponujemy TEJ osobie. Oddzielone od audytu, bo to "
                       "inna decyzja, innego czlowieka i w innym momencie "
                       "(Opis_procesu §7).",
        "fields": [
            {"title": "title", "type": "SingleLineText"},
            {"title": "type", "type": "SingleSelect",
             "options": select("business_english", "english_plus_skills",
                               "skills_only", "mieszana")},
            {"title": "headline", "type": "SingleLineText"},
            {"title": "rationale", "type": "LongText"},
            # feedback-tables-1.md: brakowalo wyjasnienia CZEGO to priorytet
            {"title": "priority", "type": "SingleSelect",
             "options": select("wysoki", "sredni", "niski"),
             "description": "Priorytet TEJ rekomendacji wzgledem innych "
                            "rekomendacji dla tej samej osoby (jedna osoba "
                            "moze miec kilka proponowanych sciezek) - pomaga "
                            "wybrac, ktora sciezke pokazac jako glowna w "
                            "ofercie."},
            # brak potwierdzonego przycisku dla tej tabeli w skrypcie (patrz
            # naglowek: Button jest tylko na offers/meetings/assessments) -
            # ai_status_field() bez `action` pisze to wprost, zamiast zmyslac
            ai_status_field(),
        ],
    },
    {
        # feedback-tables-1.md: nazwa tabeli TRAINING_MODULES -> Training_descriptions
        # (znormalizowane do lowercase snake_case - konwencja calego pliku)
        "title": "training_descriptions",
        "description": "Biblioteka modulow szkoleniowych (dzis istnieja tylko "
                       "jako tekst zaszyty na slajdach ETAP 1/ETAP 2).",
        "fields": [
            {"title": "title", "type": "SingleLineText"},
            # feedback-tables-1.md: category -> Training_Type
            {"title": "training_type", "type": "SingleSelect",
             "options": select("business_english", "english_for_it",
                               "workshop_facylitacja", "workshop_negocjacje",
                               "inne")},
            # feedback-tables-1.md: goal_statement -> learning_goal
            {"title": "learning_goal", "type": "LongText"},
            {"title": "description", "type": "LongText"},
            # feedback-tables-1.md wymienia "hours_in_package" pod ta tabela
            # bez dodatkowego kontekstu; zalozenie: to rename default_hours,
            # analogiczny do hours -> hours_in_package w recommendation_packages
            # (patrz nizej) - do potwierdzenia, jesli chodzilo o cos innego.
            {"title": "hours_in_package", "type": "Number"},
            {"title": "active", "type": "Checkbox", "default_value": True},
        ],
    },
    {
        # feedback-tables-1.md: "Nazwa tabeli: recommendation_packages, a nie items"
        "title": "recommendation_packages",
        "description": "Konkretna sciezka: ktore moduly, w jakiej kolejnosci, "
                       "ile godzin, w jakim trybie. Zasila slajd repeat:module. "
                       "`package_name` istnieje wylacznie po to, zeby display "
                       "value nie byl liczba (sort_order) - patrz naglowek skryptu.",
        "fields": [
            # feedback-tables-1.md: label -> package_name
            {"title": "package_name", "type": "SingleLineText"},
            {"title": "sort_order", "type": "Number"},
            # feedback-tables-1.md: hours -> Hours_in_Package
            {"title": "hours_in_package", "type": "Number"},
            # feedback-tables-1.md: mode -> Training_Group_Size
            {"title": "training_group_size", "type": "SingleSelect", "options": select(*MODE)},
        ],
    },
    {
        "title": "pricing",
        "description": "Cennik wersjonowany. SWIADOMIE bez relacji do ofert - "
                       "tabela referencyjna, z ktorej czlowiek odczytuje stawke. "
                       "`product` == offers.product_type, `training_group_size` == "
                       "recommendation_packages.training_group_size (wspolne "
                       "stale w skrypcie: VARIANT / MODE).",
        "fields": [
            # feedback-tables-1.md: segment -> product
            {"title": "product", "type": "SingleSelect", "options": select(*VARIANT)},
            # feedback-tables-1.md: mode -> Training_Group_Size
            {"title": "training_group_size", "type": "SingleSelect", "options": select(*MODE)},
            {"title": "hours", "type": "Number"},
            # feedback-tables-1.md: price -> total_price (vs hourly price)
            {"title": "total_price", "type": "Currency",
             "options": {"locale": "pl-PL", "code": "PLN"}},
            {"title": "valid_from", "type": "Date"},
            {"title": "valid_to", "type": "Date"},
        ],
    },
    {
        "title": "offers",
        "description": "Jedna oferta = jeden wygenerowany dokument; wiele ofert "
                       "na lead (wersje). `data_json` to zamrozony snapshot "
                       "danych - realizacja wymogu 'historia ofert' (§10).",
        "fields": [
            {"title": "title", "type": "SingleLineText"},
            {"title": "status", "type": "SingleSelect",
             "options": select("draft", "sent", "accepted", "rejected")},
            # feedback-tables-1.md: price -> total_price (vs hourly price)
            {"title": "total_price", "type": "Currency",
             "options": {"locale": "pl-PL", "code": "PLN"}},
            {"title": "hours", "type": "Number"},
            # feedback-tables-1.md: variant -> product_type, dodane Audyt
            # jezykowy/Job Interview/Webinar (juz w VARIANT), MultiSelect bo
            # "w jednej ofercie moze byc kilka roznych" produktow naraz
            {"title": "product_type", "type": "MultiSelect", "options": select(*VARIANT)},
            {"title": "version", "type": "Number"},
            {"title": "template_name", "type": "SingleLineText"},
            {"title": "file", "type": "Attachment"},
            # feedback-tables-1.md: brakowalo opisu co tu wpisywac
            {"title": "data_json", "type": "LongText",
             "description": "Zamrozony zrzut danych (JSON), z ktorych "
                            "zostal wygenerowany ten dokument - realizacja "
                            "wymogu 'historia ofert'. Zapisywane AUTOMATYCZNIE "
                            "przez automatyzacje przy generowaniu pliku - nie "
                            "edytowac recznie."},
            {"title": "warnings", "type": "LongText",
             "description": "Ostrzezenia zwrocone automatycznie przez usluge "
                            "generujaca plik oferty (np. brakujace dane w "
                            "szablonie). Zapisywane AUTOMATYCZNIE - nie "
                            "edytowac recznie."},
            {"title": "sent_at", "type": "Date"},
            {"title": "valid_until", "type": "Date"},
        ],
    },
    {
        "title": "document_templates",
        "description": "Biblioteka szablonow (.pptx/.docx). v3 §12: uogolnione "
                       "z `offer_templates`, bo renderer jest generyczny i "
                       "obsluzy tez raport audytowy. n8n bierze najnowszy "
                       "rekord z active=true I pasujacym `kind`.",
        "fields": [
            {"title": "name", "type": "SingleLineText"},
            {"title": "kind", "type": "SingleSelect",
             "options": select("offer", "audit_report", "inne")},
            {"title": "file", "type": "Attachment"},
            {"title": "active", "type": "Checkbox", "default_value": False},
            {"title": "notes", "type": "LongText"},
        ],
    },
    {
        "title": "testimonials",
        "description": "Biblioteka referencji - analityk linkuje z biblioteki "
                       "zamiast wklejac do oferty, wiec ta sama referencja jest "
                       "reuzywalna i wiadomo, gdzie byla uzyta.",
        "fields": [
            {"title": "title", "type": "SingleLineText"},
            {"title": "client_name", "type": "SingleLineText"},
            # v3 §9 - szablon PPTX uzywa {{testimonial.position}}
            {"title": "position", "type": "SingleLineText"},
            {"title": "industry", "type": "SingleSelect", "options": select(*INDUSTRY)},
            {"title": "type", "type": "SingleSelect",
             "options": select("testimonial", "case_study")},
            {"title": "content", "type": "LongText"},
            {"title": "variant", "type": "MultiSelect",
             "options": select("business_english", "english_for_it",
                               "english_business_skills")},
            {"title": "active", "type": "Checkbox", "default_value": True},
        ],
    },
    {
        "title": "projects",
        "description": "Prosty slownik projektow dla taskow.",
        "fields": [
            {"title": "name", "type": "SingleLineText"},
            {"title": "team", "type": "SingleSelect",
             "options": select("marketing", "sales", "ops")},
            {"title": "active", "type": "Checkbox", "default_value": True},
        ],
    },
    {
        "title": "task_templates",
        "description": "Czytane wylacznie przez cron w n8n (W1) - triggery CRON "
                       "w NocoDB CE sa platne, stad n8n.",
        "fields": [
            {"title": "title", "type": "SingleLineText"},
            {"title": "assignee", "type": "User"},
            {"title": "rrule", "type": "SingleLineText"},
            {"title": "due_offset_days", "type": "Number"},
            {"title": "description", "type": "LongText"},
            {"title": "active", "type": "Checkbox", "default_value": True},
        ],
    },
    {
        "title": "tasks",
        "description": "JEDNA tabela dla calej firmy - warunek dzialania widokow "
                       "'moje taski ze wszystkich projektow'.",
        "fields": [
            {"title": "title", "type": "SingleLineText"},
            {"title": "assignee", "type": "User"},
            {"title": "due_date", "type": "Date"},
            {"title": "status", "type": "SingleSelect",
             "options": select("todo", "in_progress", "done", "cancelled")},
            {"title": "priority", "type": "SingleSelect",
             "options": select("low", "normal", "high")},
            {"title": "description", "type": "LongText"},
            {"title": "created_by_flow", "type": "SingleLineText"},
        ],
    },
    {
        "title": "activities",
        "description": "Log zdarzen, append-only - pisze WYLACZNIE n8n, ludzie "
                       "tu tylko czytaja. Timeline leada + debug automatow.",
        "fields": [
            {"title": "summary", "type": "SingleLineText"},
            {"title": "type", "type": "SingleSelect",
             "options": select("lead_created", "stage_changed", "task_created",
                               "task_completed", "meeting_created",
                               "transcript_added", "ai_analysis_done",
                               "ai_accepted", "goals_provided",
                               "testimonials_provided", "offer_draft_ready",
                               "company_match_suggested", "notification_sent",
                               "automation_error")},
            {"title": "triggered_by", "type": "SingleLineText"},
            {"title": "flow", "type": "SingleLineText"},
            {"title": "payload", "type": "LongText"},
        ],
    },
]

# (tabela-wlasciciel pola, tytul pola, relation_type, tabela-cel)
# "hm" (has-many) deklarujemy po stronie "jeden" - NocoDB samo dokleja pole
# zwrotne (belongs-to) po drugiej stronie; jego nazwy NIE da sie tu narzucic,
# bo nie jest udokumentowana - zweryfikuj w UI.
# "mm" (many-to-many) tam, gdzie obie strony moga miec wiele.
RELATIONS = [
    # --- firma
    ("companies", "leads", "hm", "leads"),
    ("companies", "participants", "hm", "participants"),
    # --- lead jako centrum
    ("leads", "participants", "hm", "participants"),
    ("leads", "meetings", "hm", "meetings"),
    ("leads", "tasks", "hm", "tasks"),
    ("leads", "activities", "hm", "activities"),
    ("leads", "offers", "hm", "offers"),
    ("leads", "selected_testimonials", "mm", "testimonials"),
    # self-link: sugestia duplikatu (W5/W4v2 nigdy nie scala automatycznie)
    ("leads", "possible_duplicate", "mm", "leads"),
    # --- trzy poziomy merytoryczne (v3 "Architektura tabel")
    ("participants", "assessments", "hm", "assessments"),
    ("participants", "recommendations", "hm", "recommendations"),
    ("participants", "meetings", "mm", "meetings"),
    ("meetings", "assessments", "hm", "assessments"),
    ("recommendations", "packages", "hm", "recommendation_packages"),
    ("training_descriptions", "recommendation_packages", "hm", "recommendation_packages"),
    # --- log
    ("meetings", "activities", "hm", "activities"),
    ("tasks", "activities", "hm", "activities"),
    # --- taski
    ("projects", "tasks", "hm", "tasks"),
    ("projects", "task_templates", "hm", "task_templates"),
    ("task_templates", "tasks", "hm", "tasks"),
]


# --------------------------------------------------------- v3 -> v2 translacja
# Definicje TABLES wyzej sa pisane w czytelnym stylu v3 (type/options), bo
# stanowia dokumentacje modelu. API v2 chce czego innego - stad ta warstwa.
_UIDT = {"SingleLineText", "LongText", "Email", "PhoneNumber", "URL", "Number",
         "Date", "DateTime", "Checkbox", "SingleSelect", "MultiSelect",
         "Currency", "User", "Attachment"}


def to_v2_column(f):
    """Pole w stylu v3 -> kolumna w kontrakcie v2.

    `description` (field description widoczny w NocoDB UI pod ikonką "i" przy
    nazwie pola) - NIEZWERYFIKOWANE NA ŻYWO w tej sesji (brak dostepnej
    instancji), tylko udokumentowana funkcja NocoDB. Po uruchomieniu sprawdz
    w UI, czy opis faktycznie sie zapisal - jesli API po cichu go ignoruje,
    trzeba bedzie dopisac opisy recznie.
    """
    t = f["type"]
    assert t in _UIDT, f"nieznany typ pola: {t}"
    col = {"title": f["title"], "column_name": f["title"], "uidt": t}
    if f.get("description"):
        col["description"] = f["description"]
    opts = f.get("options") or {}
    if t in ("SingleSelect", "MultiSelect"):
        # v2 trzyma opcje jako 'a','b','c' w jednym polu dtxp, nie jako liste
        col["dtxp"] = ",".join("'%s'" % c["title"] for c in opts["choices"])
    elif t == "Currency":
        col["meta"] = {"currency_locale": opts.get("locale", "en-US"),
                       "currency_code": opts.get("code", "USD")}
    elif t == "Checkbox" and f.get("default_value"):
        col["cdf"] = "true"
    return col


def to_v2_table(t):
    return {"title": t["title"], "table_name": t["title"],
            "columns": [to_v2_column(f) for f in t["fields"]]}


def existing_tables():
    return {t["title"].strip().lower(): t["id"]
            for t in api("GET", f"/api/v2/meta/bases/{BASE_ID}/tables").get("list", [])}


def existing_fields(table_id):
    return {c["title"].strip().lower()
            for c in api("GET", f"/api/v2/meta/tables/{table_id}").get("columns", [])}


def create_tables(dry_run, source_id):
    # --dry-run ma dzialac takze bez dzialajacej instancji (na produkcji to
    # pierwsza rzecz, ktora odpalasz - zanim cokolwiek stoi). Gdy instancja
    # JEST osiagalna, i tak sprawdzamy, co juz istnieje.
    if dry_run:
        try:
            tables = existing_tables()
        except SystemExit:
            print("(instancja nieosiagalna - zakladam pusta baze)\n")
            tables = {}
    else:
        tables = existing_tables()
    ids = dict(tables)
    for t in TABLES:
        key = t["title"].lower()
        if key in tables:
            print(f"=  {t['title']}: juz istnieje (Id={tables[key]}), pomijam")
            continue
        print(f"+  {t['title']}: tworze ({len(t['fields'])} pol)")
        if dry_run:
            ids[key] = f"<{t['title']}>"
            continue
        # Zrodlo jako segment SCIEZKI - jedyna forma, ktora dziala.
        # Zweryfikowane na zywo 2026-08-03: `source_id` w ciele zadania (v3)
        # jest po cichu IGNOROWANE i tabele ladowaly w bazie `nocodb`.
        ids[key] = api("POST", f"/api/v2/meta/bases/{BASE_ID}/{source_id}/tables",
                       json=to_v2_table(t))["id"]
    return ids


def create_relations(ids, dry_run):
    for owner, field_title, rel_type, target in RELATIONS:
        owner_id, target_id = ids.get(owner), ids.get(target)
        if not owner_id or not target_id:
            print(f"!  pomijam {owner}.{field_title} -> {target}: brak id tabeli "
                  f"({owner}={owner_id}, {target}={target_id})")
            continue
        if not dry_run and field_title.lower() in existing_fields(owner_id):
            print(f"=  {owner}.{field_title}: pole juz istnieje, pomijam")
            continue
        print(f"+  {owner}.{field_title} --{rel_type}--> {target}")
        if dry_run:
            continue
        # v2: kolumna Links tworzona na tabeli-wlascicielu; relacja opisana
        # przez parentId/childId/type, nie przez options.related_table_id.
        api("POST", f"/api/v2/meta/tables/{owner_id}/columns", json={
            "uidt": "Links",
            "title": field_title,
            "column_name": field_title,
            "type": rel_type,
            "parentId": owner_id,
            "childId": target_id,
        })


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="pokaz plan, nie wywoluj API")
    args = ap.parse_args()

    print(f"NocoDB: {URL}, base: {BASE_ID}"
          f"{' [DRY RUN]' if args.dry_run else ''}")
    if args.dry_run and not SOURCE_ID:
        source_id = "<zrodlo-appdata>"
        print("źródło: wykryję przy realnym uruchomieniu (GET .../sources)\n")
    else:
        source_id = resolve_source()
        print()
    print(f"--- tabele ({len(TABLES)}) ---")
    ids = create_tables(args.dry_run, source_id)
    print(f"\n--- relacje ({len(RELATIONS)}) ---")
    create_relations(ids, args.dry_run)
    print("\nSPRAWDŹ NAJPIERW: czy tabele powstały w appdata, a nie w bazie NocoDB:")
    print("  docker exec docker-postgres-1 psql -U postgres -d appdata \\")
    print("    -c \"\\dt crm.*\"")
    print("Jeśli ich tam nie ma, a są widoczne w UI - poszły do wewnętrznej bazy")
    print("NocoDB (patrz resolve_source() w tym pliku); usuń je i popraw source_id.")
    print("\nDo wyklikania recznie (patrz naglowek skryptu):")
    print("  1. Pola Button: offers 'generuj oferte', meetings 'generuj analize',")
    print("     assessments 'generuj needs summary' - po imporcie workflowow.")
    print("  2. Widoki: Kanban po leads.stage, Calendar po tasks.due_date,")
    print("     'moje taski' per osoba (patrz nocodb_crm_schema_v2.md).")
    print("  3. Sprawdz display value kazdej tabeli i nazwy pol zwrotnych relacji.")
