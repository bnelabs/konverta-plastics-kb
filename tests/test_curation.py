import json
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

tmp = tempfile.TemporaryDirectory(prefix="kb-curation-test-")
os.environ["KB_DB_PATH"] = str(Path(tmp.name) / "curation.sqlite3")

from app.main import app, connect, ensure_schema  # noqa: E402

BULK_URL = "/api/v1/materials/bulk"
CSV_COLUMNS = (
    "code",
    "name",
    "common_uses",
    "melt_temp_c",
    "density_g_cm3",
    "toxicity_level",
    "recyclability",
    "notes",
    "source_title",
    "source_url",
    "review_status",
)


def material_row(code, **overrides):
    row = {
        "code": code,
        "name": f"Bulk test resin {code}",
        "common_uses": "Bulk import test batch",
        "melt_temp_c": "150-160",
        "density_g_cm3": 0.95,
        "toxicity_level": "Low",
        "recyclability": "Not recorded",
        "notes": "Safety note recorded for the bulk test batch.",
        "source_title": "Example technical handbook",
        "source_url": "https://example.org/materials",
        "review_status": "draft",
    }
    row.update(overrides)
    return row


def csv_document(*rows):
    lines = [",".join(CSV_COLUMNS)]
    for row in rows:
        lines.append(",".join(str(row.get(column, "")) for column in CSV_COLUMNS))
    return "\n".join(lines) + "\n"


class MaterialBulkImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # app.main's lifespan starts the MCP StreamableHTTPSessionManager, which may
        # only run once per process. tests/test_api.py already owns that lifecycle,
        # so prepare the schema directly and use the client without entering the
        # lifespan a second time.
        ensure_schema()
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()

    def setUp(self):
        self._purge_test_rows()

    def tearDown(self):
        self._purge_test_rows()

    def _purge_test_rows(self):
        """Remove rows created here so other test modules keep exact counts."""
        con = connect()
        try:
            con.execute("DELETE FROM materials WHERE code LIKE 'BULK%'")
            con.execute("DELETE FROM kb_events WHERE event='bulk_import'")
            con.commit()
        finally:
            con.close()

    def _event_count(self):
        con = connect()
        try:
            return con.execute("SELECT COUNT(*) FROM kb_events").fetchone()[0]
        finally:
            con.close()

    def test_bulk_csv_happy_path_inserts_source_backed_rows(self):
        document = csv_document(
            material_row("bulk1"),
            material_row("BULK2", review_status="verified", density_g_cm3=1.2),
        )
        response = self.client.post(
            BULK_URL, content=document, headers={"content-type": "text/csv"}
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["inserted"], 2)
        self.assertEqual(body["skipped"], 0)
        self.assertEqual(body["errors"], [])

        draft = self.client.get("/api/v1/materials/BULK1")
        self.assertEqual(draft.status_code, 200)
        self.assertEqual(draft.json()["code"], "BULK1")
        self.assertEqual(draft.json()["review_status"], "draft")
        self.assertEqual(draft.json()["source_url"], "https://example.org/materials")

        verified = self.client.get("/api/v1/materials/bulk2").json()
        self.assertEqual(verified["code"], "BULK2")
        self.assertEqual(verified["review_status"], "verified")
        self.assertAlmostEqual(verified["density_g_cm3"], 1.2)

    def test_bulk_json_partial_batch_skips_rows_without_source(self):
        rows = [
            material_row("BULK3", source_title=""),
            material_row("BULK4"),
        ]
        response = self.client.post(BULK_URL, json=rows)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["inserted"], 1)
        self.assertEqual(body["skipped"], 1)
        self.assertEqual(
            body["errors"],
            [{"row": 1, "field": "source_title", "message": "source_title required"}],
        )
        self.assertEqual(self.client.get("/api/v1/materials/BULK3").status_code, 404)
        self.assertEqual(self.client.get("/api/v1/materials/BULK4").status_code, 200)

    def test_bulk_rejects_non_https_source_url(self):
        row = material_row("BULK5", source_url="http://example.org/materials")
        response = self.client.post(BULK_URL, json=[row])
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["inserted"], 0)
        self.assertEqual(body["skipped"], 1)
        self.assertEqual(
            body["errors"],
            [
                {
                    "row": 1,
                    "field": "source_url",
                    "message": "source_url must start with https://",
                }
            ],
        )
        self.assertEqual(self.client.get("/api/v1/materials/BULK5").status_code, 404)

    def test_bulk_skips_duplicate_codes(self):
        first = self.client.post(BULK_URL, json=[material_row("BULK6")])
        self.assertEqual(first.json()["inserted"], 1)

        rows = [
            material_row("BULK6"),
            material_row("BULK6", name="Same code again"),
            material_row("BULK7"),
            material_row("hdpe"),
        ]
        response = self.client.post(BULK_URL, json=rows)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["inserted"], 1)
        self.assertEqual(body["skipped"], 3)
        self.assertEqual(
            [(error["row"], error["field"], error["message"]) for error in body["errors"]],
            [(1, "code", "duplicate code"), (2, "code", "duplicate code"), (4, "code", "duplicate code")],
        )
        self.assertEqual(self.client.get("/api/v1/materials/BULK7").status_code, 200)
        # A duplicate code must never overwrite the existing record.
        self.assertEqual(
            self.client.get("/api/v1/materials/HDPE").json()["name"],
            "High-Density Polyethylene",
        )

    def test_bulk_writes_one_audit_event_for_the_batch(self):
        before = self._event_count()
        rows = [material_row("BULK8"), material_row("BULK9", source_title="")]
        response = self.client.post(BULK_URL, json=rows)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._event_count(), before + 1)

        con = connect()
        try:
            event = con.execute(
                "SELECT event,entity_type,details FROM kb_events ORDER BY id DESC LIMIT 1"
            ).fetchone()
        finally:
            con.close()
        self.assertEqual(event["event"], "bulk_import")
        self.assertEqual(event["entity_type"], "material")
        details = json.loads(event["details"])
        self.assertEqual(details["inserted"], 1)
        self.assertEqual(details["skipped"], 1)
        self.assertEqual(details["error_count"], 1)
        self.assertEqual(details["source_format"], "json")
        self.assertEqual(details["codes"], ["BULK8"])

    def test_bulk_rejects_malformed_documents(self):
        not_an_array = self.client.post(
            BULK_URL, content='{"code": "BULKX"}', headers={"content-type": "application/json"}
        )
        self.assertEqual(not_an_array.status_code, 400)
        self.assertEqual(self.client.post(
            BULK_URL, content="{not json", headers={"content-type": "application/json"}
        ).status_code, 400)
        missing_columns = self.client.post(
            BULK_URL, content="code,name\nBULKX,Missing source columns\n", headers={"content-type": "text/csv"}
        )
        self.assertEqual(missing_columns.status_code, 400)
        self.assertEqual(self.client.get("/api/v1/materials/BULKX").status_code, 404)


if __name__ == "__main__":
    unittest.main()
