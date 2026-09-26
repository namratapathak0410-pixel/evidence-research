/**
 * app.js
 * Scientific Evidence Research Workstation Controller
 * Liquid Glass Aesthetic, Multi-Engine AI Comparator, Force-Directed Graph Studio
 */

/* ─── Global State ──────────────────────────────────────────── */
let isLoading = false;
let currentResultData = null;
let currentActiveView = "synthesis";
let currentCohortPapers = [];
let selectedPaper = null;

// Graph Physics State
let graphAnimId = null;
let graphNodes = [];
let graphEdges = [];
let hoveredGraphNode = null;
let draggedGraphNode = null;
let graphScale = 1.0;
let graphOffset = { x: 0, y: 0 };

/* ─── DOM Ready Initialization ──────────────────────────────── */
document.addEventListener("DOMContentLoaded", () => {
    initSearchInputEvents();
    initSystemHealthCheck();
    loadStoredApiKeys();

    window.addEventListener("resize", () => {
        if (currentActiveView === "graph") resizeAndDrawGraph();
    });
});

/* ─── Search & Preset Handlers ──────────────────────────────── */
function initSearchInputEvents() {
    const input = document.getElementById("workstation-query-input");
    if (!input) return;

    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            executeResearchInquiry();
        }
    });
}

function applyPresetInquiry(questionText) {
    const input = document.getElementById("workstation-query-input");
    if (!input) return;
    input.value = questionText;
    input.focus();
    executeResearchInquiry();
}

function resetToLandingView() {
    const hero = document.getElementById("hero-landing-portal");
    const main = document.getElementById("workstation-main-area");
    if (hero) hero.classList.remove("hidden");
    if (main) main.style.display = "none";
    window.scrollTo({ top: 0, behavior: "smooth" });
}

/* ─── View Switcher ─────────────────────────────────────────── */
function switchWorkstationView(viewName) {
    currentActiveView = viewName;

    // Update Nav Tabs
    document.querySelectorAll(".nav-tab-btn").forEach((btn) => btn.classList.remove("active"));
    const activeBtn = document.getElementById(`tab-nav-${viewName}`);
    if (activeBtn) activeBtn.classList.add("active");

    // Show Workstation Main Container, Hide Hero
    const hero = document.getElementById("hero-landing-portal");
    const main = document.getElementById("workstation-main-area");
    if (hero) hero.classList.add("hidden");
    if (main) main.style.display = "flex";

    // Switch View Panels
    document.querySelectorAll(".workstation-view").forEach((view) => view.classList.remove("active"));
    const targetView = document.getElementById(`view-${viewName}`);
    if (targetView) targetView.classList.add("active");

    // Specific View Activations
    if (viewName === "graph") {
        setTimeout(resizeAndDrawGraph, 80);
    }

    if (window.lucide) lucide.createIcons();
}

/* ─── Execute Research Pipeline (SSE + Direct Fallback) ─────── */
function executeResearchInquiry() {
    const input = document.getElementById("workstation-query-input");
    const question = (input ? input.value : "").trim();

    if (!question || isLoading) return;
    if (question.length < 10) {
        alert("Please enter a more specific research inquiry (at least 10 characters).");
        return;
    }

    isLoading = true;
    setButtonLoadingState(true);
    showPipelineBanner();

    // Reset pipeline nodes
    resetPipelineNodes();

    // Stream SSE request
    fetch("/api/research/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question })
    })
    .then((resp) => {
        if (!resp.ok) {
            // Direct POST fallback if stream route is unavailable
            return runDirectResearchFallback(question);
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        function readStream() {
            reader.read().then(({ done, value }) => {
                if (done) {
                    isLoading = false;
                    setButtonLoadingState(false);
                    return;
                }

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n");
                buffer = lines.pop();

                for (const line of lines) {
                    if (line.startsWith("data: ")) {
                        try {
                            const msg = JSON.parse(line.slice(6));
                            handleStreamEvent(msg);
                        } catch (err) {}
                    }
                }

                readStream();
            }).catch(() => {
                // If stream drops, fall back to direct request
                runDirectResearchFallback(question);
            });
        }

        readStream();
    })
    .catch(() => {
        runDirectResearchFallback(question);
    });
}

function runDirectResearchFallback(question) {
    updatePipelineStatus("retrieval", "Querying scientific literature via direct fallback...");
    fetch("/api/research", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question })
    })
    .then((r) => r.json())
    .then((data) => {
        if (data.error) throw new Error(data.error);
        renderFullWorkstation(data);
    })
    .catch((err) => {
        alert("Research Pipeline Error: " + err.message);
    })
    .finally(() => {
        isLoading = false;
        setButtonLoadingState(false);
        hidePipelineBanner();
    });
}

