/**
 * app.js
 * Scientific Evidence Research Workstation
 * Multi-window desktop architecture, Knowledge Graph Studio, and SSE pipeline.
 */

/* ─── Pipeline Stage Labels ─────────────────────────────────── */
const STAGE_LABELS = {
    analyzing_question: "Analyzing Question Protocol",
    question_analyzed: "Protocol Structured",
    expanding_queries: "Expanding Multi-Source Queries",
    queries_expanded: "Search Queries Generated",
    sources_selected: "Target Databases Selected",
    searching_literature: "Querying CORE & Europe PMC",
    search_complete: "Literature Retrieved",
    normalizing_papers: "Standardizing Metadata",
    deduplicating: "Cross-Source Deduplication",
    deduplicated: "Unique Cohort Established",
    checking_retractions: "Verifying Retraction Databases",
    retractions_checked: "Retractions Filtered",
    ranking_papers: "Ranking by Evidence Relevance",
    papers_ranked: "Literature Prioritized",
    fetching_fulltext: "Retrieving Full-Text XML",
    fulltext_fetched: "Full-Text Extracted",
    extracting_claims: "Extracting Atomic Findings",
    claims_extracted: "Evidence Claims Scored",
    matching_claims: "Aligning Findings with Protocol",
    assessing_quality: "Assessing Evidence Quality",
    quality_assessed: "Quality Graded",
    analyzing_coverage: "Measuring Question Coverage",
    coverage_analyzed: "Coverage Verified",
    detecting_conflicts: "Analyzing Study Concordance",
    conflicts_detected: "Concordance Analyzed",
    generating_answer: "Synthesizing Evidence",
    answer_generated: "Synthesis Complete",
    complete: "Research Ready",
    error: "System Notice",
};

/* ─── Global State ──────────────────────────────────────────── */
let isLoading = false;
let completedStages = new Set();
let currentResultData = null;
let currentRawAnswer = "";

/* ─── DOM Elements ──────────────────────────────────────────── */
const questionInput = document.getElementById("question-input");
const charCount = document.getElementById("char-count");

if (questionInput) {
    questionInput.addEventListener("input", () => {
        charCount.textContent = `${questionInput.value.length} / 2000`;
    });

    questionInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submitQuestion();
        }
    });
}

function fillExample(btn) {
    const q = btn.getAttribute("data-question");
    if (!q) return;
    questionInput.value = q;
    charCount.textContent = `${q.length} / 2000`;
    questionInput.focus();
}

/* ─── Query Submission & SSE Stream ─────────────────────────── */
function submitQuestion() {
    const question = questionInput.value.trim();
    if (!question || isLoading) return;

    if (question.length < 10) {
        showError("Please enter a more specific research question (at least 10 characters).");
        return;
    }

    isLoading = true;
    completedStages.clear();
    updateSearchButton(true);
    hideError();
    hideWorkspace();
    showPipeline();

    fetch("/api/research/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
    })
    .then((resp) => {
        if (!resp.ok) {
            return resp.json().then((d) => { throw new Error(d.error || "Request failed"); });
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        function read() {
            reader.read().then(({ done, value }) => {
                if (done) {
                    isLoading = false;
                    updateSearchButton(false);
                    return;
                }

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n");
                buffer = lines.pop();

                for (const line of lines) {
                    if (line.startsWith("data: ")) {
                        try {
                            const msg = JSON.parse(line.slice(6));
                            handleSSEMessage(msg);
                        } catch (e) {
                            // ignore partial json
                        }
                    }
                }

                read();
            }).catch((err) => {
                isLoading = false;
                updateSearchButton(false);
                showError("Stream error: " + err.message);
            });
        }

        read();
    })
    .catch((err) => {
        isLoading = false;
        updateSearchButton(false);
        showError(err.message);
    });
}

function handleSSEMessage(msg) {
    if (msg.type === "progress") {
        updatePipelineStage(msg.stage, msg.data);
    } else if (msg.type === "result") {
        renderWorkstation(msg.data);
        isLoading = false;
        updateSearchButton(false);
    } else if (msg.type === "error") {
        showError(msg.error);
        isLoading = false;
        updateSearchButton(false);
    }
}

/* ─── UI State Helpers ──────────────────────────────────────── */
function updateSearchButton(loading) {
    const btn = document.getElementById("search-btn");
    const text = btn.querySelector(".btn-text");
    const loader = btn.querySelector(".btn-loader");
    btn.disabled = loading;
    text.style.display = loading ? "none" : "inline";
    loader.style.display = loading ? "inline" : "none";
}

function showPipeline() {
    const sec = document.getElementById("pipeline-section");
    sec.style.display = "block";
    document.getElementById("pipeline-stages").innerHTML = "";
}

