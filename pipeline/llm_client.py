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
import time
import requests
from config import (
    OLLAMA_BASE_URL, OLLAMA_MODEL,
    GROQ_API_KEY, GROQ_MODEL,
    OPENAI_API_KEY, OPENAI_MODEL, OPENAI_BASE_URL
)

logger = logging.getLogger(__name__)


def _extract_json_from_text(text: str):
    """
    Extract JSON from LLM output that may contain markdown fences
    or surrounding text.
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

    # 5. Attempt partial/truncated JSON repair
    start = text.find('{')
    if start != -1:
        snippet = text[start:]
        for suffix in ['"}]}', '"}]}}', '"]}', ']}', '}', '"]', ']']:
            try:
                repaired = json.loads(snippet + suffix)
                return repaired
            except Exception:
                pass
            last_comma = snippet.rfind(',')
            if last_comma > 0:
                try:
                    repaired = json.loads(snippet[:last_comma] + suffix)
                    return repaired
                except Exception:
                    pass

    raise ValueError(f"Could not extract JSON from LLM response: {text[:200]}...")


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


def generate_json(prompt: str, temperature: float = 0.1, max_tokens: int = 512, timeout: int = 15) -> dict:
    """
    Send a prompt to LLM (Groq -> OpenAI -> Ollama -> Fallback) and parse the response as JSON.
    """
    # 1. Try Groq (Free, ultra-fast cloud LLM for Render & cloud deployment)
    if GROQ_API_KEY:
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a scientific evidence analysis AI. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
            }
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"].strip()
            return _extract_json_from_text(text)
        except Exception as e:
            logger.warning(f"Groq API call failed ({e}). Attempting secondary provider...")

    # 2. Try OpenAI-compatible provider
    if OPENAI_API_KEY:
        try:
            url = f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions"
            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a scientific evidence analysis AI. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
            }
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"].strip()
            return _extract_json_from_text(text)
        except Exception as e:
            logger.warning(f"OpenAI API call failed ({e}). Attempting Ollama...")

    # 3. Try Local Ollama
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
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()

        data = response.json()
        text = data.get("response", "").strip()
        if not text:
            raise ValueError("Empty response from Ollama")

        return _extract_json_from_text(text)

    except (requests.ConnectionError, requests.Timeout) as e:
        trip_circuit(45.0)
        logger.warning(f"Ollama request timed out or connection failed ({e}). Tripping circuit to fast fallback.")
        raise
    except requests.HTTPError as e:
        logger.error(f"Ollama HTTP error: {e}")
        raise


def generate_text(prompt: str, temperature: float = 0.3, max_tokens: int = 512, timeout: int = 15) -> str:
    """
    Send a prompt to LLM (Groq -> OpenAI -> Ollama -> Fallback) and return raw text.
    """
    # 1. Try Groq
    if GROQ_API_KEY:
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": GROQ_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.warning(f"Groq text API call failed ({e}).")

    # 2. Try OpenAI
    if OPENAI_API_KEY:
        try:
            url = f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions"
            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": OPENAI_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.warning(f"OpenAI text API call failed ({e}).")

    # 3. Try Ollama
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
    """Check active LLM provider status."""
    if GROQ_API_KEY:
        return {"running": True, "model_available": True, "provider": "groq", "models": [GROQ_MODEL]}
    if OPENAI_API_KEY:
        return {"running": True, "model_available": True, "provider": "openai", "models": [OPENAI_MODEL]}

    status = {"running": False, "model_available": False, "provider": "ollama", "models": []}
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        resp.raise_for_status()
        data = resp.json()
        status["running"] = True
        models = [m.get("name", "") for m in data.get("models", [])]
        status["models"] = models
        for m in models:
            base_name = m.split(":")[0]
            if base_name == OLLAMA_MODEL or m == OLLAMA_MODEL:
                status["model_available"] = True
                break
    except Exception:
        pass

    return status
