#!/usr/bin/env python3
r"""Etap 2/2 importu referencji klienta: dociąga pojedyncze slajdy z
`init-data/source/testimonials.pptx` do już istniejących rekordów
`testimonials` (utworzonych przez `import-testimonials.py`, etap 1 -
MUSI być uruchomiony jako pierwszy).

DLACZEGO OCR: każdy slajd w dostarczonym pliku to JEDEN płaski obrazek
(cały layout - zdjęcie, cytat, imię/rola/firma, logo, numer strony - wklejony
jako pojedyncza grafika). Tekst w XML slajdu jest pusty - zweryfikowane
2026-08-11 na dostarczonym pliku. Dopasowanie po POZYCJI (slajd i = wiersz i)
też odpada: sprawdzone wizualnie, przykładowe slajdy to przypadkowe wycinki z
pełnej talii (numery stron 17/104 wypalone w grafice), nie pierwsze N w
kolejności z arkusza. Jedyny automatyczny sygnał to OCR obrazka + dopasowanie
imienia/firmy do wiersza z xlsx.

Wymaga systemowo `tesseract-ocr` + pakiet językowy polski
(`tesseract-ocr-pol` na Debianie, `brew install tesseract-lang` na macOS) -
nazwiska mają polskie znaki diakrytyczne, domyślny angielski pakiet je psuje.

Dla każdego slajdu:
  1. wyciąga jedyny obrazek (p:pic) i robi na nim OCR (cały obrazek, bez
     przycinania do współrzędnych - różne szablony kart w pełnym pliku
     mogłyby mieć inny układ),
  2. fold()-uje tekst OCR i szuka wśród jeszcze-niedopasowanych wierszy xlsx
     dokładnie jednego, którego fold(client_name) jest podciągiem - jeśli
     DODATKOWO fold(Firma) też pasuje -> confidence "high", inaczej "medium",
  3. przy dokładnie jednym dopasowaniu: wycina ten slajd do osobnego pliku
     .pptx (technika z file-renderer-service/renderer.py:82 delete_slide -
     python-pptx nie ma natywnego cross-deck copy, ale in-place delete
     wszystkich POZOSTAŁYCH slajdów ze świeżo wczytanej kopii jest proste i
     bezpieczne), uploaduje go do NocoDB i PATCH-uje rekord: `slide_file`,
     `in_source_pptx=True`, `slide_status="done"` (slajd już gotowy - nie
     trzeba go generować przyciskiem "generuj slajd" dla tego wiersza),
  4. przy zerze albo >1 dopasowań: slajd zostaje bez przypisania - do
     ręcznego dowiązania w NocoDB UI (upload attachmentu wprost do rekordu).

Idempotentny: rekordy z już niepustym `slide_file` są pomijane (bez
ponownego uploadu przy kolejnym przebiegu).

Wymaga w środowisku (patrz .env.example): NC_API_TOKEN, NC_CRM_BASE_ID.
Opcjonalnie: NC_LOCAL_URL (default http://localhost:8081).

Usage (przez kontener testimonials-import - patrz jego README, tam też
tesseract-ocr; PEP 668 na hoście robi z gołego `pip install` problem):
  make init-data
  # albo bezpośrednio:
  ./scripts/attach-testimonial-slides.sh --dry-run   # ZAWSZE najpierw
  ./scripts/attach-testimonial-slides.sh [--pptx PATH]

  Ten plik da się też odpalić bezpośrednio (python3 scripts/attach-testimonial-slides.py),
  jeśli masz gdzieś już zainstalowane init-data/requirements.txt + tesseract-ocr.
"""
import argparse
import io
import os
import sys
import unicodedata
from collections import defaultdict

import openpyxl
import pytesseract
import requests
from PIL import Image
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

URL = os.environ.get("NC_LOCAL_URL", "http://localhost:8081").rstrip("/")
TOKEN = os.environ.get("NC_API_TOKEN")
BASE_ID = os.environ.get("NC_CRM_BASE_ID")
DEFAULT_PPTX = "init-data/source/testimonials.pptx"
DEFAULT_XLSX = "init-data/source/testimonials.xlsx"
OCR_LANG = "pol"
DRY_RUN_PREVIEW_DIR = "/tmp/testimonial-slide-preview"

if not TOKEN or not BASE_ID:
    sys.exit("Brak NC_API_TOKEN / NC_CRM_BASE_ID w środowisku - patrz .env.example.")

S = requests.Session()
S.headers.update({"xc-token": TOKEN, "Content-Type": "application/json"})


