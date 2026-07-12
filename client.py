#!/usr/bin/env python3
"""
chrome-ai Python client — submit prompts to Chrome's built-in AI APIs.

Usage:
  from client import prompt, summarize, translate, write

  text = prompt("You are helpful.", "Hello!")
  text = summarize("Long text to summarize...")
  text = translate("Hello", "en", "fr")
  text = write("Write a poem about cats")
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.error

import server as _server


def _get_base_url() -> str:
    """Get the bridge server URL, starting one if needed."""
    env_url = os.environ.get("CHROME_AI_URL", "")
    if env_url:
        return env_url.rstrip("/")

    if _server._port:  # already started in this process
        return f"http://localhost:{_server._port}"

    # Reuse a server already running on the default port
    base = f"http://localhost:{_server.DEFAULT_PORT}"
    try:
        with urllib.request.urlopen(f"{base}/health", timeout=2):
            return base
    except OSError:
        pass

    port = _server.start_server(_server.DEFAULT_PORT)
    print(
        f"chrome-ai: open http://localhost:{port} in Chrome to process jobs",
        file=sys.stderr,
    )
    return f"http://localhost:{port}"


def _submit_and_poll(
    params: dict[str, str], timeout: float = 120
) -> str:
    base = _get_base_url()

    # Submit
    payload = json.dumps(params).encode()
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

    raise TimeoutError(f"Job {prompt_id} timed out after {timeout}s")


# --- Public API ---

def prompt(
    system: str, user: str, timeout: float = 120
) -> str:
    """Call Chrome's LanguageModel API (Gemini Nano)."""
    return _submit_and_poll(
        {"api": "prompt", "system": system, "user": user}, timeout
    )


def summarize(text: str, timeout: float = 120) -> str:
    """Call Chrome's Summarizer API."""
    return _submit_and_poll({"api": "summarize", "text": text}, timeout)


def translate(
    text: str,
    source_language: str,
    target_language: str,
    timeout: float = 120,
) -> str:
    """Call Chrome's Translator API."""
    return _submit_and_poll(
        {
            "api": "translate",
            "text": text,
            "sourceLanguage": source_language,
            "targetLanguage": target_language,
        },
        timeout,
    )


def write(text: str, context: str = "", timeout: float = 120) -> str:
    """Call Chrome's Writer API."""
    return _submit_and_poll(
        {"api": "write", "text": text, "context": context}, timeout
    )
