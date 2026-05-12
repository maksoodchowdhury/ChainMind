const els = {
    healthBadge: document.getElementById("healthBadge"),
    healthDetails: document.getElementById("healthDetails"),
    refreshHealthBtn: document.getElementById("refreshHealthBtn"),

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

        const components = data.components || {};
        for (const [k, v] of Object.entries(components)) {
            const li = document.createElement("li");
            li.textContent = `${k}: ${v}`;
            els.healthDetails.appendChild(li);
        }
    } catch {
        els.healthBadge.textContent = "Unavailable";
        els.healthBadge.className = "badge badge--bad";
        const li = document.createElement("li");
        li.textContent = "Could not reach /health";
        els.healthDetails.appendChild(li);
    }
}

function renderJobs() {
    const list = [...jobs.values()].sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));
    els.jobsList.innerHTML = "";

    if (!list.length) {
        els.jobsList.classList.add("empty");
        els.jobsList.textContent = "No jobs yet.";
        return;
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
    } catch {
        els.docsList.classList.add("empty");
        els.docsList.textContent = "Failed to load documents.";
    }
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
    els.answerBox.textContent = "Your response will appear here.";
    els.sourcesBox.classList.add("empty");
    els.sourcesBox.textContent = "No sources yet.";
    els.relevanceChartContainer.style.display = "none";
    els.responseTimeMetric.textContent = "-";
    els.topScoreMetric.textContent = "-";
    els.sourcesCountMetric.textContent = "-";
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
                        "rgba(14, 122, 109, 0.8)",
                        "rgba(14, 122, 109, 0.7)",
                        "rgba(201, 96, 42, 0.8)",
                        "rgba(201, 96, 42, 0.7)",
                        "rgba(212, 165, 116, 0.8)",
                        "rgba(139, 95, 58, 0.8)",
                        "rgba(91, 158, 148, 0.8)",
                        "rgba(91, 158, 148, 0.6)",
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
                            "#0e7a6d",
                            "#c9602a",
                            "#d4a574",
                            "#8b5f3a",
                            "#5b9e94",
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
                        backgroundColor: "rgba(14, 122, 109, 0.7)",
                        borderColor: "rgba(14, 122, 109, 1)",
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
    const startTime = performance.now();
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

        jobs.set(data.job_id, {
            job_id: data.job_id,
            filename: data.filename,
            status: "PENDING",
            chunks_indexed: 0,
            created_at: new Date().toISOString(),
        });
        renderJobs();
        startPollingJobs();

        setFlash(`Uploaded ${data.filename}. Job: ${data.job_id}`);
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

    const payload = {
        query,
        top_k: Number(els.topKInput.value || 5),
        filters: buildFilters(),
    };

    els.answerBox.classList.remove("empty");
    els.answerBox.textContent = "Thinking...";

    try {
        if (els.modeInput.value === "stream") {
            await runStreamingQuery(payload);
        } else {
            await runStandardQuery(payload);
        }
    } catch (err) {
        els.answerBox.classList.remove("empty");
        els.answerBox.textContent = err.message || "Query failed.";
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
    els.uploadForm.addEventListener("submit", onUploadSubmit);
    els.queryForm.addEventListener("submit", onQuerySubmit);
    els.clearAnswerBtn.addEventListener("click", clearAnswer);
    els.refreshDocsBtn.addEventListener("click", refreshDocuments);
    els.clearCacheBtn.addEventListener("click", clearCache);
    els.apiKeyInput.addEventListener("change", persistApiKey);
}

async function init() {
    restoreApiKey();
    bind();
    renderPromptChips();
    await refreshHealth();
    await refreshJobs();
    await refreshDocuments();
    startPollingJobs();
}

init();
