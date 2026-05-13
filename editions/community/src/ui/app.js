const els = {
    healthBadge: document.getElementById("healthBadge"),
    healthDetails: document.getElementById("healthDetails"),
    refreshHealthBtn: document.getElementById("refreshHealthBtn"),
    refreshAllBtn: document.getElementById("refreshAllBtn"),
    railHealthText: document.getElementById("railHealthText"),
    railJobsCount: document.getElementById("railJobsCount"),
    railDocsCount: document.getElementById("railDocsCount"),
    showShortcutsBtn: document.getElementById("showShortcutsBtn"),
    closeShortcutsBtn: document.getElementById("closeShortcutsBtn"),
    responsePane: document.getElementById("responsePane"),
    closeResponsePaneBtn: document.getElementById("closeResponsePaneBtn"),
    shortcutModal: document.getElementById("shortcutModal"),
    liveRegion: document.getElementById("liveRegion"),
    densityModeSelect: document.getElementById("densityModeSelect"),

    apiKeyInput: document.getElementById("apiKeyInput"),
    uploadForm: document.getElementById("uploadForm"),
    fileInput: document.getElementById("fileInput"),
    supplierInput: document.getElementById("supplierInput"),
    docTypeInput: document.getElementById("docTypeInput"),
    datePeriodInput: document.getElementById("datePeriodInput"),
    uploadMessage: document.getElementById("uploadMessage"),
    jobsList: document.getElementById("jobsList"),

    queryForm: document.getElementById("queryForm"),
    queryInput: document.getElementById("queryInput"),
    topKInput: document.getElementById("topKInput"),
    modeInput: document.getElementById("modeInput"),
    filterSupplierInput: document.getElementById("filterSupplierInput"),
    filterDocTypeInput: document.getElementById("filterDocTypeInput"),
    filterDateInput: document.getElementById("filterDateInput"),
    clearAnswerBtn: document.getElementById("clearAnswerBtn"),
    promptChips: document.getElementById("promptChips"),
    answerBox: document.getElementById("answerBox"),
    sourcesBox: document.getElementById("sourcesBox"),

    refreshDocsBtn: document.getElementById("refreshDocsBtn"),
    clearCacheBtn: document.getElementById("clearCacheBtn"),
    docsList: document.getElementById("docsList"),

    // New metric elements
    responseTimeMetric: document.getElementById("responseTimeMetric"),
    topScoreMetric: document.getElementById("topScoreMetric"),
    sourcesCountMetric: document.getElementById("sourcesCountMetric"),
    relevanceChartContainer: document.getElementById("relevanceChartContainer"),
    relevanceChart: document.getElementById("relevanceChart"),

    // Document stats
    docCountStat: document.getElementById("docCountStat"),
    docSizeStat: document.getElementById("docSizeStat"),
    docTypeChartContainer: document.getElementById("docTypeChartContainer"),
    docTypeChart: document.getElementById("docTypeChart"),
    docSizeChartContainer: document.getElementById("docSizeChartContainer"),
    docSizeChart: document.getElementById("docSizeChart"),
    featureSections: Array.from(document.querySelectorAll(".feature-section")),
    stepPills: Array.from(document.querySelectorAll(".step-pill[data-step-target]")),
    sectionToggles: Array.from(document.querySelectorAll(".section-toggle[data-target]")),
};

const suggestedPrompts = [
    "What are the critical supply chain risks in Q1 2025?",
    "Which suppliers have single-source risk exposure?",
    "What is the safety stock formula and target service levels?",
    "Which region has the fastest demand growth and why?",
];

const jobs = new Map();
let pollingTimer = null;
let relevanceChartInstance = null;
let docTypeChartInstance = null;
let docSizeChartInstance = null;
const collapseStorageKey = "scrag.collapsedPanels";
const densityStorageKey = "scrag.uiDensityMode";
let lastFocusedBeforeModal = null;

