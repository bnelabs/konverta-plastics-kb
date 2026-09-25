import os
import tempfile
import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

tmp = tempfile.TemporaryDirectory(prefix="kb-test-")
os.environ["KB_DB_PATH"] = str(Path(tmp.name) / "test.sqlite3")

from app.main import app, connect, ensure_schema  # noqa: E402


class KnowledgeBaseApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_schema()
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    # Columns the materials endpoints return (a SELECT * on the materials table).
    MATERIAL_FIELDS = frozenset({
        "id", "code", "name", "common_uses", "melt_temp_c", "density_g_cm3",
        "toxicity_level", "recyclability", "notes", "source_title", "source_url",
        "review_status", "glass_transition_temp_c", "additives_common",
        "thermal_conductivity_w_m_k",
    })
    PROCESS_FIELDS = frozenset({
        "name", "description", "equipment_needed", "safety_precautions",
        "suitability_rating", "notes",
    })

    @staticmethod
    def _unique_code() -> str:
        """A resin code no other test uses, so these tests never depend on leftover rows."""
        return "QT" + uuid.uuid4().hex[:8].upper()

    def _material_payload(self, code: str, review_status: str = "draft") -> dict:
        return {
            "code": code,
            "name": f"API contract probe {code}",
            "common_uses": "Test fixture only",
            "melt_temp_c": "Verify source",
            "density_g_cm3": 1.0,
            "toxicity_level": "Not rated",
            "recyclability": "Not recorded",
            "notes": "Created by tests/test_api.py",
            "source_title": "Test fixture source",
            "source_url": f"https://example.org/{code.lower()}",
            "review_status": review_status,
            "glass_transition_temp_c": "",
            "additives_common": "",
            "thermal_conductivity_w_m_k": "",
        }

    def _create_material(self, review_status: str = "draft") -> dict:
        payload = self._material_payload(self._unique_code(), review_status)
        created = self.client.post("/api/v1/materials", json=payload)
        self.assertEqual(created.status_code, 201, created.text)
        # The whole class shares one temporary database: always put it back as found.
        self.addCleanup(self._delete_material, created.json()["code"])
        return created.json()

    def _delete_material(self, code: str) -> None:
        """Remove a material created by this suite; it has no linked processes or projects."""
        with connect() as con:
            con.execute("DELETE FROM materials WHERE code=?", (code,))

    def _needs_review_codes(self) -> set[str]:
        response = self.client.get("/api/v1/materials/needs_review")
        self.assertEqual(response.status_code, 200)
        return {row["code"] for row in response.json()}

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

    def test_material_list_and_detail_contract(self):
        listed = self.client.get("/api/v1/materials")
        self.assertEqual(listed.status_code, 200)
        rows = listed.json()
        self.assertIsInstance(rows, list)
        self.assertTrue(rows, "the seeded library should not be empty")
        for row in rows:
            self.assertTrue(self.MATERIAL_FIELDS.issubset(row), sorted(self.MATERIAL_FIELDS - set(row)))
        codes = [row["code"] for row in rows]
        self.assertEqual(codes, sorted(codes), "the directory is ordered by resin code")
        self.assertEqual(len(codes), len(set(codes)), "resin codes are unique")

        limited = self.client.get("/api/v1/materials", params={"limit": 2})
        self.assertEqual(limited.status_code, 200)
        self.assertEqual([row["code"] for row in limited.json()], codes[:2])

        detail = self.client.get("/api/v1/materials/HDPE")
        self.assertEqual(detail.status_code, 200)
        body = detail.json()
        self.assertEqual(body["code"], "HDPE", "resin code lookup is case-insensitive")
        self.assertTrue(self.MATERIAL_FIELDS.issubset(body))
        process_names = {process["name"] for process in body["processes"]}
        self.assertTrue({"Shredding", "Injection Molding"}.issubset(process_names))
        for process in body["processes"]:
            self.assertTrue(self.PROCESS_FIELDS.issubset(process), sorted(self.PROCESS_FIELDS - set(process)))
        self.assertIn("HDPE Carabiner / Clip", {project["title"] for project in body["projects"]})
        self.assertIsInstance(body["sources"], list)

    def test_needs_review_lists_only_unverified_materials(self):
        draft = self._create_material("draft")
        verified = self._create_material("verified")

        response = self.client.get("/api/v1/materials/needs_review")
        self.assertEqual(response.status_code, 200)
        rows = response.json()
        self.assertIsInstance(rows, list)
        self.assertTrue(rows, "the queue holds at least the material created above")
        for row in rows:
            self.assertTrue(self.MATERIAL_FIELDS.issubset(row), sorted(self.MATERIAL_FIELDS - set(row)))
            self.assertNotEqual(row["review_status"], "verified")

        codes = {row["code"] for row in rows}
        self.assertIn(draft["code"], codes, "a draft material belongs in the review queue")
        self.assertNotIn(verified["code"], codes, "a verified material must leave the review queue")

        # Verifying the draft removes it from the queue without touching other rows.
        updated = self.client.put(
            f"/api/v1/materials/{draft['code']}",
            json=self._material_payload(draft["code"], "verified"),
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["review_status"], "verified")
        self.assertNotIn(draft["code"], self._needs_review_codes())

    def test_needs_review_respects_limit(self):
        newest = [self._create_material("draft")["code"] for _ in range(3)]

        limited = self.client.get("/api/v1/materials/needs_review", params={"limit": 2})
        self.assertEqual(limited.status_code, 200)
        rows = limited.json()
        self.assertEqual(len(rows), 2, "limit caps the number of rows")
        self.assertNotIn("verified", {row["review_status"] for row in rows})
        self.assertIn(newest[-1], {row["code"] for row in rows}, "the newest unverified material is included")

        single = self.client.get("/api/v1/materials/needs_review", params={"limit": 1})
        self.assertEqual(single.status_code, 200)
        self.assertEqual(len(single.json()), 1)

        largest = self.client.get("/api/v1/materials/needs_review", params={"limit": 100})
        self.assertEqual(largest.status_code, 200)
        self.assertGreaterEqual(len(largest.json()), 3, "all three drafts fit in the maximum page size")

        # The endpoint declares ge=1 / le=100, so FastAPI rejects out-of-range limits.
        self.assertEqual(self.client.get("/api/v1/materials/needs_review", params={"limit": 0}).status_code, 422)
        self.assertEqual(self.client.get("/api/v1/materials/needs_review", params={"limit": 101}).status_code, 422)

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

    def test_frontend_asset_references_resolve(self):
        """Static assets must exist; the generated bundle is verified by the image build."""
        import re

        from app.main import STATIC_DIR

        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        refs = re.findall(r'(?:src|href)="(/assets/[^"]+)"', html)
        self.assertTrue(refs, "index.html should reference at least one local asset")

        generated = [ref for ref in refs if ref.startswith("/assets/dist/")]
        for ref in (r for r in refs if not r.startswith("/assets/dist/")):
            target = STATIC_DIR / ref.removeprefix("/assets/")
            self.assertTrue(target.is_file(), f"missing asset {ref}")

        # The page must load exactly the entry bundle the Dockerfile compiles.
        self.assertEqual(generated, ["/assets/dist/app.js"])

    def test_new_schema_optional_fields_are_nullable_and_persisted(self):
        # Create a material with empty optional fields
        payload = self._material_payload("OPT1", review_status="draft")
        payload["glass_transition_temp_c"] = ""
        payload["additives_common"] = ""
        payload["thermal_conductivity_w_m_k"] = ""
        created = self.client.post("/api/v1/materials", json=payload)
        self.assertEqual(created.status_code, 201)
        data = created.json()
        self.assertIn("glass_transition_temp_c", data)
        self.assertIn("additives_common", data)
        self.assertIn("thermal_conductivity_w_m_k", data)
        # Update with values
        payload["glass_transition_temp_c"] = "105 C"
        payload["additives_common"] = "Stabilizers"
        payload["thermal_conductivity_w_m_k"] = "0.19"
        updated = self.client.put(f"/api/v1/materials/{data['code']}", json=payload)
        self.assertEqual(updated.status_code, 200)
        upd = updated.json()
        self.assertEqual(upd["glass_transition_temp_c"], "105 C")
        self.assertEqual(upd["additives_common"], "Stabilizers")
        self.assertEqual(upd["thermal_conductivity_w_m_k"], "0.19")


if __name__ == "__main__":
    unittest.main()