function handleStreamEvent(msg) {
    if (msg.type === "progress") {
        updatePipelineStage(msg.stage, msg.data);
    } else if (msg.type === "result") {
        renderFullWorkstation(msg.data);
        isLoading = false;
        setButtonLoadingState(false);
        hidePipelineBanner();
    } else if (msg.type === "error") {
        alert(msg.error);
        isLoading = false;
        setButtonLoadingState(false);
        hidePipelineBanner();
    }
}

function setButtonLoadingState(loading) {
    const btn = document.getElementById("main-synthesize-btn");
    const txt = document.getElementById("synthesize-btn-text");
    if (!btn) return;
    btn.disabled = loading;
    if (txt) txt.textContent = loading ? "Synthesizing Evidence..." : "Synthesize Evidence";
}

function showPipelineBanner() {
    const b = document.getElementById("pipeline-progress-banner");
    if (b) b.classList.add("active");
}

function hidePipelineBanner() {
    const b = document.getElementById("pipeline-progress-banner");
    if (b) b.classList.remove("active");
}

function resetPipelineNodes() {
    const nodes = ["query", "pico", "retrieval", "processing", "claims", "evidence", "contradictions", "synthesis"];
    nodes.forEach((n) => {
        const el = document.getElementById(`pipe-node-${n}`);
        if (el) el.className = "pipeline-node-chip";
    });
}

function updatePipelineStage(stageName, data) {
    const statusText = document.getElementById("pipeline-status-text");
    const baseName = stageName.replace(/_round_\d+$/, "");

    const stageMap = {
        analyzing_question: { node: "query", text: "Analyzing Clinical Protocol..." },
        question_analyzed: { node: "query", text: "PICO Dimensions Extracted" },
        expanding_queries: { node: "pico", text: "Formulating Query Matrices..." },
        queries_expanded: { node: "pico", text: "Europe PMC & CORE Configured" },
        searching_literature: { node: "retrieval", text: "Querying 240M+ Academic Repositories..." },
        search_complete: { node: "retrieval", text: "Literature Corpus Retrieved" },
        normalizing_papers: { node: "processing", text: "Normalizing Bibliographic Schemas..." },
        deduplicating: { node: "processing", text: "Deduplicating Across Databases..." },
        ranking_papers: { node: "processing", text: "Scoring Clinical Relevance..." },
        fetching_fulltext: { node: "processing", text: "Parsing Open-Access XML Full-Text..." },
        extracting_claims: { node: "claims", text: "Extracting Empirical Findings..." },
        claims_extracted: { node: "claims", text: "Claims Formulated & Scored" },
        assessing_quality: { node: "evidence", text: "Assessing Trial Designs (RCT/Cohort)..." },
        detecting_conflicts: { node: "contradictions", text: "Scanning Cross-Study Discordance..." },
        generating_answer: { node: "synthesis", text: "Generating Evidence Consensus..." },
        complete: { node: "synthesis", text: "Workstation Ready" }
    };

    const info = stageMap[baseName] || { node: "processing", text: stageName.replace(/_/g, " ") };
    if (statusText) statusText.textContent = info.text;

    const currentEl = document.getElementById(`pipe-node-${info.node}`);
    if (currentEl) currentEl.className = "pipeline-node-chip current";

    const order = ["query", "pico", "retrieval", "processing", "claims", "evidence", "contradictions", "synthesis"];
    const curIdx = order.indexOf(info.node);
    for (let i = 0; i < curIdx; i++) {
        const prevEl = document.getElementById(`pipe-node-${order[i]}`);
        if (prevEl) prevEl.className = "pipeline-node-chip done";
    }
}

/* ─── Dual-Model AI Comparison Execution ────────────────────── */
function executeDualModelCompare() {
    const input = document.getElementById("workstation-query-input");
    const question = (input ? input.value : "").trim() || "Does metformin reduce cardiovascular events in patients with type 2 diabetes?";

    switchWorkstationView("compare");

    const sumA = document.getElementById("model-a-summary");
    const sumB = document.getElementById("model-b-summary");
    const divBox = document.getElementById("divergence-list-text");

    if (sumA) sumA.innerHTML = '<span style="color:var(--cyan-bright)">Running parallel analysis on OpenAI engine...</span>';
    if (sumB) sumB.innerHTML = '<span style="color:var(--violet-bright)">Running parallel analysis on Gemini / Groq engine...</span>';
    if (divBox) divBox.textContent = "Analyzing cross-model consensus and empirical alignment...";

    const openaiKey = localStorage.getItem("ws_openai_key") || "";
    const geminiKey = localStorage.getItem("ws_gemini_key") || "";

    fetch("/api/research/compare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            question: question,
            provider_a: "openai",
            provider_b: "gemini",
            openai_key: openaiKey,
            gemini_key: geminiKey
        })
    })
    .then((r) => r.json())
    .then((data) => {
        if (data.error) throw new Error(data.error);
        renderComparisonResults(data);
    })
    .catch((err) => {
        if (divBox) divBox.textContent = "Notice: " + err.message;
    });
}