function announce(text) {
    if (!els.liveRegion || !text) return;
    els.liveRegion.textContent = "";
    requestAnimationFrame(() => {
        els.liveRegion.textContent = text;
    });
}

function cssVar(name, fallback) {
    const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return value || fallback;
}

function getApiKey() {
    return els.apiKeyInput.value.trim();
}

function defaultHeaders(json = true) {
    const headers = {};
    const key = getApiKey();
    if (key) headers["X-API-Key"] = key;
    if (json) headers["Content-Type"] = "application/json";
    return headers;
}

function setFlash(msg, isError = false) {
    els.uploadMessage.textContent = msg;
    els.uploadMessage.style.color = isError ? "#b4232c" : "#54606f";
    announce(msg);
}

function createItem(title, meta, body = "") {
    const div = document.createElement("div");
    div.className = "stack-item";
    div.innerHTML = `
    <div class="stack-item__title">${title}</div>
    <div class="stack-item__meta">${meta}</div>
    ${body ? `<div>${body}</div>` : ""}
  `;
    return div;
}

function buildFilters() {
    const filters = {
        supplier: els.filterSupplierInput.value.trim(),
        doc_type: els.filterDocTypeInput.value.trim(),
        date_period: els.filterDateInput.value.trim(),
    };
    const clean = Object.fromEntries(Object.entries(filters).filter(([, v]) => v));
    return Object.keys(clean).length ? clean : null;
}

async function refreshHealth() {
    els.healthBadge.textContent = "Checking...";
    els.healthBadge.className = "badge badge--idle";
    els.healthDetails.innerHTML = "";

    try {
        const resp = await fetch("/health", { headers: defaultHeaders(false) });
        const data = await resp.json();

        const ok = data.status === "healthy";
        els.healthBadge.textContent = ok ? "Healthy" : "Unhealthy";
        els.healthBadge.className = ok ? "badge badge--ok" : "badge badge--bad";
        if (els.railHealthText) {
            els.railHealthText.textContent = ok ? "Healthy" : "Unhealthy";
        }
        announce(`System health is ${ok ? "healthy" : "unhealthy"}.`);

        const components = data.components || {};
        for (const [k, v] of Object.entries(components)) {
            const li = document.createElement("li");
            li.textContent = `${k}: ${v}`;
            els.healthDetails.appendChild(li);
        }
    } catch {
        els.healthBadge.textContent = "Unavailable";
        els.healthBadge.className = "badge badge--bad";
        if (els.railHealthText) {
            els.railHealthText.textContent = "Unavailable";
        }
        announce("System health is unavailable.");
        const li = document.createElement("li");
        li.textContent = "Could not reach /health";
        els.healthDetails.appendChild(li);
    }
}

function renderJobs() {
    const list = [...jobs.values()].sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));
    els.jobsList.innerHTML = "";

    if (!list.length) {
        if (els.railJobsCount) {
            els.railJobsCount.textContent = "0";
        }
        els.jobsList.classList.add("empty");
        els.jobsList.textContent = "No jobs yet.";
        return;
    }

    if (els.railJobsCount) {
        els.railJobsCount.textContent = String(list.length);
    }

    els.jobsList.classList.remove("empty");
    for (const j of list) {
        const meta = `Status: ${j.status} | Chunks: ${j.chunks_indexed || 0}`;
        const body = j.error ? `Error: ${j.error}` : "";
        els.jobsList.appendChild(createItem(j.filename || j.job_id, meta, body));
    }
}

async function refreshJobs() {
    try {
        const resp = await fetch("/api/documents/jobs", { headers: defaultHeaders(false) });
        if (!resp.ok) return;
        const data = await resp.json();
        for (const j of data.jobs || []) jobs.set(j.job_id, j);
        renderJobs();
    } catch {
        // ignore polling error
    }
}

function startPollingJobs() {
    if (pollingTimer) return;
    pollingTimer = setInterval(refreshJobs, 2500);
}

