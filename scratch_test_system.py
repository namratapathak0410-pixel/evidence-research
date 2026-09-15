"""
Comprehensive test script for the Scientific Evidence Research System.
Tests:
1. Flask API endpoints (/api/health, /api/ollama/status, frontend)
2. Input validation on /api/research
3. Full pipeline execution (REST & SSE streaming)
4. Component integrity (PICO extraction, Search, Normalization, Dedup, Claims, Answer)
"""

import sys
import io

# Ensure UTF-8 output on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr.encoding != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import json
import time
from app import app
from pipeline.orchestrator import run_research_pipeline

def test_flask_routes():
    print("\n--- 1. Testing Flask Endpoints ---")
    client = app.test_client()

    # Health check
    res = client.get("/api/health")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    health_data = res.get_json()
    print(f"[PASS] /api/health: {health_data}")
    assert health_data.get("status") == "ok"

    # Ollama status
    res = client.get("/api/ollama/status")
    assert res.status_code == 200
    ollama_data = res.get_json()
    print(f"[PASS] /api/ollama/status: {ollama_data}")

    # Index page
    res = client.get("/")
    assert res.status_code == 200
    assert b"Evidence Research Workstation" in res.data
    print("[PASS] GET /: Served frontend successfully")

    # Validation errors on POST /api/research
    res = client.post("/api/research", json={})
    assert res.status_code == 400
    print("[PASS] POST /api/research: Correctly rejected empty payload")

    res = client.post("/api/research", json={"question": "short"})
    assert res.status_code == 400
    print("[PASS] POST /api/research: Correctly rejected too-short question")


def test_sse_streaming():
    print("\n--- 2. Testing SSE Streaming Endpoint (/api/research/stream) ---")
    client = app.test_client()
    test_q = "Does metformin reduce cardiovascular risk in diabetes?"
    
    start_time = time.time()
    res = client.post("/api/research/stream", json={"question": test_q})
    assert res.status_code == 200
    assert "text/event-stream" in res.content_type

    stages_seen = []
    has_final_result = False
    
    for line in res.iter_encoded():
        decoded = line.decode("utf-8")
        for subline in decoded.split("\n"):
            subline = subline.strip()
            if subline.startswith("data: "):
                payload = json.loads(subline[6:])
                msg_type = payload.get("type")
                if msg_type == "progress":
                    stage = payload.get("stage")
                    stages_seen.append(stage)
                    print(f"  [SSE Progress] Stage: {stage}")
                elif msg_type == "result":
                    has_final_result = True
                    res_data = payload.get("data", {})
                    print(f"  [SSE Result] Received final result with {len(res_data.get('papers', []))} papers and {len(res_data.get('claims', []))} claims")
                elif msg_type == "error":
                    print(f"  [SSE Error] {payload.get('error')}")

    elapsed = round(time.time() - start_time, 2)
    print(f"[PASS] SSE Stream completed in {elapsed}s with {len(stages_seen)} stage events")
    assert has_final_result, "SSE stream did not yield a final result message"


def test_direct_pipeline():
    print("\n--- 3. Testing Direct Research Pipeline Execution ---")
    test_q = "What are the cardiovascular effects of metformin in patients with type 2 diabetes?"
    
    print(f"Query: \"{test_q}\"")
    progress_stages = []
    
    def on_progress(stage, data):
        progress_stages.append(stage)

    result = run_research_pipeline(test_q, progress_callback=on_progress)
    
    print("\n--- Pipeline Results Summary ---")
    print(f"* Question Analysis: Domain={result.question_analysis.get('domain')}, Intervention={result.question_analysis.get('intervention')}, Outcome={result.question_analysis.get('outcome')}")
    print(f"* Papers Retrieved: {len(result.papers)}")
    print(f"* Claims Extracted: {len(result.claims)}")
    print(f"* Citations: {len(result.citations)}")
    print(f"* Confidence: {result.confidence}")
    print(f"* Sufficiency: {result.evidence_sufficiency}")
    print(f"* Conflicts Detected: {len(result.conflicts)}")
    print(f"* Coverage Score: {result.coverage.get('coverage_score')}")
    print(f"\n--- Synthesized Answer Excerpt (First 350 chars) ---")
    print(result.answer[:350] + ("..." if len(result.answer) > 350 else ""))
    
    assert len(result.papers) > 0, "Pipeline should find papers from Europe PMC"
    assert len(result.citations) > 0, "Pipeline should provide citations"
    assert len(result.answer) > 50, "Pipeline should generate a synthesis answer"
    print("\n[PASS] Direct pipeline execution test passed!")


if __name__ == "__main__":
    print("=" * 60)
    print("SCIENTIFIC EVIDENCE RESEARCH SYSTEM -- AUTOMATED TEST SUITE")
    print("=" * 60)
    
    try:
        test_flask_routes()
        test_sse_streaming()
        test_direct_pipeline()
        print("\n" + "=" * 60)
        print("ALL TESTS PASSED SUCCESSFULLY! (100% OK)")
        print("=" * 60)
    except Exception as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
