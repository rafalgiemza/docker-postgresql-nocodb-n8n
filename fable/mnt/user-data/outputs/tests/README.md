# Test Runner — setup

E2E: runner POST-uje syntetyczne payloady webhooków NocoDB na endpointy n8n
i asertuje wynik przez API NocoDB. Zero mocków — testowany jest prawdziwy
łańcuch n8n → NocoDB → Postgres, na odizolowanej bazie.

## Środowisko testowe (jednorazowo)

1. **Baza CRM-TEST**: zduplikuj produkcyjną bazę w NocoDB (Base → Duplicate,
   bez rekordów) albo odtwórz schemat. NIGDY nie podawaj runnerowi produkcyjnego base_id —
   fixture `clean` czyści WSZYSTKIE tabele przed i po każdym teście.
2. **Kopie workflowów**: dla W1–W6 zrób kopie z suffiksem `-TEST`, wykonaj sed
   z ID tabel bazy TEST i zmień ścieżki webhooków na `test-...`
   (np. `test-w2-stage-change`). Aktywuj kopie. Uwaga W1: kopia dostaje
   dodatkowy node Webhook (path `test-w1-run`) podpięty równolegle do crona,
   żeby runner mógł odpalać przebieg na żądanie (przypadki W1-01..09).
3. **MailHog** jako SMTP-atrapa (inaczej node'y Send Email wywalą flow):
   ```yaml
   mailhog:
     image: mailhog/mailhog
     # UI na 8025 w sieci wewnętrznej; SMTP: mailhog:1025
   ```
   W n8n credential "SMTP" (kopiach testowych) wskaż `mailhog:1025`, bez auth.
4. **OpenRouter**: przypadki SEMI (W4-14..17, W6a-01) wołają prawdziwy LLM —
   ustaw najtańszy model w kopiach testowych; koszt pełnego przebiegu to grosze.

## Uruchomienie

```bash
pip install pytest requests
export NC_URL=http://localhost:PORT        # albo IP kontenera / domena
export NC_TOKEN=...
export NC_TEST_BASE=p....                  # base id CRM-TEST (nie produkcyjny!)
export N8N_URL=https://n8n.twojadomena.pl  # publiczny URL n8n (webhooki)
export WH_PREFIX=test-
pytest -v tests/
```

## Zakres

- `test_cases.md` — pełny katalog (W1–W6b, importer, przekrojowe) z trybami
  AUTO / SEMI / PROC.
- `test_workflows.py` — zaimplementowane przypadki AUTO dla W2, W3, W4 (tiery
  deterministyczne), W5, W6a (gałęzie bez LLM), W6b. Przypadki SEMI (LLM)
  i W1 (wymaga node'a test-w1-run) do dopisania wg tego samego wzorca —
  szkielet asercji strukturalnych: `wait_for("meetings", "(ai_analysis,isnot,null)")`.
- Przypadki PROC (importer) weryfikujesz przez `--dry-run` na spreparowanym
  xlsx — katalog IMP-01..10 to gotowa checklista.

## Wzorce w testach

- `wait_for(table, where, count)` — polling do skutku (webhook → n8n jest
  asynchroniczny); timeout = fail z podpowiedzią zajrzenia w execution log.
- `wait_quiet(table, where)` — asercja negatywna: przez N sekund nic nie
  powstało (testy guardów, W2-05/06, W5-02 itd.).
- Payloady budują helpery `nc_insert` / `nc_update` (z `previous_rows`!) oraz
  adaptery `tally` / `cf7` / `booking` — jeśli realny payload Twojej wersji
  NocoDB różni się kształtem, poprawiasz JEDNO miejsce w conftest.py.

## Znane ograniczenia (świadome)

- Testy są sekwencyjne (wspólna baza TEST) — nie odpalaj `pytest -n auto`.
- Asercje mailowe pominięte w v1; MailHog ma API (`GET /api/v2/messages`),
  łatwo dodać fixture, gdy będzie potrzeba.
- OWNER w test_workflows.py musi być mailem członka bazy TEST — podmień.
