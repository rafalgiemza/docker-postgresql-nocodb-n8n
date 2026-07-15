# coaction — wewnętrzny stack narzędziowy

Docker Compose stack z narzędziami wewnętrznymi (CRM/leady, automatyzacje, chat)
hostowany na Mikrus 4.1. Pełny kontekst decyzji, architektury i ryzyk:
[`.ai/PRD.md`](.ai/PRD.md); stan wdrożenia i kolejne kroki:
[`.ai/IMPLEMENTATION_PLAN.md`](.ai/IMPLEMENTATION_PLAN.md).

## Usługi

| Usługa | Rola | Dostęp |
|---|---|---|
| PostgreSQL | wspólna instancja: `n8n`, `nocodb`, `appdata` (dane CRM, schemat `appdata`+widoki `crm.*`), `rag_db` (embeddingi, przygotowanie pod RAG) | wewnętrzny |
| n8n (+ n8n-runner) | automatyzacje, webhooki leadowe, pipeline oferta/audyt | publiczny — `${N8N_HOST}` |
| NocoDB | zarządzanie leadami/ofertami (CRM-podobny UI nad `crm.*`) | publiczny — `${NC_HOST}` |
| MinIO (+ minio-init) | S3-kompatybilny storage na załączniki NocoDB, oferty, nagrania, transkrypty, backupy | wewnętrzny |
| MongoDB | baza dla LibreChat (profil `local-mongo`, patrz [`docs/librechat.md`](docs/librechat.md)) | wewnętrzny |
| LibreChat | wewnętrzny chat/asystent zespołowy (OpenRouter) | publiczny — `${LIBRECHAT_HOST}` |
| Uptime Kuma | monitoring/alerting wszystkich usług + dysk + cert expiry | publiczny — `${STATUS_HOST}` |
| autoheal | restartuje kontenery, które utknęły w stanie `unhealthy` | wewnętrzny |
| Caddy | reverse proxy + automatyczny TLS (Let's Encrypt) | publikuje porty 80/443 |

Każda usługa jest zdefiniowana w osobnym pliku pod [`fragments/`](fragments/);
[`docker-compose.yml`](docker-compose.yml) tylko je łączy (`include:`) i definiuje
wspólną sieć oraz wolumeny. `name: docker` na górze tego pliku pina nazwę
projektu Compose (kontenery `docker-<usługa>-1`, wolumeny `docker_<nazwa>`)
niezależnie od nazwy katalogu tego checkoutu. Routing na subdomeny opisuje
[`Caddyfile`](Caddyfile).

## Szybki start

```bash
make init-env   # tworzy .env z .env.example, generuje losowe sekrety
make config     # waliduje złożoną konfigurację compose (fragments/*.yml)
make up         # odpala cały stack w tle
```

Jeden `docker-compose.yml` dla dev i prod — bez plików override/overlay.
Różnice środowiskowe (hosty, protokół, cookie-domain LibreChat) idą wyłącznie
przez `.env` (patrz komentarze przy `N8N_HOST`/`MINIO_ENDPOINT`/`LIBRECHAT_URL`
w [`.env.example`](.env.example)). Postgres/n8n/NocoDB/MinIO/LibreChat/Uptime
Kuma są zawsze dostępne na `127.0.0.1:<port>` (dev: bezpośrednio z Maca; prod:
tylko przez SSH tunel/exec na VPS-ie, nigdy z sieci) — publiczny ruch zawsze
idzie przez Caddy na 80/443. Pozostałe komendy: `make help`.

## Backup

`make backup` dumpuje wszystkie bazy (`n8n`/`nocodb`/`appdata` + role) i
NocoDB attachments/Mongo do `./backups/`, a następnie pushuje ten katalog
offsite przez `restic` (dedup, incremental) — patrz
[`backup/backup.sh`](backup/backup.sh). Sekrety offsite (`RESTIC_PASSWORD`,
`RESTIC_REPOSITORY`) trzymane POZA repo, na serwerze — przykład w
[`backup/mikrus-backup.env.example`](backup/mikrus-backup.env.example).
`make restore` przywraca z lokalnych plików w `./backups/`; po całkowitej
utracie hosta najpierw `restic restore` do `./backups/`, potem `make restore`
jak zwykle.

## RAG (przygotowanie, faza 2)

Baza `rag_db` jest zakładana już przy pierwszym uruchomieniu (patrz
[`scripts/init-data.sh`](init-data.sh)), świadomie osobna od `appdata`: `appdata` jest
podłączona do NocoDB i zarządzana przez klienta, a `rag_db` mają dotykać
wyłącznie automatyzacje (n8n) i przyszły agent wyszukujący — nigdy NocoDB.
Na istniejącej instancji (VPS) dodaje się ją ręcznie przez `make add-rag-db`.

## Sekrety

`.env` nie wchodzi do repozytorium — patrz [`.env.example`](.env.example) po
listę wymaganych zmiennych.

## Dokumentacja

- [`.ai/PRD.md`](.ai/PRD.md) — architektura, ryzyka, kryteria sukcesu
- [`.ai/IMPLEMENTATION_PLAN.md`](.ai/IMPLEMENTATION_PLAN.md) — stan wdrożenia, kolejność faz
- [`docs/docker.md`](docs/docker.md) — komendy operacyjne, restart/healthcheck audit
- [`docs/postgresql.md`](docs/postgresql.md) — model baz/ról w Postgresie
- [`docs/init-n8n.md`](docs/init-n8n.md), [`docs/init-nocodb.md`](docs/init-nocodb.md), [`docs/init-minio.md`](docs/init-minio.md) — bootstrap credentiali/dostępu per usługa
- [`docs/librechat.md`](docs/librechat.md) — LibreChat gotchas, migracja na zewnętrzny Mongo
- [`docs/offer-builder.md`](docs/offer-builder.md), [`docs/pipeline.md`](docs/pipeline.md) — runbooki n8n/NocoDB (FAZA 3/5)
- [`docs/hard-reset.md`](docs/hard-reset.md) — odtworzenie środowiska od zera
- [`post-mortem/`](post-mortem/) — incydenty i follow-upy (monitoring, autoheal, healthchecki)
