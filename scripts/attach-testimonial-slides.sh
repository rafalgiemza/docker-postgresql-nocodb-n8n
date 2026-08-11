#!/bin/bash
set -e
# .env vars come from the Makefile (`include .env` + `export`), not a bash
# `source` here - patrz komentarz w seed-extra.sh.

# Etap 2/2 importu referencji klienta: dociąga pojedyncze slajdy z
# testimonials.pptx (OCR-dopasowanie) do rekordów utworzonych przez
# import-testimonials.py (etap 1 - MUSI być uruchomiony jako pierwszy).
# Pełny kontekst: nagłówek scripts/attach-testimonial-slides.py.
command -v python3 >/dev/null 2>&1 || {
  echo "❌ Brak 'python3' w PATH."
  exit 1
}
command -v tesseract >/dev/null 2>&1 || {
  echo "❌ Brak binarki 'tesseract' — zainstaluj: apt install tesseract-ocr tesseract-ocr-pol"
  exit 1
}
python3 -c "import requests, openpyxl, pytesseract, PIL, pptx" 2>/dev/null || {
  echo "❌ Brak modułów dla python3 — zainstaluj: pip3 install -r init-data/requirements.txt"
  exit 1
}

NC_URL="${NC_LOCAL_URL:-http://localhost:8081}"
echo "⏳ Czekam, aż NocoDB odpowie pod ${NC_URL}..."
for attempt in $(seq 1 30); do
  curl -fsS -o /dev/null "${NC_URL}/" 2>/dev/null && break
  if [ "$attempt" -eq 30 ]; then
    echo "❌ NocoDB (${NC_URL}) nie odpowiada po 60s — sprawdź 'make ps' / 'make logs'."
    exit 1
  fi
  sleep 2
done

python3 scripts/attach-testimonial-slides.py "$@"
