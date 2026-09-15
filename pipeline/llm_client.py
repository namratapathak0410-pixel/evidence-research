"""
llm_client.py
Centralized LLM client for the Scientific Evidence Research System.

Uses Ollama's REST API to run a local LLM. All pipeline modules
import from here instead of directly calling any LLM SDK.

Ollama API docs: https://github.com/ollama/ollama/blob/main/docs/api.md
"""

import json
import re
import logging
import requests
from config import OLLAMA_BASE_URL, OLLAMA_MODEL

logger = logging.getLogger(__name__)


def _extract_json_from_text(text: str):
    """
    Extract JSON from LLM output that may contain markdown fences
    or surrounding text.

    Tries, in order:
    1. Direct JSON parse
    2. Extract from ```json ... ``` fences
    3. Extract from ``` ... ``` fences
    4. Find first { ... } block via brace matching
    5. Find first [ ... ] block via bracket matching
    """
    text = text.strip()

    # 1. Direct parse
    try:
        res = json.loads(text)
        if isinstance(res, str):
            try:
                return json.loads(res)
            except Exception:
                pass
        return res
    except json.JSONDecodeError:
        pass

    # 2. Extract from ```json ... ``` fences
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
    if match:
        try:
            res = json.loads(match.group(1).strip())
            if isinstance(res, str):
                try:
                    return json.loads(res)
                except Exception:
                    pass
            return res
        except json.JSONDecodeError:
            pass

    # 3. Find first { ... } block via brace matching
    start = text.find('{')
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break

    # 4. Find first [ ... ] block via bracket matching
    start = text.find('[')
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == '[':
                depth += 1
            elif text[i] == ']':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break

    # 5. Attempt partial/truncated JSON repair (close unclosed quotes, brackets, braces)
    start = text.find('{')
    if start != -1:
        snippet = text[start:]
        # Try closing open strings and unbalanced brackets
        for suffix in ['"}]}', '"}]}}', '"]}', ']}', '}', '"]', ']']:
            try:
                repaired = json.loads(snippet + suffix)
                return repaired
            except Exception:
                pass
            # Try removing last trailing incomplete field
            last_comma = snippet.rfind(',')
            if last_comma > 0:
                try:
                    repaired = json.loads(snippet[:last_comma] + suffix)
                    return repaired
                except Exception:
                    pass

    raise ValueError(f"Could not extract JSON from LLM response: {text[:200]}...")


import time

_circuit_open_until = 0.0

def is_ollama_ready() -> bool:
    """Check if Ollama circuit is closed and server is responsive."""
    global _circuit_open_until
    if time.time() < _circuit_open_until:
        return False
    return True

def trip_circuit(cooldown_seconds: float = 60.0):
    """Temporarily disable Ollama calls when server times out or hangs."""
    global _circuit_open_until
    _circuit_open_until = time.time() + cooldown_seconds
    logger.warning(f"Ollama circuit tripped for {cooldown_seconds}s; using fast heuristic fallbacks.")


def generate_json(prompt: str, temperature: float = 0.1, max_tokens: int = 384, timeout: int = 12) -> dict:
    """
    Send a prompt to Ollama and parse the response as JSON.

    Args:
        prompt: The full prompt text (should instruct the model to return JSON).
        temperature: Sampling temperature (lower = more deterministic).
        max_tokens: Maximum tokens to generate.
        timeout: Request timeout in seconds.

    Returns:
        Parsed JSON dict from the model's response.

    Raises:
        ValueError: If JSON cannot be extracted from the response.
        requests.RequestException: If the Ollama API call fails.
    """
    if not is_ollama_ready():
        raise requests.ConnectionError("Ollama circuit open (temporarily bypassed due to timeout).")

    url = f"{OLLAMA_BASE_URL}/api/generate"

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
            "num_thread": 8,
            "num_ctx": 1536,
        },
        "format": "json",
    }

    try:
        logger.debug(f"Ollama request: model={OLLAMA_MODEL}, "
                      f"temp={temperature}, prompt_len={len(prompt)}")

        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()

        data = response.json()
        text = data.get("response", "").strip()

        if not text:
            raise ValueError("Empty response from Ollama")

        result = _extract_json_from_text(text)
        logger.debug(f"Ollama JSON response parsed successfully")
        return result

    except (requests.ConnectionError, requests.Timeout) as e:
        trip_circuit(45.0)
        logger.warning(f"Ollama request timed out or connection failed ({e}). Tripping circuit to fast fallback.")
        raise
    except requests.HTTPError as e:
        logger.error(f"Ollama HTTP error: {e}")
        raise


def generate_text(prompt: str, temperature: float = 0.3, max_tokens: int = 512, timeout: int = 15) -> str:
    """
    Send a prompt to Ollama and return the raw text response.

    Args:
        prompt: The full prompt text.
        temperature: Sampling temperature.
        max_tokens: Maximum tokens to generate.
        timeout: Timeout in seconds.

    Returns:
        The model's text response.
    """
    if not is_ollama_ready():
        raise requests.ConnectionError("Ollama circuit open (temporarily bypassed due to timeout).")

    url = f"{OLLAMA_BASE_URL}/api/generate"

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
            "num_thread": 8,
            "num_ctx": 1536,
        },
    }

    try:
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()

        data = response.json()
        text = data.get("response", "").strip()

        if not text:
            raise ValueError("Empty response from Ollama")

        return text

    except (requests.ConnectionError, requests.Timeout) as e:
        trip_circuit(45.0)
        logger.warning(f"Ollama text request failed ({e}). Tripping circuit.")
        raise


def check_ollama_status() -> dict:
    """
    Check if Ollama is running and the configured model is available.

    Returns:
        Dict with 'running' (bool), 'model_available' (bool), 'models' (list).
    """
    status = {"running": False, "model_available": False, "models": []}

    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        status["running"] = True

        models = [m.get("name", "") for m in data.get("models", [])]
        status["models"] = models

        # Check if our configured model is available (with or without :latest tag)
        for m in models:
            base_name = m.split(":")[0]
            if base_name == OLLAMA_MODEL or m == OLLAMA_MODEL:
                status["model_available"] = True
                break

    except Exception:
        pass

    return status
