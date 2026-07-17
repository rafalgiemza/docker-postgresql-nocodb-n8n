# Decyzja: migracja VPS z Mikr.us na Sferahost

## Kontekst

Po powtarzającym się incydencie dysku I/O na Mikr.us (`post-mortem/logs.md` — 2026-07-14, oraz gorszy powtórka 2026-07-15, ~1.5h cykli fsync-stall → Postgres crash-recovery → 503 na n8n/MinIO/librechat) Mikr.us support zaproponował migrację na nowszy hardware, ale efekt nie został jeszcze zweryfikowany jako trwale naprawiony.

Niezależnie od tego, admin Mikr.us zaproponował dodatkowy płatny dodatek "Cytrus" (~30 zł/mies.) tylko po to, żeby serwer miał adres IPv4 — potrzebny, bo domena klienta (`coaction.pl`) jest zarządzana przez panel Sferahost, a nie przez Cloudflare (jak testowa `giemza.dev` z FAZA 7 w `.ai/IMPLEMENTATION_PLAN.md`), więc nie ma proxy maskującego brak IPv4.

**Dane diagnostyczne (2026-07-17, Beszel, obecny Mikr.us 8GB):** CPU 28.4%, RAM 87% (~7GB/8GB w użyciu), dysk 17.8%, **średnie obciążenie ~125–137** przy jednoczesnym `%steal=0.00` (z wcześniejszej diagnozy iostat) — sygnatura procesów utkniętych w disk-wait (stan D czekający na fsync hosta), nie przeciążenia CPU. Spójne z hipotezą z `logs.md`.

## Decyzja

**Klient zaakceptował 2026-07-17** przejście na nowy serwer zamiast dokładania do Mikr.us (Cytrus + niepewna naprawa I/O):

