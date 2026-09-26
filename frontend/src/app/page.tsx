"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  Share2,
  Search,
  FileText,
  GitCompare,
  Table as TableIcon,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  ExternalLink,
  BookOpen,
  CheckCircle2,
  AlertTriangle,
  Copy,
  Download,
  Activity,
  Layers,
} from "lucide-react";

interface Paper {
  citationIndex?: number;
  title: string;
  authors: any[];
  pub_year?: number;
  journal?: string;
  doi?: string;
  pmid?: string;
  source?: string;
  abstract?: string;
  relevance_score?: number;
  evidence_level?: string;
}

interface Claim {
  claim_text: string;
  source_paper_title?: string;
  effect_direction?: string;
  statistical_info?: string;
  evidence_quality?: string;
  population?: string;
  intervention?: string;
  outcome?: string;
}

interface Conflict {
  topic?: string;
  resolution_notes?: string;
  severity?: string;
  conflicting_claims?: Claim[];
}

interface ResearchResult {
  question: string;
  answer: string;
  confidence: string;
  papers: Paper[];
  citations: any[];
  claims: Claim[];
  conflicts: Conflict[];
  question_analysis?: any;
  coverage?: any;
}

export default function ConnectedPapersWorkstation() {
  const [question, setQuestion] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [mode, setMode] = useState<"graph" | "synthesis" | "contradictions" | "table">("graph");
  const [result, setResult] = useState<ResearchResult | null>(null);
  const [selectedPaper, setSelectedPaper] = useState<Paper | null>(null);
  const [searchFilter, setSearchFilter] = useState("");
  const [sortBy, setSortBy] = useState<"relevance" | "year-desc" | "year-asc">("relevance");
  const [pipelineStage, setPipelineStage] = useState<string>("");
  const [comparatorA, setComparatorA] = useState<number>(1);
  const [comparatorB, setComparatorB] = useState<number>(2);

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const graphNodesRef = useRef<any[]>([]);
  const graphEdgesRef = useRef<any[]>([]);
  const animFrameRef = useRef<number | null>(null);

  // Check health on mount
  useEffect(() => {
    fetch("/api/health").catch(() => {});
  }, []);

  // Submit Question to SSE Pipeline
  const runSynthesis = async (inquiryText?: string) => {
    const q = inquiryText || question;
    if (!q || q.trim().length < 10 || isLoading) return;

    setIsLoading(true);
    setPipelineStage("Initializing Research Pipeline...");
    setMode("graph");

    try {
      const resp = await fetch("/api/research/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q }),
      });

      if (!resp.ok) {
        throw new Error("Pipeline request failed");
      }

      const reader = resp.body?.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (reader) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const msg = JSON.parse(line.slice(6));
              if (msg.type === "progress") {
                setPipelineStage(msg.stage.replace(/_/g, " ").toUpperCase());
              } else if (msg.type === "result") {
                processResult(msg.data);
                setIsLoading(false);
              } else if (msg.type === "error") {
                alert(msg.error);
                setIsLoading(false);
              }
            } catch (err) {}
          }
        }
      }
    } catch (e: any) {
      alert(e.message);
      setIsLoading(false);
    }
  };

  const processResult = (data: any) => {
    const citations = data.citations || [];
    const citMap: Record<string, any> = {};
    citations.forEach((c: any) => {
      if (c.title) citMap[c.title.toLowerCase().trim()] = c;
    });

    const papersWithIndex = (data.papers || []).map((p: Paper, idx: number) => {
      const match = citMap[(p.title || "").toLowerCase().trim()];
      return {
        ...p,
        citationIndex: match ? match.index : idx + 1,
      };
    });

    const formattedResult: ResearchResult = {
      ...data,
      papers: papersWithIndex,
    };

    setResult(formattedResult);
    if (papersWithIndex.length > 0) {
      setSelectedPaper(papersWithIndex[0]);
    }
  };

  // Format author names
  const formatAuthors = (authors: any[]) => {
    if (!authors || !Array.isArray(authors) || authors.length === 0) return "Unknown Authors";
    const names = authors.map((a) => (typeof a === "string" ? a : a.name || "")).filter(Boolean);
    if (names.length === 0) return "Unknown Authors";
    if (names.length === 1) return names[0];
    if (names.length === 2) return `${names[0]} & ${names[1]}`;
    return `${names[0]} et al.`;
  };

  // Filter and sort papers
  const papersList = (result?.papers || [])
    .filter((p) => {
      if (!searchFilter) return true;
      return (
        p.title.toLowerCase().includes(searchFilter.toLowerCase()) ||
        formatAuthors(p.authors).toLowerCase().includes(searchFilter.toLowerCase())
      );
    })
    .sort((a, b) => {
      if (sortBy === "relevance") return (b.relevance_score || 0) - (a.relevance_score || 0);
      if (sortBy === "year-desc") return (b.pub_year || 0) - (a.pub_year || 0);
      if (sortBy === "year-asc") return (a.pub_year || 0) - (b.pub_year || 0);
      return 0;
    });

  // Canvas Force Graph Simulation
  useEffect(() => {
    if (!result || mode !== "graph") return;

    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const width = canvas.parentElement?.clientWidth || 700;
    const height = canvas.parentElement?.clientHeight || 500;
    const dpr = window.devicePixelRatio || 1;

    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.scale(dpr, dpr);

    const nodes: any[] = [];
    const edges: any[] = [];

    // Origin node
    nodes.push({
      id: "origin",
      label: "Origin Query",
      fullTitle: result.question,
      color: "#1E3A8A",
      radius: 22,
      x: width / 2,
      y: height / 2,
      vx: 0,
      vy: 0,
      isOrigin: true,
    });

    const minYear = 2014;
    const maxYear = 2026;

    result.papers.forEach((p, idx) => {
      const year = p.pub_year || 2022;
      const normalized = Math.max(0, Math.min(1, (year - minYear) / (maxYear - minYear)));
      const r = Math.round(147 - normalized * (147 - 30));
      const g = Math.round(197 - normalized * (197 - 58));
      const b = Math.round(253 - normalized * (253 - 138));

      const id = `paper_${p.citationIndex || idx + 1}`;
      nodes.push({
        id,
        paper: p,
        citationIndex: p.citationIndex || idx + 1,
        label: `[${p.citationIndex || idx + 1}] ${(p.title || "").slice(0, 15)}…`,
        fullTitle: p.title,
        color: `rgb(${r}, ${g}, ${b})`,
        radius: 14 + (p.relevance_score || 0.6) * 10,
        x: width / 2 + (Math.random() - 0.5) * 280,
        y: height / 2 + (Math.random() - 0.5) * 280,
        vx: 0,
        vy: 0,
      });

      edges.push({ source: "origin", target: id });
    });

    graphNodesRef.current = nodes;
    graphEdgesRef.current = edges;

    let alpha = 1.0;
    const nodeMap = new Map(nodes.map((n) => [n.id, n]));

    const render = () => {
      if (alpha > 0.003) {
        const kRep = 3200;
        const kSpring = 0.045;
        const ideal = 95;

        for (let i = 0; i < nodes.length; i++) {
          for (let j = i + 1; j < nodes.length; j++) {
            const n1 = nodes[i];
            const n2 = nodes[j];
            const dx = n2.x - n1.x;
            const dy = n2.y - n1.y;
            const distSq = dx * dx + dy * dy + 60;
            const dist = Math.sqrt(distSq);
            const f = (kRep / distSq) * alpha;
            n1.vx -= (dx / dist) * f;
            n1.vy -= (dy / dist) * f;
            n2.vx += (dx / dist) * f;
            n2.vy += (dy / dist) * f;
          }
        }

        for (const e of edges) {
          const s = nodeMap.get(e.source);
          const t = nodeMap.get(e.target);
          if (!s || !t) continue;
          const dx = t.x - s.x;
          const dy = t.y - s.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const f = (dist - ideal) * kSpring * alpha;
          s.vx += (dx / dist) * f;
          s.vy += (dy / dist) * f;
          t.vx -= (dx / dist) * f;
          t.vy -= (dy / dist) * f;
        }

        nodes.forEach((n) => {
          n.vx += (width / 2 - n.x) * 0.015 * alpha;
          n.vy += (height / 2 - n.y) * 0.015 * alpha;
          n.vx *= 0.82;
          n.vy *= 0.82;
          n.x += n.vx;
          n.y += n.vy;
        });

        alpha *= 0.988;
      }

      ctx.clearRect(0, 0, width, height);

      // Dot background
      ctx.fillStyle = "rgba(15, 23, 42, 0.04)";
      for (let x = 14; x < width; x += 24) {
        for (let y = 14; y < height; y += 24) {
          ctx.beginPath();
          ctx.arc(x, y, 1, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      // Edges
      edges.forEach((e) => {
        const s = nodeMap.get(e.source);
        const t = nodeMap.get(e.target);
        if (!s || !t) return;
        ctx.beginPath();
        ctx.moveTo(s.x, s.y);
        ctx.lineTo(t.x, t.y);
        ctx.strokeStyle = "rgba(203, 213, 225, 0.8)";
        ctx.lineWidth = 1.2;
        ctx.stroke();
      });

      // Nodes
      nodes.forEach((n) => {
        const isSelected = selectedPaper && selectedPaper.citationIndex === n.citationIndex;
        ctx.save();
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.radius, 0, Math.PI * 2);
        ctx.fillStyle = n.color;
        ctx.fill();

        ctx.strokeStyle = isSelected ? "#2563EB" : "#FFFFFF";
        ctx.lineWidth = isSelected ? 3.5 : 1.8;
        ctx.stroke();

        // Label pill
        ctx.font = "600 10.5px sans-serif";
        const tw = ctx.measureText(n.label).width;
        const pillW = tw + 8;
        const pillX = n.x - pillW / 2;
        const pillY = n.y + n.radius + 4;

        ctx.fillStyle = isSelected ? "#0F172A" : "rgba(255, 255, 255, 0.95)";
        ctx.strokeStyle = isSelected ? "#2563EB" : "#CBD5E1";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.roundRect(pillX, pillY, pillW, 16, 3);
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = isSelected ? "#FFFFFF" : "#1E293B";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(n.label, n.x, pillY + 8);
        ctx.restore();
      });

      animFrameRef.current = requestAnimationFrame(render);
    };

    render();

    return () => {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    };
  }, [result, mode, selectedPaper]);

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-slate-50 text-slate-800">
      {/* ─── Top Navbar (Connected Papers Header) ─────────────────── */}
      <header className="h-14 bg-white border-b border-slate-200 flex items-center justify-between px-5 z-50 shrink-0 shadow-xs">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-slate-900 rounded flex items-center justify-center text-blue-400">
            <Share2 className="w-4 h-4" />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-base font-extrabold text-slate-900 tracking-tight">Connected Papers</span>
            <span className="text-[10px] font-bold uppercase bg-blue-50 text-blue-700 border border-blue-200 px-1.5 py-0.5 rounded">
              Evidence Workstation
            </span>
          </div>
        </div>

        {/* Global Query Bar */}
        <div className="flex items-center gap-2 flex-1 max-w-xl mx-6">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400 pointer-events-none" />
            <input
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && runSynthesis()}
              placeholder="Search paper title, DOI, or clinical inquiry (e.g. Does metformin reduce cardiovascular risk?)"
              className="w-full h-9 pl-9 pr-3 text-xs bg-slate-50 border border-slate-200 rounded focus:outline-none focus:border-blue-600 focus:bg-white focus:ring-2 focus:ring-blue-100 transition-all text-slate-900"
            />
          </div>
          <button
            onClick={() => runSynthesis()}
            disabled={isLoading}
            className="h-9 px-4 bg-blue-700 hover:bg-blue-800 text-white rounded font-bold text-xs flex items-center gap-1.5 shrink-0 transition-colors disabled:bg-slate-400 cursor-pointer"
          >
            <span>{isLoading ? "Building..." : "Build Graph"}</span>
            <span className="font-mono text-[10px] opacity-75">↵</span>
          </button>
        </div>

        {/* Right Switcher & System Status */}
        <div className="flex items-center gap-3">
          <div className="flex items-center bg-slate-100 p-0.5 rounded border border-slate-200">
            <button
              onClick={() => setMode("graph")}
              className={`px-3 py-1 text-xs font-semibold rounded flex items-center gap-1.5 transition-all ${
                mode === "graph" ? "bg-white text-blue-700 font-bold shadow-xs" : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <Share2 className="w-3.5 h-3.5" />
              <span>Graph</span>
            </button>
            <button
              onClick={() => setMode("synthesis")}
              className={`px-3 py-1 text-xs font-semibold rounded flex items-center gap-1.5 transition-all ${
                mode === "synthesis" ? "bg-white text-blue-700 font-bold shadow-xs" : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <FileText className="w-3.5 h-3.5" />
              <span>Synthesis</span>
            </button>
            <button
              onClick={() => setMode("contradictions")}
              className={`px-3 py-1 text-xs font-semibold rounded flex items-center gap-1.5 transition-all ${
                mode === "contradictions" ? "bg-white text-blue-700 font-bold shadow-xs" : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <GitCompare className="w-3.5 h-3.5" />
              <span>Discordance</span>
            </button>
            <button
              onClick={() => setMode("table")}
              className={`px-3 py-1 text-xs font-semibold rounded flex items-center gap-1.5 transition-all ${
                mode === "table" ? "bg-white text-blue-700 font-bold shadow-xs" : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <TableIcon className="w-3.5 h-3.5" />
              <span>Table</span>
            </button>
          </div>

          <div className="flex items-center gap-1.5 text-xs font-mono bg-slate-50 border border-slate-200 px-2 py-1 rounded text-slate-600">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
            <span>Groq 120b</span>
          </div>
        </div>
      </header>

      {/* ─── Benchmarks Quickbar ──────────────────────────────────── */}
      <div className="h-8 bg-slate-50/80 border-b border-slate-200 flex items-center px-5 gap-2 shrink-0 text-xs overflow-x-auto">
        <span className="font-bold text-slate-500 uppercase text-[10px] tracking-wider whitespace-nowrap">
          Benchmarks:
        </span>
        <button
          onClick={() => {
            const q = "Does metformin reduce cardiovascular events in patients with type 2 diabetes?";
            setQuestion(q);
            runSynthesis(q);
          }}
          className="bg-white border border-slate-200 rounded px-2 py-0.5 text-slate-600 hover:border-blue-500 hover:text-blue-700 whitespace-nowrap text-[11px]"
        >
          Metformin & Cardiovascular Events
        </button>
        <button
          onClick={() => {
            const q = "What are recent applications of transformer models in scientific information retrieval?";
            setQuestion(q);
            runSynthesis(q);
          }}
          className="bg-white border border-slate-200 rounded px-2 py-0.5 text-slate-600 hover:border-blue-500 hover:text-blue-700 whitespace-nowrap text-[11px]"
        >
          Transformers in Scientific Retrieval
        </button>
        <button
          onClick={() => {
            const q = "How effective are deep learning models for cancer detection using medical imaging?";
            setQuestion(q);
            runSynthesis(q);
          }}
          className="bg-white border border-slate-200 rounded px-2 py-0.5 text-slate-600 hover:border-blue-500 hover:text-blue-700 whitespace-nowrap text-[11px]"
        >
          Deep Learning in Cancer Imaging
        </button>
      </div>

      {/* ─── Pipeline Progress Banner ─────────────────────────────── */}
      {isLoading && (
        <div className="bg-blue-50 border-b border-blue-200 px-5 py-1.5 text-xs text-blue-900 flex items-center justify-between font-mono animate-pulse">
          <div className="flex items-center gap-2">
            <Activity className="w-3.5 h-3.5 text-blue-700 animate-spin" />
            <span>EXECUTION PIPELINE: {pipelineStage}</span>
          </div>
          <span className="text-[11px] text-blue-700">Europe PMC + CORE + Groq Cloud</span>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════
           MODE 1: THE SIGNATURE 3-PANE CONNECTED PAPERS WORKSPACE
           ═══════════════════════════════════════════════════════════════ */}
      {mode === "graph" && (
        <div className="flex flex-1 overflow-hidden bg-slate-50">
          {/* Pane 1: Left Papers List (320px) */}
          <aside className="w-80 bg-white border-r border-slate-200 flex flex-col shrink-0 overflow-hidden">
            <div className="p-3 bg-slate-50/50 border-b border-slate-200 flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold uppercase text-slate-800 tracking-wide">Papers in Graph</span>
                <span className="text-xs font-mono font-bold bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded border border-slate-200">
                  {papersList.length} papers
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <input
                  type="text"
                  placeholder="Filter by title or author..."
                  value={searchFilter}
                  onChange={(e) => setSearchFilter(e.target.value)}
                  className="flex-1 h-7 px-2 text-xs bg-white border border-slate-200 rounded focus:outline-none focus:border-blue-500"
                />
                <select
                  value={sortBy}
                  onChange={(e: any) => setSortBy(e.target.value)}
                  className="h-7 px-1 text-xs bg-white border border-slate-200 rounded text-slate-700"
                >
                  <option value="relevance">Sim</option>
                  <option value="year-desc">New</option>
                  <option value="year-asc">Old</option>
                </select>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-2 flex flex-col gap-1.5">
              {papersList.length === 0 ? (
                <div className="p-8 text-center text-xs text-slate-400">
                  Enter an inquiry and click "Build Graph" to populate literature.
                </div>
              ) : (
                papersList.map((p) => {
                  const isSelected = selectedPaper?.title === p.title;
                  return (
                    <div
                      key={p.citationIndex || p.title}
                      onClick={() => setSelectedPaper(p)}
                      className={`p-2.5 rounded border transition-all cursor-pointer border-l-3 ${
                        isSelected
                          ? "bg-blue-50/80 border-blue-300 border-l-blue-700 shadow-xs"
                          : "bg-white border-slate-200 border-l-transparent hover:bg-slate-50 hover:border-slate-300 hover:border-l-blue-300"
                      }`}
                    >
                      <div className="text-xs font-bold text-slate-900 leading-snug line-clamp-2 mb-1">
                        [{p.citationIndex}] {p.title}
                      </div>
                      <div className="text-[11px] text-slate-500 truncate mb-1.5">
                        {formatAuthors(p.authors)} ({p.pub_year || "N/A"})
                      </div>
                      <div className="flex items-center justify-between text-[10px] text-slate-400 font-mono">
                        <span className="px-1 py-0.5 rounded bg-slate-100 text-slate-600 uppercase font-semibold">
                          {p.source || "Database"}
                        </span>
                        <span>{Math.round((p.relevance_score || 0) * 100)}% Sim</span>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </aside>

          {/* Pane 2: Middle Interactive Graph View */}
          <section className="flex-1 relative bg-slate-50/70 overflow-hidden flex flex-col">
            <div className="flex-1 relative w-full h-full">
              <canvas ref={canvasRef} className="w-full h-full block cursor-grab active:cursor-grabbing" />

              {/* Floating Controls */}
              <div className="absolute top-3.5 left-3.5 flex flex-col gap-1 bg-white border border-slate-200 rounded p-1 shadow-sm">
                <button
                  onClick={() => {
                    graphNodesRef.current.forEach((n) => {
                      n.x = (n.x - 350) * 1.25 + 350;
                      n.y = (n.y - 250) * 1.25 + 250;
                    });
                  }}
                  className="w-7 h-7 flex items-center justify-center hover:bg-slate-100 rounded text-slate-700"
                  title="Zoom In"
                >
                  <ZoomIn className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => {
                    graphNodesRef.current.forEach((n) => {
                      n.x = (n.x - 350) * 0.8 + 350;
                      n.y = (n.y - 250) * 0.8 + 250;
                    });
                  }}
                  className="w-7 h-7 flex items-center justify-center hover:bg-slate-100 rounded text-slate-700"
                  title="Zoom Out"
                >
                  <ZoomOut className="w-3.5 h-3.5" />
                </button>
              </div>

              {/* Floating Bottom Legend */}
              <div className="absolute bottom-3.5 left-3.5 right-3.5 bg-white/95 backdrop-blur-sm border border-slate-200 rounded px-4 py-2 flex items-center justify-between text-xs text-slate-500 shadow-xs">
                <div className="flex items-center gap-2">
                  <span>Year:</span>
                  <span className="font-mono text-[11px]">Older (2014)</span>
                  <div className="w-32 h-2 rounded bg-gradient-to-r from-blue-300 via-blue-600 to-blue-900"></div>
                  <span className="font-mono text-[11px]">Newer (2026)</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span>Node Size:</span>
                  <span className="font-mono text-[11px]">Evidence Relevance</span>
                </div>
                <div className="font-mono font-semibold text-slate-700">
                  {result ? `${result.papers.length} papers • ${result.claims.length} claims` : "No active cohort"}
                </div>
              </div>
            </div>
          </section>

          {/* Pane 3: Right Paper & Evidence Inspector (380px) */}
          <aside className="w-96 bg-white border-l border-slate-200 flex flex-col shrink-0 overflow-y-auto">
            {selectedPaper ? (
              <div className="p-5 flex flex-col gap-4 text-xs">
                <div className="text-base font-extrabold text-slate-900 leading-snug">
                  {selectedPaper.title}
                </div>

                <div className="text-slate-600 leading-relaxed text-[11.5px]">
                  <strong>Authors:</strong> {formatAuthors(selectedPaper.authors)}
                  <br />
                  <strong>Published:</strong> {selectedPaper.pub_year || "N/A"} •{" "}
                  <strong>Journal:</strong> {selectedPaper.journal || "Peer-Reviewed Source"}
                </div>

                <div className="flex items-center gap-2 py-2 border-y border-slate-200 flex-wrap">
                  {selectedPaper.doi && (
                    <a
                      href={`https://doi.org/${encodeURIComponent(selectedPaper.doi)}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="px-2.5 py-1 bg-slate-50 hover:bg-blue-50 border border-slate-200 rounded font-semibold text-slate-700 hover:text-blue-700 flex items-center gap-1"
                    >
                      <span>DOI</span>
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  )}
                  {selectedPaper.pmid && (
                    <a
                      href={`https://pubmed.ncbi.nlm.nih.gov/${encodeURIComponent(selectedPaper.pmid)}/`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="px-2.5 py-1 bg-slate-50 hover:bg-blue-50 border border-slate-200 rounded font-semibold text-slate-700 hover:text-blue-700 flex items-center gap-1"
                    >
                      <span>PubMed</span>
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  )}
                  <button
                    onClick={() => {
                      setQuestion(selectedPaper.title);
                      runSynthesis(selectedPaper.title);
                    }}
                    className="px-2.5 py-1 bg-slate-50 hover:bg-blue-50 border border-slate-200 rounded font-semibold text-slate-700 hover:text-blue-700 cursor-pointer"
                  >
                    Set as Origin
                  </button>
                </div>

                <div>
                  <div className="font-extrabold uppercase text-[10.5px] tracking-wider text-slate-400 mb-1.5">
                    Abstract
                  </div>
                  <div className="p-3 bg-slate-50 border border-slate-200 rounded leading-relaxed text-slate-700 text-xs">
                    {selectedPaper.abstract || "No abstract text available in source metadata."}
                  </div>
                </div>

                {/* Extracted claims from this paper */}
                {result?.claims && (
                  <div>
                    <div className="font-extrabold uppercase text-[10.5px] tracking-wider text-slate-400 mb-1.5">
                      Extracted Atomic Claims
                    </div>
                    <div className="flex flex-col gap-2">
                      {result.claims
                        .filter(
                          (c) =>
                            c.source_paper_title?.toLowerCase().trim() ===
                            selectedPaper.title.toLowerCase().trim()
                        )
                        .map((c, idx) => (
                          <div key={idx} className="p-2.5 bg-white border border-slate-200 rounded text-xs">
                            <span
                              className={`text-[9.5px] font-bold uppercase px-1.5 py-0.5 rounded border inline-block mb-1 ${
                                c.effect_direction === "positive"
                                  ? "bg-emerald-50 text-emerald-800 border-emerald-200"
                                  : c.effect_direction === "negative"
                                  ? "bg-rose-50 text-rose-800 border-rose-200"
                                  : "bg-amber-50 text-amber-800 border-amber-200"
                              }`}
                            >
                              {c.effect_direction || "neutral"}
                            </span>
                            <div className="italic text-slate-800 mb-1">"{c.claim_text}"</div>
                            {c.statistical_info && (
                              <div className="font-mono text-[10.5px] text-blue-800 font-bold">
                                {c.statistical_info}
                              </div>
                            )}
                          </div>
                        ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="p-8 text-center text-xs text-slate-400">
                Select a paper node in the graph or card on the left to inspect full abstract and claims.
              </div>
            )}
          </aside>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════
           MODE 2: EVIDENCE SYNTHESIS VIEW
           ═══════════════════════════════════════════════════════════════ */}
      {mode === "synthesis" && (
        <div className="flex-1 overflow-y-auto p-6 bg-slate-50">
          <div className="max-w-5xl mx-auto flex flex-col gap-5">
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <div className="p-3 bg-white border border-slate-200 rounded">
                <div className="text-[10px] font-bold uppercase text-slate-400">Papers Retrieved</div>
                <div className="text-2xl font-mono font-extrabold text-slate-900 mt-1">
                  {result?.papers?.length || 0}
                </div>
              </div>
              <div className="p-3 bg-white border border-slate-200 rounded">
                <div className="text-[10px] font-bold uppercase text-slate-400">Claims Extracted</div>
                <div className="text-2xl font-mono font-extrabold text-slate-900 mt-1">
                  {result?.claims?.length || 0}
                </div>
              </div>
              <div className="p-3 bg-white border border-slate-200 rounded">
                <div className="text-[10px] font-bold uppercase text-slate-400">Supporting Evidence</div>
                <div className="text-2xl font-mono font-extrabold text-emerald-600 mt-1">
                  {result?.claims?.filter((c) => c.effect_direction === "positive").length || 0}
                </div>
              </div>
              <div className="p-3 bg-white border border-slate-200 rounded">
                <div className="text-[10px] font-bold uppercase text-slate-400">Conflicting Evidence</div>
                <div className="text-2xl font-mono font-extrabold text-rose-600 mt-1">
                  {result?.conflicts?.length || 0}
                </div>
              </div>
              <div className="p-3 bg-white border border-slate-200 rounded">
                <div className="text-[10px] font-bold uppercase text-slate-400">Confidence Grade</div>
                <div className="text-base font-extrabold text-blue-700 uppercase mt-1">
                  {result?.confidence || "MODERATE"}
                </div>
              </div>
            </div>

            <div className="bg-white border border-slate-200 rounded p-6 shadow-xs">
              <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400 mb-4 pb-2 border-b border-slate-100">
                Evidence Synthesis Consensus Report
              </h2>
              <div className="text-sm leading-relaxed text-slate-800 whitespace-pre-wrap">
                {result?.answer || "No synthesis available yet. Build a graph to generate evidence consensus."}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════
           MODE 3: DISCORDANCE & CONTRADICTIONS VIEW
           ═══════════════════════════════════════════════════════════════ */}
      {mode === "contradictions" && (
        <div className="flex-1 overflow-y-auto p-6 bg-slate-50">
          <div className="max-w-5xl mx-auto flex flex-col gap-5">
            <div className="bg-white border border-slate-200 rounded p-5">
              <div className="flex items-center justify-between pb-3 border-b border-slate-100 mb-4">
                <h3 className="text-xs font-bold uppercase text-slate-900 tracking-wider">
                  Interactive Comparative Study Inspector
                </h3>
                <div className="flex items-center gap-2 text-xs">
                  <select
                    value={comparatorA}
                    onChange={(e) => setComparatorA(parseInt(e.target.value, 10))}
                    className="border border-slate-200 rounded p-1 bg-white"
                  >
                    {result?.papers.map((p, idx) => (
                      <option key={idx} value={idx + 1}>
                        [#{idx + 1}] {p.title.slice(0, 45)}...
                      </option>
                    ))}
                  </select>
                  <span className="font-bold text-slate-400">vs</span>
                  <select
                    value={comparatorB}
                    onChange={(e) => setComparatorB(parseInt(e.target.value, 10))}
                    className="border border-slate-200 rounded p-1 bg-white"
                  >
                    {result?.papers.map((p, idx) => (
                      <option key={idx} value={idx + 1}>
                        [#{idx + 1}] {p.title.slice(0, 45)}...
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {result?.papers && result.papers.length >= 2 ? (
                <div className="grid grid-cols-2 gap-4">
                  <div className="p-4 bg-slate-50 border border-slate-200 rounded border-t-4 border-t-emerald-600">
                    <div className="font-bold text-xs text-slate-900 mb-1">
                      [#{comparatorA}] {result.papers[comparatorA - 1]?.title}
                    </div>
                    <div className="text-[11px] text-slate-500 mb-2">
                      {formatAuthors(result.papers[comparatorA - 1]?.authors)} ({result.papers[comparatorA - 1]?.pub_year})
                    </div>
                    <div className="text-xs text-slate-700 leading-relaxed">
                      {result.papers[comparatorA - 1]?.abstract?.slice(0, 240)}...
                    </div>
                  </div>

                  <div className="p-4 bg-slate-50 border border-slate-200 rounded border-t-4 border-t-rose-600">
                    <div className="font-bold text-xs text-slate-900 mb-1">
                      [#{comparatorB}] {result.papers[comparatorB - 1]?.title}
                    </div>
                    <div className="text-[11px] text-slate-500 mb-2">
                      {formatAuthors(result.papers[comparatorB - 1]?.authors)} ({result.papers[comparatorB - 1]?.pub_year})
                    </div>
                    <div className="text-xs text-slate-700 leading-relaxed">
                      {result.papers[comparatorB - 1]?.abstract?.slice(0, 240)}...
                    </div>
                  </div>
                </div>
              ) : (
                <div className="p-8 text-center text-xs text-slate-400">
                  Build an evidence graph to populate studies for comparative analysis.
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════
           MODE 4: PAPER TABLE MATRIX
           ═══════════════════════════════════════════════════════════════ */}
      {mode === "table" && (
        <div className="flex-1 overflow-y-auto p-6 bg-slate-50">
          <div className="max-w-5xl mx-auto bg-white border border-slate-200 rounded overflow-hidden shadow-xs">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 uppercase text-[10.5px]">
                  <th className="p-3 w-10">#</th>
                  <th className="p-3">Title</th>
                  <th className="p-3">Authors</th>
                  <th className="p-3 w-16">Year</th>
                  <th className="p-3 w-24">Source</th>
                  <th className="p-3 w-20">Sim</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {result?.papers && result.papers.length > 0 ? (
                  result.papers.map((p, idx) => (
                    <tr key={idx} className="hover:bg-slate-50">
                      <td className="p-3 font-mono font-bold text-blue-700">#{idx + 1}</td>
                      <td className="p-3 font-semibold text-slate-900">{p.title}</td>
                      <td className="p-3 text-slate-500">{formatAuthors(p.authors)}</td>
                      <td className="p-3 font-mono">{p.pub_year || "N/A"}</td>
                      <td className="p-3 uppercase font-bold text-[10px] text-slate-500">{p.source}</td>
                      <td className="p-3 font-mono font-bold text-slate-800">
                        {Math.round((p.relevance_score || 0) * 100)}%
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={6} className="p-8 text-center text-slate-400">
                      No papers retrieved yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
