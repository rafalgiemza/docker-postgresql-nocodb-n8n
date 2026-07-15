# FAZA 5 — Reszta pipeline'u: WF-1…WF-5 (lead → rekomendacja)

Pięć workflowów uzupełniających pipeline przed WF-6 (`n8n-workflows/wf1-nowy-lead.json` … `wf5-rekomendacja-draft.json`). Każdy to samodzielny `Webhook → Postgres → Respond` (WF-1/WF-2/WF-4) albo `Webhook → Postgres → HTTP (OpenRouter) → Postgres → Respond` z osobną gałęzią błędu (WF-3/WF-5), analogicznie do WF-6 (patrz [`offer-builder.md`](offer-builder.md)). Zweryfikowane lokalnie: `n8n import:workflow` importuje wszystkie sześć plików bez ostrzeżeń, a każde zapytanie SQL przetestowane bezpośrednio jako `n8n_crm_user` (patrz granty niżej) na fixture z `make seed-demo`.

| Workflow | Webhook path | Wejście (body) | Co robi |
|---|---|---|---|
| WF-1 — Nowy lead | `POST /webhook/nowy-lead` | `first_name, last_name, email, phone?, client_type, organization_name?, source?, contact_form?, label?` | Jedna CTE: opcjonalnie tworzy `organizations` (tylko gdy podano `organization_name`), potem `people` → `clients` → `opportunities(stage='nowa')` → `tasks` (przypisany do pierwszego aktywnego `role='sales'`). |
| WF-2 — Po discovery call | `POST /webhook/discovery-zakonczony` | `opportunity_id, scheduled_at?, ended_at?, duration_min?, external_event_id?, meeting_url?, attendees?` | `discovery_calls` insert → `opportunities.stage='badanie_potrzeb'` (trigger PG loguje do `opportunity_stage_history`) → task „Wklej / zatwierdź transkrypcję". |
| WF-3 — Ekstrakcja AI | `POST /webhook/analizuj-transkrypcje` | `discovery_call_id, language?, curated_text` | `transcripts` + `job_queue(kind='ai_extract')` insert → HTTP do OpenRouter (patrz niżej) → sukces: `extractions` insert + `job_queue.status='done'` + task dla metodyka; błąd (po 3 próbach): `job_queue.status='failed'` + task ręczny. |
| WF-4 — Zatwierdź ekstrakcję | `POST /webhook/zatwierdz-ekstrakcje` | `extraction_id, accepted_by_user_id` | `extractions.accepted_at` (brama, PRD §2.3) → `organizations.business_context` z payloadu → `participants` insert → `audits(status='planned')`, auditor wybrany po `clients.type` (B2B→Dorota, B2C→Ola, reguła z `seed.sql`) → task „Przeprowadź audyt". |
| WF-5 — Rekomendacja (draft AI) | `POST /webhook/audyt-zakonczony` | `audit_id` | SELECT kontekstu (scores CEFR, obserwacje, `hypothesis_recommendation` z ostatniej zaakceptowanej ekstrakcji) → HTTP do OpenRouter → sukces: `recommendations(approved_at=NULL)` + `recommendation_goals` (z `jsonb_array_elements ... WITH ORDINALITY`) + task zatwierdzenia; błąd: task ręczny „napisz rekomendację". |

**Uwaga o zakresie:** w przeciwieństwie do WF-6 (który operuje na `crm.v_offer_builder`), WF-1…WF-5 piszą wprost do `appdata.*` — to n8n działający jako *system* (PRD: `changed_by = NULL` = system/n8n), nie NocoDB, więc nie potrzeba tu warstwy widoków chroniącej przed schema drift (patrz `schema.sql` sekcja 15, komentarz przy grantach). Import/credential/aktywacja — identycznie jak WF-6 (patrz [`offer-builder.md`](offer-builder.md) krok 3): podepnij `appdata (n8n_crm_user)` pod każdy node Postgres, aktywuj.

## OpenRouter — credential dla WF-3/WF-5

Obie AI-gałęzie wołają `https://openrouter.ai/api/v1/chat/completions` (model `anthropic/claude-sonnet-4.5` przez OpenRouter — projekt używa `OPENROUTER_API_KEY`, nie bezpośrednio Anthropic, patrz `.env.example`). Node HTTP Request ma `retryOnFail` (3 próby, 2 s odstępu) i `onError: continueErrorOutput` — po wyczerpaniu prób leci druga gałąź (task ręczny), zamiast wywalać całe wykonanie.

W n8n UI → Credentials → New → **Header Auth**:
- Nazwa credentiala: `OpenRouter (n8n)` (tak nazywa się placeholder w plikach WF-3/WF-5)
- Header name: `Authorization`
- Header value: `Bearer <OPENROUTER_API_KEY z .env>`

Po imporcie podepnij ten credential pod node `HTTP: OpenRouter …` w obu workflowach (placeholder `REPLACE_W_UI`, tak samo jak dla Postgresa).

## Granty `n8n_crm_user` na `appdata.*`

`schema.sql` sekcja 15 rozszerzona o granty na konkretne tabele `appdata.*` (SELECT/INSERT/UPDATE, nigdy DELETE, nigdy `offers`/`offer_items`/`pricing_tiers` — to broni `crm.v_offer_builder` i trigger cenowy). Jedna pułapka wykryta przy testach: `log_opportunity_stage_change()` (trigger na `opportunities.stage`) insertuje do `opportunity_stage_history` jako invoker, nie `SECURITY DEFINER` — bez jawnego `GRANT INSERT` na tę tabelę WF-2 wywala się `permission denied`, mimo że n8n nigdy nie pisze tam wprost.
