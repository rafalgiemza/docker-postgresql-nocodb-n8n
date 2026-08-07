# n8n Workflows

## Example workflows for file-renderer-service

### `wf-docx-gen-example.json` — DOCX document generation

Przykład workflow'u do generowania dokumentów Word (.docx) z szablonów używając `file-renderer-service`.

**Cechy:**
- Pobiera szablon DOCX z tabeli `document_templates` (filtruje `kind=report, active=true`)
- Renderuje placeholdery `{{lead.name}}`, `{{company.title}}`, `{{report.generated_at}}` itd.
- Uploaduje wynik do NocoDB storage
- Tworzy rekord w tabeli dokumentów
- Obsługuje error path (task na błąd)

**Setup:**

1. **Importuj workflow:** n8n UI → Import → paste JSON z `wf-docx-gen-example.json`

2. **Przygotuj tabelę dokumentów** (np. `documents` lub `reports`):
   - `title` (text)
   - `kind` (select: report/audit/inne)
   - `template_name` (text)
   - `file` (Attachment)
   - `data_json` (LongText — snapshot danych użytych do renderu)
   - `warnings` (LongText — ostrzeżenia z renderingu)

3. **Przygotuj tabelę szablonów** (np. `document_templates`):
   - `name` (text)
   - `kind` (select: report/audit/inne) — musi się zgadzać z filtrami w workflow
   - `file` (Attachment — .docx)
   - `active` (checkbox)
   - `notes` (text)

4. **Dostosuj workflow do swoich tabel:**
   - Node "Fetch active template" → zmień workspace/project/table IDs
   - Node "Create document record" → zmień table ID i mapowanie pól
   - Node "Assemble render data" → dostosuj zmienne `data.*` do struktury szablonu

5. **Stwórz szablon DOCX:**
   - Dodaj placeholdery: `{{lead.contact_name}}`, `{{company.title}}`, `{{report.generated_at}}`
   - Placeholdery działają w: tekście paragrafów, tabelach, headerach, footerach
   - Wgraj szablon do `document_templates` z `active=true`

6. **Trigger workflow:**
   - Webhook endpoint: `POST /webhook/wf-docx-gen-example`
   - Body: payload z danych lead'a (zgodnie z formatem botonu w NocoDB)

**Różnice od `W9_generate_offer.json` (PPTX):**
- Endpoint: `/render-docx` zamiast `/render`
- Brak `repeat:<name>` markers — renderuje tylko placeholdery
- Nie ma mechanizmu powtarzania wierszy (wyjaśniane w file-renderer-service/README.md)
- Prostsze dane (brak listy uczestników/testimonials)

**Testy:**

Serwis ma unit testy placeholderów + integration testy w:
```bash
pytest file-renderer-service/test_docx_renderer.py -v
pytest file-renderer-service/test_app.py::test_render_docx_* -v
```

**Troubleshooting:**

- `X-Warnings: ["missing placeholder value: lead.name"]` → placeholder nie ma danych, sprawdź `data.lead.name` w "Assemble render data"
- Dokument się generuje ale placeholdery się nie renderują → check czy `{{}}` są napisane poprawnie (bez spacji wewnątrz)
- Serwis nie odpowiada → `docker compose logs file-renderer-service | tail -20`
