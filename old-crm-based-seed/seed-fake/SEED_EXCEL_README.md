# Seed NocoDB CRM z Excela

Migracja 1600 rekordów z **Statusy_z_CRM_filled.xlsx** do nowej bazy NocoDB.

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
contact_name      ← Nazwa klienta
contact_email     ← E.mail
contact_phone     ← Nr telefonu
type              ← B2B/B2C
source            ← Źródło (mapowania: Google, Polecenie, LinkedIn...)
contact_channel   ← Forma kontaktu
qualification     ← Kwalifikacja lead'a
stage             ← Etap (mapowania: utracona→lost, umowa→contract_signed)
state             ← Stan
value             ← Szansa sprzedaży (PLN)
notes             ← Notatki
legacy_id         ← Spr. ID (używany do dedup)
```

#### 2. **Companies** (tylko B2B)
```
name              ← Organizacja
industry          ← Branża
```
Link: `lead → company` (pole "company")

#### 3. **Participants** (1 per lead = 1600)
```
full_name         ← Nazwa klienta (osoba kontaktowa)
email             ← E.mail
```
Link: `lead → participant` (pole "participants")

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

## Mapowania źródeł

| Excel | NocoDB |
|-------|--------|
| Google | google |
| Polecenie | polecenie |
| LinkedIn | linkedin |
| Strona www, Cold mail, Targi, Webinar | polecenie (fallback) |
| Facebook, Kampania Ads | google (fallback) |

## Mapowania form kontaktu

| Excel | NocoDB |
|-------|--------|
| Bookings | bookings |
| Formularz WWW | formularz |
| Telefon | telefon |
| E-mail | email |
| Czat | email (fallback) |
| Spotkanie | telefon (fallback) |

## Bezpieczeństwo (idempotent)

- **Dedup**: Skrypt sprawdza `legacy_id` — jeśli lead już istnieje, pomija go
- **Brak duplikatów**: Można uruchomić wielokrotnie, nowe rekordy nie będą duplikowane
- **Transakcje**: Każdy rekord jest niezależny — jeśli jedno się nie uda, reszta pójdzie

## Troubleshooting

### "API error 401: Unauthorized"
- Token jest stary lub niepoprawny
- Generuj nowy w Account Settings

### "Brakuje tabel: leads, companies, participants"
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
- **Position brak**: Participants tworzą się tylko z imienia i emaila (brak danych o stanowisku w starym CRM)