**Sferahost VPS PRO** (https://sferahost.pl/store/litosfera-vps-nvme):

| Parametr | Wartość |
|---|---|
| Lokalizacja | Polska |
| Dysk | 120 GB NVMe |
| Transfer | nielimitowany (Fair Use) |
| Łącze | do 500 Mbps |
| vCPU | 4 (współdzielone) |
| RAM | 12 GB |
| IPv4 | 1 adres w cenie |
| IPv6 | darmowe adresy |
| Wirtualizacja | KVM |
| Rozliczenie | miesięczne, bez umowy długoterminowej |
| Cena | 59 PLN netto/mies. (najniższa cena z ostatnich 30 dni: 79 PLN netto) |

**Uzasadnienie:**
- NVMe zamiast obecnego storage adresuje bezpośrednio przyczynę fsync-stalli (host-level I/O saturation, nie problem konfiguracji n8n/Postgresa).
- IPv4 w cenie eliminuje potrzebę Cytrusa i rozwiązuje problem domeny klienta niespiętej z Cloudflare.
- 12 GB RAM / 4 vCPU daje realny zapas nad obecnym zużyciem (~7GB/8GB = 87%) — RARE (6GB) był rozważany, ale odrzucony jako zbyt ciasny.
- Rozliczenie miesięczne bez lock-inu — niskie ryzyko migracji.

Kontekst pełnej dyskusji i propozycji do klienta: e-mail wysłany na bazie szkicu z tej sesji (nie w repo, prywatna korespondencja).

## Do zrobienia (migracja)

- [ ] Provisioning nowego VPS PRO na Sferahost.
- [ ] Restore drill na nowym serwerze (dumpy `n8n`/`nocodb`/`appdata` + role + `.env` + MinIO) — to i tak było wymagane przed oddaniem projektu (`.ai/IMPLEMENTATION_PLAN.md` FAZA 6, punkt 4), teraz staje się właściwą migracją, nie tylko drillem.
- [x] **IPv4 potwierdzone dostępne** na nowym VPS (2026-07-17) — skoro `coaction.pl` i tak nie jest proxowana przez Cloudflare, model sieciowy upraszcza się do zwykłego rekordu **A (IPv4)** w panelu Sferahost, bez zależności od IPv6. Caddy dalej robi automatic HTTPS na 80/443 bez zmian.
- [x] Zaktualizować `.ai/IMPLEMENTATION_PLAN.md` FAZA 7 zgodnie z powyższym (A record zamiast AAAA, brak zależności od Cloudflare proxy).
- [ ] Cutover: podmiana DNS klienta (`coaction.pl` → rekord A na nowy adres IPv4), `.env` (`N8N_HOST`/`NC_HOST`/`WEBHOOK_URL`/itd.) bez zmian w kodzie.
- [ ] Weryfikacja end-to-end (n8n, NocoDB, MinIO, LibreChat, Kuma) na nowym serwerze przed dekomisją Mikr.us.
- [ ] Reklamacja/zwrot do Mikr.us za przerwy w działaniu (niezależny tor, nie blokuje migracji).
- [ ] Dekomisja/anulowanie starego VPS Mikr.us po potwierdzeniu stabilności nowego przez kilka dni.

Powiązane: `post-mortem/logs.md`, `post-mortem/tasks.md` (Task 3 — autoheal, wciąż aktualny na nowym serwerze).

## Aktualizacja (2026-07-17): CPU passthrough na Sferahost + pinowanie wersji obrazów

Pierwszy deploy na VPS PRO od razu ujawnił nowy problem: `mongodb` (`MongoDB 5.0+ requires a CPU with AVX support`, exit 132) i `minio` (`Fatal glibc error: CPU does not support x86-64-v2`, exit 127) crash-loopowały. `lscpu` na gościu pokazał `Model name: QEMU Virtual CPU version 2.5+` i `BIOS Model name: RHEL 7.6.0 PC (i440FX + PIIX, 1996)` — flagi kończące się na SSE2, brak nawet SSE3. To domyślny, konserwatywny model CPU typowy dla platform typu oVirt/RHV (nazewnictwo `pc-i440fx-rhel7.6.0`), nie realne ograniczenie fizycznego hosta — Sferahost nie miał ustawionego `host-passthrough` dla tej VM.

**Zgłoszone do supportu Sferahost i naprawione** — CPU passthrough włączony, nowoczesne flagi (SSE4.2/AVX/AVX2) teraz widoczne w gościu.

**Przy okazji odkryte: MinIO Community Edition jest martwe.** Repo `minio/minio` oznaczone "no longer maintained" w lutym 2026, zarchiwizowane na stałe 25 kwietnia 2026 — firma przeszła w całości na płatny AIStor. `RELEASE.2025-10-15T17-29-55Z` to ostatni release, jaki kiedykolwiek powstanie dla OSS. Niezależnie od CPU, to osobna decyzja do podjęcia przed rozbudową `crm-api`/offer-buildera (PRD §8.4-8.6) o MinIO: zamrozić ten ostatni release na stałe, czy przesiąść się na aktywnie rozwijaną alternatywę (Garage, SeaweedFS) zanim powstanie integracja S3 SDK w `crm-api`. Na razie: zamrożone, nie zdecydowane docelowo.

**Wersje obrazów w `.env.example` zaktualizowane, żeby uniknąć `latest`:**
- `MONGO_VERSION=8.0.20` — dokładnie ta wersja, którą przypina własny `docker-compose.yml` LibreChat (nie major-only `7`, nie `latest`) — omija [znany bug](https://github.com/danny-avila/LibreChat/issues/10304) przy skoku między wersjami major bez migracji `featureCompatibilityVersion`.
- `MINIO_VERSION=RELEASE.2025-10-15T17-29-55Z` — jawne przypięcie ostatniego OSS release'u zamiast domyślnego `latest`, które od teraz i tak zawsze wskazywałoby na dokładnie ten sam obraz (projekt martwy), ale jawnie jest czytelniejsze niż niejawnie.

### Do zrobienia (dopisane)

- [ ] Zdecydować docelowo: zamrożone MinIO OSS czy migracja na Garage/SeaweedFS — zanim `crm-api` (FAZA 3 w `.ai/IMPLEMENTATION_PLAN.md`) zbuduje na nim integrację S3.
- [ ] Potwierdzić u Sferahost, że `host-passthrough` przetrwa ewentualny restart/migrację VM między hostami w ich klastrze (nie tylko jednorazowa zmiana).
