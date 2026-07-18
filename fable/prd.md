# PRD — CoAction CRM (NocoDB + n8n + PostgreSQL)

Wersja: 1.0 · Data: 2026-07-18 · Status: faza 1 w trakcie wdrożenia

## 1. Kontekst i cel

CoAction (szkoła językowa B2B/B2C, ~5-osobowy zespół) zastępuje Asanę (za droga)
i Excela CEO (CRM w arkuszu, 35 kolumn, zdenormalizowany) jednym self-hosted
systemem: **NocoDB** (baza + widoki + formularze) + **n8n** (automatyzacje)
+ **PostgreSQL** (źródło prawdy, raporty SQL). Cel biznesowy: jedna baza danych
o leadach, spotkaniach i taskach; automatyzacja powtarzalnej pracy krok po
kroku, zaczynając od miejsc, gdzie dane wpadają ręcznie.

**Kryteria sukcesu fazy 1:** zespół pracuje wyłącznie w NocoDB (twarde cięcie
z Asaną/Excelem, historia zaimportowana), każdy widzi swoje taski i kalendarz,
lead ma czytelny timeline, nikt nie przepisuje danych między systemami.

## 2. Użytkownicy i role

| Osoba | Rola | Główne widoki |
|---|---|---|
| Przemek (CEO) | handlowiec, owner leadów, weryfikacja AI i dopasowań | kanban leads, taski, kolejka weryfikacji |
| Dorota | metodyczka B2B — cele szkoleniowe, audyty firmowe | taski, meetings (audyty), participants |
| Aleksandra | metodyczka B2C/1:1 — cele, audyty indywidualne | jw. |
| Paulina | finanse | taski cykliczne (fakturowanie) |
| Kasia | marketing | taski, projekty marketingowe |
| analityk (rola) | dobór referencji do ofert | taski, testimonials |

## 3. Zakres

**Faza 1 (ten dokument):** model danych, widoki, workflowy W1–W6b, intake
z 3 źródeł z kaskadą dopasowań, import legacy, Test Runner, lustro xlsx dla CEO
(okres przejściowy).
**Poza zakresem fazy 1:** generowanie ofert (PPTX/www), tabela `offers`,
formularze przed-audytowe, dashboardy SQL, wyszukiwanie po zamkniętej historii.

## 4. Infrastruktura

**Hosting: Sfera Host VPS PRO × 2** (KVM, 4 vCPU, 12 GB RAM, 120 GB NVMe,
dedykowane IPv4, PL) — migracja z Mikrusa (niestabilność). Dwa identyczne VPS-y,
różne domeny/hasła:

- **VPS-A = produkcja**, **VPS-B = staging/test** (target Test Runnera).
  Identyczny compose na obu; na VPS-B `WH_PREFIX=""` — osobny n8n eliminuje
  potrzebę kopii workflowów `-TEST` i prefiksów ścieżek (wystarczy sed z ID
  tabel bazy testowej tamtej instancji).
- Stack (docker compose): `postgres`, `nocodb` (8080 wewn.), `n8n` (5678 wewn.),
  `n8n-runner`, `caddy` (80/443, TLS) — kontenery aplikacyjne bez publikowanych
  portów, ruch tylko przez Caddy. Dedykowane IPv4 upraszcza wszystko względem
  Mikrusa: koniec puli portów i obejść typu Cytrus/tunnel.
- Ruch wewnętrzny po nazwach serwisów: n8n→NocoDB `http://nocodb:8080`,
  NocoDB→n8n `http://n8n:5678/webhook/...` (nie przez publiczny internet).
- **Backup (wymaganie twarde, po migracji do zrobienia od nowa):** cron
  `pg_dump` + kopia poza VPS (cross-backup A↔B to minimum; docelowo trzecia
  lokalizacja, np. S3/B2). Mikrusowe konto backupowe przestało istnieć —
  obecnie NIE MA offsite backupu, priorytet #1.
- MailHog na VPS-B jako SMTP-atrapa dla testów (UI :8025 wewn.).

## 5. Model danych (baza NocoDB, 9 tabel)

Szczegóły: `nocodb_crm_schema_v2.md`. Skrót relacji:

```
companies ──< leads ──< meetings / participants / tasks / activities
    │           └── }o--o{ testimonials
    └─────< participants ── |o--o{ meetings (audyt per osoba)
projects ──< tasks >── task_templates
```

- `leads` — szansa sprzedaży; kanban po `stage`, `state` (open/won/lost/archived),
  pipeline oferty `offer_prep_status`, statusy dopasowań `company_match_status`
  i `duplicate_check` + self-link `possible_duplicate`, licznik `enquiry_no`,
  kamienie milowe pisane przez n8n (`received_at`, `offer_sent_at`,
  `contract_sent_at`, `closed_at`), `legacy_id` (import).
