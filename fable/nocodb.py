"""Thin NocoDB API v2 client for the test harness (points at the TEST base)."""
import time

import requests


class NocoDB:
    TABLES = ["companies", "leads", "participants", "meetings", "tasks",
              "task_templates", "projects", "activities", "testimonials"]
    # Tables wiped between tests (order matters only for readability; NocoDB
    # link rows are cleaned up automatically on record delete):
    WIPE = ["activities", "tasks", "meetings", "participants", "leads",
            "companies", "task_templates", "testimonials"]

    def __init__(self, url, token, base_id):
        self.base = url.rstrip("/")
        self.s = requests.Session()
        self.s.headers.update({"xc-token": token, "Content-Type": "application/json"})
        self.tbl, self.lnk = {}, {}
        self._resolve(base_id)

    def _req(self, method, path, **kw):
        r = self.s.request(method, f"{self.base}{path}", timeout=30, **kw)
        assert r.ok, f"{method} {path} -> {r.status_code}: {r.text[:400]}"
        return r.json() if r.text else {}

    def _resolve(self, base_id):
        for t in self._req("GET", f"/api/v2/meta/bases/{base_id}/tables").get("list", []):
            title = t["title"].strip().lower()
            if title in self.TABLES:
                self.tbl[title] = t["id"]
        missing = [t for t in self.TABLES if t not in self.tbl]
        assert not missing, f"TEST base is missing tables: {missing}"
        for title, tid in self.tbl.items():
            self.lnk[title] = {}
            for col in self._req("GET", f"/api/v2/meta/tables/{tid}").get("columns", []):
                if col.get("uidt") in ("Links", "LinkToAnotherRecord"):
                    self.lnk[title][col["title"].strip().lower()] = col["id"]

    # ---- records -------------------------------------------------------
    def create(self, table, record):
        res = self._req("POST", f"/api/v2/tables/{self.tbl[table]}/records", json=record)
        return res.get("Id") or res.get("id")

    def get(self, table, rid):
        return self._req("GET", f"/api/v2/tables/{self.tbl[table]}/records/{rid}")

    def list(self, table, where=None, limit=200):
        q = f"?limit={limit}" + (f"&where={where}" if where else "")
        return self._req("GET", f"/api/v2/tables/{self.tbl[table]}/records{q}").get("list", [])

    def delete(self, table, ids):
        if ids:
            self._req("DELETE", f"/api/v2/tables/{self.tbl[table]}/records",
                      json=[{"Id": i} for i in ids])

    def wipe(self):
        for t in self.WIPE:
            rows = self.list(t, limit=1000)
            self.delete(t, [r["Id"] for r in rows])

    # ---- links ---------------------------------------------------------
    def link(self, table, field, rid, target_ids):
        fid = self.lnk[table][field]
        ids = target_ids if isinstance(target_ids, list) else [target_ids]
        self._req("POST", f"/api/v2/tables/{self.tbl[table]}/links/{fid}/records/{rid}",
                  json=[{"Id": i} for i in ids])

    def get_links(self, table, field, rid):
        fid = self.lnk[table][field]
        return self._req("GET",
                         f"/api/v2/tables/{self.tbl[table]}/links/{fid}/records/{rid}"
                         ).get("list", [])

    # ---- polling -------------------------------------------------------
    def wait_for(self, table, where, count=1, timeout=20, poll=0.5):
        """Poll until `where` yields >= count rows; return them. Fail on timeout."""
        deadline = time.time() + timeout
        rows = []
        while time.time() < deadline:
            rows = self.list(table, where=where)
            if len(rows) >= count:
                return rows
            time.sleep(poll)
        raise AssertionError(
            f"Timed out waiting for {count} row(s) in '{table}' where {where}; "
            f"got {len(rows)}. Check the n8n execution log.")

    def wait_quiet(self, table, where, quiet=4.0):
        """Assert that NO row matching `where` appears within `quiet` seconds."""
        time.sleep(quiet)
        rows = self.list(table, where=where)
        assert not rows, f"Expected no rows in '{table}' where {where}, got {len(rows)}"
