#!/usr/bin/env python3
r"""Tworzy CAŁY schemat CRM (17 tabel + relacje) w pustej bazie NocoDB przez
Meta API v3 — pod wdrożenie produkcji od zera.

Źródło prawdy: `docs/archive/fable/nocodb_crm_schema_v3.md` (decyzje projektowe i tabele
nowe/zmienione) + `docs/archive/fable/nocodb_crm_schema_v2.md` (pola tabel bazowych, których
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
`docs/archive/fable/W9_generate_offer.json`, node "Assemble render data"). Relacje `mm`
dostają tabelę łączącą od razu. TODO: znaleźć parametr API wymuszający nowy
typ od razu — inaczej ten sam klikany krok wraca przy każdym odtworzeniu.

GDZIE LĄDUJĄ TABELE (najważniejsze): baza NocoDB ma domyślne źródło = własna
baza metadanych NocoDB (`NC_DB`, czyli `nocodb`). `appdata` musi być podpięta
jako OSOBNE źródło (external Postgres source, alias np. "appdata (crm)",
searchPath ["crm"]) — RĘCZNIE przez NocoDB UI, patrz docs/hard-reset.md
Krok 0. Bez wskazania `source_id` tabele powstają w bazie `nocodb` — poza
źródłem prawdy, poza `make backup` i poza zasięgiem `n8n_crm_user`. Skrypt
wykrywa zewnętrzne źródło automatycznie (`resolve_source()`); override:
`NC_CRM_SOURCE_ID`. WYMÓG: źródło musi już istnieć w bazie PRZED tym
skryptem — inaczej nie ma czego wykryć. Po uruchomieniu zweryfikuj w
Postgresie (`\dt crm.*`), nie tylko w UI.

Alternatywa, której świadomie tu nie wybrano: napisać te 17 tabel jako
ręcznie utrzymywany SQL DDL i puścić go przez psql + `meta-diff/apply`.
Byłoby deterministyczne i wersjonowane w gicie, ale kolumny `Links` to nie
czysty SQL — NocoDB trzyma dla nich własne metadane (i tabele `_nc_m2m_*`),
więc po samym SQL-u relacje trzeba by i tak odtwarzać w NocoDB. Stąd API.

CZEGO TEN SKRYPT NIE ROBI (do wyklikania ręcznie po uruchomieniu):
  1. Dokończenia pól typu Button (`offers` "generuj ofertę", `meetings`
     "Generuj analizę", `assessments` "Generuj needs summary", `testimonials`
     "generuj slajd" i "generuj obrazek") — create_buttons() tworzy je już
     jako placeholder akcji "Open URL" z formułą `NOW()` (nie wymaga
     webhooka), bo akcja "Run Webhook" wymaga ID istniejącego webhooka
     n8n, którego przed importem workflowów jeszcze nie ma. Po imporcie
     workflowów: otwórz pole w UI, zmień akcję na "Run Webhook", wklej
     webhook.
  2. Widoków (Kanban/Calendar/Grid per osoba) — patrz v2 "Widoki".
  3. Nazw pól zwrotnych, które NocoDB samo nadaje dla relacji `hm` — nie są
     udokumentowane, sprawdź i popraw w UI.
  4. Display value: NocoDB bierze pierwsze pole z listy — dlatego w każdej
     tabeli pole "nazwowe" jest pierwsze. Zweryfikuj w UI.
  5. ZMIANY NA JUŻ WDROŻONEJ BAZIE (patrz `docs/archive/fable/feedback-tables-1.md`,
     nałożone na TABLES/RELATIONS 2026-08-06): `create_tables()` pomija CAŁĄ
     tabelę, jeśli tytuł już istnieje — nie ma diffa na poziomie pojedynczego
     pola. Jeśli baza z 16 tabelami już żyje w produkcji, ponowne uruchomienie
     tego skryptu NIE przemianuje `recommendation_items`→`recommendation_packages`,
     `training_modules`→`training_descriptions`, ani nie dopisze nowych
     opcji do istniejących SingleSelect/description — te tabele po prostu
     zostaną pominięte jako "już istnieje". Zmiany trzeba nanieść ręcznie w
     UI NocoDB (rename tabeli/pola zachowuje Id i dane) albo osobnym
     skryptem migracyjnym (PATCH po Id). Ten sam problem dotyczy zmian z
     2026-08-11 (cennik.xlsx): nowe pola dopisane do `pricing` (segment,
     rabat, bonusowe godziny, ceny za h) NIE powstaną same na już wdrożonej
     tabeli `pricing` — dodaj je ręcznie w UI, dokładnie pod tymi nazwami i
     typami co w TABLES niżej. Tabela `package_variants` jest NOWA (tytuł
     jeszcze nie istnieje), więc ją `make init-schema` utworzy automatycznie
     — tak samo relację `offers`↔`pricing` (RELATIONS, mm).
     TABLES/RELATIONS niżej to teraz
     aktualny stan docelowy, nie automatyczny diff.

Idempotentny: tabele i pola-relacje o istniejącym tytule są pomijane.

Wymaga w środowisku (patrz .env.example): NC_API_TOKEN, NC_CRM_BASE_ID.
Opcjonalnie NC_LOCAL_URL (domyślnie http://localhost:8081), NC_CRM_SOURCE_ID
(override dla resolve_source()). NOCODB_CRM_USER/NOCODB_CRM_PASSWORD/APP_DB
sluza tylko do zbudowania connection stringa w komunikacie bledu, gdy nawet
listy zrodel nie da sie odczytac (ani v3, ani v2) - patrz resolve_source().

Usage:
  make init-schema
  # albo bezpośrednio:
  set -a; source .env; set +a
  python3 scripts/init-schema.py --dry-run
  python3 scripts/init-schema.py
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
# Uzywane tylko do zbudowania connection stringa w komunikacie bledu resolve_source(),
# gdy nawet listy zrodel nie da sie odczytac - patrz tam.
APP_DB = os.environ.get("APP_DB", "appdata")
NOCODB_CRM_USER = os.environ.get("NOCODB_CRM_USER")
NOCODB_CRM_PASSWORD = os.environ.get("NOCODB_CRM_PASSWORD")

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
    (`NC_DB`, czyli `nocodb`). `appdata` musi być podpięta jako OSOBNE źródło
    (ręcznie przez UI: alias np. "appdata (crm)", type pg,
    searchPath ["crm"] — patrz docs/hard-reset.md Krok 0). Tworzenie tabel
    bez wskazania source_id ląduje w bazie `nocodb` zamiast w `appdata` -
    czyli poza źródłem prawdy, poza `make backup` i poza zasięgiem
    `n8n_crm_user`.
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
    if NOCODB_CRM_USER and NOCODB_CRM_PASSWORD:
        conn_str = (f"postgresql://{NOCODB_CRM_USER}:{NOCODB_CRM_PASSWORD}"
                    f"@postgres:5432/{APP_DB}")
        conn_hint = (f"Wklej ten connection string w NocoDB UI (Base → Data "
                     f"Sources → New → Postgres → Connection String), a Schema "
                     f"ustaw recznie na `crm` (nie wchodzi w connection string):\n"
                     f"  {conn_str}\n")
    else:
        conn_hint = ("Brak NOCODB_CRM_USER / NOCODB_CRM_PASSWORD w środowisku - "
                     "nie moge zbudowac connection stringa. Podepnij zrodlo "
                     "recznie w NocoDB UI (Host=postgres Port=5432 "
                     f"Database={APP_DB} Schema=crm, "
                     "User/Password = NOCODB_CRM_USER / NOCODB_CRM_PASSWORD z .env).\n")
    sys.exit("Nie moge odczytac listy zrodel bazy (ani v3, ani v2).\n" + conn_hint +
             "Po podpieciu zrodla w UI odczytaj jego id (Base → Data Sources) "
             "i podaj jako NC_CRM_SOURCE_ID w .env, potem uruchom ponownie.")


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
# cennik.xlsx (2026-08-11) kolumna "Liczba kursow" - prog wolumenowy klienta
# (ile kursow juz kupil), rozne stawki w pricing wg wielkosci wspolpracy.
CUSTOMER_SEGMENT = ("A) <10", "B) 10-19", "C) >19")


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


# testimonials 2026-08-11: import 140+ referencji z pptx klienta + generowanie
# per-testimonial slajdu i jego zrzutu do obrazka. Inny cykl niz ai_status_field
# (tam: szkic -> akceptacja czlowieka; tu: pojedyncze zdarzenie "wygeneruj
# plik", stad osobna, prostsza lista statusow). Dwa niezalezne kroki (slajd,
# potem obrazek) => prefiksowane pola, bo NocoDB nie pozwoli na dwa pola
# "n8n_status" w jednej tabeli.
GEN_STATUS = ("generating", "done", "error")


def gen_status_field(prefix, action):
    return {"title": f"{prefix}_status", "type": "SingleSelect",
            "options": select(*GEN_STATUS),
            "description": f'Status automatyzacji n8n po kliknieciu "{action}": '
                           f'generating (w trakcie) -> done (gotowe) -> error '
                           f'(szczegoly w {prefix}_note).'}


def gen_note_field(prefix, action):
    return {"title": f"{prefix}_note", "type": "LongText",
            "description": f'Blad zwrocony przez n8n przy "{action}" - '
                           f'wypelniane tylko gdy {prefix}_status = error.'}


# --------------------------------------------------------------- definicje tabel
# Kolejność pól ma znaczenie: pierwsze pole zostaje display value.
TABLES = [
    {
        "title": "companies",
        "icon": "🏢",
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
        "icon": "🎯",
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
            # feedback-tables-1.md/init v2 zakladaly "hot"/"oferta_specjalna",
            # ale realna taksonomia "Szansa sprzedaży Etykieta" ze starego CRM
            # (generate_crm_data.py DEAL_LABELS) to zupelnie inna lista -
            # dopisana ponizej, stare dwie opcje zostaja (nieszkodliwe, na
            # wypadek gdyby juz cos ich uzywalo z proby na stagingu).
            {"title": "label", "type": "SingleSelect",
             "options": select("hot", "oferta_specjalna", "Nowy klient", "Upsell",
                               "Odnowienie", "Projekt jednorazowy", "Abonament",
                               "Pilne")},
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
            # Number, nie SingleLineText - inaczej sortowanie/porownania sa
            # leksykograficzne (a-z), np. "1000" < "999".
            {"title": "legacy_id", "type": "Number"},
        ],
    },
    {
        "title": "participants",
        "icon": "🧑‍🎓",
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
        "icon": "👋",
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
        "icon": "📝",
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
        "icon": "🧭",
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
        "icon": "📚",
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
        "icon": "📦",
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
        "icon": "💰",
        "description": "Cennik wersjonowany, jeden wiersz = jedna kombinacja "
                       "segment x hours x tryb. `product` == "
                       "offers.product_type, `training_group_size` == "
                       "recommendation_packages.training_group_size (wspolne "
                       "stale w skrypcie: VARIANT / MODE). cennik.xlsx "
                       "(2026-08-11): rozszerzone o pelna strukture cen z "
                       "arkusza klientki (segment, rabat, bonusowe godziny, "
                       "ceny za h) - patrz opisy pol nizej; offers.pricing "
                       "(RELATIONS, mm) linkuje oferte do konkretnego wiersza "
                       "uzytego przy total_price - v3 zakladalo brak relacji "
                       "do ofert, to swiadoma zmiana wobec tamtego zapisu.",
        "fields": [
            # feedback-tables-1.md: segment -> product
            {"title": "product", "type": "SingleSelect", "options": select(*VARIANT)},
            # cennik.xlsx kolumna "Liczba kursow"
            {"title": "customer_segment", "type": "SingleSelect",
             "options": select(*CUSTOMER_SEGMENT),
             "description": "Prog wolumenowy klienta wg liczby wczesniej "
                            "zakupionych kursow (cennik.xlsx 'Liczba "
                            "kursow'). Wplywa na stawke w tym wierszu."},
            # feedback-tables-1.md: mode -> Training_Group_Size
            {"title": "training_group_size", "type": "SingleSelect", "options": select(*MODE)},
            {"title": "hours", "type": "Number"},
            # cennik.xlsx kolumna "Kontynuacja czy nowy kurs?" - caly
            # dostarczony arkusz dotyczyl wylacznie kontynuacji; pole
            # zostawione, zeby przyszly cennik dla nowych kursow mogl zyc w
            # tej samej tabeli zamiast w kolejnej rownoleglej.
            {"title": "course_type", "type": "SingleSelect",
             "options": select("kontynuacja", "nowy_kurs"),
             "description": "Czy stawka dotyczy kontynuacji istniejacego "
                            "kursu, czy nowego kursu od zera (cennik.xlsx "
                            "'Kontynuacja czy nowy kurs?')."},
            {"title": "continuation_bonus_hours", "type": "Number",
             "description": "Dodatkowe godziny doliczane przy kontynuacji "
                            "(cennik.xlsx 'Dodatkowe godziny za "
                            "kontynuacje')."},
            {"title": "upfront_payment_bonus", "type": "Checkbox", "default_value": False,
             "description": "Czy klient dostaje dodatkowa godzine za "
                            "platnosc z gory (cennik.xlsx 'Dodatkowa h za "
                            "platnosc z gory')."},
            # feedback-tables-1.md: price -> total_price (vs hourly price)
            {"title": "total_price", "type": "Currency",
             "options": {"locale": "pl-PL", "code": "PLN"},
             "description": "Standardowa cena za pakiet, przed rabatem "
                            "(cennik.xlsx 'Standardowa cena za pakiet')."},
            {"title": "discounted_price", "type": "Currency",
             "options": {"locale": "pl-PL", "code": "PLN"},
             "description": "Cena po rabacie, np. za platnosc z gory "
                            "(cennik.xlsx 'Po rabacie')."},
            {"title": "hours_with_bonus", "type": "Number",
             "description": "Laczna liczba godzin w pakiecie po doliczeniu "
                            "bonusow (cennik.xlsx 'Wielkosc pakietu z "
                            "bonusowymi h')."},
            {"title": "price_per_hour", "type": "Currency",
             "options": {"locale": "pl-PL", "code": "PLN"},
             "description": "cennik.xlsx 'Cena za godzine'."},
            {"title": "group_size", "type": "Number",
             "description": "Liczba osob w grupie dla tego wiersza (1 "
                            "indywidualnie, 2 w parach, 4 grupowo) - "
                            "cennik.xlsx 'Liczba osob w grupie'."},
            {"title": "price_per_hour_per_person", "type": "Currency",
             "options": {"locale": "pl-PL", "code": "PLN"},
             "description": "cennik.xlsx 'Cena za godzine za osobe'."},
            {"title": "price_per_hour_with_bonus", "type": "Currency",
             "options": {"locale": "pl-PL", "code": "PLN"},
             "description": "cennik.xlsx 'Cena za h z bonusami'."},
            {"title": "price_per_hour_per_person_with_bonus", "type": "Currency",
             "options": {"locale": "pl-PL", "code": "PLN"},
             "description": "cennik.xlsx 'Cena za h za osobe z bonusami'."},
            {"title": "valid_from", "type": "Date"},
            {"title": "valid_to", "type": "Date"},
        ],
    },
    {
        "title": "package_variants",
        "icon": "🎁",
        "description": "Katalog gotowych pakietow (Business English, English "
                       "for IT, English + Business Skills: ..., Job "
                       "Interview) do krotkich opisow na slajdzie 'NASZA "
                       "REKOMENDACJA' (warianty_slajd_4.txt, 2026-08-11). "
                       "Inny byt niz training_descriptions: to gotowy "
                       "PRODUKT pokazywany klientowi na slajdzie "
                       "rekomendacji, nie pojedynczy modul do skladania "
                       "sciezki ETAP 1/ETAP 2.",
        "fields": [
            {"title": "name", "type": "SingleLineText"},
            {"title": "short_description", "type": "LongText",
             "description": "Kilkuzdaniowy opis pakietu na slajd 'NASZA "
                            "REKOMENDACJA' - {{package.shortdescription}}."},
            {"title": "default_hours", "type": "Number",
             "description": "Domyslna/typowa liczba godzin pakietu - "
                            "{{package.hours}}."},
            {"title": "lesson_frequency", "type": "Number",
             "description": "Ile zajec tygodniowo w typowym harmonogramie - "
                            "{{lessonfrequency}}."},
            {"title": "lesson_minutes", "type": "Number",
             "description": "Dlugosc pojedynczych zajec w minutach - "
                            "{{lesson.minutes}}."},
            {"title": "active", "type": "Checkbox", "default_value": True},
        ],
    },
    {
        "title": "offers",
        "icon": "📄",
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
        "icon": "🗂️",
        "description": "Biblioteka szablonow (.pptx/.docx). v3 §12: uogolnione "
                       "z `offer_templates`, bo renderer jest generyczny i "
                       "obsluzy tez raport audytowy. n8n bierze najnowszy "
                       "rekord z active=true I pasujacym `kind`.",
        "fields": [
            {"title": "name", "type": "SingleLineText"},
            {"title": "kind", "type": "SingleSelect",
             "options": select("offer", "audit_report", "testimonial_slide", "inne")},
            {"title": "file", "type": "Attachment"},
            {"title": "active", "type": "Checkbox", "default_value": False},
            {"title": "notes", "type": "LongText"},
        ],
    },
    {
        "title": "testimonials",
        "icon": "💬",
        "description": "Biblioteka referencji - analityk linkuje z biblioteki "
                       "zamiast wklejac do oferty, wiec ta sama referencja jest "
                       "reuzywalna i wiadomo, gdzie byla uzyta. 2026-08-11: "
                       "rozszerzone pod import 140+ referencji z pliku pptx "
                       "klienta, plus generowanie per-testimonial slajdu "
                       "(szablon w document_templates, kind=testimonial_slide) "
                       "i jego zrzutu do obrazka - patrz slide_*/image_* nizej.",
        "fields": [
            {"title": "title", "type": "SingleLineText"},
            {"title": "client_name", "type": "SingleLineText"},
            # v3 §9 - szablon PPTX uzywa {{testimonial.position}}
            {"title": "position", "type": "SingleLineText"},
            {"title": "type", "type": "SingleSelect",
             "options": select("testimonial", "case_study")},
            {"title": "content", "type": "LongText"},
            {"title": "translation", "type": "LongText"},
            {"title": "variant", "type": "MultiSelect",
             "options": select("business_english", "english_for_it",
                               "english_business_skills")},
            # klient (2026-08-11): brak dzis ustalonej listy person/tematow -
            # wolny tekst, zamienic na SingleSelect gdy pojawi sie kanoniczna
            # lista wartosci (jak przy INDUSTRY).
            {"title": "buyer_persona", "type": "SingleLineText"},
            {"title": "refers_to", "type": "SingleLineText"},
            # klient: "Czy mozemy uzywac (SM, www, ofertowanie, zdjecie z
            # nazwiskiem, nazwa firmy)" - realne dane w tej kolumnie (sprawdzone
            # 2026-08-11 na dostarczonym xlsx) to NIE lista kanalow, tylko
            # mieszanka TAK / puste / "-" / "???" i pelnych zdan z zastrzezeniami
            # ("jedynie do ofert", "to nie jest nasz student", linki). SingleSelect
            # (nie MultiSelect - yes/no/partially wykluczaja sie wzajemnie).
            {"title": "usage_consent", "type": "SingleSelect",
             "options": select("yes", "no", "partially"),
             "description": "Czy mozna uzywac tej referencji (SM, www, "
                            "ofertowanie, zdjecie z nazwiskiem, nazwa firmy) - "
                            "ogolna klasyfikacja. Szczegoly/zastrzezenia "
                            "(np. 'jedynie do ofert') w usage_limitations."},
            {"title": "usage_limitations", "type": "LongText",
             "description": "Pelny, surowy tekst zrodlowej kolumny zgody - "
                            "zastrzezenia, konteksty, linki, ktorych "
                            "usage_consent (yes/no/partially) nie odda."},
            {"title": "in_source_pptx", "type": "Checkbox", "default_value": False,
             "description": "Zaznaczone, jesli ta referencja byla juz obecna "
                            "jako gotowy slajd w pliku pptx dostarczonym "
                            "przez klienta (zamiast bycia tylko tekstem)."},
            {"title": "notes", "type": "LongText"},
            {"title": "company_logo", "type": "Attachment"},
            {"title": "avatar", "type": "Attachment"},
            {"title": "slide_file", "type": "Attachment",
             "description": "Wygenerowany pojedynczy slajd pptx (przycisk "
                            "'generuj slajd'). Czlowiek sprawdza, moze "
                            "poprawic i nadpisac tym polem przed kliknieciem "
                            "'generuj obrazek'."},
            gen_status_field("slide", "generuj slajd"),
            gen_note_field("slide", "generuj slajd"),
            {"title": "image", "type": "Attachment",
             "description": "Zrzut slide_file do obrazka - wynik przycisku "
                            "'generuj obrazek'."},
            gen_status_field("image", "generuj obrazek"),
            gen_note_field("image", "generuj obrazek"),
            {"title": "active", "type": "Checkbox", "default_value": True},
        ],
    },
    {
        "title": "projects",
        "icon": "🚀",
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
        "icon": "🔁",
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
        "icon": "✅",
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
        "icon": "📜",
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
    # jedna opinia = jedna osoba w jednej firmie w danym momencie - hm, nie mm
    # (jak wyzej: wiele testimoniali moze naleziec do jednej firmy, ale nie
    # odwrotnie). industry/size czytane przez link, nie duplikowane na testimonials.
    ("companies", "testimonials", "hm", "testimonials"),
    # --- lead jako centrum
    ("leads", "participants", "hm", "participants"),
    ("leads", "meetings", "hm", "meetings"),
    ("leads", "tasks", "hm", "tasks"),
    ("leads", "activities", "hm", "activities"),
    ("leads", "offers", "hm", "offers"),
    # self-link: sugestia duplikatu (W5/W4v2 nigdy nie scala automatycznie)
    ("leads", "possible_duplicate", "mm", "leads"),
    # --- wybor szablonu i testimoniali per oferta: to samo rozumowanie co
    # przy price/hours/template - jeden lead moze miec wiele ofert (wersji),
    # wiec to co rozni sie per-oferta zyje na offers, nie na leads.
    # `document_templates.active` zostaje jako podpowiedz dla czlowieka ("ten
    # szablon jest aktualny"), W9 juz go NIE uzywa do wyboru - czyta wprost
    # link z offers (patrz W9 "Get offer template").
    ("document_templates", "offers", "hm", "offers"),
    # przeniesione z leads (byla tam do 2026-08-10) - dwie oferty dla tego
    # samego leada moga chciec innych referencji w wygenerowanym dokumencie.
    ("offers", "selected_testimonials", "mm", "testimonials"),
    # cennik.xlsx (2026-08-11): offers.product_type jest juz MultiSelect
    # ("w jednej ofercie moze byc kilka roznych produktow naraz"), wiec
    # jedna oferta moze objac kilka wierszy cennika (np. rozny hours/tryb
    # per produkt) - stad mm, nie hm. Kazdy link wskazuje wiersz pricing,
    # z ktorego wzieta zostala kwota w offers.total_price.
    ("offers", "pricing", "mm", "pricing"),
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

# Placeholdery dla 5 pol Button, ktorych ten skrypt swiadomie nie tworzy w
# pelni (patrz naglowek, "CZEGO TEN SKRYPT NIE ROBI" #1) - akcja "Run
# Webhook" wymaga ID istniejacego webhooka n8n, ktorego przed importem
# workflowow jeszcze nie ma. Zamiast zostawiac te pola do recznego
# stworzenia od zera, create_buttons() nizej tworzy je juz teraz jako
# Button/"Open URL" z formula NOW() (placeholder, niewymagajacy webhooka ani
# referencji do innych pol) - po imporcie workflowow zostaje tylko otworzyc
# pole w UI i przelaczyc akcje na "Run Webhook". Etykiety 1:1 z tekstem juz
# obecnym w opisach pol (ai_status_field/gen_status_field), zeby "kliknij
# przycisk X" w opisie wskazywalo na pole o tej samej nazwie.
BUTTONS = [
    ("offers", "generuj ofertę"),
    ("meetings", "Generuj analizę"),
    ("assessments", "Generuj needs summary"),
    ("testimonials", "generuj slajd"),
    ("testimonials", "generuj obrazek"),
]

BUTTON_PLACEHOLDER_NOTE = (
    'PLACEHOLDER utworzony przez init-schema.py: akcja "Open URL" z formula '
    'NOW() (nieuzywana, tylko zeby pole bylo poprawne). Po imporcie '
    'workflowa n8n: otworz to pole w UI, zmien akcje na "Run Webhook", '
    'wybierz/wklej wlasciwy webhook, zapisz.'
)


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
        # ZWERYFIKOWANE NA ŻYWO 2026-08-09: `dtxp` (styl MySQL ENUM) tworzy
        # pole poprawnego typu, ale na źródle Postgres jest po cichu
        # IGNOROWANY - kolumna powstaje z PUSTĄ listą opcji w UI. Zostawiony
        # tu jako nieszkodliwy no-op (na wypadek innego typu źródła); realne
        # opcje ustawia dopiero sync_select_options() niżej, osobnym
        # `PATCH .../meta/columns/{id}` z `colOptions.options`.
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


def table_columns(table_id):
    return {c["title"].strip().lower(): c
            for c in api("GET", f"/api/v2/meta/tables/{table_id}").get("columns", [])}


# Paleta kolorów opcji SingleSelect/MultiSelect - podzbiór domyślnej palety
# NocoDB, cyklicznie po indeksie opcji. `color` w colOptions.options nie jest
# udokumentowany jako opcjonalny, więc zawsze go wysyłamy - nie polegamy na
# domyślnym przypisaniu po stronie API.
SELECT_COLORS = ["#cfdffe", "#d0f1fd", "#c2f5e9", "#d4f7e0", "#ffefdb",
                  "#fee2d5", "#ffdaf6", "#ffdce5", "#eeeefe", "#e5e5e9"]


def sync_select_options(ids, dry_run):
    """Dobija opcje SingleSelect/MultiSelect osobnym PATCH-em per pole.

    ZWERYFIKOWANE NA ŻYWO 2026-08-09: `POST .../tables` z `dtxp` (patrz
    to_v2_column) tworzy te pola z pusta lista opcji na źródle Postgres -
    trzeba je dopiero uzupełnić przez `PATCH /api/v2/meta/columns/{id}`
    z `colOptions.options`. Bezwarunkowe (nie sprawdza, czy opcje już są) -
    PATCH tą samą listą jest tani i idempotentny, więc leczy też tabele
    utworzone wcześniejszym (zepsutym) przebiegiem tego skryptu.
    """
    for t in TABLES:
        table_id = ids.get(t["title"].lower())
        if not table_id:
            continue
        for f in t["fields"]:
            if f["type"] not in ("SingleSelect", "MultiSelect"):
                continue
            choices = [c["title"] for c in f["options"]["choices"]]
            print(f"~  {t['title']}.{f['title']}: {len(choices)} opcji")
            if dry_run:
                continue
            col = table_columns(table_id).get(f["title"].lower())
            if not col:
                print(f"!  {t['title']}.{f['title']}: pole nie istnieje, pomijam")
                continue
            options = [{"title": c, "color": SELECT_COLORS[i % len(SELECT_COLORS)]}
                       for i, c in enumerate(choices)]
            api("PATCH", f"/api/v2/meta/columns/{col['id']}",
                json={"colOptions": {"options": options}})


def sync_table_icons(ids, dry_run):
    """Ustawia emoji-ikonke kazdej tabeli w bocznym menu NocoDB (`TABLES[].icon`).

    Osobny, bezwarunkowy PATCH per tabela - jak sync_select_options(), NIE
    czesc to_v2_table()/create_tables(). Dwa powody: (1) create_tables()
    pomija CAŁĄ tabele, jesli tytul juz istnieje (patrz naglowek skryptu,
    "CZEGO TEN SKRYPT NIE ROBI" #5) - na juz wdrozonej produkcji (od
    2026-08-10) wszystkie 17 tabel juz istnieje, wiec ikonki inline przy
    tworzeniu nigdy by sie nie wykonaly; (2) analogiczny przypadek z dtxp w
    to_v2_column() pokazal, ze NocoDB po cichu ignoruje niektore pola przy
    bulk POST tabeli - bezpieczniej i tak zrobic to osobnym PATCH-em.

    Kontrakt NIEZWERYFIKOWANY NA ZYWO w tej sesji (brak dostepnej instancji):
    `PATCH /api/v2/meta/tables/{id}` z body `{"meta": {"icon": "<emoji>"}}`,
    surowy unicode emoji - wg zgloszenia nocodb/nocodb#13004 (Meta API v3,
    ten sam ksztalt meta.icon) i wzorca aktualizacji z nc-gui
    (`dbTable.update(tableId, {meta})`). NIE prefiks iconify (`"emojione:smile"`)
    z PR #4630 z 2022 - to stary format sprzed obecnego emoji-pickera.
    Sprawdz w UI po pierwszym uruchomieniu, czy ikonki faktycznie sie
    zapisaly.
    """
    for t in TABLES:
        icon = t.get("icon")
        table_id = ids.get(t["title"].lower())
        if not icon or not table_id:
            continue
        print(f"~  {t['title']}: {icon}")
        if dry_run:
            continue
        api("PATCH", f"/api/v2/meta/tables/{table_id}", json={"meta": {"icon": icon}})


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


def create_buttons(ids, dry_run):
    """Placeholdery Button/"Open URL" dla BUTTONS - patrz komentarz przy
    definicji listy. Osobny przebieg po utworzeniu tabel (jak
    create_relations/sync_select_options), bo bulk table-create po cichu
    ignoruje/psuje niektore rzeczy (patrz dtxp w to_v2_column) - kontrakt dla
    pojedynczego POST-a na kolumne NIEZWERYFIKOWANY NA ZYWO w tej sesji,
    sprawdz po pierwszym uruchomieniu.
    """
    for table, label in BUTTONS:
        table_id = ids.get(table)
        if not table_id:
            print(f"!  pomijam przycisk {table}.{label}: brak id tabeli ({table}={table_id})")
            continue
        if not dry_run and label.lower() in existing_fields(table_id):
            print(f"=  {table}.{label}: przycisk juz istnieje, pomijam")
            continue
        print(f"+  {table}.{label}: przycisk (placeholder Open URL / NOW())")
        if dry_run:
            continue
        api("POST", f"/api/v2/meta/tables/{table_id}/columns", json={
            "title": label,
            "column_name": label,
            "uidt": "Button",
            "type": "url",
            "formula_raw": "NOW()",
            "label": label,
            "theme": "solid",
            "color": "brand",
            "description": BUTTON_PLACEHOLDER_NOTE,
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
    print(f"\n--- ikonki tabel ---")
    sync_table_icons(ids, args.dry_run)
    print(f"\n--- relacje ({len(RELATIONS)}) ---")
    create_relations(ids, args.dry_run)
    print(f"\n--- opcje SingleSelect/MultiSelect ---")
    sync_select_options(ids, args.dry_run)
    print(f"\n--- przyciski (placeholder Open URL / NOW()) ---")
    create_buttons(ids, args.dry_run)
    print("\nSPRAWDŹ NAJPIERW: czy tabele powstały w appdata, a nie w bazie NocoDB:")
    print("  docker exec docker-postgres-1 psql -U postgres -d appdata \\")
    print("    -c \"\\dt crm.*\"")
    print("Jeśli ich tam nie ma, a są widoczne w UI - poszły do wewnętrznej bazy")
    print("NocoDB (patrz resolve_source() w tym pliku); usuń je i popraw source_id.")
    print("\nDo wyklikania recznie (patrz naglowek skryptu):")
    print("  1. Pola Button juz istnieja jako placeholder (Open URL / NOW()) -")
    print("     po imporcie workflowow otworz kazde w UI, zmien akcje na")
    print("     'Run Webhook', wklej webhook: offers 'generuj oferte', meetings")
    print("     'Generuj analize', assessments 'Generuj needs summary',")
    print("     testimonials 'generuj slajd' i 'generuj obrazek'.")
    print("  2. Widoki: Kanban po leads.stage, Calendar po tasks.due_date,")
    print("     'moje taski' per osoba (patrz nocodb_crm_schema_v2.md).")
    print("  3. Sprawdz display value kazdej tabeli i nazwy pol zwrotnych relacji.")
    print("  4. Ikonki tabel: kontrakt PATCH .../meta/tables/{id} meta.icon "
          "niezweryfikowany na zywo - sprawdz w UI, czy sie zapisaly.")