async function refreshDocuments() {
    els.docsList.innerHTML = "";
    try {
        const resp = await fetch("/api/documents/list", { headers: defaultHeaders(false) });
        const data = await resp.json();
        const docs = data.documents || [];

        if (!docs.length) {
            els.docsList.classList.add("empty");
            els.docsList.textContent = "No documents indexed yet.";
            els.docTypeChartContainer.style.display = "none";
            els.docSizeChartContainer.style.display = "none";
            els.docCountStat.textContent = "0";
            els.docSizeStat.textContent = "0";
            if (els.railDocsCount) {
                els.railDocsCount.textContent = "0";
            }
            return;
        }

        els.docsList.classList.remove("empty");
        for (const doc of docs) {
            const sizeKb = (doc.size / 1024).toFixed(1);
            const modified = new Date(doc.modified * 1000).toLocaleString();
            els.docsList.appendChild(createItem(doc.filename, `${sizeKb} KB | Updated: ${modified}`));
        }

        // Create charts
        createDocumentCharts(docs);
        if (els.railDocsCount) {
            els.railDocsCount.textContent = String(docs.length);
        }
    } catch {
        els.docsList.classList.add("empty");
        els.docsList.textContent = "Failed to load documents.";
    }
}

function setupStepObserver() {
    if (!els.stepPills?.length) return;
    const targets = els.stepPills
        .map((pill) => document.getElementById(pill.dataset.stepTarget || ""))
        .filter(Boolean);
    if (!targets.length) return;

    const observer = new IntersectionObserver(
        (entries) => {
            const visible = entries
                .filter((entry) => entry.isIntersecting)
                .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
            if (!visible) return;

            const activeId = visible.target.id;
            for (const pill of els.stepPills) {
                const isActive = pill.dataset.stepTarget === activeId;
                pill.classList.toggle("is-active", isActive);
            }
        },
        {
            threshold: [0.25, 0.5, 0.75],
            rootMargin: "-20% 0px -50% 0px",
        }
    );

    for (const target of targets) {
        observer.observe(target);
    }
}

async function refreshAllPanels() {
    await Promise.all([refreshHealth(), refreshJobs(), refreshDocuments()]);
}

function getCollapsedPanels() {
    try {
        return JSON.parse(localStorage.getItem(collapseStorageKey) || "{}");
    } catch {
        return {};
    }
}

function saveCollapsedPanels(state) {
    localStorage.setItem(collapseStorageKey, JSON.stringify(state));
}

function setPanelCollapsed(targetId, collapsed) {
    const panel = document.getElementById(targetId);
    const toggle = els.sectionToggles.find((btn) => btn.dataset.target === targetId);
    if (!panel || !toggle) return;

    const expandLabel = toggle.dataset.labelExpand || "Expand";
    const collapseLabel = toggle.dataset.labelCollapse || "Collapse";
    panel.classList.toggle("is-collapsed", collapsed);
    toggle.setAttribute("aria-expanded", String(!collapsed));
    toggle.textContent = collapsed ? expandLabel : collapseLabel;
}

function setupSectionToggles() {
    const state = getCollapsedPanels();
    for (const toggle of els.sectionToggles) {
        const targetId = toggle.dataset.target;
        if (!targetId) continue;

        const panel = document.getElementById(targetId);
        const defaultCollapsed = Boolean(panel?.classList.contains("is-collapsed"));
        const hasSaved = Object.prototype.hasOwnProperty.call(state, targetId);
        setPanelCollapsed(targetId, hasSaved ? Boolean(state[targetId]) : defaultCollapsed);
        toggle.addEventListener("click", () => {
            const currentlyCollapsed = document.getElementById(targetId)?.classList.contains("is-collapsed");
            const nextCollapsed = !currentlyCollapsed;
            setPanelCollapsed(targetId, nextCollapsed);
            const next = getCollapsedPanels();
            next[targetId] = nextCollapsed;
            saveCollapsedPanels(next);
        });
    }
}