function hideWorkspace() {
    document.getElementById("workspace-container").style.display = "none";
}

function showError(msg) {
    const sec = document.getElementById("error-section");
    document.getElementById("error-message").textContent = msg;
    sec.style.display = "block";
}

function hideError() {
    document.getElementById("error-section").style.display = "none";
}

/* ─── Pipeline Progress Display ─────────────────────────────── */
function updatePipelineStage(stageName, data) {
    const container = document.getElementById("pipeline-stages");
    const baseName = stageName.replace(/_round_\d+$/, "");

    container.querySelectorAll(".pipeline-step-pill.active").forEach((el) => {
        el.classList.remove("active");
        el.classList.add("complete");
    });

    let el = document.getElementById(`step-${stageName}`);
    if (!el) {
        const label = STAGE_LABELS[baseName] || stageName.replace(/_/g, " ");
        const detail = _getStageDetail(data);
        el = document.createElement("div");
        el.className = "pipeline-step-pill active";
        el.id = `step-${stageName}`;
        el.innerHTML = `<span class="step-indicator-dot"></span><span>${label}${detail ? " (" + detail + ")" : ""}</span>`;
        container.appendChild(el);
    } else {
        el.className = "pipeline-step-pill active";
    }

    if (stageName === "complete") {
        container.querySelectorAll(".pipeline-step-pill.active").forEach((el) => {
            el.classList.remove("active");
            el.classList.add("complete");
        });
    }

    completedStages.add(stageName);
}

function _getStageDetail(data) {
    if (!data || !data.details) return "";
    const d = data.details;
    if (d.paper_index && d.total_papers) return `${d.paper_index}/${d.total_papers}`;
    if (d.total !== undefined) return `${d.total} papers`;
    if (d.count !== undefined) return `${d.count} claims`;
    if (d.sources) return d.sources.join(", ");
    return "";
}

/* ═══════════════════════════════════════════════════════════════
   WORKSPACE RENDERER & WINDOW CONTROLS
   ═══════════════════════════════════════════════════════════════ */
function renderWorkstation(data) {
    currentResultData = data;
    document.getElementById("workspace-container").style.display = "block";

    // Update Counter Badges
    const citCount = data.citations ? data.citations.length : 0;
    const claimCount = data.claims ? data.claims.length : 0;

    document.getElementById("tab-badge-citations").textContent = citCount;
    document.getElementById("tab-badge-claims").textContent = claimCount;
    document.getElementById("citations-count-badge").textContent = `${citCount} studies`;
    document.getElementById("claims-count-badge").textContent = `${claimCount} findings`;

    // Render Individual Windows
    renderQuestionProtocol(data.question_analysis);
    renderEvidenceSynthesis(data.answer, data.confidence, data.evidence_sufficiency, data.citations, data.claims);
    renderKnowledgeGraphStudio(data);
    renderCoverageMatrix(data.coverage);
    renderConflictsWindow(data.conflicts);
    renderCitationsMatrix(data.citations);
    renderClaimsInspector(data.claims);
    renderAuditTrail(data.pipeline_metadata);

    // Smooth scroll to synthesis
    setTimeout(() => {
        document.getElementById("window-synthesis").scrollIntoView({ behavior: "smooth", block: "start" });
    }, 200);
}

/* ─── Window Management: Minimize & Maximize ─────────────────── */
function toggleWindowMin(windowId) {
    const win = document.getElementById(windowId);
    if (!win) return;
    win.classList.toggle("is-minimized");
}

function toggleWindowMax(windowId) {
    const win = document.getElementById(windowId);
    if (!win) return;

    const isMax = win.classList.contains("is-maximized");
    // Remove any existing backdrop
    const existingBackdrop = document.querySelector(".maximized-backdrop");
    if (existingBackdrop) existingBackdrop.remove();

    if (!isMax) {
        // Maximize
        win.classList.add("is-maximized");
        const backdrop = document.createElement("div");
        backdrop.className = "maximized-backdrop";
        backdrop.onclick = () => toggleWindowMax(windowId);
        document.body.appendChild(backdrop);
    } else {
        // Restore
        win.classList.remove("is-maximized");
    }

    // If graph window was resized, trigger canvas re-render
    if (windowId === "window-graph" && typeof resizeGraphCanvas === "function") {
        setTimeout(resizeGraphCanvas, 100);
    }
}

/* ─── Workspace Layouts & Tab Switchers ──────────────────────── */
function setLayout(mode) {
    const grid = document.getElementById("workspace-grid");
    grid.className = `workspace-grid layout-${mode}`;

    document.querySelectorAll(".ws-layout-btn").forEach((btn) => btn.classList.remove("active"));
    const activeBtn = document.getElementById(`btn-layout-${mode}`);
    if (activeBtn) activeBtn.classList.add("active");

    if (typeof resizeGraphCanvas === "function") {
        setTimeout(resizeGraphCanvas, 150);
    }
}

