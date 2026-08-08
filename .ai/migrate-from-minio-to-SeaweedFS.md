# Migracja: MinIO → SeaweedFS

## 0. Kontekst i decyzja

MinIO Community Edition jest martwe (repo `minio/minio` zarchiwizowane na stałe
25.04.2026, firma przeszła na płatny AIStor) — patrz `.ai/PRD.md` §4/§11 pkt 7,
`post-mortem/mikrus/vps-migration-decision.md`. Decyzja (2026-08-08): migrujemy
na **SeaweedFS** zamiast zamrażać ostatni OSS release MinIO na stałe.

Dlaczego SeaweedFS, nie Garage/AIStor Free:

- **Garage** odpada — nie wspiera wersjonowania bucketów (dokumentacja: "na
  liście życzeń, niezaimplementowane"), a `scripts/minio-init.sh` już dziś
  explicit wymaga wersjonowania na `offers`/`templates` (dokumenty komercyjne,
  nigdy nie nadpisywane po cichu). Rezygnacja z tego wymogu byłaby regresją.
- **AIStor Free** odpada jako "aktywnie rozwijana alternatywa" — to ten sam
  produkt/firma, która pół roku wcześniej zarchiwizowała OSS. Zero wysiłku
  migracyjnego (identyczne API/`mc`), ale zero niezależności od jednego
  dostawcy i brak SLA/supportu nawet na free tier.
- **SeaweedFS** — Apache 2.0, aktywny rozwój (release co ~3 tyg.), pełny
  parytet funkcji: wersjonowanie bucketów, lifecycle policies, S3 API.
  Niezależny vendor.

**Moment migracji:** jesteśmy na końcówce testów, **brak danych
produkcyjnych** — najtańszy możliwy moment, żeby to zrobić raz porządnie,
zanim `file-renderer-service`/offers dostaną bezpośrednią integrację S3 SDK
(PRD §14 pkt 4 explicit to flaguje jako "zrób to zanim ktoś zacznie na tym
budować").

**Wersja obrazu: przypięta na `4.41`** (najnowszy stabilny release w chwili
pisania tego planu, sierpień 2026) — ta sama filozofia jawnego pinowania co
`MINIO_VERSION`/`MONGO_VERSION` dziś w `.env.example`.

## 1. Zakres

**Zmienia się:**
- Serwis obiektowy: `minio` (+ `minio-init`) → `seaweedfs` (+ `seaweedfs-init`)
- Wszystkie `MINIO_*` zmienne env → `SEAWEEDFS_*`
- Sposób provisioningu użytkownika/uprawnień: dynamiczne `mc admin user/policy`
  (MinIO-proprietary Admin API) → statyczny plik `s3.json` (SeaweedFS IAM-style
  identity config), renderowany z env varów przy starcie kontenera
- Nazwa wolumenu Docker: `minio_storage` → `seaweedfs_storage`
- Port S3 API: `9000` → `8333` (natywny default SeaweedFS)

**Zostaje bez zmian (świadomie, poza zakresem tej migracji):**
- Wzorzec "jeden `docker-compose.yml` dla dev i prod, różnice tylko przez
  `.env`" — bez override'ów
- Model 6 bucketów (`attachments`/`offers`/`templates`/`recordings`/
  `transcripts`/`backups`) i ich semantyka (wersjonowanie na offers/templates,
  lifecycle-expiry na recordings/backups) — 1:1 z dzisiejszym stanem, **mimo
  że `offers`/`templates` są dziś nieużywane** (`file-renderer-service`
  uploaduje przez NocoDB do bucketu `attachments`, patrz
  `.ai/IMPLEMENTATION_PLAN.md` linia 32) — to osobny, świadomy dług, nie
  rozwiązujemy go teraz
- Granularność backupu (`make backup`/`make restore`, dump-per-wolumen) —
  tylko nazwy zmiennych/wolumenu się zmieniają, nie struktura
- NocoDB integruje się z S3 tym samym mechanizmem (`NC_S3_*`), zero zmian po
  stronie NocoDB poza wartościami zmiennych
- Brak multi-node/HA, brak Postgres-backed filer store — single-node,
  embedded LevelDB filer store, tak samo "grubo" jak dzisiejszy pojedynczy
  kontener MinIO

**Jawnie poza zakresem:**
- Redesign architektury bucketów / wdrożenie `offers`/`recordings` na
  poważnie (backlog fazy 2, osobna decyzja)
- Admin UI/konsola webowa (MinIO miało `:9001`; SeaweedFS w tym planie go nie
  ma — patrz §5 "Otwarte pytania")

## 2. Nowa architektura SeaweedFS

Jeden kontener, tryb "all-in-one" (master + volume + filer + S3 gateway w
jednym procesie) — bezpośredni odpowiednik dzisiejszego pojedynczego
kontenera `minio`:

```
weed server -dir=/data -filer -s3 \
  -s3.port=8333 -s3.config=/etc/seaweedfs/s3.json \
  -ip=seaweedfs
```

Kluczowe: **`-dir=/data` musi być jawnie ustawiony** — domyślnie to
`os.TempDir()` (efemeryczne!), więc bez tej flagi dane przepadną przy
restarcie kontenera. To jest różnica od MinIO, gdzie `/data` jest domyślne.

Porty (potwierdzone we `weed/command/server.go` i dokumentacji SeaweedFS):

| Port | Komponent | Ekspozycja |
|---|---|---|
| 8333 | S3 API (odpowiednik MinIO `:9000`) | `127.0.0.1:8333` (dev) + przez Caddy (prod), jak dziś MinIO |
| 9333 | Master (status klastra) | wewnętrzny, opcjonalnie `127.0.0.1:9333` do debugowania |
| 8888 | Filer | wewnętrzny |
| 8080 | Volume server | wewnętrzny |

**Brak odpowiednika konsoli `:9001`** MinIO w tym planie — patrz §5.

### Model tożsamości (zamiast `mc admin user/policy`)

SeaweedFS nie ma admin API kompatybilnego z `mc admin`. Zamiast dynamicznego
tworzenia usera po starcie (jak dziś `minio-init.sh`), tożsamości definiuje
się **statycznie** w pliku `s3.json`, wczytywanym przy starcie przez
`-s3.config`:

```json
{
  "identities": [
    {
      "name": "root",
      "credentials": [
        { "accessKey": "${SEAWEEDFS_ROOT_ACCESS_KEY}", "secretKey": "${SEAWEEDFS_ROOT_SECRET_KEY}" }
      ],
      "actions": ["Admin", "Read", "Write", "List", "Tagging"]
    },
    {
      "name": "nocodb",
      "credentials": [
        { "accessKey": "${NOCODB_SEAWEEDFS_ACCESS_KEY}", "secretKey": "${NOCODB_SEAWEEDFS_SECRET_KEY}" }
      ],
      "actions": [
        "Read:${SEAWEEDFS_BUCKET_ATTACHMENTS}",
        "Write:${SEAWEEDFS_BUCKET_ATTACHMENTS}",
        "List:${SEAWEEDFS_BUCKET_ATTACHMENTS}",
        "Tagging:${SEAWEEDFS_BUCKET_ATTACHMENTS}"
      ]
    }
  ]
}
```

Ten plik trzeba wyrenderować z env varów PRZED startem `weed server` (shell
obsługuje `${VAR}` w heredocu natywnie, bez potrzeby `envsubst`) — nowy
`scripts/seaweedfs-entrypoint.sh`, montowany read-only tak jak dziś
`scripts/minio-init.sh`.

**Efekt uboczny (pozytywny):** provisioning usera przestaje być osobnym
one-shot krokiem zależnym od healthchecku — jest gotowy w momencie startu
`weed server`. `seaweedfs-init` (odpowiednik `minio-init`) zajmuje się już
tylko tworzeniem bucketów + wersjonowaniem + lifecycle, nie userami.

## 3. Plan zmian plik po pliku

| Plik | Zmiana |
|---|---|
| `fragments/minio.yml` → `fragments/seaweedfs.yml` | Nowy serwis `seaweedfs`, obraz `chrislusf/seaweedfs:${SEAWEEDFS_VERSION}`, `command` jak w §2, wolumen `seaweedfs_storage:/data`, mount `scripts/seaweedfs-entrypoint.sh` + template `s3.json`, port `127.0.0.1:8333:8333` |
| `fragments/minio-init.yml` → `fragments/seaweedfs-init.yml` | Analogiczny one-shot, ale bez `NOCODB_MINIO_*` (te idą teraz do `seaweedfs` service, nie do initu) |
| `scripts/minio-init.sh` → `scripts/seaweedfs-init.sh` | Usunąć blok `mc admin policy/user` (przeniesiony do identity config). Zostaje: `mc alias set` + `mc mb`/`mc version enable`/`mc ilm add` dla 6 bucketów — **do zweryfikowania w FAZA 0, patrz §4** |
| **Nowy:** `scripts/seaweedfs-entrypoint.sh` | Renderuje `/etc/seaweedfs/s3.json` z env (`root`/`nocodb` identities), potem `exec weed server ...` |
| `docker-compose.yml` | `include:` sekcja: `minio.yml`/`minio-init.yml` → `seaweedfs.yml`/`seaweedfs-init.yml`; `volumes:` `minio_storage` → `seaweedfs_storage` |
| `fragments/nocodb.yml` | `NC_S3_BUCKET_NAME=${SEAWEEDFS_BUCKET_ATTACHMENTS}`, `NC_S3_ACCESS_KEY=${NOCODB_SEAWEEDFS_ACCESS_KEY}`, `NC_S3_ACCESS_SECRET=${NOCODB_SEAWEEDFS_SECRET_KEY}`, `NC_S3_ENDPOINT=${SEAWEEDFS_ENDPOINT}`; `depends_on: minio-init` → `seaweedfs-init` (i teraz też `seaweedfs: condition: service_healthy`, bo user musi być już wczytany) |
| `fragments/caddy.yml` | `MINIO_HOST` → `SEAWEEDFS_HOST` (env + network alias), `depends_on: minio` → `seaweedfs` |
| `Caddyfile` | `{$MINIO_HOST} { reverse_proxy minio:9000 }` → `{$SEAWEEDFS_HOST} { reverse_proxy seaweedfs:8333 }` |
| `.env.example` | Cały blok "MinIO" zastąpić blokiem "SeaweedFS" — patrz §3.1 niżej |
| `backup/backup.sh` | `MINIO_VOLUME="docker_minio_storage"` → `SEAWEEDFS_VOLUME="docker_seaweedfs_storage"`, nazwa archiwum `minio_$TS.tar.gz` → `seaweedfs_$TS.tar.gz`, komentarze |
| `Makefile` / `backup/restore.sh` | Wolumen + nazwa pliku archiwum jak wyżej. **Aktualizacja po merge'u develop (2026-08-08):** równolegle na `develop` `restore` został wyekstrahowany z Makefile do osobnego `backup/restore.sh` (`fix(restore): stop app containers before DROP DATABASE, extract to script`) — konflikt przy merge'u tego brancha, rozwiązany ręcznie, `SEAWEEDFS_VOLUME`/`seaweedfs_$TS.tar.gz` poprawnie przeniesione na nową strukturę, zweryfikowane |
| `scripts/versions.sh` | Wiersz `report "minio" ... "minio --version"` → `report "seaweedfs" "docker-seaweedfs-1" "weed version"` |
| `docs/init-minio.md` → `docs/init-seaweedfs.md` | Przepisany runbook wdrożenia na VPS (nowe zmienne, nowy gotcha o `-dir=/data`, brak konsoli) |
| `docs/docker.md` | Zdanie o restart policy: `minio` → `seaweedfs` w liście serwisów |
| `docs/librechat.md` | `MINIO_HOST` → `SEAWEEDFS_HOST` we wzmiance o DNS |
| `README.md` | Wiersz tabeli serwisów, sekcja backupu, link do `docs/init-seaweedfs.md` |
| `.ai/PRD.md` | §4 zaktualizować status ("MinIO OSS martwe" → "zmigrowano na SeaweedFS, decyzja zamknięta"), §11 pkt 7, §14 pkt 4 oznaczyć jako rozwiązane |
| `.ai/IMPLEMENTATION_PLAN.md` | Status table: wiersz MinIO → SeaweedFS |
| `post-mortem/mikrus/vps-migration-decision.md` | Domknąć otwarty punkt "Zdecydować docelowo: zamrożone MinIO OSS czy migracja" — odsyłacz do tego pliku |

### 3.1 Nowy blok `.env.example`

Zastępuje sekcję "MinIO" (dziś linie 100–138):

```bash
# SeaweedFS — S3-kompatybilny storage (następca MinIO, zob.
# .ai/migrate-from-minio-to-SeaweedFS.md dla uzasadnienia). Buckety +
# tożsamość nocodb są tworzone/wczytywane automatycznie: buckety przez
# jednorazowy `seaweedfs-init` (scripts/seaweedfs-init.sh), tożsamości
# statycznie z s3.json renderowanego przy starcie `seaweedfs`
# (scripts/seaweedfs-entrypoint.sh) — na każdym `make up`.
SEAWEEDFS_VERSION=4.41
SEAWEEDFS_ROOT_ACCESS_KEY=seaweedfsroot
SEAWEEDFS_ROOT_SECRET_KEY=changeSeaweedfsRootSecretKey

# SEAWEEDFS_HOST — prod: subdomena serwowana przez Caddy, tak samo resolved
# *wewnątrz* sieci Dockera (network alias na serwisie caddy, patrz
# fragments/caddy.yml), żeby NocoDB i przeglądarka trafiały pod ten sam host.
# SEAWEEDFS_ENDPOINT — co faktycznie widzi klient S3 NocoDB.
#   Local dev: SEAWEEDFS_ENDPOINT=http://localhost:8333 (zawsze też
#     osiągalne na 127.0.0.1:8333, patrz fragments/seaweedfs.yml)
#   Prod:      https://<SEAWEEDFS_HOST>, przez Caddy, jak niżej
SEAWEEDFS_HOST=minio.giemza.dev
SEAWEEDFS_ENDPOINT=https://minio.giemza.dev

# Buckety: offers/templates wersjonowane (dokumenty komercyjne, nigdy
# nadpisywane po cichu); recordings/backups wygasają przez lifecycle rules.
SEAWEEDFS_BUCKET_ATTACHMENTS=attachments
SEAWEEDFS_BUCKET_OFFERS=offers
SEAWEEDFS_BUCKET_TEMPLATES=templates
SEAWEEDFS_BUCKET_RECORDINGS=recordings
SEAWEEDFS_BUCKET_TRANSCRIPTS=transcripts
SEAWEEDFS_BUCKET_BACKUPS=backups

# Least-privilege tożsamość, którą łączy się NocoDB — scoped do bucketu
# attachments (Read/Write/List/Tagging), nigdy root. Zdefiniowana statycznie
# w s3.json (nie dynamicznym admin API jak wcześniej w MinIO).
NOCODB_SEAWEEDFS_ACCESS_KEY=nocodb
NOCODB_SEAWEEDFS_SECRET_KEY=changeNocodbSeaweedfsSecretKey
```

**Uwaga:** `SEAWEEDFS_HOST` powyżej celowo zostawiony jako `minio.giemza.dev`
(bez zmiany wartości) — patrz §5, decyzja o DNS.

## 4. Kolejność wykonania

### FAZA 0 — walidacja narzędzi (lokalnie, throwaway, ~30 min) — ✅ ZROBIONE 2026-08-08

**Wynik: `mc` w pełni wystarcza, zero potrzeby fallbacku na `aws-cli`.**
Potwierdzone empirycznie na throwaway `chrislusf/seaweedfs:4.41`:
- `mc mb`/`mc version enable`/`mc version info` działają 1:1.
- `mc cp`/`mc cat` (PUT/GET) **wymagają poprawnie skonfigurowanego
  `-s3.config`** — bez niego SeaweedFS odrzuca podpisane żądania
  (`Signed request requires setting up SeaweedFS S3 authentication`), mimo że
  `mc mb` bez configu przechodzi. Nie wpływa na plan (`-s3.config` był już
  założony), ale ważne przy debugowaniu: brak configu ≠ "otwarty dostęp",
  tylko inny, mylący błąd na PUT/GET.
- Scoping tożsamości działa dokładnie wg schematu z §2 (`Read:bucket` itd.)
  — zweryfikowano, że tożsamość `nocodb` może pisać do `attachments`, ale
  dostaje `Insufficient permissions` na `offers`.
- Presigned URL (`mc share download`) działa identycznie jak w MinIO/S3 —
  zweryfikowano nieautoryzowanym `curl` na wygenerowany link.
- Healthcheck: `http://<master>:9333/cluster/status` → HTTP 200,
  `{"IsLeader":true,"Leader":"...","MaxVolumeId":N}` — potwierdzone jako
  stabilny endpoint. **Doprecyzowane w FAZA 2:** wewnątrz kontenera trzeba
  bić w `127.0.0.1:9333`, nie `localhost:9333` — obraz rozwiązuje `localhost`
  na `::1` jako pierwszy, a `weed` słucha tylko IPv4, więc `wget` z `localhost`
  dostaje "Connection refused" mimo że port faktycznie żyje. Ten sam pitfall,
  co już udokumentowany dla healthchecków `caddy`/`librechat` w
  `docs/docker.md` — z hosta (`docker run -p ...`) problem nie był widoczny,
  bo port-publishing tłumaczy to inaczej niż DNS wewnątrz kontenera.
- **Gotcha odkryty, nie przewidziany w tym planie pierwotnie:** obecna wersja
  `mc` **nie ma flagi `--id`** dla `mc ilm add`/`mc ilm rule add` (w
  przeciwieństwie do starego wywołania z `minio-init.sh`, `mc ilm add --id
  recordings-expiry ...`). Bez `--id` każde wywołanie tworzy NOWĄ regułę z
  losowym ID — powtórne `make up` piętrzyłoby duplikaty. Naprawione w
  `scripts/seaweedfs-init.sh` przez guard `mc ilm rule ls` (exit 1 = brak
  reguły jeszcze, exit 0 = już jest) przed `mc ilm rule add`.
- **Entrypoint wymaga chaingingu, nie prostego override'u.** Obraz
  `chrislusf/seaweedfs` ma własny `/entrypoint.sh`, który chowniuje `/data`
  na użytkownika `seaweed` i dropuje uprawnienia przez `su-exec` przed
  odpaleniem `weed`. Pełne zastąpienie entrypointu własnym skryptem
  (bezpośredni `exec weed server ...`) pomija ten krok i zostawia `/data`
  jako `root`-owned. Rozwiązanie: `scripts/seaweedfs-entrypoint.sh` renderuje
  `s3.json`, a na końcu robi `exec /entrypoint.sh server ...` (woła
  oryginalny entrypoint z właściwymi argumentami) zamiast wywoływać `weed`
  bezpośrednio — zweryfikowane lokalnie, `/data` poprawnie `seaweed:seaweed`.

Zanim przepiszemy `minio-init.sh` na sztywno, sprawdzić na gołym
`docker run` (bez wpinania w cały stack), czy `mc` faktycznie obsługuje
przeciwko SeaweedFS to, czego dziś używamy:

```bash
docker run -d --name sw-test -p 8333:8333 chrislusf/seaweedfs:4.41 \
  server -dir=/data -filer -s3 -s3.port=8333
mc alias set test http://localhost:8333 any any   # SeaweedFS bez configu = brak auth
mc mb test/probe
mc version enable test/probe      # <- KLUCZOWE do zweryfikowania
mc ilm add --id x --expiry-days 30 test/probe   # <- KLUCZOWE do zweryfikowania
```

- Jeśli oba działają → `scripts/seaweedfs-init.sh` zostaje na `mc`, minimalna
  zmiana względem dzisiejszego `minio-init.sh`.
- Jeśli nie → fallback na `aws s3api put-bucket-versioning` /
  `put-bucket-lifecycle-configuration` (surowe wywołania S3 API, które
  SeaweedFS na pewno wspiera — potwierdzone w dokumentacji jako
  `PutBucketVersioning`/`PutBucketLifecycleConfiguration`) w miejsce `mc`.

Przy okazji zweryfikować dokładny healthcheck endpoint — kandydat:
`wget -q --spider http://localhost:9333/cluster/status`.

### FAZA 1 — kod (nowe fragmenty, skrypty, env) — bez wdrożenia — ✅ ZROBIONE 2026-08-08

- [x] `scripts/seaweedfs-entrypoint.sh` (renderuje `s3.json` inline, bez osobnego pliku template)
- [x] `scripts/seaweedfs-init.sh` (z guardem idempotencji na `mc ilm rule add`, patrz FAZA 0)
- [x] `fragments/seaweedfs.yml`, `fragments/seaweedfs-init.yml`
- [x] Usunięto `fragments/minio.yml`, `fragments/minio-init.yml`, `scripts/minio-init.sh` (`git rm`)
- [x] `docker-compose.yml`, `fragments/nocodb.yml`, `fragments/caddy.yml`, `Caddyfile`
- [x] `.env.example` (blok z §3.1)
- [x] `backup/backup.sh`, `Makefile` (restore), `scripts/versions.sh`
- [x] Dokumentacja: `docs/init-seaweedfs.md` (przeniesiony z `docs/init-minio.md`), `docs/docker.md`, `docs/librechat.md`, `README.md`, `.ai/PRD.md`, `.ai/IMPLEMENTATION_PLAN.md`, `post-mortem/mikrus/vps-migration-decision.md`
- [ ] `docker compose config` — walidacja że całość się parsuje (FAZA 2)

### FAZA 2 — test lokalny — ✅ ZROBIONE 2026-08-08

Nie wymagało `down -v`: nowy wolumen `seaweedfs_storage` tworzony od zera
automatycznie, stary `minio_storage` po prostu przestał być referencjonowany
— bez utraty danych n8n/nocodb/postgres. Uruchomiony tylko celowy podzbiór
(`postgres seaweedfs seaweedfs-init nocodb`), nie cały stack.

- [x] `docker compose up -d --remove-orphans postgres seaweedfs seaweedfs-init nocodb`
- [x] `seaweedfs` osiąga `healthy` (po poprawce healthchecku na `127.0.0.1`,
      patrz FAZA 0 wyżej), `seaweedfs-init` kończy się sukcesem (po dodaniu
      retry-loop, patrz wyżej) — wszystkie 6 bucketów utworzone, `offers`/
      `templates` versioned, `recordings`/`backups` z lifecycle rule
- [x] Smoke test upload/download/presigned URL — **wykonany bezpośrednio
      przez `mc` z DOKŁADNIE tymi credentialami, jakie ma `nocodb`**
      (`NOCODB_SEAWEEDFS_ACCESS_KEY`/`SECRET_KEY`, bucket `attachments`),
      zamiast przez kontener `nocodb` samego w sobie — patrz uwaga niżej.
- [x] Wersjonowanie potwierdzone już w FAZA 0 (dwa uploady tego samego klucza
      → dwie osobne wersje w `mc ls --versions`)
- [x] `make backup` → `seaweedfs_<ts>.tar.gz` (8.2 KB, realne dane wolumenu:
      `.dat`/`.idx`/`.vif` pliki SeaweedFS) — sukces. `mongodump` failuje w
      tym częściowym stacku (kontener `mongodb` celowo nieuruchomiony), to
      nie dotyczy SeaweedFS.
- [x] Restore drill: wypakowanie `seaweedfs_<ts>.tar.gz` na świeży wolumen
      testowy — sukces, pliki obecne.

**Nie przetestowano lokalnie:** rzeczywisty kontener `nocodb` end-to-end
(upload przez UI) — port `127.0.0.1:8081` na tej maszynie deweloperskiej był
zajęty przez proces VSCode Insidersa (`Code - Insiders Helper`, potwierdzone
`lsof`/`ps`), nie przez żaden kontener tego projektu — `seed-service` (który
początkowo podejrzewaliśmy) mapuje `127.0.0.1:8001`, nie `8081`, i w compose
gada z NocoDB po wewnętrznej sieci Dockera (`http://nocodb:8080`), nie przez
localhost. **Ten konkretny konflikt jest specyficzny dla tej maszyny
deweloperskiej i nie powtórzy się na VPS** (nic tam nie zajmuje 8081 poza
samym Dockerem). Zdecydowano pominąć — funkcjonalność już potwierdzona przez
identyczne credentiale/bucket bezpośrednio przez `mc`. Pełny test przez UI
NocoDB pozostaje w FAZA 4 na vps-staging.

### FAZA 3 — dokumentacja

- [ ] `docs/init-seaweedfs.md` (przepisany `docs/init-minio.md`)
- [ ] `README.md`, `docs/docker.md`, `docs/librechat.md`
- [ ] `.ai/PRD.md`, `.ai/IMPLEMENTATION_PLAN.md`,
      `post-mortem/mikrus/vps-migration-decision.md` (zamknięcie otwartego punktu)

### FAZA 4 — wdrożenie na VPS

- [ ] Decyzja DNS (patrz §5) — jeśli zmiana hosta: nowy rekord A/AAAA przed
      deployem, inaczej Caddy nie wystawi certu
- [ ] `.env` na VPS: dopisać `SEAWEEDFS_*`, usunąć `MINIO_*` (diff jak w
      `docs/init-minio.md` dziś: `diff <(grep -oE '^[A-Z_]+=' .env.example | sort) <(grep -oE '^[A-Z_]+=' .env | sort)`)
- [ ] `git pull && make up`
- [ ] Powtórzyć smoke testy z FAZA 2 na VPS
- [ ] Dopiero PO potwierdzeniu stabilności: skasować stary wolumen
      `docker_minio_storage` (`docker volume rm docker_minio_storage`) —
      **destrukcyjne, wymaga jawnego potwierdzenia użytkownika w danym
      momencie, nie robić automatycznie**

## 5. Otwarte pytania / decyzje do podjęcia

1. **DNS/hostname** — zostawić `minio.giemza.dev` wskazujący teraz na
   SeaweedFS (zero DNS/cert churn, tylko nazwa trochę myląca długoterminowo),
   czy przenieść na nową subdomenę (np. `s3.giemza.dev`, wymaga nowego
   rekordu + certu przed cutover). **Rekomendacja: zostawić bez zmian** —
   subdomena to tylko nazwa proxy targetu, nie ma technicznego kosztu
   niezgodności z nazwą backendu. Zaimplementowane wg rekomendacji.
2. ~~**`mc` vs `aws-cli`**~~ — rozstrzygnięte w FAZA 0: `mc` w pełni
   wystarcza.
3. ~~**Dokładny endpoint healthchecku**~~ — rozstrzygnięte w FAZA 0:
   `master:9333/cluster/status`, HTTP 200 + `"IsLeader":true`.
4. **Konsola webowa** — MinIO miało `:9001`. SeaweedFS ma nowszy, prostszy
   tryb `weed mini` z wbudowanym Admin UI (`:23646`), ale jest świeższy/mniej
   sprawdzony niż klasyczne `weed server`. Ten plan **nie** wprowadza żadnej
   konsoli (zarządzanie przez `mc`/`aws-cli` z shella, tak jak dziś przy
   ręcznej diagnostyce MinIO). Do rozważenia jako osobne ulepszenie później,
   jeśli brak GUI okaże się realnym problemem w praktyce.

## 6. Ryzyko / rollback

Brak danych produkcyjnych = migracja jest tania do cofnięcia. Rollback:
`git revert` commitów tej migracji przywraca `fragments/minio*.yml` +
`scripts/minio-init.sh` + stary `.env.example`; wolumen `minio_storage` (jeśli
jeszcze nie skasowany — patrz FAZA 4 ostatni punkt) zawiera dane do momentu
jawnego `docker volume rm`. Nie kasować `docker_minio_storage` przed pełną
weryfikacją nowego stacku na VPS.

## 7. Checklist (flat, do odhaczania w trakcie realizacji)

- [x] FAZA 0: zweryfikować `mc version enable`/`mc ilm add` przeciw SeaweedFS
- [x] FAZA 0: zweryfikować healthcheck endpoint
- [x] FAZA 1: nowe fragmenty/skrypty/env (kod)
- [x] FAZA 3: dokumentacja zaktualizowana (zrobiona równolegle z FAZA 1)
- [x] FAZA 1/2: `docker compose config` przechodzi
- [x] FAZA 2: test lokalny (`docker compose up -d --remove-orphans`, podzbiór
      serwisów) + smoke testy (upload, presigned URL, versioning,
      backup/restore) — kontener `nocodb` end-to-end pominięty lokalnie
      (konflikt portu 8081 z VSCode na tej maszynie, nie z projektem),
      zostaje na FAZA 4
- [ ] FAZA 4 (użytkownik, na vps-staging): DNS (jeśli dotyczy) + `.env` na VPS
      + deploy
- [ ] FAZA 4 (użytkownik): smoke testy na VPS — załączniki NocoDB,
      generowanie dokumentów, backupy
- [ ] FAZA 4 (użytkownik): stary wolumen `docker_minio_storage` skasowany (po
      potwierdzeniu, ręcznie)