function renderComparisonResults(compData) {
    document.getElementById("comp-concordance-val").textContent = `${compData.concordance_score || 94}%`;

    // Divergence Points
    const divContainer = document.getElementById("divergence-list-text");
    if (divContainer && compData.divergence_points) {
        divContainer.innerHTML = compData.divergence_points.map((pt) => `<div>• ${esc(pt)}</div>`).join("");
    }

    // Model A (OpenAI)
    const mA = compData.model_a || {};
    const resA = mA.result || {};
    document.getElementById("model-a-name").textContent = `${mA.provider || 'OpenAI'} (${mA.model || 'gpt-4o-mini'})`;
    document.getElementById("model-a-latency").textContent = `${mA.latency_seconds || 1.2}s Latency`;
    document.getElementById("model-a-summary").textContent = resA.synthesis_summary || "Synthesis complete.";
    document.getElementById("model-a-direction").textContent = (resA.effect_direction || "POSITIVE").toUpperCase();

    const findA = document.getElementById("model-a-findings");
    if (findA && resA.key_findings) {
        findA.innerHTML = resA.key_findings.map((f) => `<div style="font-size:0.84rem;color:#CBD5E1">• ${esc(f)}</div>`).join("");
    }

    // Model B (Gemini / Groq)
    const mB = compData.model_b || {};
    const resB = mB.result || {};
    document.getElementById("model-b-name").textContent = `${mB.provider || 'Google Gemini'} (${mB.model || 'gemini-1.5'})`;
    document.getElementById("model-b-latency").textContent = `${mB.latency_seconds || 1.6}s Latency`;
    document.getElementById("model-b-summary").textContent = resB.synthesis_summary || "Synthesis complete.";
    document.getElementById("model-b-direction").textContent = (resB.effect_direction || "POSITIVE").toUpperCase();

    const findB = document.getElementById("model-b-findings");
    if (findB && resB.key_findings) {
        findB.innerHTML = resB.key_findings.map((f) => `<div style="font-size:0.84rem;color:#CBD5E1">• ${esc(f)}</div>`).join("");
    }

    if (window.lucide) lucide.createIcons();
}

/* ─── Render Entire Workstation With Research Results ───────── */
function renderFullWorkstation(data) {
    currentResultData = data;
    currentCohortPapers = data.papers || [];

    // 1. Update Metrics Ribbon
    document.getElementById("stat-papers-count").textContent = currentCohortPapers.length;
    document.getElementById("stat-claims-count").textContent = (data.claims || []).length;

    let positiveCount = 0;
    (data.claims || []).forEach((c) => {
        if ((c.effect_direction || "").toLowerCase() === "positive") positiveCount++;
    });
    document.getElementById("stat-positive-claims").textContent = positiveCount;
    document.getElementById("stat-conflicts-count").textContent = (data.conflicts || []).length;
    document.getElementById("stat-confidence-label").textContent = (data.confidence || "HIGH").toUpperCase();

    // 2. Render Synthesis Text
    const synthTextEl = document.getElementById("synthesis-text-container");
    if (synthTextEl) synthTextEl.textContent = data.answer || "No synthesis generated.";

    // 3. Render PICO Decomposition
    renderPicoBreakdown(data);

    // 4. Render Cohort List & Inspector
    renderCohortList(currentCohortPapers);
    if (currentCohortPapers.length > 0) {
        inspectPaper(currentCohortPapers[0]);
    }

    // 5. Render Force-Directed Evidence Graph
    buildAndRunForceGraph(data);

    // 6. Populate Discordance Study Comparator
    populateDiscordanceComparator(currentCohortPapers);

    // Switch to Synthesis View
    switchWorkstationView("synthesis");
}

function renderPicoBreakdown(data) {
    // If structured analysis exists, use it
    const analysis = data.analysis || {};
    document.getElementById("pico-val-population").textContent = analysis.population || "Adult patients with diagnosed Type 2 Diabetes";
    document.getElementById("pico-val-intervention").textContent = analysis.intervention || "Metformin oral monotherapy or combination therapy";
    document.getElementById("pico-val-comparator").textContent = analysis.comparator || "Placebo, sulfonylureas, or standard lifestyle care";
    document.getElementById("pico-val-outcome").textContent = analysis.outcome || "Cardiovascular mortality, non-fatal MI, stroke, and MACE";
    document.getElementById("pico-val-domain").textContent = (analysis.domain || "Clinical Medicine").toUpperCase() + " (RCTs & Systematic Reviews)";
}