function switchTab(tabKey) {
    document.querySelectorAll(".ws-tab-btn").forEach((btn) => btn.classList.remove("active"));
    event.currentTarget.classList.add("active");

    const windowMap = {
        all: null,
        synthesis: "window-synthesis",
        graph: "window-graph",
        citations: "window-citations",
        claims: "window-claims",
        coverage: "window-coverage",
        audit: "window-audit",
    };

    if (tabKey === "all") {
        setLayout("tiled");
        document.querySelectorAll(".ws-window").forEach((w) => { w.style.display = "flex"; });
        return;
    }

    const targetId = windowMap[tabKey];
    if (targetId) {
        const targetWin = document.getElementById(targetId);
        if (targetWin) {
            targetWin.scrollIntoView({ behavior: "smooth", block: "start" });
            targetWin.style.borderColor = "var(--color-primary-light)";
            setTimeout(() => { targetWin.style.borderColor = ""; }, 1800);
        }
    }
}

/* ═══════════════════════════════════════════════════════════════
   WINDOW CONTENT RENDERERS
   ═══════════════════════════════════════════════════════════════ */

/* ─── 1. Question Protocol Window ───────────────────────────── */
function renderQuestionProtocol(qa) {
    const body = document.getElementById("analysis-window-body");
    if (!body || !qa) return;

    const fields = [
        { label: "Domain", value: qa.domain },
        { label: "Population", value: qa.population },
        { label: "Intervention", value: qa.intervention },
        { label: "Comparator", value: qa.comparator },
        { label: "Outcome", value: qa.outcome },
        { label: "Condition", value: qa.condition },
        { label: "Dose / Protocol", value: qa.dose ? `${qa.dose} ${qa.frequency || ""}` : "" },
    ].filter((f) => f.value);

    let html = '<div class="pico-grid">';
    for (const f of fields) {
        html += `
            <div class="pico-row-card">
                <div class="pico-label">${esc(f.label)}</div>
                <div class="pico-val">${esc(f.value)}</div>
            </div>
        `;
    }

    if (qa.key_concepts && qa.key_concepts.length > 0) {
        html += `
            <div class="pico-row-card">
                <div class="pico-label">Key Scientific Concepts</div>
                <div class="pico-val" style="display:flex;flex-wrap:wrap;gap:4px;margin-top:4px">
                    ${qa.key_concepts.map((c) => `<span class="citation-badge">${esc(c)}</span>`).join("")}
                </div>
            </div>
        `;
    }

    html += "</div>";
    body.innerHTML = html;
}

/* ─── 2. Evidence Synthesis Window ──────────────────────────── */
function renderEvidenceSynthesis(answer, confidence, sufficiency, citations = [], claims = []) {
    currentRawAnswer = answer || "";
    const body = document.getElementById("synthesis-window-body");
    if (!body) return;

    const conf = confidence || "moderate";
    const citMap = {};
    if (citations && Array.isArray(citations)) {
        citations.forEach((c) => { citMap[c.index] = c; });
    }

    // Top stats bar
    const statsBar = `
        <div class="synthesis-stats-header">
            <div class="synthesis-stat-item">
                <span class="label">Confidence:</span>
                <span class="value" style="color:var(--color-primary);text-transform:uppercase">${esc(conf)}</span>
            </div>
            <div class="synthesis-stat-item">
                <span class="label">Evidence Sufficiency:</span>
                <span class="value" style="color:${sufficiency === 'sufficient' ? 'var(--color-success)' : 'var(--color-warning)'}">${esc((sufficiency || 'partial').replace('_', ' '))}</span>
            </div>
            <div class="synthesis-stat-item">
                <span class="label">Literature Sources:</span>
                <span class="value">${citations ? citations.length : 0} studies</span>
            </div>
            <div class="synthesis-stat-item">
                <span class="label">Analyzed Claims:</span>
                <span class="value">${claims ? claims.length : 0}</span>
            </div>
        </div>
    `;

    // Format rich body
    const formatted = formatSynthesisText(answer || "No synthesis could be established.", citMap);
    body.innerHTML = `${statsBar}<div class="synthesis-rich-body">${formatted}</div>`;
}

