# PostgreSQL Database Management Guide

Ten przewodnik opisuje, jak zarządzać bazami danych PostgreSQL uruchomionymi w kontenerze Docker (`docker-postgres-1`).

---

## 1. Wejście do interaktywnej konsoli (psql)

Aby połączyć się z PostgreSQL jako superużytkownik `postgres`:
```bash
docker exec -it docker-postgres-1 psql -U postgres
```

Aby połączyć się od razu z konkretną bazą danych (np. aplikacyjną `appdata`):
```bash
docker exec -it docker-postgres-1 psql -U postgres -d appdata
```
*Uwaga: Hasło dla użytkownika `postgres` jest zdefiniowane w `.env` jako `POSTGRES_PASSWORD`.*

---

## 2. Listowanie baz danych

### Z poziomu konsoli psql:
Po wejściu do konsoli `psql` wpisz:
```sql
\l
-- lub wersja szczegółowa (pokazuje rozmiar i tabele kodowania):
\l+
```

### Bezpośrednio z terminala hosta (bez wchodzenia do psql):
```bash
docker exec -it docker-postgres-1 psql -U postgres -c "\l"
```

---

## 3. Usuwanie bazy danych (Drop Database)

⚠️ **Ważne:** Nie można usunąć bazy danych, do której są podłączone aktywne sesje (np. n8n lub NocoDB). Przed usunięciem bazy należy zatrzymać te serwisy lub wymusić zamknięcie ich połączeń.

### Krok 1: Zatrzymaj serwisy korzystające z bazy (Zalecane)
```bash
docker compose stop n8n nocodb
```

### Krok 2: Usuń bazę danych

#### Opcja A: Z poziomu terminala hosta (najprostsza)
```bash
docker exec -it docker-postgres-1 dropdb -U postgres appdata
```

#### Opcja B: Z poziomu konsoli psql
Połącz się z inną bazą danych (np. domyślną `postgres`), aby nie usuwać bazy, na której aktualnie stoisz:
```bash
docker exec -it docker-postgres-1 psql -U postgres -d postgres
```
Następnie w konsoli `psql`:
```sql
-- (Opcjonalnie) Jeśli nie zatrzymałeś serwisów, zamknij siłowo aktywne połączenia do bazy 'appdata':
SELECT pg_terminate_backend(pg_stat_activity.pid)
FROM pg_stat_activity
WHERE pg_stat_activity.datname = 'appdata'
  AND pid <> pg_backend_pid();

-- Usuń bazę danych:
DROP DATABASE appdata;
```

---

## 4. Tworzenie nowej bazy danych (Create Database)

### Opcja A: Z poziomu terminala hosta (najprostsza)
```bash
docker exec -it docker-postgres-1 createdb -U postgres -O appdata_owner appdata
```
*Gdzie `-O appdata_owner` oznacza ustawienie właściciela (owner) na użytkownika `appdata_owner`.*

### Opcja B: Z poziomu konsoli psql
Połącz się z bazą jako superuser:
```bash
docker exec -it docker-postgres-1 psql -U postgres
```
W konsoli `psql` wykonaj:
```sql
-- Upewnij się, że użytkownik/rola istnieje (jeśli nie, utwórz go):
-- CREATE USER appdata_owner WITH PASSWORD 'twoje_haslo';

-- Stwórz bazę danych z wybranym właścicielem:
CREATE DATABASE appdata OWNER appdata_owner;
```

---

## 5. Wgrywanie schematu z pliku `schema.sql`

Plik `schema.sql` zawiera definicje tabel, indeksów, triggerów i komentarzy dla bazy aplikacyjnej.

### Opcja A: Przez strumień wejściowy (Zalecane — uruchom z katalogu repo na hoście)
Najwygodniejszy sposób, który przesyła plik bezpośrednio z Twojego systemu do kontenera:
```bash
docker exec -i docker-postgres-1 psql -U appdata_owner -d appdata < schema.sql
```
*💡 **Wskazówka:** Używamy flagi `-i` (interactive) zamiast `-it`, aby poprawnie przekierować strumień pliku.*

### Opcja B: Z poziomu zamontowanego wolumenu w kontenerze
Plik `schema.sql` jest automatycznie montowany w kontenerze pod ścieżką `/docker-entrypoint-initdb.d/schema.sql` (zgodnie z `docker-compose.yml`). Możesz go uruchomić bezpośrednio w kontenerze:
```bash
docker exec -it docker-postgres-1 psql -U appdata_owner -d appdata -f /docker-entrypoint-initdb.d/schema.sql
```

---

## 6. Wgrywanie danych testowych z pliku `seed.sql`

Plik `seed.sql` zawiera przykładowe scenariusze i dane testowe (użytkownicy, klienci, deale, zadania). Należy go wgrywać **po** zaimportowaniu schematu bazy danych.

Ponieważ plik `seed.sql` nie jest domyślnie montowany wewnątrz kontenera, najprostszym i najszybszym sposobem jest przesłanie go za pomocą strumienia wejściowego.

### Uruchom z katalogu repo na hoście:
```bash
docker exec -i docker-postgres-1 psql -U appdata_owner -d appdata < seed.sql
```

