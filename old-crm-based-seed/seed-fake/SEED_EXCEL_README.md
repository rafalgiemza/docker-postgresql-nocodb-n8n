# Seed NocoDB CRM z Excela

Migracja 1600 rekordów z **Statusy_z_CRM_filled.xlsx** do nowej bazy NocoDB.

> Zaktualizowane pod schemat po `fable/feedback-tables-1.md` (2026-08-06) —
> wymaga bazy stworzonej aktualną wersją `fable/create_offer_tables.py`
> (tabela `attendees`, nie `participants`; pola `lead_name`/`lead_type`/
> `lead_source`/`deal_value` na `leads`; nowe listy opcji `lead_source`/
> `contact_channel`/`industry`).

## Przygotowanie

1. **Uzyskaj token NocoDB**
   - Otwórz NocoDB → User menu (prawy górny róg) → Account Settings → Tokens
   - Wygeneruj nowy token
   - Wklej do `.env`:
     ```bash
     NC_API_TOKEN=<YOUR_TOKEN>
     ```

2. **Pobierz Base ID**
   - Otwórz NocoDB → twoja baza CRM
   - Z adresu URL: `https://nocodb.../nc/BASE_ID/...`
   - Wklej do `.env`:
     ```bash
     NC_CRM_BASE_ID=<BASE_ID>
     ```

3. **Opcjonalnie: URL NocoDB** (jeśli nie localhost:8081)
   ```bash
   NC_LOCAL_URL=https://back-office-coaction-test.giemza.dev
   ```

## Uruchomienie

```bash
cd old-crm-based-seed/seed-fake

# Instalacja dependencies (tylko za pierwszym razem)
pip install -r requirements.txt

# Załaduj env (z poziomu seed-fake)
set -a; source ../../.env; set +a

# Test (preview, bez zmian w bazie)
python3 seed_nocodb_from_excel.py --dry-run

# Pełna migracja
python3 seed_nocodb_from_excel.py
```

## Co się stanie

### Czytane z Excela (1600 rekordów)
- Nazwa klienta, Email, Telefon
- B2B/B2C typ, Branża, Etap, Stan
- Źródło (Google, Polecenie, LinkedIn, itd)
- Forma kontaktu (Bookings, Email, Formularz, Telefon)
- Kwalifikacja (MQL, SQL)
- Szansa sprzedaży (wartość w PLN)
- Notatki

### Tworzone w NocoDB

#### 1. **Leads** (1600 sztuk)
```
lead_name         ← Nazwa klienta
contact_email     ← E.mail
contact_phone     ← Nr telefonu
lead_type         ← B2B/B2C
lead_source       ← Źródło (mapowania: Google, Recommendation, LinkedIn...)
contact_channel   ← Forma kontaktu
qualification     ← Kwalifikacja lead'a
stage             ← Etap (mapowania: utracona→lost, umowa→contract_signed)
state             ← Stan
deal_value        ← Szansa sprzedaży (PLN)
notes             ← Notatki + wartości bez mapowania (patrz niżej)
legacy_id         ← Spr. ID (używany do dedup)
```

#### 2. **Companies** (tylko B2B)
```
name              ← Organizacja
industry          ← Branża
```
Link: `lead → company` (pole "company")

#### 3. **Attendees** (1 per lead = 1600)
```
full_name         ← Nazwa klienta (osoba kontaktowa)
email             ← E.mail
```
Link: `lead → attendee` (pole "attendees")

## Wartości bez odpowiednika w nowych listach opcji

Nowe listy `lead_source`/`contact_channel` (patrz `fable/feedback-tables-1.md`)
nie pokrywają 1:1 wszystkiego, co było w starym CRM. Tam, gdzie nie ma sensownego
odpowiednika, skrypt **nie** wciska wartości na siłę do najbliższej złej opcji —
zostawia pole puste i dopisuje oryginał ze starego CRM do `notes`, np.:
`Źródło (stary CRM): Strona www`. Dotyczy to: Źródła "Strona www"/"Kampania
Ads"/"Targi" oraz Formy kontaktu "Czat"/"Spotkanie".

## Mapowania stage'ów

| Excel | NocoDB |
|-------|--------|
| nowy lead | new |
| badanie potrzeb | audit |
| demo | discovery_done |
| oferta wysłana | offer_sent |
| omówienie oferty | offer_discussed |
| umowa wysłana | contract_sent |
| umowa podpisana | contract_signed |
| utracona | lost |
| brak kwalifikacji | new |

## Mapowania źródeł (`lead_source`)

| Excel | NocoDB |
|-------|--------|
| Google | Google |
| Polecenie | Recommendation |
| LinkedIn | LinkedIn |
| Facebook | Facebook |
| Webinar | Webinar |
| Cold mail | Outreach |
| Strona www, Kampania Ads, Targi | *(brak odpowiednika → notes)* |

## Mapowania form kontaktu (`contact_channel`)

| Excel | NocoDB |
|-------|--------|
| Bookings | Bookings |
| Formularz WWW | Formularz |
| Telefon | Telefon |
| E-mail | Mail |
| Czat, Spotkanie | *(brak odpowiednika → notes)* |

## Mapowania branż (`industry`)

| Excel | NocoDB |
|-------|--------|
| IT | IT |
| Logistyka | Transport/Logistics |
| Edukacja | Education |
| Finanse, Usługi finansowe | Finance |
| Medyczna | Medicine |
| Produkcja | Manufacturing |
| Handel | Retail |

## Bezpieczeństwo (idempotent)

- **Dedup**: Skrypt sprawdza `legacy_id` — jeśli lead już istnieje, pomija go
- **Brak duplikatów**: Można uruchomić wielokrotnie, nowe rekordy nie będą duplikowane
- **Transakcje**: Każdy rekord jest niezależny — jeśli jedno się nie uda, reszta pójdzie

## Troubleshooting

### "API error 401: Unauthorized"
- Token jest stary lub niepoprawny
- Generuj nowy w Account Settings

### "Brakuje tabel: leads, companies, attendees"
- Uruchom najpierw `python3 fable/create_offer_tables.py`
- Baza musi być już schematyzowana

### "Plik Excela nie znaleziony"
- Plik musi być w tym samym folderze: `Statusy_z_CRM_filled.xlsx`
- Uruchom skrypt z poziomu: `old-crm-based-seed/seed-fake/`

### "Link field 'company' not found"
- Tabela `leads` nie ma pola relacji "company"
- Sprawdź w UI NocoDB: Leads → Column name (szukaj Links field)
- Możliwe nazwy: "company", "companies", "company_link"

## Notatki

- **Bez poważnych zmian**: Jeśli nazwa pola relacji się nie zgadza, skrypt wypisze ostrzeżenie i pójdzie dalej
- **Dane historyczne**: Excel zawiera dane historyczne — stage'i są mapowane na możliwy stan w nowej bazie
- **Bez meetingsów**: Daty badania/demo są w Excelu, ale teraz ich nie tworzymy — można dodać później
- **Position brak**: Attendees tworzą się tylko z imienia i emaila (brak danych o stanowisku w starym CRM)