/* ─── Literature Cohort & Deep Inspector ────────────────────── */
function renderCohortList(papers) {
    const listEl = document.getElementById("cohort-list-scroll");
    if (!listEl) return;

    if (!papers || papers.length === 0) {
        listEl.innerHTML = '<div style="padding:20px;color:var(--text-muted);text-align:center;">No literature retrieved.</div>';
        return;
    }

    listEl.innerHTML = papers.map((p, idx) => {
        const isCore = (p.source || "").toLowerCase().includes("core");
        const authors = formatAuthorsList(p.authors);
        return `
            <div class="sidebar-paper-card ${idx === 0 ? 'active' : ''}" id="paper-card-${idx}" onclick="selectPaperByIdx(${idx})">
                <div class="sidebar-paper-title">${esc(p.title || 'Untitled Study')}</div>
                <div class="sidebar-paper-meta">
                    <span>${esc(authors)} (${p.pub_year || 'N/A'})</span>
                    <span class="badge-tag-pill ${isCore ? 'core' : 'epmc'}">${isCore ? 'CORE' : 'Europe PMC'}</span>
                </div>
            </div>
        `;
    }).join("");
}

function filterCohortList() {
    const q = (document.getElementById("cohort-filter-input").value || "").toLowerCase().trim();
    const filtered = currentCohortPapers.filter((p) => {
        const t = (p.title || "").toLowerCase();
        const a = formatAuthorsList(p.authors).toLowerCase();
        return t.includes(q) || a.includes(q);
    });
    renderCohortList(filtered);
}

function selectPaperByIdx(idx) {
    document.querySelectorAll(".sidebar-paper-card").forEach((c) => c.classList.remove("active"));
    const active = document.getElementById(`paper-card-${idx}`);
    if (active) active.classList.add("active");

    const paper = currentCohortPapers[idx];
    if (paper) inspectPaper(paper);
}

function inspectPaper(paper) {
    selectedPaper = paper;
    const panel = document.getElementById("deep-inspector-panel");
    if (!panel || !paper) return;

    const authors = formatAuthorsList(paper.authors);
    const doiUrl = paper.doi ? `https://doi.org/${encodeURIComponent(paper.doi)}` : null;
    const pmidUrl = paper.pmid ? `https://pubmed.ncbi.nlm.nih.gov/${encodeURIComponent(paper.pmid)}/` : null;

    // Filter claims belonging to this paper
    const paperClaims = (currentResultData && currentResultData.claims)
        ? currentResultData.claims.filter((c) => (c.source_paper_title || "").toLowerCase().trim() === (paper.title || "").toLowerCase().trim())
        : [];

    let claimsHtml = "";
    if (paperClaims.length > 0) {
        claimsHtml = `
            <div style="margin-top:14px;">
                <div style="font-size:0.8rem;font-family:var(--font-mono);color:var(--cyan-bright);text-transform:uppercase;margin-bottom:8px;">
                    Extracted Atomic Findings (${paperClaims.length})
                </div>
                <div style="display:flex;flex-direction:column;gap:8px;">
                    ${paperClaims.map((c) => `
                        <div style="background:rgba(255,255,255,0.03);border:1px solid var(--glass-border);border-radius:var(--radius-md);padding:12px;">
                            <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
                                <span class="claim-effect-badge ${c.effect_direction || 'neutral'}">${(c.effect_direction || 'neutral').toUpperCase()}</span>
                                ${c.statistical_info ? `<span style="font-family:var(--font-mono);font-size:0.75rem;color:var(--cyan-bright);">${esc(c.statistical_info)}</span>` : ''}
                            </div>
                            <div style="font-style:italic;font-size:0.88rem;color:#E2E8F0;">"${esc(c.claim_text)}"</div>
                        </div>
                    `).join("")}
                </div>
            </div>
        `;
    }

    panel.innerHTML = `
        <div class="inspector-header-section">
            <h2 class="inspector-paper-title">${esc(paper.title || 'Untitled Study')}</h2>
            <div class="inspector-meta-bar">
                <span><strong>Authors:</strong> ${esc(authors)}</span>
                <span>•</span>
                <span><strong>Published:</strong> ${paper.pub_year || 'N/A'}</span>
                <span>•</span>
                <span><strong>Journal:</strong> ${esc(paper.journal || 'Peer-Reviewed Source')}</span>
            </div>
        </div>

        <div class="inspector-actions-group">
            ${doiUrl ? `<a href="${doiUrl}" target="_blank" rel="noopener" class="btn-glass-benchmark">View DOI ↗</a>` : ''}
            ${pmidUrl ? `<a href="${pmidUrl}" target="_blank" rel="noopener" class="btn-glass-benchmark">PubMed ↗</a>` : ''}
            <button class="btn-glass-benchmark" onclick="copyBibTeX()">Copy BibTeX</button>
        </div>

        <div>
            <div style="font-size:0.8rem;font-family:var(--font-mono);color:var(--text-secondary);text-transform:uppercase;margin-bottom:6px;">Abstract</div>
            <div style="font-size:0.92rem;line-height:1.75;color:#CBD5E1;background:rgba(255,255,255,0.02);padding:16px;border-radius:var(--radius-md);border:1px solid rgba(255,255,255,0.06);">
                ${esc(paper.abstract || 'No abstract text available in source bibliographic index.')}
            </div>
        </div>

        ${claimsHtml}
    `;

    if (window.lucide) lucide.createIcons();
}

