# Wystawienie MinIO na VPS (załączniki/awatary NocoDB)

Kod (serwisy `minio`/`minio-init`, wpis w Caddyfile, `scripts/minio-init.sh`) jest już w repo — SeaweedFS był próbowany jako następca MinIO i wycofany (2026-08-08 → 2026-08-26, zob. `post-mortem/mikrus/vps-migration-decision.md`). Na VPS trzeba go wdrożyć i dopiąć konfigurację, która nie idzie z Gitem: `.env` i DNS.

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

Zmienne do dodania (wzorzec w `.env.example` sekcja "MinIO"):

- `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` — hasło **inne** niż placeholder `changeMinioRootPassword` (wersja obrazu nie jest już w `.env` — jest literałem w `fragments/minio-compose.yml`)
- `MINIO_HOST` — subdomena, np. `minio.giemza.dev`
- `MINIO_ENDPOINT=https://minio.giemza.dev` — musi być tym samym publicznym hostem co `MINIO_HOST` (patrz gotcha niżej)
- `MINIO_BUCKET_ATTACHMENTS`, `MINIO_BUCKET_OFFERS`, `MINIO_BUCKET_TEMPLATES`, `MINIO_BUCKET_RECORDINGS`, `MINIO_BUCKET_TRANSCRIPTS`, `MINIO_BUCKET_BACKUPS`
- `NOCODB_MINIO_ACCESS_KEY`, `NOCODB_MINIO_SECRET_KEY` — dane roli, którą `scripts/minio-init.sh` utworzy automatycznie (nie ręcznie w MinIO)

## 3. DNS

Dodaj rekord dla `MINIO_HOST` (`minio.giemza.dev`) wskazujący na ten sam adres VPS co `N8N_HOST`/`NC_HOST`. Bez tego Caddy nie wystawi certu Let's Encrypt dla tej subdomeny.

## 4. Start

```bash
make up
```

`Makefile` używa `docker compose`. To ściągnie `minio` + `minio/mc`, wystartuje `minio`, poczeka na healthcheck (`mc ready local`) i uruchomi jednorazowo `minio-init` — tworzy buckety z PRD §8.5 (`offers`/`templates` versioned, `recordings`/`backups` z lifecycle expiry) oraz least-privilege rolę `nocodb` scoped do bucketu `attachments`.

## 5. Weryfikacja

```bash
make ps
docker compose logs minio-init
```

Ostatnia linia loga `minio-init` powinna brzmieć `MinIO buckets + nocodb user ready.`, a sam kontener powinien zakończyć się kodem 0 — od tego zależy start `nocodb` (`depends_on: minio-init: condition: service_completed_successfully`).

Test uploadu w praktyce: w NocoDB dodaj pole typu Attachment do dowolnej tabeli i wgraj plik — powinien trafić do bucketu `attachments` bez żadnej ręcznej konfiguracji S3 w UI NocoDB.

## Gotcha: `MINIO_ENDPOINT` musi być publicznym hostem, nie wewnętrznym

NocoDB nie proxuje pobierania załączników przez siebie — zwraca przeglądarce bezpośredni, podpisany link do `NC_S3_ENDPOINT`. Dlatego `MINIO_ENDPOINT` musi być tym samym, publicznie rozwiązywalnym adresem co dla przeglądarki (`https://${MINIO_HOST}`), a jednocześnie osiągalnym z kontenera `nocodb`. Rozwiązane network aliasem `${MINIO_HOST}` na serwisie `caddy` w `docker-compose.yml` — kontener rozwiązuje tę nazwę na Caddy'ego przez wewnętrzne DNS Dockera, przeglądarka przez publiczne DNS; oba trafiają do tego samego Caddy'ego → `minio:9000`.

Jeśli DNS dla `MINIO_HOST` nie jest jeszcze ustawiony: upload i tak zadziała (idzie przez backend NocoDB), ale podgląd/pobieranie załączników w UI będzie martwe, dopóki rekord nie trafi do sieci.

## CPU: `minio` wymaga x86-64-v2

Ostatni obraz OSS MinIO (`RELEASE.2025-10-15T17-29-55Z`, zob. komentarz w `fragments/minio-compose.yml`) crashuje (`Fatal glibc error: CPU does not support x86-64-v2`) na hoście bez `host-passthrough` — dokładnie to uderzyło przy pierwszym stawianiu VPS-A/VPS-B (2026-07-17, `post-mortem/mikrus/vps-migration-decision.md`). Przed `make up` na nowym serwerze sprawdź `lscpu | grep -o 'avx[0-9]*' | sort -u` (patrz `docs/staging-vps-fresh-setup.md` Krok 0) — pusty wynik oznacza brak AVX/x86-64-v2, zgłoś do supportu i czekaj na fix zanim pójdziesz dalej.

## Jeśli `minio-init` failuje

```bash
docker compose logs minio
docker compose run --rm minio-init
```

Najczęstsza przyczyna: `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` w `.env` nie zgadza się z tym, na czym `minio` już wystartował na istniejącym wolumenie (`minio_storage`) — hasło roota jest ustawiane tylko raz, przy pierwszym starcie na pustym wolumenie, tak jak w Postgresie (patrz `docs/hard-reset.md`).
