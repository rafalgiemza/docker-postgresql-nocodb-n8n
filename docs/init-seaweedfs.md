# Wystawienie SeaweedFS na VPS (załączniki/awatary NocoDB)

Kod (serwisy `seaweedfs`/`seaweedfs-init`, wpis w Caddyfile, `scripts/seaweedfs-entrypoint.sh`, `scripts/seaweedfs-init.sh`) jest już w repo — następca MinIO, zob. [`.ai/migrate-from-minio-to-SeaweedFS.md`](../.ai/migrate-from-minio-to-SeaweedFS.md) dla pełnego uzasadnienia migracji. Na VPS trzeba go wdrożyć i dopiąć konfigurację, która nie idzie z Gitem: `.env` i DNS.

## 1. Pobranie zmian na VPS

```bash
cd docker
git pull
```

## 2. Uzupełnienie `.env`

`.env` jest gitignored, więc nowe zmienne z `.env.example` nie pojawiły się w nim same. Porównaj i dopisz brakujące:

```bash
diff <(grep -oE '^[A-Z_]+=' .env.example | sort) <(grep -oE '^[A-Z_]+=' .env | sort)
```

Zmienne do dodania (wzorzec w `.env.example` sekcja "SeaweedFS"):

- `SEAWEEDFS_ROOT_ACCESS_KEY`, `SEAWEEDFS_ROOT_SECRET_KEY` — sekret **inny** niż placeholder `changeSeaweedfsRootSecretKey` (wersja obrazu nie jest już w `.env` — jest literałem w `fragments/seaweedfs-compose.yml`)
- `SEAWEEDFS_HOST` — subdomena, np. `minio.giemza.dev` (nazwa subdomeny celowo nie zmieniona przy migracji z MinIO — zero DNS/cert churn, patrz decyzja w `.ai/migrate-from-minio-to-SeaweedFS.md` §5)
- `SEAWEEDFS_ENDPOINT=https://minio.giemza.dev` — musi być tym samym publicznym hostem co `SEAWEEDFS_HOST` (patrz gotcha niżej)
- `SEAWEEDFS_BUCKET_ATTACHMENTS`, `SEAWEEDFS_BUCKET_OFFERS`, `SEAWEEDFS_BUCKET_TEMPLATES`, `SEAWEEDFS_BUCKET_RECORDINGS`, `SEAWEEDFS_BUCKET_TRANSCRIPTS`, `SEAWEEDFS_BUCKET_BACKUPS`
- `NOCODB_SEAWEEDFS_ACCESS_KEY`, `NOCODB_SEAWEEDFS_SECRET_KEY` — **inaczej niż w MinIO**, ta tożsamość nie jest tworzona dynamicznie po starcie. Musi być ustawiona w `.env` PRZED pierwszym `make up` — `scripts/seaweedfs-entrypoint.sh` wczytuje ją do statycznego `s3.json` przy starcie kontenera `seaweedfs`.

## 3. DNS

Dodaj rekord dla `SEAWEEDFS_HOST` (`minio.giemza.dev`) wskazujący na ten sam adres VPS co `N8N_HOST`/`NC_HOST`. Bez tego Caddy nie wystawi certu Let's Encrypt dla tej subdomeny.

## 4. Start

```bash
make up
```

`Makefile` używa `docker compose`. To ściągnie `seaweedfs` (obraz `chrislusf/seaweedfs`) + `minio/mc` (do `seaweedfs-init` — narzędzie `mc` zostaje, jest kompatybilne z S3 API SeaweedFS dla operacji, których używamy), wystartuje `seaweedfs`, poczeka na healthcheck (`master:9333/cluster/status`) i uruchomi jednorazowo `seaweedfs-init` — tworzy buckety z PRD §8.5 (`offers`/`templates` versioned, `recordings`/`backups` z lifecycle expiry).

## 5. Weryfikacja

```bash
make ps
docker compose logs seaweedfs-init
```

Ostatnia linia loga `seaweedfs-init` powinna brzmieć `SeaweedFS buckets ready.`, a sam kontener powinien zakończyć się kodem 0 — od tego zależy start `nocodb` (`depends_on: seaweedfs-init: condition: service_completed_successfully`).

Test uploadu w praktyce: w NocoDB dodaj pole typu Attachment do dowolnej tabeli i wgraj plik — powinien trafić do bucketu `attachments` bez żadnej ręcznej konfiguracji S3 w UI NocoDB.

## Gotcha: `SEAWEEDFS_ENDPOINT` musi być publicznym hostem, nie wewnętrznym

NocoDB nie proxuje pobierania załączników przez siebie — zwraca przeglądarce bezpośredni, podpisany link do `NC_S3_ENDPOINT`. Dlatego `SEAWEEDFS_ENDPOINT` musi być tym samym, publicznie rozwiązywalnym adresem co dla przeglądarki (`https://${SEAWEEDFS_HOST}`), a jednocześnie osiągalnym z kontenera `nocodb`. Rozwiązane network aliasem `${SEAWEEDFS_HOST}` na serwisie `caddy` w `docker-compose.yml` — kontener rozwiązuje tę nazwę na Caddy'ego przez wewnętrzne DNS Dockera, przeglądarka przez publiczne DNS; oba trafiają do tego samego Caddy'ego → `seaweedfs:8333`.

Jeśli DNS dla `SEAWEEDFS_HOST` nie jest jeszcze ustawiony: upload i tak zadziała (idzie przez backend NocoDB), ale podgląd/pobieranie załączników w UI będzie martwe, dopóki rekord nie trafi do sieci.

## Brak konsoli webowej (inaczej niż MinIO `:9001`)

SeaweedFS w tym setupie nie ma wbudowanej konsoli przeglądarkowej. Diagnostyka/ręczne operacje na bucketach — przez `mc` (tak jak `seaweedfs-init.sh`) lub `docker exec` do kontenera `seaweedfs` + `weed shell`. Patrz `.ai/migrate-from-minio-to-SeaweedFS.md` §5, jeśli brak GUI okaże się realnym problemem.

## Jeśli `seaweedfs-init` failuje

```bash
docker compose logs seaweedfs
docker compose run --rm seaweedfs-init
```

Najczęstsza przyczyna: `SEAWEEDFS_ROOT_ACCESS_KEY`/`SEAWEEDFS_ROOT_SECRET_KEY` w `.env` nie zgadza się z tym, co `seaweedfs` wczytał do `s3.json` przy starcie — sprawdź, czy kontener `seaweedfs` w ogóle wystartował poprawnie (`docker compose logs seaweedfs`) przed debugowaniem `seaweedfs-init`.
