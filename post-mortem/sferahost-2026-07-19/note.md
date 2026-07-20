# Post-mortem: zamrożenie VPS PRO (Sferahost), 2026-07-19

## Skrót

Serwer produkcyjny (Sferahost VPS PRO, `sferahost-vps-pro-1`) padł ok. 2 doby po migracji z Mikr.us ([[project_vps_strategy]] / `post-mortem/mikrus/vps-migration-decision.md`). SSH nie odpowiadało — dostęp odzyskany przez rescue mode odblokowany przez support Sferahost. **Przyczyna: zamrożenie całej maszyny wirtualnej na poziomie hosta/hypervisora, ~14,5h przestoju. Nie config aplikacji, nie powtórka fsync-stall z Mikr.us.**

## Timeline

| Czas (CEST) | Zdarzenie |
|---|---|
| 2026-07-17 14:57 | Start bieżącego (wtedy) boota, stos działa normalnie |
| 2026-07-19 do ~07:10 | Normalna praca — CPU ze zwykłym wzorcem baseline + okresowe skoki (cron/backup), dysk stabilny |
| **2026-07-19 07:10:36** | **Kernel przestaje logować cokolwiek** — ostatnie wpisy to rutynowy szum `[UFW BLOCK]` (odrzucone skany portów), bez żadnego ostrzeżenia (`hung task` itp.) przed ciszą |
| 07:10 → 21:43 | **~14,5h serwer nie odpowiada** (SSH martwe). W tym oknie dane Beszela pokazują CPU spłaszczone do ~0,8% (brak realnej aktywności) i finalny gwałtowny spadek raportowanego zużycia dysku (14579→1757 MB) w ostatnich próbkach |
| 21:43:33–21:45:04 | Restart maszyny (support/hypervisor) — pierwszy boot trwa ~2 min i ma **zegar cofnięty o ~2h** (FIRST ENTRY 21:43:33, LAST ENTRY 19:44:07) |
| 21:45:04 | Stabilny restart, system wraca, wszystkie kontenery healthy |

## Dowody i dlaczego wykluczają config aplikacji

1. **Cisza w journalu jest natychmiastowa, nie narastająca.** Brak stopniowej degradacji (żadnych komunikatów o zawieszonych taskach) — sieć i logowanie kernela urywają się w tej samej sekundzie. To pasuje do zamrożenia/pauzy całej VM przez hypervisor, nie do deadlocka I/O wewnątrz gościa.
2. **Wszystkie kontenery Dockera wróciły z `RestartCount=0`, `ExitCode=0`, `OOMKilled=false` i identycznym `FinishedAt`** — czyli padły i wstały razem, dokładnie raz. Brak pętli crash-recovery pojedynczych usług (inaczej niż w incydencie Mikr.us — patrz niżej).
3. **Cofnięcie zegara systemowego o ~2h** na krótkotrwałym boocie tuż po przywróceniu — coś, czego żadna aplikacja/config w tym repo nie jest w stanie spowodować; typowy podpis interwencji na poziomie hypervisora (wznowienie/reset VM z rozjechanym RTC hosta).
4. Limity pamięci wszystkich usług (`fragments/*.yml`) sumują się do ~8,5GB na hoście z 12GB RAM — brak podstaw do OOM jako przyczyny; log kernela też nie pokazuje żadnego `oom-killer`.

## Czym to NIE jest

**To nie jest powtórka wzorca z Mikr.us** ([[project_disk_io_stall_pattern]], `post-mortem/mikrus/logs.md`) — tam fsync-stall powodował cykliczne `FATAL: the database system is in recovery mode` w Postgresie co 10–20 min przez >1,5h, z realnymi restartami kontenera. Tu nie ma ani jednego restartu na poziomie kontenera przed finalnym, jednorazowym całościowym restartem VM.

## Kontekst — druga anomalia na tej samej maszynie w tydzień

To już drugi potwierdzony problem po stronie hosta na tej konkretnej VM ([[project_new_vps_cpu_limits]]) — 2026-07-17 Sferahost nie miał ustawionego `host-passthrough` dla CPU (zgłoszone i naprawione). Teraz kolejna anomalia infrastrukturalna, tym razem poważniejsza (pełny przestój, nie tylko crash-loop dwóch kontenerów).

## Do zrobienia

- [ ] Zgłoszenie do Sferahost z dokładnym timeline'em (`07:10:36` zamrożenie, `21:43:33` wznowienie z rozjechanym zegarem) — poprosić o wyjaśnienie ze strony hosta (awaria fizycznego hosta klastra? migracja live? utrata łączności ze storage?) i o rekompensatę za przestój.
- [ ] Przywołać poprzedni ticket (CPU passthrough) jako kontekst — druga anomalia w tydzień na tej samej maszynie.
- [ ] Zdecydować, czy trzeci taki incydent powinien wznowić decyzję o dostawcy VPS ([[project_vps_strategy]]).
- [ ] Zweryfikować po fakcie realny stan dysku (`df -h`, `du -sh /var/lib/docker/volumes/*`) względem 14579 MB sprzed spadku — potwierdzić brak faktycznej utraty danych.

Powiązane: `post-mortem/sferahost-2026-07-19/logs.md` (surowe komendy i output), `post-mortem/sferahost-2026-07-19/p1mp7alm.csv` (Beszel — dysk), `post-mortem/sferahost-2026-07-19/p8fe289b.csv` (Beszel — CPU).