def api(method, path, **kw):
    try:
        r = S.request(method, f"{URL}{path}", timeout=30, **kw)
    except requests.RequestException as e:
        sys.exit(f"Nie moge sie polaczyc z NocoDB ({URL}): {type(e).__name__}. "
                 f"Sprawdz NC_LOCAL_URL / czy kontener stoi.")
    if not r.ok:
        sys.exit(f"NocoDB API error {r.status_code} on {method} {path}: {r.text[:500]}")
    return r.json() if r.text else {}


# ----------------------------------------------------------------- helpers
def fold(s):
    """Accent/case-insensitive compare key. Strips leading/trailing
    punctuation - real dane maja literowki jak 'Grabowska-' (sprawdzone
    2026-08-11), ktore inaczej lamalyby dopasowanie po podciągu."""
    s = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore") \
        .decode().lower().strip()
    return s.strip(" -,.")


def clean_header(h):
    return " ".join(str(h or "").split())


# ----------------------------------------------------------------- xlsx candidates
# Duplikuje mały fragment import-testimonials.py (nagłówki, load_rows) zamiast
# importować ten moduł - tak jak seed-extra.py świadomie NIE importuje
# init-schema.py (import ma efekty uboczne: sys.exit przy braku env w chwili
# importu). Trzymaj w zgodzie, jeśli nagłówki xlsx się zmienią.
HEADERS = {
    "content": "Opinia",
    "client_name": "Imię i nazwisko",
    "company": "Firma",
}


def load_candidates(xlsx_path):
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb[wb.sheetnames[0]]
    raw_rows = list(ws.iter_rows(values_only=True))
    headers = [clean_header(h) for h in raw_rows[0]]
    missing = [h for h in HEADERS.values() if h not in headers]
    if missing:
        sys.exit(f"Brakuje oczekiwanych nagłówków w {xlsx_path}: {missing}")
    idx = {key: headers.index(h) for key, h in HEADERS.items()}
    out = []
    for r in raw_rows[1:]:
        if not any(v not in (None, "") for v in r):
            continue
        client_name = str(r[idx["client_name"]] or "").strip()
        content = str(r[idx["content"]] or "").strip()
        company = clean_header(r[idx["company"]])
        if not client_name:
            continue
        out.append({"key": (fold(client_name), fold(content)),
                    "client_name": client_name, "company": company})
    return out


# ----------------------------------------------------------------- NocoDB meta/records
def resolve_meta():
    tables = {t["title"].strip().lower(): t["id"]
              for t in api("GET", f"/api/v2/meta/bases/{BASE_ID}/tables").get("list", [])}
    if "testimonials" not in tables:
        sys.exit("Brak tabeli `testimonials` (uruchom najpierw `make init-schema`).")
    return tables["testimonials"]


def existing_records(tid):
    """key(fold(client_name), fold(content)) -> {"Id":..., "has_slide": bool}.

    Bez `fields=` - `fields` w NocoDB v2 to allowlist, NIE dokleja Id
    automatycznie (patrz ten sam fix w import-testimonials.py). Tabela mala,
    pelne rekordy sa tanie.
    """
    rows = api("GET", f"/api/v2/tables/{tid}/records?limit=1000").get("list", [])
    out = {}
    for r in rows:
        key = (fold(r.get("client_name")), fold(r.get("content")))
        out[key] = {"Id": r["Id"], "has_slide": bool(r.get("slide_file"))}
    return out