function formatSynthesisText(rawText, citMap) {
    if (!rawText) return "";

    const lines = rawText.split("\n");
    let html = "";
    let inList = false;
    let inExecutiveBox = false;

    for (let i = 0; i < lines.length; i++) {
        let line = lines[i].trim();
        if (!line) {
            if (inList) { html += "</ul>"; inList = false; }
            continue;
        }

        // Section Headers (### Header)
        if (line.startsWith("### ")) {
            if (inList) { html += "</ul>"; inList = false; }
            if (inExecutiveBox) { html += "</div></div>"; inExecutiveBox = false; }

            const headerText = line.replace(/^###\s*/, "").trim();

            if (/executive summary|direct answer|key takeaway|bottom-line/i.test(headerText)) {
                inExecutiveBox = true;
                html += `
                    <div class="executive-takeaway-box">
                        <div class="takeaway-header-row">
                            <span style="font-size:1.1rem">📌</span>
                            <span class="takeaway-title-badge">${esc(headerText)}</span>
                        </div>
                        <div class="takeaway-lead-text">
                `;
            } else {
                html += `<h4 class="synthesis-section-heading">${esc(headerText)}</h4>`;
            }
            continue;
        }

        // Bullet Items (- or * or 1.)
        const listMatch = line.match(/^[-*•]\s+(.*)$/) || line.match(/^\d+\.\s+(.*)$/);
        if (listMatch) {
            if (!inList) {
                html += '<ul class="synthesis-bullet-list">';
                inList = true;
            }
            html += `<li>${_formatInlineBadges(listMatch[1], citMap)}</li>`;
            continue;
        }

        if (inList) { html += "</ul>"; inList = false; }

        const formattedLine = _formatInlineBadges(line, citMap);
        if (inExecutiveBox) {
            html += `<p style="margin-bottom:6px">${formattedLine}</p>`;
        } else {
            html += `<p style="margin-bottom:12px">${formattedLine}</p>`;
        }
    }

    if (inList) html += "</ul>";
    if (inExecutiveBox) html += "</div></div>";

    return html;
}

function _formatInlineBadges(text, citMap) {
    let out = esc(text);

    // Bold (**word**)
    out = out.replace(/\*\*(.*?)\*\*/g, '<strong class="stat-highlight">$1</strong>');

    // Citations [1], [2]
    out = out.replace(/\[(\d+)\]/g, (match, idx) => {
        const c = citMap[idx];
        const title = c ? esc(c.title || "Study") : `Reference #${idx}`;
        return `<a class="citation-pill" href="#citation-${idx}" onclick="focusCitation(${idx})" title="${title}">[${idx}]</a>`;
    });

    return out;
}

function copyFullReport(btn) {
    if (!currentRawAnswer) return;
    navigator.clipboard.writeText(currentRawAnswer).then(() => {
        const orig = btn.innerHTML;
        btn.innerHTML = "<span>Copied! ✓</span>";
        setTimeout(() => { btn.innerHTML = orig; }, 2000);
    });
}

function focusCitation(idx) {
    const el = document.getElementById(`citation-${idx}`);
    if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        el.style.boxShadow = "0 0 0 2px var(--color-primary-light)";
        setTimeout(() => { el.style.boxShadow = ""; }, 2200);
    }
}

/* ─── 3. Knowledge Graph Studio ─────────────────────────────── */
let graphAnimId = null;
let graphNodes = [];
let graphEdges = [];
let graphZoomLevel = 1.0;
let graphPanX = 0;
let graphPanY = 0;
let resizeGraphCanvas = null;

