# Nowy VPS-B (staging) — postawienie od zera

Runbook do wymiany obecnego `coaction-test` (VPS-B, staging, Sferahost) na nowy
serwer, gdy dane na starym stagingu są jednorazowe/testowe i nie trzeba ich
zachować. Jeśli trzeba przenieść realne workflowy n8n / dane NocoDB ze starego
stagingu, użyj zamiast tego
[`staging-vps-restic-migration.md`](staging-vps-restic-migration.md).

## Krok 0 — sprawdź CPU passthrough PRZED instalacją czegokolwiek

Sferahost potrafi postawić VM z domyślnym, konserwatywnym modelem CPU
(`QEMU Virtual CPU`, brak SSE3+/AVX) dopóki support ręcznie nie włączy
`host-passthrough` — dokładnie to samo uderzyło przy stawianiu obecnych
VPS-A/VPS-B (2026-07-17, patrz
[`post-mortem/mikrus/vps-migration-decision.md`](../post-mortem/mikrus/vps-migration-decision.md)),
crashloopując MongoDB (`requires a CPU with AVX support`) i MinIO
(`CPU does not support x86-64-v2`).

```bash
lscpu | grep -E "Model name|Flags" | head -5
lscpu | grep -o 'avx[0-9]*' | sort -u   # pusty wynik = brak AVX
```

Jeśli brak `avx`/`avx2` we flagach — zgłoś do supportu Sferahost prośbę o
`host-passthrough` na tej VM i **czekaj na potwierdzenie zanim pójdziesz
dalej** (MongoDB dla LibreChat inaczej nie wystartuje).

## Krok 1 — bootstrap systemu (Docker, user `deploy`, firewall, fail2ban)

Panel Sferahost nie wstrzykuje cloud-init user-data przy tworzeniu VM, więc
[`vps/init-mikrus.yaml`](../vps/init-mikrus.yaml) odpalamy ręcznie jako
zwykły skrypt bash po SSH (root) — pełna, przetestowana wersja poleceń jest
w historii tej rozmowy / czatu, w skrócie: apt update+upgrade, repo Dockera,
pakiety (`docker-ce` + compose plugin, `fail2ban`, `ufw`, `unattended-upgrades`),
user `deploy` (sudo+docker, tylko klucz SSH, hasło zablokowane),
`sshd_config.d/99-hardening.conf` (`PermitRootLogin no`,
`PasswordAuthentication no`), `ufw allow OpenSSH/80/443`.

**Zanim zamkniesz sesję roota** — zaloguj się w nowym oknie jako
`ssh deploy@<ip>` i sprawdź `docker ps`, żeby nie zostać zablokowanym.

## Krok 2 — sklonuj repo i wygeneruj `.env`

```bash
ssh deploy@<ip-nowego-serwera>
git clone <url-repo> coaction && cd coaction
make init-env      # ./scripts/generate-env.sh — .env z .env.example, losowe sekrety
```

Domeny w `.env.example` (`N8N_HOST=n8n.giemza.dev`,
`NC_HOST=back-office.giemza.dev`, `MINIO_HOST=minio.giemza.dev`,
`LIBRECHAT_HOST=chat.giemza.dev`, `STATUS_HOST=status.giemza.dev`,
`BESZEL_HOST=beszel.giemza.dev`) to właśnie środowisko UAT/staging — **nie
trzeba ich zmieniać**, tylko przepiąć DNS (Krok 3). Zweryfikuj mimo to
`N8N_HOST`/`NC_HOST`/`WEBHOOK_URL` ręcznie (patrz
[`hard-reset.md`](hard-reset.md) punkt 3) na wypadek gdyby konwencja się
zmieniła.

```bash
make config   # waliduje złożony compose (fragments/*.yml)
make up       # odpala cały stack w tle
docker compose ps   # poczekaj aż wszystko "healthy"
```

## Krok 3 — DNS

W panelu, gdzie zarządzana jest domena `giemza.dev` (Cloudflare — patrz
`.ai/IMPLEMENTATION_PLAN.md` FAZA 7), przepnij rekordy **A** dla
`n8n`/`back-office`/`minio`/`chat`/`status`/`beszel` z IP starego
`coaction-test` na IP nowego serwera.

## Krok 4 — jednorazowy bootstrap kont + schemat + dane

Dokładnie jak w [`hard-reset.md`](hard-reset.md) od "Krok 0" w dół:
NocoDB sign-up + External Source na `appdata`/`crm`, API token, n8n owner
setup, potem:

```bash
make init-schema   # 16 tabel CRM w NocoDB (Meta API)
make init-data     # leads/companies/participants z historycznego Excela
make seed-extra    # opcjonalnie: dane testowe do pozostałych tabel — NIE na prod
```

n8n: zaimportuj workflowy z `docs/archive/fable/W*.json` (Workflows → Import
from File), podepnij credentiale, aktywuj.

## Krok 5 — weryfikacja i sprzątanie

Odpal zapytania weryfikacyjne z końca [`hard-reset.md`](hard-reset.md)
("Weryfikacja że baza faktycznie istnieje"). Po kilku dniach stabilnej pracy
nowego serwera:

- zaktualizuj swoje notatki (`.env.local`) o nowy adres IP / hasło roota,
- zdecyduj o dekomisji/anulowaniu starego `coaction-test` na Sferahost.