def upload_attachment(content, filename, mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation"):
    """POST /api/v2/storage/upload - wzorzec z docs/archive/fable/nocodb.py:65.
    Odpowiedź JSON to bezpośrednio wartość do przypisania polu Attachment."""
    r = S.post(f"{URL}/api/v2/storage/upload",
              files={"file": (filename, content, mimetype)},
              headers={"Content-Type": None})
    if not r.ok:
        sys.exit(f"Upload {filename} -> {r.status_code}: {r.text[:400]}")
    return r.json()


def update_record(tid, rec_id, fields):
    api("PATCH", f"/api/v2/tables/{tid}/records", json=[{"Id": rec_id, **fields}])


# ----------------------------------------------------------------- pptx / OCR
def slide_image_blob(slide):
    """Zwraca (blob, n_pics). None jako blob, jeśli slajd nie ma dokładnie
    1 obrazka (nietypowy slajd - do ręcznego przejrzenia)."""
    pics = [shp for shp in slide.shapes if shp.shape_type == MSO_SHAPE_TYPE.PICTURE]
    if len(pics) != 1:
        return None, len(pics)
    return pics[0].image.blob, 1


def ocr_text(blob):
    return pytesseract.image_to_string(Image.open(io.BytesIO(blob)), lang=OCR_LANG)


# python-pptx nie ma natywnego cross-deck slide copy (patrz komentarz w
# file-renderer-service/renderer.py). delete_slide() STAMTĄD, 1:1: usuwa
# slajd z listy + zrzuca relację - do wycięcia pojedynczego slajdu ładujemy
# świeżą kopię prezentacji i usuwamy z niej wszystko OPRÓCZ jednego.
def delete_slide(prs, slide):
    lst = prs.slides._sldIdLst
    for i in list(lst):
        if prs.part.rels[i.rId].target_part is slide.part:
            prs.part.drop_rel(i.rId)
            lst.remove(i)
            return


def extract_single_slide(pptx_path, target_index):
    prs = Presentation(pptx_path)
    slides = list(prs.slides)
    target = slides[target_index]
    for i, s in enumerate(slides):
        if i != target_index:
            delete_slide(prs, s)
    out = io.BytesIO()
    prs.save(out)
    return out.getvalue()


# ----------------------------------------------------------------- matching
def match_candidates(ocr_folded, candidates):
    """candidates: lista jeszcze-niedopasowanych {"key","client_name","company"}.
    Zwraca (matched_candidate_or_None, confidence_str)."""
    name_hits = [c for c in candidates if fold(c["client_name"]) and
                fold(c["client_name"]) in ocr_folded]
    if len(name_hits) != 1:
        return None, "brak" if not name_hits else "niejednoznaczne"
    c = name_hits[0]
    confidence = "high" if (c["company"] and fold(c["company"]) in ocr_folded) else "medium"
    return c, confidence


# ----------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--pptx", default=DEFAULT_PPTX)
    ap.add_argument("--xlsx", default=DEFAULT_XLSX)
    args = ap.parse_args()

    print(f"NocoDB: {URL}, base: {BASE_ID}{' [DRY RUN]' if args.dry_run else ''}")
    for p in (args.pptx, args.xlsx):
        if not os.path.exists(p):
            sys.exit(f"Nie znaleziono pliku: {p}")

    tid = resolve_meta()
    records = existing_records(tid)
    candidates_all = load_candidates(args.xlsx)
    # Tylko wiersze, ktore juz istnieja w bazie (etap 1 je utworzyl) I nie
    # maja jeszcze przypietego slajdu.
    candidates = [c for c in candidates_all
                 if records.get(c["key"], {}).get("Id") and not records[c["key"]]["has_slide"]]
    print(f"Kandydatów do dopasowania (istnieją w bazie, bez slide_file): {len(candidates)}")

    prs = Presentation(args.pptx)
    n_slides = len(prs.slides)
    print(f"Slajdów w pptx: {n_slides}")
    os.makedirs(DRY_RUN_PREVIEW_DIR, exist_ok=True)

    stats = defaultdict(int)
    for idx, slide in enumerate(prs.slides):
        blob, n_pics = slide_image_blob(slide)
        if blob is None:
            stats["nietypowy_slajd"] += 1
            print(f"slajd {idx+1}: pomijam - {n_pics} obrazków zamiast 1")
            continue

        text = ocr_text(blob)
        matched, confidence = match_candidates(fold(text), candidates)
        if not matched:
            stats[f"niedopasowane_{confidence}"] += 1
            print(f"slajd {idx+1}: {confidence}")
            continue

        candidates.remove(matched)  # jeden slajd = jeden wiersz, bez powtórek
        stats[f"dopasowane_{confidence}"] += 1
        rec = records[matched["key"]]
        print(f"slajd {idx+1}: -> {matched['client_name']!r} (confidence={confidence})")

        if confidence == "medium" or args.dry_run:
            fname = f"{idx+1:03d}_{fold(matched['client_name']).replace(' ', '_')}.png"
            with open(os.path.join(DRY_RUN_PREVIEW_DIR, fname), "wb") as f:
                f.write(blob)

        if args.dry_run:
            continue

        single = extract_single_slide(args.pptx, idx)
        fname = f"slide_{fold(matched['client_name']).replace(' ', '_')}.pptx"
        uploaded = upload_attachment(single, fname)
        update_record(tid, rec["Id"], {
            "slide_file": uploaded,
            "in_source_pptx": True,
            "slide_status": "done",
        })
        stats["uploaded"] += 1

    print("\n===== REPORT =====")
    for k, v in sorted(stats.items()):
        print(f"{k}: {v}")
    print(f"\nNiedopasowane wiersze (istnieją w bazie, zostały bez slajdu): "
         f"{len(candidates)}")
    for c in candidates:
        print(f"  {c['client_name']!r} / {c['company']!r}")
    print(f"\nPodglądy 'medium'/niejednoznacznych zapisane w {DRY_RUN_PREVIEW_DIR}/"
         f" - obejrzyj przed realnym przebiegiem.")
    if args.dry_run:
        print("\n(dry run - nic nie zapisano)")


if __name__ == "__main__":
    main()