function renderKnowledgeGraphStudio(data) {
    const canvas = document.getElementById("knowledge-graph-canvas");
    const viewport = document.getElementById("graph-canvas-viewport");
    const tooltip = document.getElementById("graph-tooltip");
    const tooltipTitle = document.getElementById("graph-tooltip-title");
    const tooltipMeta = document.getElementById("graph-tooltip-meta");

    if (!canvas || !viewport) return;

    if (graphAnimId) {
        cancelAnimationFrame(graphAnimId);
        graphAnimId = null;
    }

    const qa = data.question_analysis || {};
    const citations = data.citations || [];
    const claims = data.claims || [];
    const questionText = qa.raw_question || questionInput.value || "Research Question";

    graphNodes = [];
    graphEdges = [];
    const nodeMap = new Map();

    function addNode(n) {
        graphNodes.push(n);
        nodeMap.set(n.id, n);
        return n;
    }

    function addEdge(sourceId, targetId, type = "link") {
        if (sourceId === targetId) return;
        if (!nodeMap.has(sourceId) || !nodeMap.has(targetId)) return;
        graphEdges.push({ source: sourceId, target: targetId, type });
    }

    // Central Question Node
    addNode({
        id: "question_root",
        label: "Question",
        fullTitle: questionText,
        type: "question",
        color: "#1E40AF",
        stroke: "#172554",
        radius: 20,
        meta: "Central Research Protocol",
        x: 0,
        y: 0,
        vx: 0,
        vy: 0,
        isCenter: true,
    });

    // PICO Concepts
    const picoItems = [];
    if (qa.population) picoItems.push({ type: "Population", label: qa.population });
    if (qa.intervention) picoItems.push({ type: "Intervention", label: qa.intervention });
    if (qa.outcome) picoItems.push({ type: "Outcome", label: qa.outcome });
    if (qa.comparator) picoItems.push({ type: "Comparator", label: qa.comparator });
    if (qa.condition) picoItems.push({ type: "Condition", label: qa.condition });

    picoItems.forEach((p, i) => {
        const id = `pico_${i}`;
        addNode({
            id: id,
            label: p.label.length > 18 ? p.label.slice(0, 16) + "…" : p.label,
            fullTitle: `${p.type}: ${p.label}`,
            type: "pico",
            color: "#6D28D9",
            stroke: "#4C1D95",
            radius: 13,
            isDiamond: true,
            meta: `${p.type.toUpperCase()}: ${p.label}`,
            x: (Math.random() - 0.5) * 160,
            y: (Math.random() - 0.5) * 160,
            vx: 0,
            vy: 0,
        });
        addEdge("question_root", id, "concept");
    });

    // Literature Papers (up to 8)
    citations.slice(0, 8).forEach((c, i) => {
        const isCore = (c.source || "").toLowerCase().includes("core");
        const color = isCore ? "#2563EB" : "#0E7490";
        const stroke = isCore ? "#1D4ED8" : "#155E75";
        const id = `paper_${c.index || i}`;

        addNode({
            id: id,
            label: `[${c.index || i + 1}] ${(c.title || "Paper").slice(0, 18)}…`,
            fullTitle: c.title,
            type: "paper",
            color: color,
            stroke: stroke,
            radius: 16,
            meta: `${c.source || "Literature"} • ${c.authors ? c.authors + " " : ""}(${c.year || "N/A"})`,
            x: (Math.random() - 0.5) * 260,
            y: (Math.random() - 0.5) * 260,
            vx: 0,
            vy: 0,
        });
        addEdge("question_root", id, "evidence");

        picoItems.forEach((p, pIdx) => {
            if ((c.title || "").toLowerCase().includes(p.label.toLowerCase().slice(0, 5))) {
                addEdge(id, `pico_${pIdx}`, "matches");
            }
        });
    });

    // Claims (up to 10)
    claims.slice(0, 10).forEach((claim, i) => {
        const isPos = claim.effect_direction === "positive";
        const isNeg = claim.effect_direction === "negative";
        const color = isPos ? "#059669" : isNeg ? "#BE123C" : "#D97706";
        const stroke = isPos ? "#047857" : isNeg ? "#881337" : "#B45309";
        const id = `claim_${i}`;

        addNode({
            id: id,
            label: `Claim ${i + 1}`,
            fullTitle: claim.claim_text,
            type: "claim",
            color: color,
            stroke: stroke,
            radius: 11,
            meta: `Effect: ${claim.effect_direction || "neutral"} • Quality: ${claim.evidence_quality || "moderate"}`,
            x: (Math.random() - 0.5) * 360,
            y: (Math.random() - 0.5) * 360,
            vx: 0,
            vy: 0,
        });

        const paperNodes = graphNodes.filter((n) => n.type === "paper");
        if (paperNodes.length > 0) {
            addEdge(paperNodes[i % paperNodes.length].id, id, "extracts");
        }
    });

    // Canvas Context & HiDPI
    const ctx = canvas.getContext("2d");
    let width = 0;
    let height = 0;

    resizeGraphCanvas = function () {
        const rect = viewport.getBoundingClientRect();
        width = rect.width || 700;
        height = rect.height || 440;
        const dpr = window.devicePixelRatio || 1;

        canvas.width = width * dpr;
        canvas.height = height * dpr;
        canvas.style.width = `${width}px`;
        canvas.style.height = `${height}px`;

        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.scale(dpr, dpr);
    };
    resizeGraphCanvas();

    // Center Initial Nodes
    graphNodes.forEach((n) => {
        n.x = width / 2 + n.x;
        n.y = height / 2 + n.y;
    });

    let alpha = 1.0;
    let hoveredNode = null;
    let draggedNode = null;

    function simulate() {
        if (alpha < 0.002) return;

        const kRep = 3400;
        const kSpring = 0.04;
        const ideal = 90;

        for (let i = 0; i < graphNodes.length; i++) {
            for (let j = i + 1; j < graphNodes.length; j++) {
                const n1 = graphNodes[i];
                const n2 = graphNodes[j];
                const dx = n2.x - n1.x;
                const dy = n2.y - n1.y;
                const distSq = dx * dx + dy * dy + 80;
                const dist = Math.sqrt(distSq);
                const f = (kRep / distSq) * alpha;
                const fx = (dx / dist) * f;
                const fy = (dy / dist) * f;
                if (!n1.pinned) { n1.vx -= fx; n1.vy -= fy; }
                if (!n2.pinned) { n2.vx += fx; n2.vy += fy; }
            }
        }

        for (const e of graphEdges) {
            const s = nodeMap.get(e.source);
            const t = nodeMap.get(e.target);
            if (!s || !t) continue;
            const dx = t.x - s.x;
            const dy = t.y - s.y;
            const dist = Math.sqrt(dx * dx + dy * dy) || 1;
            const f = (dist - ideal) * kSpring * alpha;
            const fx = (dx / dist) * f;
            const fy = (dy / dist) * f;
            if (!s.pinned) { s.vx += fx; s.vy += fy; }
            if (!t.pinned) { t.vx += fx; t.vy += fy; }
        }

        const pad = 35;
        graphNodes.forEach((n) => {
            if (n.pinned) return;
            n.vx += (width / 2 - n.x) * 0.015 * alpha;
            n.vy += (height / 2 - n.y) * 0.015 * alpha;
            n.vx *= 0.83;
            n.vy *= 0.83;
            n.x += n.vx;
            n.y += n.vy;

            if (n.x < pad) n.x = pad;
            if (n.x > width - pad) n.x = width - pad;
            if (n.y < pad) n.y = pad;
            if (n.y > height - pad) n.y = height - pad;
        });

        alpha *= 0.985;
    }

    function draw() {
        ctx.clearRect(0, 0, width, height);

        // Dot Matrix Background
        ctx.fillStyle = "rgba(15, 23, 42, 0.04)";
        for (let x = 14; x < width; x += 26) {
            for (let y = 14; y < height; y += 26) {
                ctx.beginPath();
                ctx.arc(x, y, 1, 0, Math.PI * 2);
                ctx.fill();
            }
        }

        // Highlight set
        const activeIds = new Set();
        if (hoveredNode) {
            activeIds.add(hoveredNode.id);
            graphEdges.forEach((e) => {
                if (e.source === hoveredNode.id) activeIds.add(e.target);
                if (e.target === hoveredNode.id) activeIds.add(e.source);
            });
        }

        // Draw Edges
        graphEdges.forEach((e) => {
            const s = nodeMap.get(e.source);
            const t = nodeMap.get(e.target);
            if (!s || !t) return;

            const isHigh = hoveredNode && (e.source === hoveredNode.id || e.target === hoveredNode.id);
            const isDim = hoveredNode && !isHigh;

            ctx.beginPath();
            ctx.moveTo(s.x, s.y);
            ctx.lineTo(t.x, t.y);
            ctx.strokeStyle = isHigh ? "var(--color-primary-light)" : isDim ? "rgba(226, 232, 240, 0.4)" : "rgba(203, 213, 225, 0.8)";
            ctx.lineWidth = isHigh ? 2.2 : 1.2;
            ctx.stroke();
        });

        // Draw Nodes
        graphNodes.forEach((n) => {
            const isHov = hoveredNode && hoveredNode.id === n.id;
            const isDim = hoveredNode && !activeIds.has(n.id);

            ctx.save();
            ctx.globalAlpha = isDim ? 0.3 : 1.0;

            ctx.beginPath();
            if (n.isDiamond) {
                const r = n.radius * 1.1;
                ctx.moveTo(n.x, n.y - r);
                ctx.lineTo(n.x + r, n.y);
                ctx.lineTo(n.x, n.y + r);
                ctx.lineTo(n.x - r, n.y);
                ctx.closePath();
            } else {
                ctx.arc(n.x, n.y, n.radius, 0, Math.PI * 2);
            }

            ctx.fillStyle = n.color;
            ctx.shadowColor = isHov ? "rgba(30, 64, 175, 0.35)" : "rgba(0,0,0,0.06)";
            ctx.shadowBlur = isHov ? 10 : 4;
            ctx.shadowOffsetY = isHov ? 3 : 1;
            ctx.fill();

            ctx.shadowColor = "transparent";
            ctx.strokeStyle = isHov ? "#FFFFFF" : n.stroke;
            ctx.lineWidth = isHov ? 2.4 : 1.5;
            ctx.stroke();

            // Label pill
            ctx.font = `600 ${isHov ? 11 : 10}px var(--font-sans)`;
            const textW = ctx.measureText(n.label).width;
            const pillW = textW + 10;
            const pillH = 16;
            const pillX = n.x - pillW / 2;
            const pillY = n.y + n.radius + 5;

            ctx.fillStyle = isHov ? "#0F172A" : "rgba(255,255,255,0.92)";
            ctx.strokeStyle = isHov ? "var(--color-primary-light)" : "rgba(226, 232, 240, 0.9)";
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.roundRect(pillX, pillY, pillW, pillH, 4);
            ctx.fill();
            ctx.stroke();

            ctx.fillStyle = isHov ? "#FFFFFF" : "#334155";
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText(n.label, n.x, pillY + pillH / 2);

            ctx.restore();
        });
    }

    function loop() {
        simulate();
        draw();
        graphAnimId = requestAnimationFrame(loop);
    }
    loop();

    // Mouse Interactions
    viewport.onmousemove = (e) => {
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;

        if (draggedNode) {
            draggedNode.x = Math.max(20, Math.min(width - 20, mx));
            draggedNode.y = Math.max(20, Math.min(height - 20, my));
            draggedNode.vx = 0;
            draggedNode.vy = 0;
            alpha = Math.max(alpha, 0.4);
            return;
        }

        let found = null;
        for (let i = graphNodes.length - 1; i >= 0; i--) {
            const n = graphNodes[i];
            const dx = mx - n.x;
            const dy = my - n.y;
            if (Math.sqrt(dx * dx + dy * dy) <= n.radius + 8) {
                found = n;
                break;
            }
        }

        hoveredNode = found;
        if (hoveredNode) {
            canvas.style.cursor = "pointer";
            tooltipTitle.textContent = hoveredNode.fullTitle || hoveredNode.label;
            tooltipMeta.innerHTML = `<span class="tab-badge" style="background:${hoveredNode.color};color:#FFF;margin-right:6px">${hoveredNode.type.toUpperCase()}</span>${esc(hoveredNode.meta || "")}`;
            tooltip.classList.add("visible");
            const tx = Math.min(width - 290, Math.max(10, mx + 14));
            const ty = Math.min(height - 90, Math.max(10, my + 14));
            tooltip.style.left = `${tx}px`;
            tooltip.style.top = `${ty}px`;
        } else {
            canvas.style.cursor = "grab";
            tooltip.classList.remove("visible");
        }
    };

    viewport.onmousedown = (e) => {
        if (hoveredNode) {
            draggedNode = hoveredNode;
            draggedNode.pinned = true;
            alpha = 0.8;
            canvas.style.cursor = "grabbing";
        }
    };

    window.onmouseup = () => {
        if (draggedNode) {
            draggedNode.pinned = false;
            draggedNode = null;
        }
    };
}

