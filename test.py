#!/usr/bin/env python3
"""Tests for chrome-ai server and Python client — no AI model needed."""

import json
import time
import unittest
import urllib.request
import urllib.error

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server import start_server, _pending, _results, _lock


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = start_server(0)
        cls.base = f"http://localhost:{cls.port}"
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        with _lock:
            _pending.clear()
            _results.clear()

    def _get(self, path, expected_status=200):
        req = urllib.request.Request(f"{self.base}{path}")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            if e.code == expected_status:
                return e.code, e.read()
            raise

    def _post(self, path, data, expected_status=200):
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(
            f"{self.base}{path}",
            data=body,
            headers={"Content-Type": "application/json"} if body else {},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            if e.code == expected_status:
                return e.code, e.read()
            raise

    def test_health(self):
        status, body = self._get("/health")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data["ok"])
        self.assertIn("port", data)
        self.assertIn("pending", data)

    def test_bridge_page_returns_html(self):
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"<!DOCTYPE html>", body)

    def test_options_cors(self):
        req = urllib.request.Request(f"{self.base}/prompt", method="OPTIONS")
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 204)
            self.assertEqual(
                resp.headers.get("Access-Control-Allow-Origin"), "*"
            )

    def test_404_unknown_path(self):
        status, _ = self._get("/nonexistent", expected_status=404)
        self.assertEqual(status, 404)

    def test_submit_prompt_returns_id(self):
        status, body = self._post("/prompt", {"system": "sys", "user": "hello"})
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIn("id", data)
        self.assertEqual(len(data["id"]), 12)

    def test_pending_shows_submitted_prompts(self):
        self._post("/prompt", {"system": "s1", "user": "u1"})
        self._post("/prompt", {"system": "s2", "user": "u2"})

        status, body = self._get("/pending")
        data = json.loads(body)
        self.assertEqual(len(data), 2)

    def test_result_202_while_pending(self):
        _, body = self._post("/prompt", {"system": "", "user": "x"})
        pid = json.loads(body)["id"]
        status, _ = self._get(f"/result/{pid}", expected_status=202)
        self.assertEqual(status, 202)

    def test_result_returns_after_submission(self):
        _, body = self._post("/prompt", {"system": "", "user": "x"})
        pid = json.loads(body)["id"]

        self._post(f"/result/{pid}", {"status": "done", "text": "answer"})

        status, body = self._get(f"/result/{pid}")
        data = json.loads(body)
        self.assertEqual(data["status"], "done")
        self.assertEqual(data["text"], "answer")

    def test_result_error_status(self):
        _, body = self._post("/prompt", {"system": "", "user": "x"})
        pid = json.loads(body)["id"]
        self._post(f"/result/{pid}", {"status": "error", "error": "boom"})

        _, body = self._get(f"/result/{pid}")
        data = json.loads(body)
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error"], "boom")

    def test_result_one_shot(self):
        """Result consumed on first GET — second returns 202."""
        _, body = self._post("/prompt", {"system": "", "user": "x"})
        pid = json.loads(body)["id"]
        self._post(f"/result/{pid}", {"status": "done", "text": "ans"})

        _, body1 = self._get(f"/result/{pid}")
        self.assertEqual(json.loads(body1)["text"], "ans")

        status, _ = self._get(f"/result/{pid}", expected_status=202)
        self.assertEqual(status, 202)

    def test_submit_and_poll_cycle(self):
        """Full submit-pending-result cycle without the client module."""
        # Submit
        _, body = self._post("/prompt", {"system": "sys", "user": "hello"})
        pid = json.loads(body)["id"]

        # Simulate bridge page processing
        _, pending_body = self._get("/pending")
        pending = json.loads(pending_body)
        self.assertTrue(any(j["id"] == pid for j in pending))

        # Submit result
        self._post(f"/result/{pid}", {"status": "done", "text": "reply:hello"})

        # Read result
        _, result_body = self._get(f"/result/{pid}")
        data = json.loads(result_body)
        self.assertEqual(data["status"], "done")
        self.assertEqual(data["text"], "reply:hello")


if __name__ == "__main__":
    unittest.main()
