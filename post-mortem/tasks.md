# Post-mortem follow-up: monitoring/alerting + restart-policy audit

## Context

`post-mortem/logs.md` documents a real incident on 2026-07-14: a ~25-minute host-level disk I/O stall on the VPS (Proxmox) caused Postgres fsync calls to take 170–220s, which broke n8n's connection (`Broken pipe`) and pushed Postgres into crash-recovery loops (`503 Database is not ready!` for end users). The DB itself is tiny (5 executions, 14MB) so pruning was ruled out as a cause — this was purely a host storage stall. The post-mortem recommends two concrete follow-ups:

1. Add monitoring/alerting so incidents like this are caught in real time instead of by users reporting 503s.
2. Confirm/harden `restart: unless-stopped` across containers, not just Postgres.

These are tracked as two separate tasks, to be implemented independently.

Notably, task 2's premise turned out to be already mostly satisfied: every long-running service in `docker/docker-compose.yml` already has `restart: unless-stopped` (postgres, n8n, n8n-runner, nocodb, minio, mongodb, librechat, caddy). `minio-init` is intentionally `restart: 'no'` (one-shot job, already commented as such). The real gap is two missing **healthchecks** (`n8n-runner`, `caddy`), not restart policy.

Also, monitoring is not a new idea — `.ai/IMPLEMENTATION_PLAN.md` (FAZA 1, item 3) and `.ai/PRD.md` already call for **Uptime Kuma** (~120MB RAM budget, monitor everything + disk + cert expiry, exposed behind Caddy on a `status.` subdomain) but it was never implemented (❌ in the status table). This post-mortem is the trigger to finally build it.

---

## Task 1 — Add Uptime Kuma monitoring/alerting

- [x] Add `uptime-kuma` service to `docker/docker-compose.yml` (image `louislam/uptime-kuma:1`), `restart: unless-stopped`, own named volume (`kuma_storage`), resource limits similar to nocodb. Also labeled `autoheal=true` (Task 3).
- [x] Add healthcheck, matching other services' pattern.
  - Verified live: `wget -qO- http://localhost:3001` (the pattern used elsewhere) fails with `wget: not found` — this image has `curl` but no `wget`. Switched to Kuma's own bundled `/app/extra/healthcheck` binary, the same one upstream's own Dockerfile uses for its `HEALTHCHECK`. Confirmed `docker-uptime-kuma-1` reaches `healthy`.
- [x] Add `STATUS_HOST` env var to `docker/.env.example` (mirrors `N8N_HOST`/`NC_HOST`/`MINIO_HOST`/`LIBRECHAT_HOST`).
- [x] Add `{$STATUS_HOST} { reverse_proxy uptime-kuma:3001 }` block to `docker/Caddyfile`.
- [x] Add `STATUS_HOST` to `caddy` service's `environment:` in `docker-compose.yml`/`docker-compose.prod.yml`, and `depends_on: uptime-kuma`.
- [x] Add dev port mapping (`3001:3001`) for `uptime-kuma` in `docker/docker-compose.override.yml`.
- [ ] Manual step (not code): configure monitors + alert channels (Discord/Telegram webhook) inside the Kuma web UI after first boot — stored in Kuma's own SQLite DB, no new secrets needed in `.env`.
- [x] Update `.ai/IMPLEMENTATION_PLAN.md` status table (Uptime Kuma row) from ❌ to ✅.

Files touched: `docker/docker-compose.yml`, `docker/docker-compose.override.yml`, `docker/Caddyfile`, `docker/.env.example`, `.ai/IMPLEMENTATION_PLAN.md`.

## Task 2 — Restart-policy / healthcheck audit

- [x] Add `healthcheck:` to `n8n-runner` in `docker/docker-compose.yml` (currently none) — check what health/metrics endpoint the `n8nio/runners` image exposes; if none exists, document that explicitly rather than fabricating one.
  - Verified by `docker exec` + `ss -tlnp` against a running container: the bundled task-runner-launcher listens on port 5680 (`/healthz`), not 5681 as the launcher's own docs implied — that per-runner health server isn't actually exposed here.