function applyDensityMode(mode) {
    const nextMode = mode === "ops" ? "ops" : "focus";
    document.body.classList.toggle("mode-focus", nextMode === "focus");
    document.body.classList.toggle("mode-ops", nextMode === "ops");
    if (els.densityModeSelect) {
        els.densityModeSelect.value = nextMode;
    }
    localStorage.setItem(densityStorageKey, nextMode);
}

function setupDensityMode() {
    const savedMode = localStorage.getItem(densityStorageKey) || "focus";
    applyDensityMode(savedMode);
    if (els.densityModeSelect) {
        els.densityModeSelect.addEventListener("change", () => {
            applyDensityMode(els.densityModeSelect.value);
        });
    }
}

function setActiveFeature(sectionId) {
    if (sectionId !== "query-section") {
        closeResponsePane();
    }

    for (const section of els.featureSections) {
        const isActive = section.id === sectionId;
        section.classList.toggle("feature-active", isActive);
        section.classList.toggle("feature-hidden", !isActive);
    }

    for (const pill of els.stepPills) {
        const isActive = pill.dataset.stepTarget === sectionId;
        pill.classList.toggle("is-active", isActive);
        if (isActive) {
            pill.setAttribute("aria-current", "step");
        } else {
            pill.removeAttribute("aria-current");
        }
    }
}

function setupFeatureSwitcher() {
    const defaultFeature = "upload-section";
    setActiveFeature(defaultFeature);

    for (const pill of els.stepPills) {
        pill.addEventListener("click", (event) => {
            event.preventDefault();
            const target = pill.dataset.stepTarget;
            if (!target) return;
            setActiveFeature(target);
            document.getElementById(target)?.scrollIntoView({ behavior: "smooth", block: "start" });
        });
    }
}

function applyStartupDefaults() {
    // Always start in calm mode with Upload as the first visible workflow step.
    localStorage.removeItem(collapseStorageKey);
    localStorage.setItem(densityStorageKey, "focus");
}

function toggleShortcutModal(forceOpen) {
    if (!els.shortcutModal) return;
    const isOpen = forceOpen ?? !els.shortcutModal.classList.contains("is-open");
    els.shortcutModal.classList.toggle("is-open", isOpen);
    els.shortcutModal.setAttribute("aria-hidden", String(!isOpen));

    if (isOpen) {
        lastFocusedBeforeModal = document.activeElement;
        const focusables = getModalFocusables();
        focusables[0]?.focus();
        announce("Keyboard shortcut panel opened.");
    } else {
        if (lastFocusedBeforeModal && typeof lastFocusedBeforeModal.focus === "function") {
            lastFocusedBeforeModal.focus();
        }
        announce("Keyboard shortcut panel closed.");
    }
}

function getModalFocusables() {
    if (!els.shortcutModal) return [];
    const selectors = [
        "button:not([disabled])",
        "a[href]",
        "input:not([disabled])",
        "select:not([disabled])",
        "textarea:not([disabled])",
        "[tabindex]:not([tabindex='-1'])",
    ];
    return Array.from(els.shortcutModal.querySelectorAll(selectors.join(","))).filter(
        (el) => el.offsetParent !== null
    );
}

function trapModalFocus(event) {
    if (!els.shortcutModal?.classList.contains("is-open") || event.key !== "Tab") return;

    const focusables = getModalFocusables();
    if (!focusables.length) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    const active = document.activeElement;

    if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus();
    } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
    }
}

function bindKeyboardShortcuts() {
    document.addEventListener("keydown", (event) => {
        const tag = event.target?.tagName;
        const inInput = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
        const key = event.key;

        if (key === "Escape") {
            if (els.responsePane?.classList.contains("is-open")) {
                closeResponsePane();
                return;
            }
            toggleShortcutModal(false);
            return;
        }

        if (key === "?" && !event.ctrlKey && !event.metaKey) {
            event.preventDefault();
            toggleShortcutModal();
            return;
        }

        if (inInput) return;

        if (key === "/") {
            event.preventDefault();
            els.queryInput.focus();
            return;
        }

        if (key.toLowerCase() === "u") {
            event.preventDefault();
            els.fileInput.focus();
            return;
        }

        if (key.toLowerCase() === "r") {
            event.preventDefault();
            refreshAllPanels();
            return;
        }

        const sectionMap = {
            "1": "upload-section",
            "2": "query-section",
            "3": "docs-section",
        };
        if (sectionMap[key]) {
            event.preventDefault();
            const target = sectionMap[key];
            setActiveFeature(target);
            document.getElementById(target)?.scrollIntoView({ behavior: "smooth", block: "start" });
        }
    });
}

