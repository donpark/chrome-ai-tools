#!/usr/bin/env python3
"""
chrome-ai Python client — submit prompts to Chrome's built-in AI APIs.

Usage:
  from chrome_ai.client import nano_prompt

  text = nano_prompt("You are helpful.", "Hello!")
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.request
import urllib.error

from chrome_ai.server import start_server, _port as _server_port


def _get_base_url() -> str:
    """Get the bridge server URL, starting one if needed."""
    env_url = os.environ.get("CHROME_AI_URL", "")
    if env_url:
        return env_url.rstrip("/")

    # Auto-start the server if not already running
    port = _server_port or start_server()
    return f"http://localhost:{port}"


def nano_prompt(
    system: str, user: str, timeout: float = 120
) -> str:
    """Call Chrome's LanguageModel API (Gemini Nano).

    Opens a bridge page in Chrome if not already running.
    """
    base = _get_base_url()

    # Submit
    payload = json.dumps({"system": system, "user": user}).encode()
    req = urllib.request.Request(
        f"{base}/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        prompt_id = json.loads(resp.read())["id"]

    # Poll
    deadline = time.time() + timeout
    while time.time() < deadline:
        req = urllib.request.Request(f"{base}/result/{prompt_id}")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                if data.get("status") == "done":
                    return data["text"]
                if data.get("status") == "error":
                    raise RuntimeError(data["error"])
        except urllib.error.HTTPError as e:
            if e.code == 202:
                time.sleep(1)
                continue
            raise
        time.sleep(1)

    raise TimeoutError(f"Prompt {prompt_id} timed out after {timeout}s")
