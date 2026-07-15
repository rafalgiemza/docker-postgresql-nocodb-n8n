# LibreChat — czat AI dla zespołu (PRD §1.1)

Zero kroków ręcznych dla samych kontenerów — `make up` startuje `mongodb`+`librechat` tak samo jak resztę stacku. Celowo minimalna instalacja: tylko LibreChat + własna MongoDB (`MONGO_URI`), **bez** admin-panelu/Meilisearch/RAG API/pgvector z domyślnego compose upstream — żadne z nich nie są w zakresie MVP ani w budżecie RAM z PRD (tabela w §1.1 liczy tylko LibreChat 600 MB + MongoDB 500 MB). Zero integracji z danymi CRM w Postgresie — to świadomie osobny byt.

Pierwsza osoba z zespołu zakłada konto sama przez UI pod `LIBRECHAT_HOST` — rejestracja jest domyślnie otwarta (`ALLOW_REGISTRATION=true`). Gdy zespół już ma konta, przełącz `ALLOW_REGISTRATION=false` w `.env` i zrób `make down && make up` — dalsze konta wymagają wtedy ręcznego `docker exec ... npm run create-user`.

**Gotcha:** `librechat.yaml` konfiguruje jeden custom endpoint (OpenRouter), reużywając istniejący `OPENROUTER_API_KEY` (ten sam, którego używa n8n) zamiast trzymać drugi sekret. LibreChat czyta klucz endpointu z env var o dokładnie tej nazwie, jaka jest w yamlu — stąd rebind we fragmentach compose (`fragments/librechat.yml`): `OPENROUTER_KEY=${OPENROUTER_API_KEY}`. Nazwanie tego wprost `OPENROUTER_API_KEY` przekierowałoby też wbudowany endpoint OpenAI LibreChata przez OpenRouter, czego nie chcemy.

**Ready-to-migrate (PRD §8.7) — dokupienie zewnętrznego/managed Mongo:** LibreChat rozmawia z Mongo wyłącznie przez `MONGO_URI`, domyślnie wskazujący na lokalny kontener `mongodb` (serwis pod profilem `local-mongo`, aktywowanym przez `COMPOSE_PROFILES` w `.env`). Podmiana na zewnętrzny Mongo to czysta zmiana `.env`, zero edycji compose:
1. `MONGO_URI` → connection string od dostawcy (np. Atlas)
2. `COMPOSE_PROFILES=` (puste) — lokalny kontener `mongodb` przestaje się odpalać
3. `make down && make up`

`librechat`'s `depends_on: mongodb` ma `required: false` właśnie po to, żeby start nie blokował się na nieistniejącym (bo odgaszonym profilem) lokalnym kontenerze.

**Prod:** wymaga rekordu DNS dla `LIBRECHAT_HOST` (`chat.<domena>`) wskazującego na ten sam adres VPS co `N8N_HOST`/`NC_HOST`/`MINIO_HOST` — bez niego Caddy nie wystawi certu.

**Dev vs prod — `LIBRECHAT_URL`:** jeden `docker-compose.yml` dla obu środowisk (patrz `fragments/librechat.yml`) — `DOMAIN_CLIENT`/`DOMAIN_SERVER` (cookie-domain/CORS w LibreChat) czytają pełny scheme+host z `LIBRECHAT_URL` w `.env`, osobno od `LIBRECHAT_HOST` (który służy tylko routingowi w Caddyfile). W dev LibreChat jest też zawsze dostępny bezpośrednio na `127.0.0.1:3080` (bez Caddy) — `LIBRECHAT_URL` musi się wtedy zgadzać z tym, co faktycznie widzi przeglądarka (`http://localhost:3080`), inaczej logowanie/sesja się wysypie. Patrz komentarz przy `LIBRECHAT_URL` w [`.env.example`](../.env.example).