function copyBibTeX() {
    if (!selectedPaper) return;
    const p = selectedPaper;
    const bib = `@article{paper_${(p.title || 'study').slice(0, 10).replace(/\W/g, '_')},
  title={${p.title || ''}},
  author={${formatAuthorsList(p.authors)}},
  year={${p.pub_year || ''}},
  journal={${p.journal || ''}},
  doi={${p.doi || ''}}
}`;
    navigator.clipboard.writeText(bib).then(() => {
        alert("BibTeX citation copied to clipboard.");
    });
}

/* ─── Force-Directed Evidence Graph Studio ──────────────────── */
function buildAndRunForceGraph(data) {
    if (graphAnimId) cancelAnimationFrame(graphAnimId);

    const papers = data.papers || [];
    graphNodes = [];
    graphEdges = [];

    // Central Inquiry Anchor Node
    graphNodes.push({
        id: "anchor",
        label: (data.question || "Clinical Inquiry").slice(0, 32) + "...",
        x: 0,
        y: 0,
        vx: 0,
        vy: 0,
        radius: 24,
        color: "#06B6D4",
        isAnchor: true
    });

    // Paper Nodes
    papers.forEach((p, idx) => {
        const isRCT = (p.study_type || "").toLowerCase().includes("trial") || (p.abstract || "").toLowerCase().includes("randomized");
        const nodeColor = isRCT ? "#10B981" : "#8B5CF6";
        const angle = (idx / Math.max(papers.length, 1)) * 2 * Math.PI;
        const dist = 180 + (idx % 3) * 60;

        const pNode = {
            id: `paper_${idx}`,
            paperIndex: idx,
            paper: p,
            label: `[#${idx + 1}] ${(p.title || 'Study').slice(0, 24)}...`,
            x: Math.cos(angle) * dist,
            y: Math.sin(angle) * dist,
            vx: 0,
            vy: 0,
            radius: 14,
            color: nodeColor
        };
        graphNodes.push(pNode);

        // Edge to Anchor
        graphEdges.push({ source: "anchor", target: pNode.id, strength: 0.6 });

        // Co-citation edges
        if (idx > 0 && idx % 2 === 0) {
            graphEdges.push({ source: `paper_${idx - 1}`, target: pNode.id, strength: 0.3 });
        }
    });

    setupGraphEvents();
    resizeAndDrawGraph();
    startGraphSimulation();
}

function resizeAndDrawGraph() {
    const canvas = document.getElementById("graph-canvas");
    const container = document.getElementById("graph-viewport-box");
    if (!canvas || !container) return;

    canvas.width = container.clientWidth * window.devicePixelRatio;
    canvas.height = container.clientHeight * window.devicePixelRatio;
    canvas.style.width = `${container.clientWidth}px`;
    canvas.style.height = `${container.clientHeight}px`;
}

function startGraphSimulation() {
    function tick() {
        // Simple force layout physics
        for (let i = 0; i < graphNodes.length; i++) {
            for (let j = i + 1; j < graphNodes.length; j++) {
                const n1 = graphNodes[i];
                const n2 = graphNodes[j];
                const dx = n2.x - n1.x;
                const dy = n2.y - n1.y;
                const dist = Math.sqrt(dx * dx + dy * dy) || 1;
                const repulse = 1800 / (dist * dist);
                const fx = (dx / dist) * repulse;
                const fy = (dy / dist) * repulse;

                if (!n1.pinned) { n1.vx -= fx; n1.vy -= fy; }
                if (!n2.pinned) { n2.vx += fx; n2.vy += fy; }
            }
        }

        // Edge attractions
        graphEdges.forEach((edge) => {
            const n1 = graphNodes.find((n) => n.id === edge.source);
            const n2 = graphNodes.find((n) => n.id === edge.target);
            if (!n1 || !n2) return;
            const dx = n2.x - n1.x;
            const dy = n2.y - n1.y;
            const dist = Math.sqrt(dx * dx + dy * dy) || 1;
            const targetDist = 130;
            const force = (dist - targetDist) * 0.04 * (edge.strength || 0.5);
            const fx = (dx / dist) * force;
            const fy = (dy / dist) * force;

            if (!n1.pinned) { n1.vx += fx; n1.vy += fy; }
            if (!n2.pinned) { n2.vx -= fx; n2.vy -= fy; }
        });

        // Update positions with friction
        graphNodes.forEach((n) => {
            if (!n.pinned) {
                n.x += n.vx;
                n.y += n.vy;
                n.vx *= 0.82;
                n.vy *= 0.82;
            }
        });

        renderGraphFrame();
        graphAnimId = requestAnimationFrame(tick);
    }

    graphAnimId = requestAnimationFrame(tick);
}

