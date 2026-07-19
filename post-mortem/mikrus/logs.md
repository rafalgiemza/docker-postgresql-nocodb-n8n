Mieliśmy awarię dziś na VPS Mikr.us, wrzucam z

Kluczowe fragmenty:
2026-07-14 10:16:57.890 [248364] LOG: syncing data directory (fsync), elapsed time: 169.68 s
...
2026-07-14 10:38:09.471 [1] LOG: server process (PID 250237) was terminated by signal 13: Broken pipe
2026-07-14 10:38:09.471 [1] LOG: terminating any other active server processes
Co się tu stało:

Fsync trwał 169–221 sekund na pojedynczy plik. To jest patologicznie wolno — normalnie fsync trwa milisekundy. To nie jest problem samego n8n ani Postgresa, tylko dysk na VPS-ie miał ekstremalne opóźnienia I/O w tym oknie czasowym (09:45–10:40).
Postgres, próbując zapisać dane, blokował się na tym wolnym I/O. Klient (n8n) w końcu przerywał połączenie (timeout) → Broken pipe (SIGPIPE) → Postgres uznawał to za nieczyste zamknięcie → wchodził w crash recovery → w trakcie recovery odrzucał wszystkie nowe połączenia (FATAL: the database system is in recovery mode) → n8n dostawał 503 Database is not ready!.
To się powtórzyło kilka razy (pętla: recovery → krótko działa → znowu broken pipe → znowu recovery), aż w końcu ok. 10:40 się ustabilizowało i od tego czasu (do 12:45 w logach) checkpointy trwają normalnie (0,5–2s), więc teraz powinno działać.

Podejrzany współsprawca: przed każdym crashem widać mnóstwo Failed to hard-delete executions — to n8n próbujące wyczyścić starą historię wykonań (pruning). Jeśli masz dużo nagromadzonych executions, hard-delete generuje ciężkie zapytania DELETE, co samo w sobie mocno obciąża I/O — a w połączeniu z i tak już wolnym dyskiem VPS-a mogło to być bezpośrednim wyzwalaczem.
Co sprawdzić teraz:
bash# czy n8n już wstało
docker ps -a
curl -sI http://localhost:5678

# ile masz executions w bazie (main podejrzany o rozmiar)
docker exec -it docker-postgres-1 psql -U n8n -d n8n -c "SELECT count(*) FROM execution_entity;"
docker exec -it docker-postgres-1 psql -U n8n -d n8n -c "SELECT pg_size_pretty(pg_database_size('n8n'));"

# czy w tym oknie czasowym (9:45-10:40) leciał backup/snapshot na hoście Proxmox
# to VPS na Proxmove (widać po /dev/mapper/pve-vm--268), więc warto sprawdzić harmonogram backupów w Proxmox
Rekomendacja (szczerze):

Jeśli execution_entity ma miliony wierszy — to jest realny problem do naprawienia, nie ignoruj. Ustaw agresywniejsze przycinanie: EXECUTIONS_DATA_PRUNE=true, EXECUTIONS_DATA_MAX_AGE (godziny) i EXECUTIONS_DATA_PRUNE_MAX_COUNT na rozsądne wartości w zmiennych środowiskowych n8n, żeby baza nie rosła bez końca.
Skoro to Proxmox VPS — sprawdź, czy w oknie 9:45–10:40 nie leciał backup/snapshot na hoście (to bardzo częsta przyczyna 100+ sekundowych fsync na gościu VM). Jeśli tak — to nie jest coś, co naprawisz w samym n8n/Postgresie, tylko trzeba przesunąć harmonogram backupów albo zgłosić to providerowi jeśli to VPS współdzielony.
Na przyszłość: dodaj monitoring/alert na docker logs docker-postgres-1 | grep FATAL albo prościej healthcheck bijący w n8n co minutę, żebyś wiedział o takich sytuacjach zanim użytkownicy zgłoszą błąd.

Podeślij output z tych komend (execution_entity count i czy n8n już odpowiada), to potwierdzimy że wróciło do normy i ustalimy czy trzeba czyścić executions.free -h
false 0 false 2026-07-12T15:39:14.92025801Z
               total        used        free      shared  buff/cache   available
Mem:           8.0Gi       1.1Gi       6.6Gi        20Mi       344Mi       6.9Gi
Swap:             0B          0B          0BDiagnosed disk I/O bottleneck, ruled out memory issuesDiagnosed disk I/O bottleneck, ruled out memory issuesTo potwierdza moją hipotezę i wyklucza jedną z alternatyw:

OOMKilled: false, RestartCount: 0 — kontener Postgresa nigdy nie został zabity przez system ani restartowany przez Dockera. To ważne, bo wyklucza scenariusz "zabrakło RAM-u".
8GB RAM, użyte tylko 1.1GB — pamięci masz mnóstwo, to na 100% nie jest przyczyna.
Kontener działa nieprzerwanie od 12 lipca, a crashe w logach są z 14 lipca ok. 10:16–10:40. To oznacza, że sam proces Postgresa (nie kontener) się posypał wewnętrznie — dokładnie to widzieliśmy w logach: server process terminated by signal 13: Broken pipe, po czym Postgres sam się zrestartował i wszedł w recovery.