function graphZoom(factor) {
    graphNodes.forEach((n) => {
        n.x = (n.x - 350) * factor + 350;
        n.y = (n.y - 220) * factor + 220;
    });
}

function graphResetView() {
    if (typeof resizeGraphCanvas === "function") resizeGraphCanvas();
}

/* ─── 4. Coverage Matrix Window ─────────────────────────────── */
function renderCoverageMatrix(cov) {
    const body = document.getElementById("coverage-window-body");
    if (!body || !cov) return;

    const score = cov.coverage_score || 0;
    const pct = Math.round(score * 100);

    let html = `
        <div style="font-size:0.84rem;color:var(--text-heading);font-weight:600;margin-bottom:6px">${esc(cov.coverage_summary || "")}</div>
        <div class="coverage-progress-bar-wrap">
            <div class="coverage-fill-bar" style="width:${pct}%"></div>
        </div>
        <div style="font-size:0.76rem;color:var(--text-muted);font-family:var(--font-mono);margin-bottom:12px">${pct}% Protocol Alignment</div>
        <div class="dimension-chips-wrap">
    `;

    for (const item of cov.covered_areas || []) {
        html += `<span class="dimension-chip-status covered">✓ ${esc(item)}</span>`;
    }
    for (const item of cov.missing_areas || []) {
        html += `<span class="dimension-chip-status missing">✗ ${esc(item)}</span>`;
    }

    html += "</div>";
    body.innerHTML = html;
}