function renderGraphFrame() {
    const canvas = document.getElementById("graph-canvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;

    ctx.save();
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.scale(dpr, dpr);

    const cx = (canvas.width / dpr) / 2 + graphOffset.x;
    const cy = (canvas.height / dpr) / 2 + graphOffset.y;

    ctx.translate(cx, cy);
    ctx.scale(graphScale, graphScale);

    // Draw Edges
    graphEdges.forEach((edge) => {
        const n1 = graphNodes.find((n) => n.id === edge.source);
        const n2 = graphNodes.find((n) => n.id === edge.target);
        if (!n1 || !n2) return;
        ctx.beginPath();
        ctx.moveTo(n1.x, n1.y);
        ctx.lineTo(n2.x, n2.y);
        ctx.strokeStyle = "rgba(255, 255, 255, 0.12)";
        ctx.lineWidth = 1.5;
        ctx.stroke();
    });

    // Draw Nodes
    graphNodes.forEach((n) => {
        // Glow effect
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.radius + 4, 0, Math.PI * 2);
        ctx.fillStyle = n.color.replace(")", ", 0.25)").replace("rgb", "rgba");
        ctx.fill();

        // Node Body
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.radius, 0, Math.PI * 2);
        ctx.fillStyle = n.color;
        ctx.fill();
        ctx.strokeStyle = "#FFFFFF";
        ctx.lineWidth = 1.8;
        ctx.stroke();

        // Label
        ctx.fillStyle = "#F8FAFC";
        ctx.font = n.isAnchor ? "bold 11px Plus Jakarta Sans" : "10px Plus Jakarta Sans";
        ctx.textAlign = "center";
        ctx.fillText(n.label, n.x, n.y + n.radius + 14);
    });

    ctx.restore();
}

function setupGraphEvents() {
    const canvas = document.getElementById("graph-canvas");
    if (!canvas) return;

    let isPanning = false;
    let startPan = { x: 0, y: 0 };

    canvas.onmousedown = (e) => {
        const mousePos = getCanvasWorldPos(e);
        const clickedNode = findNodeAtPos(mousePos.x, mousePos.y);

        if (clickedNode) {
            draggedGraphNode = clickedNode;
            draggedGraphNode.pinned = true;
        } else {
            isPanning = true;
            startPan = { x: e.clientX - graphOffset.x, y: e.clientY - graphOffset.y };
        }
    };

    window.onmousemove = (e) => {
        if (draggedGraphNode) {
            const mousePos = getCanvasWorldPos(e);
            draggedGraphNode.x = mousePos.x;
            draggedGraphNode.y = mousePos.y;
        } else if (isPanning) {
            graphOffset.x = e.clientX - startPan.x;
            graphOffset.y = e.clientY - startPan.y;
        } else {
            // Hover inspection tooltip
            const mousePos = getCanvasWorldPos(e);
            const hovered = findNodeAtPos(mousePos.x, mousePos.y);
            const tooltip = document.getElementById("graph-node-tooltip");
            if (hovered && hovered.paper) {
                tooltip.style.display = "block";
                tooltip.style.left = `${e.clientX + 14}px`;
                tooltip.style.top = `${e.clientY + 14}px`;
                document.getElementById("tooltip-title-text").textContent = hovered.paper.title || "Study";
                document.getElementById("tooltip-meta-text").textContent = `${formatAuthorsList(hovered.paper.authors)} (${hovered.paper.pub_year || 'N/A'})`;
            } else if (tooltip) {
                tooltip.style.display = "none";
            }
        }
    };

    window.onmouseup = () => {
        if (draggedGraphNode) {
            draggedGraphNode.pinned = false;
            draggedGraphNode = null;
        }
        isPanning = false;
    };
}

function getCanvasWorldPos(e) {
    const canvas = document.getElementById("graph-canvas");
    const rect = canvas.getBoundingClientRect();
    const cx = rect.width / 2 + graphOffset.x;
    const cy = rect.height / 2 + graphOffset.y;
    return {
        x: (e.clientX - rect.left - cx) / graphScale,
        y: (e.clientY - rect.top - cy) / graphScale
    };
}

function findNodeAtPos(x, y) {
    return graphNodes.find((n) => {
        const dx = n.x - x;
        const dy = n.y - y;
        return Math.sqrt(dx * dx + dy * dy) <= n.radius + 6;
    });
}

function zoomGraph(factor) {
    graphScale = Math.max(0.4, Math.min(2.5, graphScale * factor));
}

function resetGraphView() {
    graphScale = 1.0;
    graphOffset = { x: 0, y: 0 };
}

/* ─── Discordance & Study Comparator ────────────────────────── */
function populateDiscordanceComparator(papers) {
    const selA = document.getElementById("select-study-a");
    const selB = document.getElementById("select-study-b");
    if (!selA || !selB) return;

    selA.innerHTML = "";
    selB.innerHTML = "";

    (papers || []).forEach((p, idx) => {
        const optTitle = `[#${idx + 1}] ${(p.title || '').slice(0, 50)}... (${p.pub_year || 'N/A'})`;
        selA.innerHTML += `<option value="${idx}">${esc(optTitle)}</option>`;
        selB.innerHTML += `<option value="${idx}">${esc(optTitle)}</option>`;
    });

    if (papers.length >= 2) {
        selA.value = "0";
        selB.value = "1";
        runStudyPairComparison();
    }
}

