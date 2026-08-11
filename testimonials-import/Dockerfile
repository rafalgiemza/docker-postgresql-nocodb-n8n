# Jednorazowy kontener-narzędzie dla scripts/import-testimonials.py i
# scripts/attach-testimonial-slides.py - NIE serwis HTTP jak seed-service,
# uruchamiany przez `docker compose run --rm` (patrz README.md).
#
# Obraz daje tylko runtime (Python + tesseract + pip deps) - kod
# (scripts/) i dane (init-data/) są montowane jako wolumeny w
# fragments/testimonials-import.yml, NIE kopiowane COPY-em. Dzięki temu
# `git pull` działa od razu, bez `docker compose build` - rebuild jest
# potrzebny tylko gdy zmieni się init-data/requirements.txt albo ten
# Dockerfile. (Odwrotnie niż seed-service, gdzie kod jest w obrazie - patrz
# jego README/historia dla kontekstu tamtej decyzji.)
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-pol \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY init-data/requirements.txt ./init-data/requirements.txt
RUN pip install --no-cache-dir -r init-data/requirements.txt
