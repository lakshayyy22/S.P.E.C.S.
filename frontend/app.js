(() => {
  "use strict";

  const API_BASE = window.CATALOG_API_BASE || "http://localhost:8000";

  const dropZone = document.getElementById("dropZone");
  const fileInput = document.getElementById("fileInput");
  const fileChip = document.getElementById("fileChip");
  const fileName = document.getElementById("fileName");
  const fileRows = document.getElementById("fileRows");
  const clearFile = document.getElementById("clearFile");
  const runBtn = document.getElementById("runBtn");
  const errorBanner = document.getElementById("errorBanner");

  const progressSection = document.getElementById("progressSection");
  const progIndex = document.getElementById("progIndex");
  const progTotal = document.getElementById("progTotal");
  const progressFill = document.getElementById("progressFill");
  const statOk = document.getElementById("statOk");
  const statFail = document.getElementById("statFail");
  const statSources = document.getElementById("statSources");
  const downloadBar = document.getElementById("downloadBar");
  const downloadBtn = document.getElementById("downloadBtn");
  const downloadSummary = document.getElementById("downloadSummary");

  const resultsSection = document.getElementById("resultsSection");
  const resultsList = document.getElementById("resultsList");

  let selectedFile = null;
  let okCount = 0, failCount = 0, sourceCount = 0;
  let activeEventSource = null;
  let isStreamFinished = false;

  function showError(message) {
    if (!errorBanner) return;
    errorBanner.textContent = message;
    errorBanner.classList.add("visible");
  }

  function clearError() {
    if (!errorBanner) return;
    errorBanner.textContent = "";
    errorBanner.classList.remove("visible");
  }

  function setFile(file) {
    if (!file) return;
    const ext = file.name.toLowerCase().split(".").pop();
    if (!["xlsx", "xls", "csv"].includes(ext)) {
      showError("Unsupported file type. Please choose a .xlsx, .xls or .csv file.");
      return;
    }
    clearError();
    selectedFile = file;
    if (fileName) fileName.textContent = file.name;
    if (fileRows) fileRows.textContent = `${(file.size / 1024).toFixed(1)} KB`;
    if (fileChip) fileChip.classList.add("visible");
    if (runBtn) {
      runBtn.disabled = false;
      runBtn.textContent = "Run enrichment pipeline";
    }
  }

  if (dropZone && fileInput) {
    dropZone.onclick = (e) => {
      if (e.target !== fileInput) {
        fileInput.click();
      }
    };

    dropZone.ondragover = (e) => {
      e.preventDefault();
      dropZone.classList.add("dragover");
    };

    dropZone.ondragleave = () => {
      dropZone.classList.remove("dragover");
    };

    dropZone.ondrop = (e) => {
      e.preventDefault();
      dropZone.classList.remove("dragover");
      if (e.dataTransfer && e.dataTransfer.files.length) {
        setFile(e.dataTransfer.files[0]);
      }
    };
  }

  if (fileInput) {
    fileInput.onchange = (e) => {
      if (e.target.files && e.target.files.length) {
        setFile(e.target.files[0]);
      }
    };
  }

  if (clearFile) {
    clearFile.onclick = (e) => {
      e.stopPropagation();
      selectedFile = null;
      if (fileInput) fileInput.value = "";
      if (fileChip) fileChip.classList.remove("visible");
      if (runBtn) runBtn.disabled = true;
    };
  }

  if (runBtn) {
    runBtn.onclick = async (e) => {
      e.preventDefault();
      if (!selectedFile) return;

      clearError();
      isStreamFinished = false;

      if (activeEventSource) {
        activeEventSource.close();
        activeEventSource = null;
      }

      runBtn.disabled = true;
      runBtn.textContent = "Uploading...";
      if (resultsList) resultsList.innerHTML = "";
      if (resultsSection) resultsSection.classList.remove("visible");
      if (downloadBar) downloadBar.classList.remove("visible");

      okCount = failCount = sourceCount = 0;
      if (statOk) statOk.textContent = "0";
      if (statFail) statFail.textContent = "0";
      if (statSources) statSources.textContent = "0";

      try {
        const form = new FormData();
        form.append("file", selectedFile);
        const uploadRes = await fetch(`${API_BASE}/api/upload`, { method: "POST", body: form });
        if (!uploadRes.ok) {
          const err = await uploadRes.json().catch(() => ({ detail: uploadRes.statusText }));
          throw new Error(err.detail || "Upload failed.");
        }
        const uploadData = await uploadRes.json();
        startProcessing(uploadData.job_id, uploadData.total_rows);
      } catch (err) {
        showError(err.message || "Something went wrong uploading the file.");
        runBtn.disabled = false;
        runBtn.textContent = "Run enrichment pipeline";
      }
    };
  }

  function startProcessing(jobId, total) {
    if (progressSection) progressSection.classList.add("visible");
    if (resultsSection) resultsSection.classList.add("visible");
    if (progTotal) progTotal.textContent = total;
    if (progIndex) progIndex.textContent = "0";
    if (progressFill) {
      progressFill.style.width = "0%";
      progressFill.classList.remove("done");
    }
    if (runBtn) runBtn.textContent = "Processing...";

    const source = new EventSource(`${API_BASE}/api/process/${jobId}`);
    activeEventSource = source;

    source.addEventListener("start", (e) => {
      try {
        const data = JSON.parse(e.data);
        if (progTotal) progTotal.textContent = data.total;
      } catch (_) {}
    });

    source.addEventListener("progress", (e) => {
      try {
        const data = JSON.parse(e.data);
        if (progIndex) progIndex.textContent = data.index;
        if (progTotal) progTotal.textContent = data.total;
        if (progressFill && data.total > 0) {
          progressFill.style.width = `${(data.index / data.total) * 100}%`;
        }

        if (data.status === "success") okCount++; else failCount++;
        sourceCount += data.sources_found || 0;
        if (statOk) statOk.textContent = okCount;
        if (statFail) statFail.textContent = failCount;
        if (statSources) statSources.textContent = sourceCount;

        upsertCard(data);
      } catch (_) {}
    });

    source.addEventListener("done", (e) => {
      isStreamFinished = true;
      source.close();
      activeEventSource = null;

      try {
        const data = JSON.parse(e.data);
        if (progressFill) {
          progressFill.style.width = "100%";
          progressFill.classList.add("done");
        }
        if (downloadBar) downloadBar.classList.add("visible");
        if (downloadBtn) {
          downloadBtn.href = `${API_BASE}${data.download_url}`;
          downloadBtn.setAttribute("download", `enriched_catalog_${jobId}.csv`);
        }
        if (downloadSummary) {
          downloadSummary.textContent = `${data.succeeded} verified · ${data.failed} failed`;
        }
      } catch (_) {}

      if (runBtn) {
        runBtn.disabled = false;
        runBtn.textContent = "Enrichment Complete";
      }
    });

    source.addEventListener("error", () => {
      if (isStreamFinished || (source && source.readyState === EventSource.CLOSED)) {
        if (source) source.close();
        activeEventSource = null;
        return;
      }

      source.close();
      activeEventSource = null;

      if (runBtn) {
        runBtn.disabled = false;
        runBtn.textContent = "Run enrichment pipeline";
      }
    });
  }

  function upsertCard(data) {
    if (!resultsList) return;
    const id = `card-${data.index}`;
    let card = document.getElementById(id);
    if (!card) {
      card = document.createElement("div");
      card.className = "card";
      card.id = id;
      resultsList.appendChild(card);
    }
    renderCard(card, data);
  }

  function escapeHtml(str) {
    return String(str ?? "").replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }

  function countAnomalies(anomalies) {
    if (!anomalies) return 0;
    return Object.values(anomalies).reduce((sum, arr) => sum + (Array.isArray(arr) ? arr.length : 0), 0);
  }

  function renderCard(card, data) {
    const citations = data.citations || {};
    const anomalies = data.anomalies || {};
    const citationCount = Object.keys(citations).length;
    const anomalyCount = countAnomalies(anomalies);
    const wasExpanded = card.classList.contains("expanded");
    const activeTab = card.dataset.activeTab || "citations";

    let statusClass = "processing";
    if (data.status === "success") { statusClass = "success"; }
    else if (data.status === "error") { statusClass = "error"; }

    const brandHtml = data.brand ? `<span class="brand">${escapeHtml(data.brand)}</span> &middot; ` : "";

    let bodyHtml;
    if (data.status === "error") {
      bodyHtml = `<div class="card-error">⚠ ${escapeHtml(data.error || "Processing failed for this row.")}</div>`;
    } else if (citationCount === 0 && anomalyCount === 0) {
      bodyHtml = `<div class="empty-note">No structured attributes were extracted for this product from the reviewed sources.</div>`;
    } else {
      bodyHtml = `
        <div class="tabs">
          <button type="button" class="tab-btn ${activeTab === "citations" ? "active" : ""}" data-tab="citations">
            Citations <span class="n">${citationCount}</span>
          </button>
          <button type="button" class="tab-btn ${activeTab === "anomalies" ? "active" : ""}" data-tab="anomalies">
            Anomalies <span class="n">${anomalyCount}</span>
          </button>
          <button type="button" class="close-tab" title="Collapse">&times;</button>
        </div>
        <div class="tab-panel" data-panel="citations" style="${activeTab === "citations" ? "" : "display:none"}">
          ${renderCitations(citations)}
        </div>
        <div class="tab-panel" data-panel="anomalies" style="${activeTab === "anomalies" ? "" : "display:none"}">
          ${renderAnomalies(anomalies)}
        </div>
      `;
    }

    card.innerHTML = `
      <div class="card-head">
        <span class="status-dot ${statusClass}"></span>
        <div class="card-titles">
          <div class="pn">${brandHtml}${escapeHtml(data.part_num || "—")}</div>
          <div class="name">${escapeHtml(data.product_name || "")}</div>
        </div>
        <div class="card-meta">
          ${citationCount ? `<span class="badge cite">${citationCount} cite<span class="full">d</span></span>` : ""}
          ${anomalyCount ? `<span class="badge anomaly">${anomalyCount} anomal${anomalyCount === 1 ? "y" : "ies"}</span>` : ""}
          <span class="chevron">&#9656;</span>
        </div>
      </div>
      <div class="card-body">${bodyHtml}</div>
    `;

    if (wasExpanded) card.classList.add("expanded");

    const head = card.querySelector(".card-head");
    if (head) {
      head.onclick = () => {
        card.classList.toggle("expanded");
      };
    }

    const closeBtn = card.querySelector(".close-tab");
    if (closeBtn) {
      closeBtn.onclick = (e) => {
        e.stopPropagation();
        card.classList.remove("expanded");
      };
    }

    card.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.onclick = (e) => {
        e.stopPropagation();
        const tab = btn.dataset.tab;
        card.dataset.activeTab = tab;
        card.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
        card.querySelectorAll(".tab-panel").forEach((p) => {
          p.style.display = p.dataset.panel === tab ? "" : "none";
        });
      };
    });
  }

  function renderCitations(citations) {
    const keys = Object.keys(citations);
    if (!keys.length) {
      return `<div class="empty-note">No source citations recorded for this product.</div>`;
    }
    const rows = keys.map((label) => `
      <div class="detail-row">
        <div class="k">${escapeHtml(label)}</div>
        <div class="v"><a href="${escapeHtml(citations[label])}" target="_blank" rel="noopener noreferrer">${escapeHtml(citations[label])}</a></div>
      </div>
    `).join("");
    return `<div class="detail-table">${rows}</div>`;
  }

  function renderAnomalies(anomalies) {
    const keys = Object.keys(anomalies);
    if (!keys.length) {
      return `<div class="empty-note">No conflicting values were found across sources — every source agreed.</div>`;
    }
    const rows = keys.flatMap((label) => {
      const entries = Array.isArray(anomalies[label]) ? anomalies[label] : [];
      return entries.map((entry) => `
        <div class="detail-row">
          <div class="k">${escapeHtml(label)}</div>
          <div class="v">
            <span class="anomaly-val">${escapeHtml(entry.Value ?? entry.value)}</span>
            <a href="${escapeHtml(entry.Url ?? entry.url)}" target="_blank" rel="noopener noreferrer">source</a>
          </div>
        </div>
      `);
    }).join("");
    return `<div class="detail-table">${rows}</div>`;
  }
})();