Jeśli wolisz wykonać to jako superużytkownik `postgres`:
```bash
docker exec -i docker-postgres-1 psql -U postgres -d appdata < seed.sql
```

---

## 7. Tworzenie kopii zapasowej (Backup) i jej przywracanie (Restore)

### Tworzenie kopii zapasowej (Backup)
Aby zrzucić całą bazę danych do pliku `.sql` na Twoim komputerze (hoście), użyj narzędzia `pg_dump`. 

⚠️ **Wskazówka:** Do tworzenia kopii używamy `docker exec` bez flagi `-i` oraz `-t` (czyli bez `-it`). Zapobiega to dodaniu znaków kontrolnych terminala (TTY) do pliku wyjściowego, co mogłoby uszkodzić plik kopii zapasowej.

#### Backup bazy aplikacyjnej `appdata`:
```bash
docker exec docker-postgres-1 pg_dump -U postgres -d appdata > backup_appdata.sql
```

#### Backup bazy n8n:
```bash
docker exec docker-postgres-1 pg_dump -U postgres -d n8n > backup_n8n.sql
```

---

### Przywracanie kopii zapasowej (Restore)

Aby przywrócić zapisaną wcześniej kopię zapasową, najlepiej najpierw zresetować bazę danych do stanu pustego (aby uniknąć błędów związanych z konfliktami istniejących kluczy/tabel), a następnie wczytać plik kopii przez strumień wejściowy (`<`).

#### Krok 1: Zatrzymaj aplikacje korzystające z bazy (aby zwolnić blokady połączeń)
```bash
docker compose stop n8n nocodb
```

#### Krok 2: Usuń i utwórz bazę na nowo jako czystą
```bash
docker exec -it docker-postgres-1 dropdb -U postgres appdata
docker exec -it docker-postgres-1 createdb -U postgres -O appdata_owner appdata
```

#### Krok 3: Wczytaj plik kopii zapasowej do nowo utworzonej bazy
```bash
docker exec -i docker-postgres-1 psql -U appdata_owner -d appdata < backup_appdata.sql
```
*(Wskazówka: Do wczytywania kopii używamy flagi `-i`, aby poprawnie przekazać strumień pliku).*

#### Krok 4: Uruchom aplikacje ponownie
```bash
docker compose up -d n8n nocodb
```

---

## 8. Automatyczna migracja / Wgrywanie schematu za pomocą `migrate.sh`

Do katalogu repo został dodany skrypt `migrate.sh`, który w pełni automatyzuje proces wgrywania schematu bazy danych z pliku `schema.sql`.

Skrypt jest idealny do użycia zarówno lokalnie, jak i na serwerze VPS, ponieważ:
- **Automatycznie wczytuje zmienne** z lokalnego pliku `.env` (odczytuje nazwę bazy `APP_DB` oraz właściciela `APPDATA_OWNER_USER`).
- **Dynamicznie wyszukuje kontener** bazy danych na podstawie etykiet Docker Compose (dzięki czemu działa poprawnie niezależnie od nazwy katalogu/projektu na VPS).
- **Zabezpiecza proces** poprzez flagę `ON_ERROR_STOP=1`, natychmiast przerywając działanie przy napotkaniu błędu w pliku SQL.

### Uruchomienie skryptu (z katalogu repo):
```bash
./migrate.sh
```

---

## 9. Automatyczne wgrywanie danych testowych za pomocą `seed.sh`

Analogicznie do skryptu migracji, dodany został skrypt `seed.sh` umożliwiający automatyczne załadowanie danych testowych z pliku `seed.sql`.

Skrypt:
- **Pobiera konfigurację** z Twojego lokalnego pliku `.env` (odczytuje bazy danych i użytkowników).
- **Automatycznie wykrywa właściwy kontener** bazy danych na serwerze lokalnym oraz VPS.
- **Wgrywa dane testowe** w bezpieczny sposób ze wstrzymaniem działania przy błędzie (`ON_ERROR_STOP=1`).

### Uruchomienie skryptu (z katalogu repo):
```bash
./seed.sh
```

---

## Pro Tip: Szybki reset bazy danych do stanu początkowego (Schema + Seed)

Jeśli chcesz całkowicie wyczyścić bazę `appdata` i postawić ją na nowo ze świeżym schematem oraz danymi seed, wykonaj następującą sekwencję komend w katalogu repo:

```bash
# 1. Zatrzymaj serwisy korzystające z bazy
docker compose stop n8n nocodb

# 2. Usuń i stwórz bazę na nowo
docker exec -it docker-postgres-1 dropdb -U postgres appdata
docker exec -it docker-postgres-1 createdb -U postgres -O appdata_owner appdata

# 3. Wgraj schemat bazy danych
docker exec -i docker-postgres-1 psql -U appdata_owner -d appdata < schema.sql

# 4. Wgraj dane testowe
docker exec -i docker-postgres-1 psql -U appdata_owner -d appdata < seed.sql

# 5. Uruchom zatrzymane serwisy z powrotem
docker compose up -d n8n nocodb
```