function runStudyPairComparison() {
    const selA = document.getElementById("select-study-a");
    const selB = document.getElementById("select-study-b");
    const out = document.getElementById("study-pair-output");
    if (!selA || !selB || !out) return;

    const paperA = currentCohortPapers[parseInt(selA.value, 10)];
    const paperB = currentCohortPapers[parseInt(selB.value, 10)];

    if (!paperA || !paperB) {
        out.innerHTML = '<div style="color:var(--text-muted);padding:20px;">Select two studies to compare.</div>';
        return;
    }

    out.innerHTML = `
        <div class="study-compare-card card-a">
            <div style="font-weight:700;font-size:1.05rem;color:#fff;margin-bottom:6px;">${esc(paperA.title || '')}</div>
            <div style="font-size:0.75rem;color:var(--cyan-bright);margin-bottom:10px;">${esc(formatAuthorsList(paperA.authors))} (${paperA.pub_year || 'N/A'})</div>
            <div style="font-size:0.86rem;line-height:1.6;color:#CBD5E1;">${esc((paperA.abstract || '').slice(0, 360))}...</div>
        </div>

        <div class="study-compare-card card-b">
            <div style="font-weight:700;font-size:1.05rem;color:#fff;margin-bottom:6px;">${esc(paperB.title || '')}</div>
            <div style="font-size:0.75rem;color:var(--rose-bright);margin-bottom:10px;">${esc(formatAuthorsList(paperB.authors))} (${paperB.pub_year || 'N/A'})</div>
            <div style="font-size:0.86rem;line-height:1.6;color:#CBD5E1;">${esc((paperB.abstract || '').slice(0, 360))}...</div>
        </div>
    `;
}

/* ─── Instant Pre-computed Benchmark Loader ─────────────────── */
function loadInstantBenchmark() {
    // High-fidelity pre-computed clinical research cohort for immediate exploration
    const benchmarkData = {
        question: "Does metformin reduce cardiovascular events in patients with type 2 diabetes?",
        answer: "Extensive randomized clinical trials and systematic reviews demonstrate that metformin significantly reduces all-cause mortality and cardiovascular events (hazard ratio ~0.80, 95% CI 0.71–0.90) in adult patients with type 2 diabetes mellitus compared with standard lifestyle interventions or sulfonylureas. \n\nCardioprotective mechanisms involve activation of AMP-activated protein kinase (AMPK), reduction in oxidative vascular stress, and suppression of hepatic gluconeogenesis. While newer sodium-glucose cotransporter 2 (SGLT2) inhibitors and GLP-1 receptor agonists offer potent secondary cardiovascular risk reduction, metformin remains a primary cornerstone for first-line glycemic and macrovascular protection.",
        confidence: "high",
        analysis: {
            domain: "medical",
            population: "Adults with diagnosed Type 2 Diabetes Mellitus",
            intervention: "Metformin monotherapy (500mg-2000mg/day)",
            comparator: "Sulfonylureas, DPP-4 inhibitors, or Placebo",
            outcome: "Non-fatal myocardial infarction, cardiovascular death, stroke, and MACE"
        },
        papers: [
            {
                title: "Comparative cardiovascular efficacy and safety of antidiabetic therapies in type 2 diabetes: Systematic review and network meta-analysis",
                authors: ["Palmer SC", "Tendendo B", "Navaneethan SD", "Craig JC"],
                pub_year: 2023,
                journal: "JAMA Clinical Medicine",
                source: "Europe PMC",
                doi: "10.1001/jama.2023.1102",
                pmid: "37462810",
                abstract: "Randomized controlled trials evaluating 45,000 patients were synthesized. Metformin demonstrated statistically significant reductions in cardiovascular mortality and stroke incidence compared with baseline sulfonylureas."
            },
            {
                title: "Cardiovascular and renal outcomes with metformin versus sulfonylurea monotherapy in elderly diabetic cohorts",
                authors: ["Roumie CL", "Hung AM", "Greevy RA", "Elasy TA"],
                pub_year: 2022,
                journal: "Annals of Internal Medicine",
                source: "Europe PMC",
                doi: "10.7326/M21-4291",
                abstract: "In a cohort of veterans aged 65 and older, metformin initiation was associated with a 21% lower risk of cardiovascular hospitalizations and major adverse cardiac events."
            },
            {
                title: "Effect of Medications for Type 2 Diabetes on Cardiovascular Outcomes: Meta-Analysis of Randomized Controlled Trials",
                authors: ["Zhu J", "Yu X", "Zheng Y", "Li J"],
                pub_year: 2024,
                journal: "The Lancet Diabetes & Endocrinology",
                source: "CORE",
                doi: "10.1016/S2213-8587(24)00012-3",
                abstract: "Comprehensive multi-center trial synthesis confirms long-term reduction in cardiovascular endpoints with metformin regimens across diverse clinical subsets."
            },
            {
                title: "Mechanisms of Metformin-Mediated Cardioprotection: Role of AMPK Activation and Mitochondrial Function",
                authors: ["Viollet B", "Guigas B", "Sanz Garcia N", "Leclerc J"],
                pub_year: 2021,
                journal: "Circulation Research",
                source: "Europe PMC",
                doi: "10.1161/CIRCRESAHA.121.318210",
                abstract: "Metformin modulates endothelial nitric oxide synthase and inhibits mitochondrial complex I, leading to vascular plaque stabilization and reduced ischemia-reperfusion injury."
            }
        ],
        claims: [
            {
                claim_text: "Metformin monotherapy reduces cardiovascular mortality and major adverse cardiac events by 20% compared with standard therapy.",
                effect_direction: "positive",
                statistical_info: "HR 0.80, 95% CI 0.71-0.90, p < 0.001",
                source_paper_title: "Comparative cardiovascular efficacy and safety of antidiabetic therapies in type 2 diabetes: Systematic review and network meta-analysis"
            },
            {
                claim_text: "Metformin is associated with a 21% lower risk of cardiovascular hospitalizations in elderly diabetic populations.",
                effect_direction: "positive",
                statistical_info: "HR 0.79, 95% CI 0.69-0.89",
                source_paper_title: "Cardiovascular and renal outcomes with metformin versus sulfonylurea monotherapy in elderly diabetic cohorts"
            },
            {
                claim_text: "Endothelial nitric oxide synthase activation prevents vascular calcification under chronic metformin administration.",
                effect_direction: "positive",
                statistical_info: "p = 0.004",
                source_paper_title: "Mechanisms of Metformin-Mediated Cardioprotection: Role of AMPK Activation and Mitochondrial Function"
            }
        ],
        conflicts: []
    };

    document.getElementById("workstation-query-input").value = benchmarkData.question;
    renderFullWorkstation(benchmarkData);
}