- [x] Add `healthcheck:` to `caddy` (currently none in either `docker-compose.yml` or `docker-compose.prod.yml`) — e.g. `wget -qO- http://localhost:2019/config/` (Caddy's admin API) or a simpler TCP check.
  - Used Caddy's admin API on `127.0.0.1:2019/config/` (not `localhost` — same IPv6-first pitfall already documented for the librechat healthcheck). Confirmed it survives the `docker-compose.prod.yml` overlay merge (only `image`/`ports`/`environment`/`volumes`/`depends_on` are overridden there), so no prod.yml changes needed.
- [x] No changes needed for `restart:` itself anywhere — document this finding (e.g. short note in `docker/docs/docker.md`) so it's not re-investigated later.
  - Documented in `docker/docs/docker.md` under "Restart Policy & Healthcheck Audit (2026-07-14)".

Files touched: `docker/docker-compose.yml`, `docker/docker-compose.prod.yml` (if caddy healthcheck needs restating there), possibly `docker/docs/docker.md`.

## Task 3 — Auto-restart on `unhealthy` (autoheal)

Triggered by a live incident on 2026-07-14 evening: n8n silently stopped responding for a few minutes with no crash, no restart, and no trace in either container's logs — a manual `docker restart docker-n8n-1` fixed it. Root cause: Docker's own healthcheck only ever marks a container `unhealthy`, it never restarts it — `restart: unless-stopped` only reacts to the container process exiting, not to a failing healthcheck. Task 2's healthchecks were necessary but not sufficient on their own.

- [x] Add `autoheal` service (`willfarrell/autoheal:latest`) to `docker/docker-compose.yml` — watches the Docker socket, restarts any container labeled `autoheal=true` once `unhealthy` for `AUTOHEAL_INTERVAL` (10s).
- [x] Label every service that already has a healthcheck (`postgres`, `n8n`, `n8n-runner`, `nocodb`, `minio`, `mongodb`, `librechat`, `caddy`) with `autoheal=true`.
- [x] **Found and fixed a real bug while testing this**: n8n's healthcheck hit `/healthz` (liveness-only, never reflects DB state — known n8n issue [n8n-io/n8n#10274](https://github.com/n8n-io/n8n/issues/10274)), confirmed live when `docker ps`/`make ps` showed n8n `healthy` while the UI was actually showing `{"code":503,"message":"Database is not ready!"}`. Switched the healthcheck to `/healthz/readiness`, which actually checks DB connection/migration state — without this fix, neither Docker's health status nor `autoheal` would ever react to this exact failure mode. Also updated `docker/simulate-pg-crash.sh` to poll `/healthz/readiness` instead of `/healthz`.
- [x] Validated both `docker compose -f docker-compose.yml config` and the `-f docker-compose.prod.yml` overlay parse cleanly.
- [ ] Deploy (`docker compose up -d` — only recreates the changed services + adds the new `autoheal` container, no full-stack restart needed) and confirm `docker ps` shows `docker-autoheal-1` running and n8n's health status still flips to `healthy` against the new endpoint.
- [ ] Verify end-to-end: run `docker/simulate-pg-crash.sh` (or manually stop a labeled service responding) and confirm autoheal actually restarts it — check `docker logs docker-autoheal-1` for the restart event.

Files touched: `docker/docker-compose.yml`, `docker/simulate-pg-crash.sh`.

---

## Verification

- `docker compose -f docker-compose.yml config` (and with `-f docker-compose.prod.yml`) to confirm both compose files still parse correctly after edits.
- `make up` locally, then `docker ps` to confirm `uptime-kuma` reaches `healthy` and `caddy`/`n8n-runner` show a health status instead of none.
- Hit `http://localhost:3001` (dev) to confirm Kuma's setup wizard loads; create one test monitor (e.g. against n8n's `/healthz`) to confirm end-to-end alerting works before considering Task 1 done.
- `curl -sI https://${STATUS_HOST}` against the VPS after prod deploy to confirm Caddy is routing correctly (TLS cert issued).
