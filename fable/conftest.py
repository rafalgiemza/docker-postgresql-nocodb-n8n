"""Test Runner fixtures. Environment (all REQUIRED, no prod defaults on purpose):

  NC_URL        NocoDB URL (as reachable from the runner)
  NC_TOKEN      NocoDB API token
  NC_TEST_BASE  base id of the CRM-TEST base (NEVER the production base)
  N8N_URL       n8n URL
  WH_PREFIX     webhook path prefix of the TEST workflow copies (default: 'test-')

Run:  pytest -v tests/
"""
import os

import pytest
import requests

from .nocodb import NocoDB


def _env(name, default=None):
    v = os.environ.get(name, default)
    assert v, f"Missing env var {name}"
    return v


@pytest.fixture(scope="session")
def nc():
    return NocoDB(_env("NC_URL"), _env("NC_TOKEN"), _env("NC_TEST_BASE"))


@pytest.fixture(autouse=True)
def clean(nc):
    """Every test starts and ends with an empty TEST base."""
    nc.wipe()
    yield
    nc.wipe()


@pytest.fixture(scope="session")
def hook():
    n8n = _env("N8N_URL").rstrip("/")
    prefix = os.environ.get("WH_PREFIX", "test-")

    def post(path, payload):
        r = requests.post(f"{n8n}/webhook/{prefix}{path}", json=payload, timeout=30)
        assert r.ok, f"webhook {path} -> {r.status_code}: {r.text[:300]}"
        return r

    return post


# --------------------------------------------------------------- payload builders
def nc_insert(rows):
    """Synthetic NocoDB 'records.after.insert' webhook payload."""
    return {"type": "records.after.insert",
            "data": {"rows": rows if isinstance(rows, list) else [rows]}}


def nc_update(row, prev):
    """Synthetic NocoDB 'records.after.update' payload (with previous record)."""
    return {"type": "records.after.update",
            "data": {"rows": [row], "previous_rows": [prev]}}


def tally(name, email, phone="", message=""):
    return {"data": {"fields": [
        {"label": "Imię i nazwisko", "value": name},
        {"label": "E-mail", "value": email},
        {"label": "Telefon", "value": phone},
        {"label": "Wiadomość", "value": message},
    ]}}


def cf7(name, email, phone="", message=""):
    return {"your-name": name, "your-email": email,
            "your-phone": phone, "your-message": message}


def booking(name, email, start="2026-08-01T10:00:00", notes=""):
    return {"customerName": name, "customerEmail": email, "customerPhone": "",
            "customerNotes": notes, "startTime": start, "endTime": None}