- `companies` — byt trwały, `domains` jako klucz dedupu.
- `participants` — osoby szkolone (≠ kupujący); 5 ocen CEFR ze slajdów ofert.
- `meetings` — tylko realne spotkania; `transcript`, `ai_analysis` (n8n),
  maszyna stanów `processing_status`.
- `tasks` — JEDNA tabela dla całej firmy (warunek widoków "moje taski");
  markery `lead:{id}` / `meeting:{id}` w opisie wiążą taski pipeline'ów.
- `activities` — append-only log, pisze WYŁĄCZNIE n8n; timeline leada + debug
  (`flow`, `payload` JSON, typ `automation_error`).
- `task_templates` (RRULE dla W1), `projects`, `testimonials` (biblioteka
  referencji, many-to-many z leads).

**Zasady projektowe:** ludzie zmieniają statusy tam, gdzie pracują — n8n
wykonuje robotę i pisze historię; automat NIGDY nie scala po cichu (auto-akcja
tylko przy dokładnym mailu, reszta = sugestia + task); decyzje przez pola
select, nie komentarze (komentarze nie triggerują webhooków w CE); guardy
stara/nowa wartość w każdym workflow na update (triggery per-pole są płatne).

## 6. Widoki (mapowanie na wymagania)

| Wymaganie | Realizacja |
|---|---|
| moje taski ze wszystkich projektów | `tasks` Grid per osoba (filtr assignee, locked) |
| kalendarz moich tasków | `tasks` Calendar po `due_date` per osoba |
| taski cykliczne | `task_templates` + W1 (cron n8n; workflows NocoDB płatne) |
| kanban etapów leadów | `leads` Kanban po `stage`, filtr `state=open` |
| dodaj lead ręcznie | `leads` Form view |
| kalendarz spotkań | `meetings` Calendar po `starts_at` |
| timeline leada | `activities` w expanded record leada |
| kolejka weryfikacji AI | `meetings` Grid, `processing_status=ai_draft_ready` |
| produkcja ofert | `leads` Kanban po `offer_prep_status` |

## 7. Automatyzacje n8n

| WF | Trigger | Funkcja |
|---|---|---|
| W1 | cron 06:00 | taski cykliczne z szablonów (RRULE: DAILY/WEEKLY;BYDAY/MONTHLY;BYMONTHDAY), idempotentny |
| W2 | leads update | kamienie milowe + state przy zmianie stage; task "uzupełnij powód utraty"; mail do ownera |
| W3 | tasks insert+update | powiadomienie mail do assignee (łata brak notyfikacji w NocoDB CE) |
| W4 v2 | 3 webhooki: Tally / CF7 / Bookings | adaptery → wspólna kaskada dopasowań (niżej) |
| W5 | leads insert | dedup firmy po domenie e-mail (lista domen publicznych!), pending_confirmation + komentarz; guard: pomija leady z już podlinkowaną firmą |
| W6a | meetings update | transkrypcja → OpenRouter → `ai_analysis` → weryfikacja; akceptacja → cele (routing B2B→Dorota / B2C→Aleksandra); braki/odrzuty → taski naprawcze |
| W6b | leads update | cele → referencje → walidacja linków → task "złóż ofertę" + `draft_ready` |

**Kaskada intake (W4 v2):** Tier 1 dokładny e-mail (jedyna auto-akcja: otwarty
lead → task "napisał ponownie" bez nowego leada; zamknięty → nowy lead,
`enquiry_no+1`, dziedziczenie firmy) → Tier 2 domena (delegowane do W5) →
Tier 3 imię+nazwisko/telefon po normalizacji (sugestia duplikatu, nigdy
auto-merge) → Tier 4 LLM jako EKSTRAKTOR kryteriów (maile/nazwiska/firmy
z treści; deterministyczne wyszukiwanie po ekstrakcji; `type_signal` dla B2B
z prywatnego maila) → Tier 5 czysty nowy lead + task "zaklasyfikuj".
Booking z MS Bookings zawsze tworzy meeting i linkuje do leada z kaskady.
Każdy przebieg loguje do `activities` (kryteria AI w payload).

**Integracje:** Tally (natywny webhook), Contact Form 7 (wymaga wtyczki
webhook na WP; mapa pól w adapterze), MS Bookings (przez Power Automate →
HTTP POST), OpenRouter (model konfigurowalny per env).

## 8. Migracja danych

