# Task: odzyskiwanie hasła w LibreChat

## Context

Klient ma skrzynki pocztowe w domenie `coaction.pl`. Potrzebny jest self-service reset hasła dla użytkowników LibreChat (dziś: rejestracja domenowo ograniczona do `coaction.pl` w `librechat.yaml`, `ALLOW_REGISTRATION=true`, brak jakiejkolwiek konfiguracji mailowej w `.env.example`/`fragments/librechat.yml` — potwierdzone grepem, zero `EMAIL_*`/`SMTP` w repo). Dziś jedyna ścieżka to ręczny reset przez `docker exec ... mongosh` (patrz `docs/librechat-users-manage.md`), co nie skaluje się poza Rafała.

## Decyzja

**Użyć natywnego mechanizmu resetu hasła w LibreChat** (formularz „Forgot password" już istnieje w UI logowania), podpiętego pod SMTP jednej ze skrzynek `coaction.pl` (np. `noreply@coaction.pl`) przez zmienne `EMAIL_*` w `.env`. Zero custom kodu — LibreChat sam generuje token, wysyła link resetujący i waliduje go.

**Odrzucone: n8n/NocoDB jako nośnik resetu.** LibreChat trzyma hasła i tokeny resetu we własnej Mongo — obejście natywnego flow wymagałoby albo wyłączenia go i budowania równoległej logiki (webhook w n8n generujący token, zapis bezpośrednio do Mongo, wysyłka linku), czyli duplikowania czegoś, co LibreChat już robi bezpiecznie, albo trzymania kolejnego sekretu/uprawnienia do bazy Mongo poza samą aplikacją. Sensowne tylko jako fallback, gdyby SMTP dla `coaction.pl` był niedostępny (np. tylko webmail bez danych SMTP) — wtedy n8n mógłby wysyłać przez inny kanał.

## Otwarte pytanie (blokujące)

Czy mamy dane SMTP do skrzynki na `coaction.pl` (host/port/login/hasło) do użycia jako nadawca maili resetujących? Bez tego nie da się ruszyć z implementacją — pytanie zadane użytkownikowi, odpowiedź jeszcze nie potwierdzona w tej rozmowie (permission prompt padł przed odpowiedzią).

## Zadania (do wykonania po potwierdzeniu SMTP)

- [ ] Potwierdzić dane SMTP dla skrzynki nadawczej `coaction.pl` (host, port, encryption, login, hasło) — od klienta/dostawcy hostingu poczty.
- [ ] Zweryfikować dokładne nazwy zmiennych `EMAIL_*` obsługiwane przez wersję LibreChat wpiętą w projekcie (`LIBRECHAT_VERSION` w `.env.example`) — sprawdzić upstream docs/`.env.example` LibreChat dla tego tagu, nie zakładać z pamięci.
- [ ] Dodać `EMAIL_*` (host/port/username/password/from/from_name) do `.env.example` (placeholdery) i `.env`/`.env.prod` (realne wartości, ręcznie — patrz zasada „nie modyfikować .env.* automatycznie").
- [ ] Zrebindować `EMAIL_*` w `environment:` serwisu `librechat` w `fragments/librechat.yml`, analogicznie do istniejącego wzorca (`OPENROUTER_KEY=${OPENROUTER_API_KEY}`).
- [ ] Sprawdzić, czy trzeba dodatkowo ustawić flagę włączającą reset hasła (do zweryfikowania w docs dla przypiętej wersji — w części wersji LibreChat jest to zawsze aktywne, gdy `EMAIL_*` skonfigurowane).
- [ ] `make down && make up`, przetestować end-to-end: „Forgot password" na `LIBRECHAT_URL` → mail dociera → link resetuje hasło → logowanie nowym hasłem działa.
- [ ] Zaktualizować `docs/librechat.md` o sekcję resetu hasła (gotcha z nazwą zmiennej env, jeśli jakaś wystąpi, analogicznie do gotchy z `OPENROUTER_KEY`).

## Pliki do zmiany

`.env.example`, `.env`/`.env.prod` (ręcznie), `fragments/librechat.yml`, `docs/librechat.md`.

## Weryfikacja

- `docker compose config` po zmianach w fragmencie, żeby potwierdzić że compose nadal się parsuje.
- Realny test „Forgot password" w przeglądarce (dev: `http://localhost:3080`, prod: `LIBRECHAT_URL`) — nie tylko wysyłka maila, ale też że link faktycznie resetuje hasło w Mongo i logowanie nowym hasłem przechodzi.