function renderSources(sources = []) {
    els.sourcesBox.innerHTML = "";
    if (!sources.length) {
        els.sourcesBox.classList.add("empty");
        els.sourcesBox.textContent = "No sources returned.";
        return;
    }

    els.sourcesBox.classList.remove("empty");
    for (const src of sources) {
        const title = src.document || "Unknown document";
        const score = typeof src.score === "number" ? src.score.toFixed(3) : "n/a";
        const metaPairs = src.metadata ? Object.entries(src.metadata).map(([k, v]) => `${k}: ${v}`).join(" | ") : "";
        const body = `${src.content_snippet || ""}<br/><small>${metaPairs}</small>`;
        els.sourcesBox.appendChild(createItem(title, `Score: ${score}`, body));
    }
}

function clearAnswer() {
    els.answerBox.classList.add("empty");
    els.answerBox.textContent = "Your answer will appear here.";
    els.sourcesBox.classList.add("empty");
    els.sourcesBox.textContent = "Source citations will appear here.";
    els.relevanceChartContainer.style.display = "none";
    els.responseTimeMetric.textContent = "-";
    els.topScoreMetric.textContent = "-";
    els.sourcesCountMetric.textContent = "-";
    announce("Response panel reset.");
}

function updateMetrics(sources = [], responseTime = 0) {
    // Response time
    els.responseTimeMetric.textContent = responseTime > 0 ? `${responseTime.toFixed(0)}ms` : "-";

    // Top score
    if (sources.length > 0) {
        const topScore = Math.max(...sources.map(s => s.score || 0));
        els.topScoreMetric.textContent = topScore ? topScore.toFixed(3) : "-";
    } else {
        els.topScoreMetric.textContent = "-";
    }

    // Sources count
    els.sourcesCountMetric.textContent = sources.length.toString();
}

function setStreamingState(active) {
    els.answerBox.classList.toggle("is-streaming", active);
}

function openResponsePane() {
    if (!els.responsePane) return;
    els.responsePane.classList.add("is-open");
    els.responsePane.setAttribute("aria-hidden", "false");
}

function closeResponsePane() {
    if (!els.responsePane) return;
    els.responsePane.classList.remove("is-open");
    els.responsePane.setAttribute("aria-hidden", "true");
    setStreamingState(false);
}

function createRelevanceChart(sources = []) {
    if (sources.length === 0) {
        els.relevanceChartContainer.style.display = "none";
        return;
    }

    els.relevanceChartContainer.style.display = "block";

    const labels = sources.slice(0, 8).map((s, i) => `Source ${i + 1}`);
    const scores = sources.slice(0, 8).map(s => Math.round((s.score || 0) * 1000) / 1000);

    if (relevanceChartInstance) {
        relevanceChartInstance.destroy();
    }

    const ctx = els.relevanceChart.getContext("2d");
    relevanceChartInstance = new Chart(ctx, {
        type: "bar",
        data: {
            labels: labels,
            datasets: [
                {
                    label: "Relevance Score",
                    data: scores,
                    backgroundColor: [
                        cssVar("--accent", "#0b7c7a"),
                        "rgba(11, 124, 122, 0.82)",
                        cssVar("--accent-2", "#e07a2f"),
                        "rgba(224, 122, 47, 0.78)",
                        cssVar("--accent-3", "#1f4d7a"),
                        "rgba(31, 77, 122, 0.78)",
                        "rgba(83, 163, 159, 0.85)",
                        "rgba(111, 142, 168, 0.82)",
                    ],
                    borderRadius: 6,
                    borderSkipped: false,
                },
            ],
        },
        options: {
            indexAxis: "y",
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: false },
            },
            scales: {
                x: {
                    beginAtZero: true,
                    max: 1,
                    ticks: { color: "#54606f" },
                    grid: { color: "rgba(216, 206, 192, 0.3)" },
                },
                y: {
                    ticks: { color: "#54606f" },
                    grid: { display: false },
                },
            },
        },
    });
}

