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

    def test_404_unknown_path(self):
        status, _ = self._get("/nonexistent", expected_status=404)
        self.assertEqual(status, 404)

    # --- Prompt (backward compat) ---

    def test_prompt_backward_compat(self):
        """POST /prompt without api field defaults to prompt."""
        _, body = self._post("/prompt", {"system": "sys", "user": "hello"})
        pid = json.loads(body)["id"]

        _, pending_body = self._get("/pending")
        pending = json.loads(pending_body)
        job = next(j for j in pending if j["id"] == pid)
        self.assertEqual(job["api"], "prompt")
        self.assertEqual(job["system"], "sys")
        self.assertEqual(job["user"], "hello")

    # --- Summarize ---

    def test_summarize_submit(self):
        _, body = self._post("/prompt", {"api": "summarize", "text": "long text"})
        pid = json.loads(body)["id"]

        _, pending_body = self._get("/pending")
        pending = json.loads(pending_body)
        job = next(j for j in pending if j["id"] == pid)
        self.assertEqual(job["api"], "summarize")
        self.assertEqual(job["text"], "long text")

    # --- Translate ---

    def test_translate_submit(self):
        _, body = self._post("/prompt", {
            "api": "translate",
            "text": "hello",
            "sourceLanguage": "en",
            "targetLanguage": "fr",
        })
        pid = json.loads(body)["id"]

        _, pending_body = self._get("/pending")
        pending = json.loads(pending_body)
        job = next(j for j in pending if j["id"] == pid)
        self.assertEqual(job["api"], "translate")
        self.assertEqual(job["text"], "hello")
        self.assertEqual(job["sourceLanguage"], "en")
        self.assertEqual(job["targetLanguage"], "fr")

    # --- Write ---

    def test_write_submit(self):
        _, body = self._post("/prompt", {
            "api": "write",
            "text": "write a poem",
            "context": "cats",
        })
        pid = json.loads(body)["id"]

        _, pending_body = self._get("/pending")
        pending = json.loads(pending_body)
        job = next(j for j in pending if j["id"] == pid)
        self.assertEqual(job["api"], "write")
        self.assertEqual(job["text"], "write a poem")
        self.assertEqual(job["context"], "cats")

    # --- Result lifecycle ---

    def test_result_202_while_pending(self):
        _, body = self._post("/prompt", {"api": "prompt", "system": "", "user": "x"})
        pid = json.loads(body)["id"]
        status, _ = self._get(f"/result/{pid}", expected_status=202)
        self.assertEqual(status, 202)

    def test_result_returns_after_submission(self):
        _, body = self._post("/prompt", {"api": "summarize", "text": "x"})
        pid = json.loads(body)["id"]
        self._post(f"/result/{pid}", {"status": "done", "text": "answer"})

        status, body = self._get(f"/result/{pid}")
        data = json.loads(body)
        self.assertEqual(data["status"], "done")
        self.assertEqual(data["text"], "answer")

    def test_result_error_status(self):
        _, body = self._post("/prompt", {"api": "prompt", "system": "", "user": "x"})
        pid = json.loads(body)["id"]
        self._post(f"/result/{pid}", {"status": "error", "error": "boom"})

        _, body = self._get(f"/result/{pid}")
        data = json.loads(body)
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error"], "boom")

    def test_result_one_shot(self):
        """Result consumed on first GET — second returns 202."""
        _, body = self._post("/prompt", {"api": "prompt", "system": "", "user": "x"})
        pid = json.loads(body)["id"]
        self._post(f"/result/{pid}", {"status": "done", "text": "ans"})

        _, body1 = self._get(f"/result/{pid}")
        self.assertEqual(json.loads(body1)["text"], "ans")

        status, _ = self._get(f"/result/{pid}", expected_status=202)
        self.assertEqual(status, 202)

    def test_full_submit_pending_result_cycle(self):
        """End-to-end cycle without the client module."""
        _, body = self._post("/prompt", {
            "api": "translate",
            "text": "hello",
            "sourceLanguage": "en",
            "targetLanguage": "es",
        })
        pid = json.loads(body)["id"]

        _, pending_body = self._get("/pending")
        pending = json.loads(pending_body)
        self.assertTrue(any(j["id"] == pid for j in pending))

        self._post(f"/result/{pid}", {"status": "done", "text": "hola"})

        _, result_body = self._get(f"/result/{pid}")
        data = json.loads(result_body)
        self.assertEqual(data["status"], "done")
        self.assertEqual(data["text"], "hola")


if __name__ == "__main__":
    unittest.main()
