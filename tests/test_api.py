import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

tmp = tempfile.TemporaryDirectory(prefix="kb-test-")
os.environ["KB_DB_PATH"] = str(Path(tmp.name) / "test.sqlite3")
os.environ["APP_ENV"] = "development"
os.environ["ALLOW_UNAUTHENTICATED_DEV"] = "1"

from app.main import app, ensure_schema  # noqa: E402
import app.main as kb_main  # noqa: E402


class KnowledgeBaseApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_schema()
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def test_health_and_metrics(self):
        self.assertEqual(self.client.get("/healthz").status_code, 200)
        metrics = self.client.get("/api/v1/metrics").json()
        self.assertEqual(metrics["records"]["materials"], 6)
        self.assertEqual(metrics["records"]["projects"], 2)

    def test_missing_access_configuration_fails_closed_outside_dev_mode(self):
        original = kb_main.allow_unauthenticated_dev
        try:
            kb_main.allow_unauthenticated_dev = False
            response = self.client.get("/api/v1/metrics")
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["detail"], "Cloudflare Access is not configured")
        finally:
            kb_main.allow_unauthenticated_dev = original

    def test_material_search_and_detail(self):
        results = self.client.get("/api/v1/materials", params={"q": "milk"})
        self.assertEqual(results.status_code, 200)
        self.assertEqual(results.json()[0]["code"], "HDPE")
        detail = self.client.get("/api/v1/materials/hdpe").json()
        self.assertEqual(detail["code"], "HDPE")
        self.assertTrue(detail["processes"])
        self.assertEqual(self.client.get("/api/v1/materials/nope").status_code, 404)

    def test_processes_projects_and_compatibility(self):
        self.assertEqual(len(self.client.get("/api/v1/processes").json()), 4)
        self.assertEqual(len(self.client.get("/api/v1/projects").json()), 2)
        rule = self.client.get("/api/v1/compatibility", params={"material_a":"pet","material_b":"pvc"})
        self.assertEqual(rule.status_code, 200)
        self.assertEqual(rule.json()["compatibility_status"], "Incompatible")

    def test_source_backed_material_editor_and_duplicate_guard(self):
        payload = {
            "code": "abs", "name": "Acrylonitrile butadiene styrene",
            "common_uses": "Appliance housings", "melt_temp_c": "Verify source",
            "density_g_cm3": 1.04, "toxicity_level": "Not rated",
            "recyclability": "Varies by local stream", "notes": "Draft only",
            "source_title": "Example technical source", "source_url": "https://example.org/abs",
            "review_status": "draft",
        }
        created = self.client.post("/api/v1/materials", json=payload)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["code"], "ABS")
        self.assertEqual(created.json()["review_status"], "draft")
        self.assertEqual(self.client.post("/api/v1/materials", json=payload).status_code, 409)
        payload["name"] = "ABS updated"
        payload["review_status"] = "verified"
        updated = self.client.put("/api/v1/materials/ABS", json=payload)
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["name"], "ABS updated")
        self.assertEqual(updated.json()["review_status"], "verified")

    def test_frontend_is_served(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Materials, made useful", response.text)


if __name__ == "__main__":
    unittest.main()
