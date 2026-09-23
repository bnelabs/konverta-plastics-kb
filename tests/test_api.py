import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

tmp = tempfile.TemporaryDirectory(prefix="kb-test-")
os.environ["KB_DB_PATH"] = str(Path(tmp.name) / "test.sqlite3")

from app.main import app, ensure_schema  # noqa: E402


class KnowledgeBaseApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_schema()
        cls.client = TestClient(app)

    def test_health_and_metrics(self):
        self.assertEqual(self.client.get("/healthz").status_code, 200)
        metrics = self.client.get("/api/v1/metrics").json()
        self.assertEqual(metrics["records"]["materials"], 6)
        self.assertEqual(metrics["records"]["projects"], 2)

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

    def test_frontend_is_served(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Materials, made useful", response.text)


if __name__ == "__main__":
    unittest.main()