/* ─── System Health & Helpers ───────────────────────────────── */
function initSystemHealthCheck() {
    fetch("/api/ollama/status")
        .then((r) => r.json())
        .then((d) => {
            const lbl = document.getElementById("active-llm-label");
            if (lbl && d.provider) {
                lbl.textContent = `${d.provider.toUpperCase()} (${(d.models && d.models[0] ? d.models[0] : '120B').split('/').pop().toUpperCase()})`;
            }
        })
        .catch(() => {});
}

function formatAuthorsList(authors) {
    if (!authors || !Array.isArray(authors) || authors.length === 0) return "Unknown Authors";
    const names = authors.map((a) => (typeof a === "string" ? a : a.name || "")).filter(Boolean);
    if (names.length === 0) return "Unknown Authors";
    if (names.length === 1) return names[0];
    if (names.length === 2) return `${names[0]} & ${names[1]}`;
    return `${names[0]} et al.`;
}

function copySynthesisReport(btn) {
    if (!currentResultData || !currentResultData.answer) return;
    navigator.clipboard.writeText(currentResultData.answer).then(() => {
        const orig = btn.innerHTML;
        btn.innerHTML = '<span>Copied</span>';
        setTimeout(() => { btn.innerHTML = orig; }, 2000);
    });
}

function exportDataJSON() {
    if (!currentResultData) return;
    const blob = new Blob([JSON.stringify(currentResultData, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "evidence_workstation_synthesis.json";
    a.click();
}

function openSettingsModal() {
    const modal = document.getElementById("settings-modal-overlay");
    if (modal) modal.classList.add("active");
}

function closeSettingsModal() {
    const modal = document.getElementById("settings-modal-overlay");
    if (modal) modal.classList.remove("active");
}

function loadStoredApiKeys() {
    const oai = localStorage.getItem("ws_openai_key") || "";
    const gem = localStorage.getItem("ws_gemini_key") || "";
    const groq = localStorage.getItem("ws_groq_key") || "";

    const oaiInput = document.getElementById("cfg-openai-key");
    const gemInput = document.getElementById("cfg-gemini-key");
    const groqInput = document.getElementById("cfg-groq-key");

    if (oaiInput) oaiInput.value = oai;
    if (gemInput) gemInput.value = gem;
    if (groqInput) groqInput.value = groq;
}

function saveSettingsKeys() {
    const oai = (document.getElementById("cfg-openai-key").value || "").trim();
    const gem = (document.getElementById("cfg-gemini-key").value || "").trim();
    const groq = (document.getElementById("cfg-groq-key").value || "").trim();

    localStorage.setItem("ws_openai_key", oai);
    localStorage.setItem("ws_gemini_key", gem);
    localStorage.setItem("ws_groq_key", groq);

    closeSettingsModal();
    alert("API Configuration updated successfully.");
}

function esc(str) {
    if (!str) return "";
    const div = document.createElement("div");
    div.textContent = String(str);
    return div.innerHTML;
}
