"""
app.py
Flask application for the Scientific Evidence Research System.

Provides:
  POST /api/research         — run the full pipeline (JSON response)
  GET  /api/research/stream  — SSE stream of pipeline progress
  GET  /                     — serve the frontend
"""

import json
import queue
import logging
import threading
from flask import Flask, request, jsonify, Response, send_from_directory
from flask_cors import CORS
from config import FLASK_HOST, FLASK_PORT, FLASK_DEBUG
from pipeline.orchestrator import run_research_pipeline

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
# Suppress noisy library loggers
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# ─── Flask App ────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder="static", static_url_path="/static")
CORS(app)


@app.route("/")
def index():
    """Serve the frontend."""
    return send_from_directory("static", "index.html")


@app.route("/api/research", methods=["POST"])
def research():
    """
    Run the full evidence research pipeline.

    Request JSON: { "question": "your research question" }
    Response JSON: complete ResearchResult
    """
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()

    if not question:
        return jsonify({"error": "Please provide a research question."}), 400

    if len(question) < 10:
        return jsonify({"error": "Question is too short. Please be more specific."}), 400

    if len(question) > 2000:
        return jsonify({"error": "Question is too long. Please keep it under 2000 characters."}), 400

    logger.info(f"Research request: {question[:100]}...")

    try:
        result = run_research_pipeline(question)
        return jsonify(result.to_dict())
    except Exception as e:
        logger.error(f"Research pipeline error: {e}", exc_info=True)
        return jsonify({
            "error": f"An error occurred during research: {str(e)}",
            "question": question,
        }), 500


@app.route("/api/research/stream", methods=["POST"])
def research_stream():
    """
    Run the pipeline with Server-Sent Events for real-time progress updates.

    Request JSON: { "question": "your research question" }
    Response: SSE stream with stage updates, ending with the full result.
    """
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()

    if not question:
        return jsonify({"error": "Please provide a research question."}), 400

    if len(question) < 10:
        return jsonify({"error": "Question is too short."}), 400

    progress_queue = queue.Queue()

    def progress_callback(stage, stage_data):
        progress_queue.put({
            "type": "progress",
            "stage": stage,
            "data": stage_data,
        })

    def run_pipeline():
        try:
            result = run_research_pipeline(question, progress_callback)
            progress_queue.put({
                "type": "result",
                "data": result.to_dict(),
            })
        except Exception as e:
            logger.error(f"Pipeline error: {e}", exc_info=True)
            progress_queue.put({
                "type": "error",
                "error": str(e),
            })
        finally:
            progress_queue.put(None)  # sentinel

    # Start pipeline in background thread
    thread = threading.Thread(target=run_pipeline, daemon=True)
    thread.start()

    def generate():
        while True:
            try:
                msg = progress_queue.get(timeout=2)  # Check queue every 2s
                if msg is None:
                    break
                yield f"data: {json.dumps(msg)}\n\n"
            except queue.Empty:
                if not thread.is_alive():
                    yield f"data: {json.dumps({'type': 'error', 'error': 'Pipeline thread stopped unexpectedly'})}\n\n"
                    break
                # Send SSE keep-alive comment so browser connection never drops
                yield ": keepalive\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.route("/api/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "service": "scientific-evidence-research"})


@app.route("/api/ollama/status")
def ollama_status():
    """Check Ollama service and model availability."""
    from pipeline.llm_client import check_ollama_status
    return jsonify(check_ollama_status())


@app.route("/api/research/compare", methods=["POST"])
def compare_research():
    """
    Compare evidence synthesis across OpenAI and Gemini (or Groq).
    Request JSON:
      {
        "question": "Does metformin reduce cardiovascular events?",
        "provider_a": "openai",
        "provider_b": "gemini",
        "openai_key": "...",
        "gemini_key": "..."
      }
    """
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "Please provide a research inquiry to compare."}), 400

    provider_a = data.get("provider_a") or "openai"
    provider_b = data.get("provider_b") or "gemini"
    openai_key = data.get("openai_key") or None
    gemini_key = data.get("gemini_key") or None

    try:
        from pipeline.comparator import compare_models
        res = compare_models(
            question=question,
            provider_a=provider_a,
            provider_b=provider_b,
            openai_key=openai_key,
            gemini_key=gemini_key
        )
        return jsonify(res)
    except Exception as e:
        logger.error(f"Comparator error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    logger.info(f"Starting Scientific Evidence Research System on "
                f"{FLASK_HOST}:{FLASK_PORT}")
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG, threaded=True)