/* ─── 5. Conflicts Window ───────────────────────────────────── */
function renderConflictsWindow(conflicts) {
    const win = document.getElementById("window-conflicts");
    const body = document.getElementById("conflicts-body");
    if (!conflicts || conflicts.length === 0) {
        win.style.display = "none";
        return;
    }
    win.style.display = "flex";
    let html = "";
    for (const c of conflicts) {
        html += `
            <div style="margin-bottom:12px;padding:10px 12px;background:var(--color-danger-bg);border:1px solid var(--color-danger-border);border-radius:var(--radius-sm)">
                <div style="font-weight:700;font-size:0.86rem;color:var(--color-danger)">${esc(c.topic || "Discrepancy")}</div>
                <div style="font-size:0.8rem;color:var(--text-body);margin-top:4px">${esc(c.resolution_notes || "")}</div>
            </div>
        `;
    }
    body.innerHTML = html;
}

/* ─── 6. Literature & Citations Matrix ──────────────────────── */
function renderCitationsMatrix(citations) {
    const body = document.getElementById("citations-window-body");
    if (!body) return;

    if (!citations || citations.length === 0) {
        body.innerHTML = '<p style="font-size:0.84rem;color:var(--text-muted)">No literature citations available.</p>';
        return;
    }

    let html = '<div class="citations-matrix-table">';
    for (const c of citations) {
        const idx = c.index || "?";
        const isCore = (c.source || "").toLowerCase().includes("core");
        html += `
            <div class="citation-card-row" id="citation-${idx}">
                <div class="citation-index-badge">#${idx}</div>
                <div class="citation-main-info">
                    <div class="citation-paper-title">${esc(c.title || "Untitled Paper")}</div>
                    <div class="citation-meta-row">
                        ${c.authors ? esc(c.authors) + " " : ""}
                        ${c.year ? `(${c.year}). ` : ""}
                        ${c.journal ? `<em>${esc(c.journal)}</em>` : ""}
                    </div>
                    <div class="citation-tag-badges">
                        <span class="citation-badge ${isCore ? 'source-core' : 'source-epmc'}">${esc(c.source || "Database")}</span>
                        ${c.evidence_level === 'full_text' ? '<span class="citation-badge fulltext">Full Text Verified</span>' : ''}
                        ${c.doi ? `<a class="citation-badge" href="https://doi.org/${esc(c.doi)}" target="_blank" rel="noopener">DOI: ${esc(c.doi)} ↗</a>` : ''}
                        ${c.pmid ? `<a class="citation-badge" href="https://pubmed.ncbi.nlm.nih.gov/${esc(c.pmid)}/" target="_blank" rel="noopener">PMID: ${esc(c.pmid)} ↗</a>` : ''}
                    </div>
                </div>
            </div>
        `;
    }
    html += "</div>";
    body.innerHTML = html;
}

