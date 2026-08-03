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

## Data Volume

Excel (`Statusy_z_CRM_filled.xlsx`) montowany z:
```
./old-crm-based-seed/seed-fake:/data
```

Jeśli chcesz inną ścieżkę, zmień w `docker-compose.yml`.
