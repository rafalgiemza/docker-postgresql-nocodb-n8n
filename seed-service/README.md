# Seed Service - NocoDB CRM Seeder

FastAPI service do migracji 1600 rekordów ze starego CRM (Excel) do NocoDB.

## Struktura

```
seed-service/
├── Dockerfile          - Python 3.12 slim + FastAPI
├── requirements.txt    - openpyxl, requests, fastapi, uvicorn
├── seed_app.py         - FastAPI app z endpointami
└── README.md           - ta dokumentacja
```

## Endpoints

### `GET /health`
Health check - zwraca status usługi i konfiguracji.

```bash
curl http://localhost:8001/health
```

### `GET /preview?limit=5`
Podgląd pierwszych N rekordów z Excela (bez połączenia do NocoDB).

```bash
curl http://localhost:8001/preview?limit=10
```

Response:
```json
{
  "total_records": 1600,
  "preview_count": 10,
  "records": [
    {
      "nazwa": "Spółdzielnia Kochman",
      "email": "szymon.plewnia@...",
      "typ": "B2B",
      "etap": "utracona",
      "wartosc": 5000
    },
    ...
  ]
}
```

### `POST /seed?dry_run=true`
Dry-run - podgląd bez zmian w bazie (wymaga NC_API_TOKEN + NC_CRM_BASE_ID).

```bash
curl -X POST http://localhost:8001/seed?dry_run=true
```

### `POST /seed?dry_run=false`
Pełna migracja - tworzy leads, companies, participants w NocoDB.

```bash
curl -X POST http://localhost:8001/seed?dry_run=false
```

### `POST /seed-upload` ⭐ (dla n8n form)
Upload file + seeding z dowolnym serwerem NocoDB.

```bash
curl -X POST \
  -F "file=@Statusy_z_CRM_filled.xlsx" \
  -F "nc_url=http://nocodb:8080" \
  -F "nc_token=YOUR_TOKEN" \
  -F "nc_base_id=YOUR_BASE_ID" \
  "http://localhost:8001/seed-upload?dry_run=false"
```

**Query params:**
- `nc_url` - URL NocoDB (default: env NC_LOCAL_URL)
- `nc_token` - API token (default: env NC_API_TOKEN)
- `nc_base_id` - Base ID (default: env NC_CRM_BASE_ID)
- `dry_run` - true/false (default: true)

**Response (success):**
```json
{
  "dry_run": false,
  "file_name": "data.xlsx",
  "total_records": 1600,
  "created_leads": 1600,
  "created_companies": 600,
  "created_participants": 1600,
  "skipped": 0,
  "errors": [],
  "message": "Seeding ukończony..."
}
```

## Docker Compose

Dodaj do `docker-compose.yml`:

```yaml
  seed-service:
    build: ./seed-service
    container_name: coaction-seed-service
    ports:
      - "8001:8000"
    environment:
      NC_LOCAL_URL: http://nocodb:8081
      NC_API_TOKEN: ${NC_API_TOKEN}
      NC_CRM_BASE_ID: ${NC_CRM_BASE_ID}
    volumes:
      - ./old-crm-based-seed/seed-fake:/data
    networks:
      - coaction-network
    depends_on:
      - nocodb
```

## Uruchomienie

```bash
# Build
docker-compose build seed-service

# Start
docker-compose up -d seed-service

# Logs
docker-compose logs -f seed-service

# Test
curl http://localhost:8001/health
curl http://localhost:8001/preview?limit=5

# Dry-run
curl -X POST http://localhost:8001/seed?dry_run=true

# Pełna migracja
curl -X POST http://localhost:8001/seed?dry_run=false
```

## Konfiguracja

Wymaga w `.env`:
```
NC_API_TOKEN=<token z NocoDB>
NC_CRM_BASE_ID=<base ID>
```

Opcjonalnie:
```
NC_LOCAL_URL=http://nocodb:8081  # default: http://localhost:8081
```

## API Docs

Dostępne na: `http://localhost:8001/docs` (Swagger UI)

## Co będzie zmigrowaneː

- ✅ 1600 leads
- ✅ ~600 companies (B2B)
- ✅ 1600 participants
- ✅ Linking: lead → company, lead → participant

## Zmienne środowiskowe

| Zmienna | Opis | Default |
|---------|------|---------|
| `NC_LOCAL_URL` | URL NocoDB | `http://localhost:8081` |
| `NC_API_TOKEN` | Token API | - (wymagany) |
| `NC_CRM_BASE_ID` | ID bazy CRM | - (wymagany) |

## n8n Integration

### Workflow: Upload + Seed

1. **Form node** (HTTP Request / Form)
   - File input (multipart)
   - Text inputs: `nc_url`, `nc_token`, `nc_base_id`
   - Button: "Seed CRM"

2. **POST to /seed-upload**
   ```
   POST http://seed-service:8000/seed-upload
   ?nc_url={{$node.Form.data.nc_url}}
   &nc_token={{$node.Form.data.nc_token}}
   &nc_base_id={{$node.Form.data.nc_base_id}}
   &dry_run=false
   
   Body: file={{$node.Form.data.file}}
   ```

3. **Response node** (show results)
   - `created_leads`, `created_companies`, `created_participants`
   -Errors (jeśli są)

### Klient Flow

```
[Form Upload] → [HTTP POST /seed-upload] → [Show Results]
     ↓
  File + params
     ↓
  Seed-service
     ↓
  NocoDB (klientowska baza)
```

Klient może:
- Uploadować Excel z tym samym schema
- Podać swój NocoDB server + token + base_id
- Seed-service zarobi całą robotę (dry-run / full)

## Data Volume

Excel (`Statusy_z_CRM_filled.xlsx`) montowany z:
```
./old-crm-based-seed/seed-fake:/data
```

Jeśli chcesz inną ścieżkę, zmień w `docker-compose.yml`.