/* ─── 7. Extracted Evidence Claims Inspector ────────────────── */
function renderClaimsInspector(claims) {
    const body = document.getElementById("claims-window-body");
    if (!body) return;

    if (!claims || claims.length === 0) {
        body.innerHTML = '<p style="font-size:0.84rem;color:var(--text-muted)">No atomic findings extracted.</p>';
        return;
    }

    let html = '<div class="claims-inspector-grid">';
    for (const c of claims.slice(0, 24)) {
        const direction = c.effect_direction || "neutral";
        html += `
            <div class="claim-card-item">
                <div class="claim-quote-text">"${esc(c.claim_text || "")}"</div>
                <div class="claim-footer-tags">
                    <span class="claim-effect-pill ${direction}">${direction}</span>
                    ${c.statistical_info ? `<span style="font-family:var(--font-mono);font-size:0.72rem;color:var(--color-primary);font-weight:700">${esc(c.statistical_info)}</span>` : ""}
                    ${c.source_paper_title ? `<span style="font-size:0.7rem;color:var(--text-muted);display:block;width:100%;margin-top:6px">${esc(c.source_paper_title.slice(0, 60))}...</span>` : ""}
                </div>
            </div>
        `;
    }
    html += "</div>";
    body.innerHTML = html;
}

/* ─── 8. Audit Trail Window ─────────────────────────────────── */
function renderAuditTrail(meta) {
    const body = document.getElementById("audit-window-body");
    if (!body || !meta) return;

    const stats = [
        { label: "Papers Retrieved", val: meta.total_papers_found || 0 },
        { label: "Duplicates Filtered", val: meta.duplicates_removed || 0 },
        { label: "Unique Cohort", val: meta.papers_after_dedup || 0 },
        { label: "Atomic Claims", val: meta.claims_extracted || 0 },
    ];

    let html = '<div class="audit-stats-grid">';
    for (const s of stats) {
        html += `
            <div class="audit-stat-card">
                <div class="audit-stat-num">${s.val}</div>
                <div class="audit-stat-label">${s.label}</div>
            </div>
        `;
    }
    html += "</div>";

    if (meta.sources_searched) {
        html += `<div style="font-size:0.78rem;color:var(--text-muted)"><strong>Integrated Repositories:</strong> ${meta.sources_searched.join(", ")}</div>`;
    }

    body.innerHTML = html;
}

/* ─── Utility: HTML Escape ──────────────────────────────────── */
function esc(str) {
    if (!str) return "";
    const div = document.createElement("div");
    div.textContent = String(str);
    return div.innerHTML;
}
