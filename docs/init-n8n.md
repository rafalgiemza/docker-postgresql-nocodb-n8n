# Podłączenie n8n do Postgresa (node PostgreSQL)

n8n nigdy nie łączy się jako superuser — używa osobnej, ograniczonej roli. **Są dwa różne credentiale do dwóch różnych baz — łatwo je pomylić:**

- **n8n (własna baza n8n)** — §1/§2 poniżej. Node Postgres z tym credentialem widzi tylko `public`/`pg_catalog`/tabele wewnętrzne n8n (`workflow_entity`, `execution_entity`, ...) — **nigdy appdata/crm**. Jeśli w node'zie Postgres widzisz tylko `public` i tabele meta, to właśnie ten credential jest podpięty zamiast poniższego.
- **appdata (CRM)** — §3 poniżej. Ten credential trzeba dodać osobno, żeby workflowy CRM (`n8n-workflows/wf1..wf6*.json`) widziały schematy `appdata`/`crm`.

## 1. Pobranie danych logowania (baza n8n)

Na hoście, w katalogu repo:

```bash
grep -E "^POSTGRES_(NON_ROOT_USER|NON_ROOT_PASSWORD|DB)=" .env
```

## 2. Konfiguracja credentiala w n8n do własnej bazy n8n (node Postgres)

- **Host**: `postgres` (nazwa serwisu w sieci docker-compose)
- **Port**: `5432`
- **Database**: wartość `POSTGRES_DB`
- **User**: wartość `POSTGRES_NON_ROOT_USER`
- **Password**: wartość `POSTGRES_NON_ROOT_PASSWORD`
- **SSL**: wyłączone (ruch wewnątrz sieci docker)

Jeśli n8n łączy się spoza sieci compose (inny host / zdalnie), host/port będą inne — do ustalenia osobno.

## 3. Konfiguracja credentiala w n8n do appdata (CRM)

To jest credential, którego faktycznie potrzebują workflowy CRM (`n8n-workflows/wf1..wf6*.json`), np. WF-6 "Zatwierdź ofertę" pisze/czyta `crm.v_offer_builder`. Rola `n8n_crm_user` jest ograniczona: `REVOKE ALL` na `appdata`/`public`, dostęp scoped per-tabela (`schema.sql` §15).

Dane logowania:
```bash
grep -E "^(N8N_CRM_USER|N8N_CRM_PASSWORD|APP_DB)=" .env
```

Konfiguracja credentiala (**New Credential → Postgres**):
- **Host**: `postgres`
- **Port**: `5432`
- **Database**: wartość `APP_DB` (domyślnie `appdata`)
- **User**: wartość `N8N_CRM_USER` (domyślnie `n8n_crm_user`)
- **Password**: wartość `N8N_CRM_PASSWORD`
- **SSL**: wyłączone
- **Nazwa credentiala**: `appdata (n8n_crm_user)` — dokładnie taka, jakiej oczekują node'y w zaimportowanych workflow JSON, żeby podpięcie było wyborem z listy, nie zgadywaniem.

Ten credential jest też tworzony automatycznie przez `make wire-apps` (`scripts/crm-wire-init.sh`, patrz `docs/init-nocodb.md`) — powyższe kroki są potrzebne tylko do ręcznego odtworzenia/debugowania, gdy automatyzacja zawiedzie.