function createDocumentCharts(docs = []) {
    if (docs.length === 0) {
        els.docTypeChartContainer.style.display = "none";
        els.docSizeChartContainer.style.display = "none";
        return;
    }

    // Update stats
    els.docCountStat.textContent = docs.length.toString();
    const totalSizeMb = (docs.reduce((sum, d) => sum + (d.size || 0), 0) / (1024 * 1024)).toFixed(2);
    els.docSizeStat.textContent = totalSizeMb;

    // Group by type
    const typeMap = {};
    const sizeMap = {};
    docs.forEach(doc => {
        const filename = doc.filename || "Unknown";
        const ext = filename.split(".").pop().toUpperCase();
        typeMap[ext] = (typeMap[ext] || 0) + 1;
        sizeMap[filename] = (doc.size / 1024).toFixed(1);
    });

    // Doc Type Chart
    if (Object.keys(typeMap).length > 0) {
        els.docTypeChartContainer.style.display = "block";
        if (docTypeChartInstance) docTypeChartInstance.destroy();
        const typeCtx = els.docTypeChart.getContext("2d");
        docTypeChartInstance = new Chart(typeCtx, {
            type: "doughnut",
            data: {
                labels: Object.keys(typeMap),
                datasets: [
                    {
                        data: Object.values(typeMap),
                        backgroundColor: [
                            cssVar("--accent", "#0b7c7a"),
                            cssVar("--accent-2", "#e07a2f"),
                            cssVar("--accent-3", "#1f4d7a"),
                            "#6f8ea8",
                            "#53a39f",
                        ],
                        borderColor: "#fffdfa",
                        borderWidth: 2,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                plugins: {
                    legend: {
                        position: "bottom",
                        labels: { color: "#54606f", font: { size: 12 } },
                    },
                },
            },
        });
    }

    // Doc Size Chart (top 6 by size)
    const topDocs = docs.sort((a, b) => (b.size || 0) - (a.size || 0)).slice(0, 6);
    if (topDocs.length > 0) {
        els.docSizeChartContainer.style.display = "block";
        if (docSizeChartInstance) docSizeChartInstance.destroy();
        const sizeCtx = els.docSizeChart.getContext("2d");
        docSizeChartInstance = new Chart(sizeCtx, {
            type: "bar",
            data: {
                labels: topDocs.map((d, i) => `Doc ${i + 1}`),
                datasets: [
                    {
                        label: "Size (KB)",
                        data: topDocs.map(d => (d.size / 1024).toFixed(1)),
                        backgroundColor: "rgba(31, 77, 122, 0.72)",
                        borderColor: cssVar("--accent-3", "#1f4d7a"),
                        borderRadius: 6,
                        borderWidth: 1,
                    },
                ],
            },
            options: {
                indexAxis: "y",
                responsive: true,
                maintainAspectRatio: true,
                plugins: {
                    legend: { display: true, position: "top" },
                },
                scales: {
                    x: {
                        beginAtZero: true,
                        ticks: { color: "#54606f" },
                        grid: { color: "rgba(216, 206, 192, 0.3)" },
                    },
                    y: {
                        ticks: { color: "#54606f" },
                        grid: { display: false },
                    },
                },
            },
        });
    }
}

async function runStandardQuery(payload) {
    const startTime = performance.now();
    const resp = await fetch("/api/query/", {
        method: "POST",
        headers: defaultHeaders(true),
        body: JSON.stringify(payload),
    });
    const endTime = performance.now();
    const responseTime = endTime - startTime;

    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "Query failed");

    els.answerBox.classList.remove("empty");
    els.answerBox.textContent = data.answer || "No answer returned.";
    renderSources(data.sources || []);
    updateMetrics(data.sources || [], responseTime);
    createRelevanceChart(data.sources || []);
}

async function runStreamingQuery(payload) {
    setStreamingState(true);
    const startTime = performance.now();
    try {
        const resp = await fetch("/api/query/stream", {
            method: "POST",
            headers: defaultHeaders(true),
            body: JSON.stringify(payload),
        });

        if (!resp.ok) {
            let detail = "Streaming query failed";
            try {
                const data = await resp.json();
                detail = data.detail || detail;
            } catch {
                // keep fallback detail
            }
            throw new Error(detail);
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";
        let answer = "";

        els.answerBox.classList.remove("empty");
        els.answerBox.textContent = "";
        renderSources([]);

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });

            const blocks = buffer.split("\n\n");
            buffer = blocks.pop() || "";

            for (const block of blocks) {
                const line = block.split("\n").find((l) => l.startsWith("data: "));
                if (!line) continue;
                const payloadText = line.slice(6);
                if (payloadText === "[DONE]") {
                    const endTime = performance.now();
                    updateMetrics([], endTime - startTime);
                    return;
                }

                try {
                    const parsed = JSON.parse(payloadText);
                    if (parsed.error) {
                        throw new Error(parsed.error);
                    }
                    if (parsed.token) {
                        answer += parsed.token;
                        els.answerBox.textContent = answer;
                    }
                } catch (e) {
                    if (e instanceof Error) throw e;
                }
            }
        }
    } finally {
        setStreamingState(false);
    }
}