To domyka obraz: RAM i sam kontener są ok, winny jest dysk / I/O na hoście VPS w tym konkretnym oknie czasowym. Fsync trwający 170-220 sekund na pojedynczy plik to ewidentnie temporary I/O stall na poziomie hosta (Proxmox), nie problem konfiguracji n8n/Postgresa.
Co bym teraz zrobił, po kolei:

Sprawdź czy to się powtarza — jeśli w logach Proxmoxa/VPS-a (panel providera) widać zaplanowane backupy/snapshoty w okolicach 9:45-10:40 UTC, to prawdopodobnie sprawca. Zapytaj providera VPS albo sprawdź harmonogram w Proxmoxie.
Sprawdź obecny rozmiar bazy i liczbę executions (to może pogłębiać problem przy kolejnym I/O stallu):

bashdocker exec -it docker-postgres-1 psql -U n8n -d n8n -c "SELECT count(*) FROM execution_entity;"
docker exec -it docker-postgres-1 psql -U n8n -d n8n -c "SELECT pg_size_pretty(pg_database_size('n8n'));"

Jeśli executions jest dużo (setki tysięcy+), ustaw pruning w n8n (EXECUTIONS_DATA_PRUNE=true, EXECUTIONS_DATA_MAX_AGE, EXECUTIONS_DATA_PRUNE_MAX_COUNT), żeby zmniejszyć obciążenie I/O przy kolejnych hard-delete.
Na przyszłość — dodaj prosty monitoring (np. healthcheck co minutę bijący w /healthz n8n + alert przy 503), żebyś widział takie stalle zanim zgłoszą to userzy.

Podeślij output z punktu 2 (count + rozmiar bazy) — to powie nam, czy pruning jest realnym priorytetem, czy to był jednorazowy incydent I/O, który można zignorować.⇒  docker exec -it docker-postgres-1 psql -U n8n -d n8n -c "SELECT count(*) FROM execution_entity;"
docker exec -it docker-postgres-1 psql -U n8n -d n8n -c "SELECT pg_size_pretty(pg_database_size('n8n'));"
 count 
-------
     5
(1 row)
 pg_size_pretty 
----------------
 14 MB
(1 row)Diagnosed host-side I/O bottleneck despite minimal data volumeDiagnosed host-side I/O bottleneck despite minimal data volumeTo wyklucza moją hipotezę o pruningu. 5 executions i 14MB bazy — to jest tak mała baza, że żadne "Failed to hard-delete executions" nie powinno w ogóle obciążać dysku w sposób, który tłumaczyłby 170-220 sekundowy fsync. Ten log o hard-delete to był tylko efekt uboczny (n8n próbował sprzątać w tle i też dostawał timeouty), a nie przyczyna.
Czyli zostaje jedna wiarygodna przyczyna: czysty I/O stall na poziomie hosta VPS, niezwiązany z niczym co dzieje się w n8n czy Postgresie. Coś na hoście (backup, snapshot, inny tenant na tym samym storage, resync macierzy) zablokowało dysk na ~25 minut (9:45-10:40 UTC), a Postgres i n8n są tu tylko ofiarami, nie winowajcami.
Szczerze, co bym teraz zrobił:

Nie próbuj tego naprawiać od strony n8n/Postgresa — nie ma tu nic do zoptymalizowania, baza jest mikroskopijna. To strata czasu.
Sprawdź to na poziomie hosta, jeśli masz do niego dostęp (Proxmox):

Panel Proxmoxa → harmonogram backupów/snapshotów dla tej VM, sprawdź czy pokrywa się z 9:45-10:40 UTC 14 lipca.
Jeśli to VPS u zewnętrznego providera (nie własny Proxmox) — napisz do supportu z dokładnym oknem czasowym i logami fsync, zapytaj czy w tym czasie był maintenance/storage incident na ich stronie.


Zabezpiecz się na przyszłość, żeby to nie bolało, niezależnie od przyczyny:

Dodaj Postgresowi restart policy unless-stopped (jeśli jeszcze nie ma) — to akurat samo się podniosło, ale przy dłuższym stallu może nie.
Prosty monitoring: curl do /healthz n8n co minutę + alert (nawet cron + webhook na Discord/Telegram) — żebyś wiedział o incydencie w czasie rzeczywistym, a nie po fakcie od użytkowników.
Jeśli takie stalle będą się powtarzać częściej niż raz na jakiś czas — to sygnał, że warto rozważyć migrację na inny storage/VPS provider, bo 200-sekundowy fsync na 14MB bazie to naprawdę złe I/O.



Na ten moment traktowałbym to jako pojedynczy incydent do zaobserwowania, a nie problem do gruntownego fixowania — chyba że zobaczysz to jeszcze raz w ciągu najbliższych dni/tygodnia. Wtedy to już wzorzec, nie przypadek.