`import_legacy_excel.py`: Excel CEO → NocoDB. Selecty normalizowane do realnych
opcji; 12 kolumn dat → kamienie milowe + rekordy meetings (done); planowane
działania → otwarte taski; `enquiry_no` liczony z historii; pełny surowy wiersz
w payload activity (nic nie ginie); idempotencja po `legacy_id`.
**Procedura:** pola `legacy_id`+`received_at` → `--dry-run` → uzupełnienie
STAGE_MAP wg raportu → wyłączenie W3/W4/W5 → import → włączenie workflowów.
Okres przejściowy: `legacy_crm_2.xlsx` — read-only lustro generowane od zera
z widoku SQL `legacy_crm_mirror` (Postgres → n8n → xlsx), układ kolumn 1:1 ze
starym Excelem + kolumna linków do rekordów NocoDB; sunset ~2 mies. po migracji.
(Widok SQL do napisania po migracji — czeka na `\dt`/`\d` z nowego Postgresa.)

## 9. Testy

Test Runner (pytest, katalog 63 przypadków w `tests/test_cases.md`): syntetyczne
payloady webhooków NocoDB → endpointy n8n → asercje przez API. ~25 przypadków
AUTO zaimplementowanych (guardy, kaskada, pułapki typu substring domen);
SEMI = LLM z asercjami strukturalnymi; PROC = importer przez dry-run.
Po migracji na 2 VPS-y: runner celuje w VPS-B (osobna instancja = koniec kopii
workflowów i prefiksów).

## 10. Artefakty projektu

| Plik | Zawartość |
|---|---|
| `nocodb_crm_schema_v2.md` | pełny schemat 9 tabel + zasady |
| `crm_flow.mermaid`, `crm_erd.mermaid`, `crm_intake_matching.mermaid` | diagramy: cykl życia leada, ERD, kaskada intake |
| `W1..W6b*.json` + `README.md` (`n8n_workflows_coaction.zip`) | importowalne workflowy + instrukcja placeholderów/webhooków |
| `W4v2_intake_matching.json` | intake 3 źródeł + kaskada (zastępuje W4) |
| `W0_seed_sample_data.json`, `seed_nocodb.py`, `sample_data_overview.md` | dane przykładowe (2 drogi) + mapa relacji |
| `import_legacy_excel.py` | migracja legacy z dry-run |
| `test_runner_coaction.zip` (`tests/`) | katalog przypadków + harness pytest |

## 11. Znane ograniczenia i ryzyka

1. **Brak offsite backupu po migracji** — otwarte, priorytet #1.
2. NocoDB CE: brak powiadomień push/apki mobilnej (łatane przez W3 mail),
   jedna aktywna sesja per konto (ryzyko UX telefon+laptop — do weryfikacji
   na bieżącej wersji), triggery per-pole płatne (stąd guardy), komentarze
   bez webhooków, filtrowane rollupy płatne (raporty → SQL na Postgresie).
3. Kształt payloadów webhooków NocoDB różni się między wersjami (pole User:
   obiekt/tablica) — guardy pisane defensywnie; po każdym upgrade NocoDB
   przebieg Test Runnera na VPS-B PRZED aktualizacją produkcji.
4. Tier 3/4 matchuje tylko otwarte leady i firmy (limit 200) — świadoma
   granica; przy skali setek zapytań/mies. → wyszukiwanie w Postgresie.
5. Wiązanie tasków pipeline'ów markerami w opisie — nie edytować ręcznie.
6. Seed i import nie są transakcyjne — seed tworzy duplikaty przy re-runie
   (importer nie, dzięki `legacy_id`).

## 12. Backlog (faza 2)

Tabela `offers` + generowanie oferty PPTX/www z pól `participants` i
`testimonials`; formularze przed-audytowe dla uczestników; AI-draft
`needs_summary` z transkrypcji; dashboard SQL (czas new→won, konwersja per
source, per branża); asercje mailowe w Test Runnerze (MailHog API); rozszerzenie
parsera RRULE (YEARLY/INTERVAL); wyszukiwanie po zamkniętej historii (Postgres
FTS); sunset lustra xlsx.

## 13. Status / najbliższe kroki

- [x] schemat, seed (przeszedł na realnej bazie), workflowy, importer, testy — dostarczone
- [ ] migracja stacku Mikrus → Sfera VPS-A/B (compose + Caddy + DNS)
- [ ] **backup offsite** (pg_dump + cross-copy A↔B minimum)
- [ ] podmiana placeholderów workflowów na ID z nowej instancji (sed per VPS)
- [ ] wtyczka webhook CF7 na WordPressie + realny payload → mapa pól adaptera
- [ ] Power Automate dla Bookings → adapter
- [ ] dry-run importu na pełnym Excelu → STAGE_MAP → import na produkcji
- [ ] widok SQL `legacy_crm_mirror` + workflow lustra (po dostarczeniu `\dt`/`\d`)
- [ ] przebieg Test Runnera na VPS-B → poprawka builderów payloadów pod realną wersję NocoDB
- [ ] rollout zespołowy: pokaz `crm_flow.mermaid`, widoki per osoba, data twardego cięcia