async function hasIndexedDocuments() {
    try {
        const resp = await fetch("/api/documents/list", { headers: defaultHeaders(false) });
        if (!resp.ok) return true;
        const data = await resp.json();
        return (data.documents || []).length > 0;
    } catch {
        // If we cannot verify, do not block queries.
        return true;
    }
}

function isEmptyKnowledgeBaseError(message = "") {
    const text = String(message).toLowerCase();
    return [
        "no documents",
        "empty knowledgebase",
        "empty knowledge base",
        "index not ready",
        "index not initialized",
        "no index",
    ].some((marker) => text.includes(marker));
}

function showEmptyKnowledgeBaseFeedback() {
    openResponsePane();
    els.answerBox.classList.remove("empty");
    els.answerBox.textContent =
        "No documents are indexed yet. Upload at least one document in Step 1 before running a query.";
    els.sourcesBox.classList.add("empty");
    els.sourcesBox.textContent = "Source citations will appear here.";
    announce("No documents are indexed yet. Please upload a document first.");
}

async function onUploadSubmit(e) {
    e.preventDefault();
    const file = els.fileInput.files[0];
    if (!file) {
        setFlash("Please select a file.", true);
        return;
    }

    setFlash("Uploading...");
    const formData = new FormData();
    formData.append("file", file);
    if (els.supplierInput.value.trim()) formData.append("supplier", els.supplierInput.value.trim());
    if (els.docTypeInput.value.trim()) formData.append("doc_type", els.docTypeInput.value.trim());
    if (els.datePeriodInput.value.trim()) formData.append("date_period", els.datePeriodInput.value.trim());

    try {
        const resp = await fetch("/api/documents/upload", {
            method: "POST",
            headers: defaultHeaders(false),
            body: formData,
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || "Upload failed");

        const ingestionId = data.job_id || data.event_id;
        if (ingestionId) {
            jobs.set(ingestionId, {
                job_id: ingestionId,
                filename: data.filename,
                status: "PENDING",
                chunks_indexed: 0,
                created_at: new Date().toISOString(),
            });
        }

        renderJobs();
        startPollingJobs();

        const modeLabel = data.event_id ? "Event" : "Job";
        const idText = ingestionId ? `${modeLabel}: ${ingestionId}` : "Queued";
        setFlash(`Uploaded ${data.filename}. ${idText}`);

        els.uploadForm.reset();
        if (localStorage.getItem("scrag.apiKey")) {
            els.apiKeyInput.value = localStorage.getItem("scrag.apiKey");
        }

        await refreshDocuments();
    } catch (err) {
        setFlash(err.message || "Upload failed", true);
    }
}

async function onQuerySubmit(e) {
    e.preventDefault();
    const query = els.queryInput.value.trim();
    if (!query) return;

    const hasDocs = await hasIndexedDocuments();
    if (!hasDocs) {
        showEmptyKnowledgeBaseFeedback();
        return;
    }

    const payload = {
        query,
        top_k: Number(els.topKInput.value || 5),
        filters: buildFilters(),
    };

    openResponsePane();
    els.answerBox.classList.remove("empty");
    els.answerBox.textContent = "Thinking...";
    setStreamingState(false);

    try {
        if (els.modeInput.value === "stream") {
            await runStreamingQuery(payload);
        } else {
            await runStandardQuery(payload);
        }
    } catch (err) {
        const message = err?.message || "Query failed.";
        if (isEmptyKnowledgeBaseError(message)) {
            showEmptyKnowledgeBaseFeedback();
            return;
        }
        els.answerBox.classList.remove("empty");
        els.answerBox.textContent = message;
        renderSources([]);
    }
}

async function clearCache() {
    try {
        const resp = await fetch("/cache", {
            method: "DELETE",
            headers: defaultHeaders(false),
        });
        const data = await resp.json();
        alert(`Cache status: ${data.status}, deleted: ${data.deleted}`);
    } catch {
        alert("Failed to clear cache.");
    }
}

function renderPromptChips() {
    for (const text of suggestedPrompts) {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "prompt-chip";
        chip.textContent = text;
        chip.addEventListener("click", () => {
            els.queryInput.value = text;
            els.queryInput.focus();
        });
        els.promptChips.appendChild(chip);
    }
}

function persistApiKey() {
    localStorage.setItem("scrag.apiKey", els.apiKeyInput.value.trim());
}

function restoreApiKey() {
    const saved = localStorage.getItem("scrag.apiKey");
    if (saved) els.apiKeyInput.value = saved;
}

function bind() {
    els.refreshHealthBtn.addEventListener("click", refreshHealth);
    if (els.refreshAllBtn) {
        els.refreshAllBtn.addEventListener("click", refreshAllPanels);
    }
    if (els.showShortcutsBtn) {
        els.showShortcutsBtn.addEventListener("click", () => toggleShortcutModal(true));
    }
    if (els.closeShortcutsBtn) {
        els.closeShortcutsBtn.addEventListener("click", () => toggleShortcutModal(false));
    }
    if (els.closeResponsePaneBtn) {
        els.closeResponsePaneBtn.addEventListener("click", closeResponsePane);
    }
    if (els.shortcutModal) {
        els.shortcutModal.addEventListener("click", (e) => {
            if (e.target === els.shortcutModal) {
                toggleShortcutModal(false);
            }
        });
        els.shortcutModal.addEventListener("keydown", trapModalFocus);
    }
    els.uploadForm.addEventListener("submit", onUploadSubmit);
    els.queryForm.addEventListener("submit", onQuerySubmit);
    els.clearAnswerBtn.addEventListener("click", clearAnswer);
    els.refreshDocsBtn.addEventListener("click", refreshDocuments);
    els.clearCacheBtn.addEventListener("click", clearCache);
    els.apiKeyInput.addEventListener("change", persistApiKey);
}

async function init() {
    applyStartupDefaults();
    restoreApiKey();
    bind();
    setupDensityMode();
    setupFeatureSwitcher();
    setupSectionToggles();
    bindKeyboardShortcuts();
    renderPromptChips();
    await refreshAllPanels();
    startPollingJobs();
}

init();
