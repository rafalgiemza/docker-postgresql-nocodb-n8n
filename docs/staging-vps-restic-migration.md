# Nowy VPS-B (staging) — migracja danych ze starego coaction-test przez restic

Runbook do wymiany obecnego `coaction-test` (VPS-B, staging, Sferahost) na
nowy serwer **z zachowaniem danych** (workflowy n8n klikane w UI, dane
NocoDB/`appdata`). Jeśli staging można postawić od zera bez migracji danych,
użyj zamiast tego prostszego
[`staging-vps-fresh-setup.md`](staging-vps-fresh-setup.md) — Kroki 0–3 poniżej
są z niego przejęte 1:1, więc jeśli już go przeszedłeś, przejdź od razu do
Kroku 4.

**Kluczowa różnica względem stawiania od zera**: `.env` na nowym serwerze musi
być **dokładnie tym samym plikiem** co na starym `coaction-test` (te same
hasła DB, ten sam `N8N_ENCRYPTION_KEY`) — dumpy Postgresa i szyfrowane
credentiale n8n są nieodtwarzalne bez oryginalnych sekretów. Nie odpalaj tu
`make init-env` / `scripts/generate-env.sh`.

## Krok 0 — sprawdź CPU passthrough PRZED instalacją czegokolwiek

Jak w [`staging-vps-fresh-setup.md`](staging-vps-fresh-setup.md#krok-0--sprawdź-cpu-passthrough-przed-instalacją-czegokolwiek):

```bash
lscpu | grep -o 'avx[0-9]*' | sort -u   # pusty wynik = brak AVX → zgłoś do Sferahost, czekaj na fix
```

## Krok 1 — bootstrap systemu

Jak w [`staging-vps-fresh-setup.md`](staging-vps-fresh-setup.md#krok-1--bootstrap-systemu-docker-user-deploy-firewall-fail2ban)
— `vps/init-mikrus.yaml` odpalony ręcznie po SSH: Docker, user `deploy`,
`ufw`, `fail2ban`, hardening sshd. Zweryfikuj `ssh deploy@<ip>` w nowym oknie
przed zamknięciem sesji roota.

## Krok 2 — świeży backup na STARYM coaction-test

Na starym serwerze upewnij się, że offsite backup jest aktualny (jeśli cron
z `backup/mikrus-backup.env.example` już działa, snapshoty i tak lecą co
noc — ale przed migracją warto wymusić świeży):

```bash
ssh root@<ip-starego-coaction-test>
cd coaction   # albo gdziekolwiek jest checkout
make backup   # dump wszystkich baz + wolumeny NocoDB/MinIO + Mongo, push offsite (restic)
```

Jeśli `/etc/mikrus-backup.env` (`RESTIC_REPOSITORY`/`RESTIC_PASSWORD`) nie
jest jeszcze skonfigurowany na starym serwerze — zrób to najpierw, inaczej
`make backup` zostawi dump tylko lokalnie w `./backups/` i nic nie pójdzie
offsite (patrz nagłówek [`backup/backup.sh`](../backup/backup.sh)).

## Krok 3 — sklonuj repo i skopiuj DOKŁADNIE ten sam `.env`

Na nowym serwerze:

```bash
ssh deploy@<ip-nowego-serwera>
git clone <url-repo> coaction && cd coaction
```

Skopiuj `.env` bezpośrednio ze starego serwera (nie generuj nowego):

```bash
scp root@<ip-starego-coaction-test>:~/coaction/.env ./.env
```

Domeny (`N8N_HOST`/`NC_HOST`/itd.) zostają identyczne — zmienia się tylko
DNS (Krok 6), nie `.env` (dokładnie tak jak przy migracji Mikr.us→Sferahost,
patrz `post-mortem/mikrus/vps-migration-decision.md`: "`.env` bez zmian w
kodzie").

## Krok 4 — zainstaluj restic + rclone, skopiuj sekrety offsite

```bash
sudo apt-get install -y restic rclone
```

Skopiuj też `/etc/mikrus-backup.env` (albo jego odpowiednik) ze starego
serwera — te same `RESTIC_REPOSITORY`/`RESTIC_PASSWORD` — oraz konfigurację
`rclone` dla remote'a `offsite` (`rclone config file` na starym serwerze
pokaże ścieżkę, zwykle `~/.config/rclone/rclone.conf`):

```bash
scp root@<ip-starego-coaction-test>:/etc/mikrus-backup.env /tmp/
sudo mv /tmp/mikrus-backup.env /etc/mikrus-backup.env
sudo chmod 600 /etc/mikrus-backup.env

scp -r root@<ip-starego-coaction-test>:~/.config/rclone ~/.config/
```

## Krok 5 — restic restore → `make restore` → `make up`

`backup.sh` robi `restic backup "$REPO_ROOT/backups"` na **absolutnej
ścieżce** — restic ją odtwarza jeden do jednego. Prościej więc sklonować repo na
nowym serwerze do tej samej ścieżki co na starym (`~/coaction` w przykładach
wyżej), żeby restore trafił wprost w `./backups/`:

```bash
cd ~/coaction
. /etc/mikrus-backup.env
restic snapshots                      # sprawdź, który snapshot chcesz (zwykle "latest")
restic restore latest --target /      # odtwarza $REPO_ROOT/backups z absolutną ścieżką
ls backups/                           # powinny być pliki *_<timestamp>.*
```

Jeśli ścieżka checkoutu jest INNA niż na starym serwerze, `restic restore
latest --target /tmp/restore` i przenieś ręcznie zagnieżdżony
`.../coaction/backups/*` do lokalnego `./backups/`.

Dalej dokładnie jak `make restore` w [`hard-reset.md`](hard-reset.md) /
`README.md` (sekcja Backup) — użyj timestampu z nazw plików w `./backups/`:

```bash
make restore RESTORE_TS=<timestamp>   # stopuje n8n/nocodb/minio, drop+restore DB, restore wolumenów
make up                               # odpala resztę stacku
docker compose ps                     # poczekaj aż wszystko "healthy"
```

## Krok 6 — DNS + weryfikacja

Przepnij rekordy **A** (`n8n`/`back-office`/`minio`/`chat`/`status`/`beszel`
pod `giemza.dev`) na IP nowego serwera. Sprawdź, że workflowy n8n i dane w
NocoDB widoczne są tak jak na starym stagingu — zaloguj się do obu UI i
porównaj.

Po kilku dniach stabilnej pracy: zaktualizuj `.env.local` (nowe IP/hasło),
zdecyduj o dekomisji starego `coaction-test`.
