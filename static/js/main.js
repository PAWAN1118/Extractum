let currentResults = null;

const uploadForm = document.getElementById("uploadForm");
const pdfFile = document.getElementById("pdfFile");
const dropZone = document.getElementById("dropZone");
const fileName = document.getElementById("fileName");
const fileMeta = document.getElementById("fileMeta");
const submitBtn = document.getElementById("submitBtn");
const btnText = document.getElementById("btnText");
const btnLoader = document.getElementById("btnLoader");
const statusCard = document.getElementById("statusCard");
const statusText = document.getElementById("statusText");
const emptyState = document.getElementById("emptyState");
const resultsSection = document.getElementById("results");

function formatBytes(bytes) {
    if (!bytes) return "0 KB";
    const units = ["B", "KB", "MB", "GB"];
    const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    return `${(bytes / (1024 ** index)).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function setStatus(message, state = "ready") {
    statusText.textContent = message;
    statusCard.classList.toggle("is-busy", state === "busy");
    statusCard.classList.toggle("is-error", state === "error");
}

function setLoading(isLoading) {
    submitBtn.disabled = isLoading;
    btnText.textContent = isLoading ? "Extracting..." : "Extract Data";
    btnLoader.hidden = !isLoading;
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function updateFileDisplay(file) {
    if (!file) {
        fileName.textContent = "Drop a PDF here or browse";
        fileMeta.textContent = "Up to 50 MB, PDF only";
        return;
    }

    fileName.textContent = file.name;
    fileMeta.textContent = `${formatBytes(file.size)} selected`;
    setStatus("PDF selected. Ready to extract.");
}

function buildFormData() {
    const formData = new FormData();
    formData.append("file", pdfFile.files[0]);

    uploadForm.querySelectorAll('input[type="checkbox"]').forEach((input) => {
        formData.append(input.name, input.checked ? "true" : "false");
    });

    uploadForm.querySelectorAll('input[type="number"]').forEach((input) => {
        const value = String(input.value || "").trim();
        if (value) {
            formData.append(input.name, value);
        }
    });

    uploadForm.querySelectorAll("select").forEach((input) => {
        const value = String(input.value || "").trim();
        if (value) {
            formData.append(input.name, value);
        }
    });

    return formData;
}

function countCharacters(results) {
    return (results.extractions?.text?.pages || []).reduce((total, page) => {
        return total + Number(page.char_count || 0);
    }, 0);
}

function renderSummary(results) {
    const textPages = results.extractions?.text?.total_pages || 0;
    const tables = results.extractions?.tables?.total_tables || 0;
    const images = results.extractions?.images?.total_images || 0;
    const characters = countCharacters(results);
    const totalMs = Number(results.timing_ms?.total || 0);

    document.getElementById("summaryGrid").innerHTML = [
        ["Pages", results.metadata?.total_pages || textPages || 0],
        ["Characters", characters.toLocaleString()],
        ["Tables", tables],
        ["Images", images],
        ["Time", totalMs ? `${(totalMs / 1000).toFixed(1)}s` : "N/A"],
    ].map(([label, value]) => `
        <div class="summary-card">
            <span>${label}</span>
            <strong>${value}</strong>
        </div>
    `).join("");
}

function renderWarnings(results) {
    const target = document.getElementById("warnings");
    const warnings = results.warnings || [];

    if (!warnings.length) {
        target.hidden = true;
        target.innerHTML = "";
        return;
    }

    target.hidden = false;
    target.innerHTML = warnings.map((warning) => `
        <div class="warning-item">${escapeHtml(warning)}</div>
    `).join("");
}

function renderMetadata(results) {
    const metadata = results.metadata || {};
    const entries = [
        ["Title", metadata.title || "N/A"],
        ["Author", metadata.author || "N/A"],
        ["Subject", metadata.subject || "N/A"],
        ["Creator", metadata.creator || "N/A"],
        ["Producer", metadata.producer || "N/A"],
        ["Pages", metadata.total_pages || "N/A"],
    ];

    document.getElementById("scanStatus").textContent = results.is_scanned
        ? "Scanned PDF detected"
        : "Text-based PDF detected";

    document.getElementById("metadata").innerHTML = entries.map(([label, value]) => `
        <div class="metadata-item">
            <span>${escapeHtml(label)}</span>
            <strong>${escapeHtml(value)}</strong>
        </div>
    `).join("");
}

function renderText(results) {
    const pages = results.extractions?.text?.pages || [];
    const method = results.extractions?.text?.method;
    const target = document.getElementById("text-content");

    if (!pages.length) {
        target.innerHTML = '<div class="empty-pane">No text was extracted for this run.</div>';
        return;
    }

    target.innerHTML = pages.map((page) => `
        <article class="page-text">
            <h4>Page ${escapeHtml(page.page)}${method ? ` - ${escapeHtml(method)}` : ""}</h4>
            <pre>${escapeHtml(page.text || "No text found on this page.")}</pre>
        </article>
    `).join("");
}

function getTableHeaders(table) {
    if (Array.isArray(table.headers) && table.headers.length) {
        return table.headers;
    }

    const firstRow = table.data?.[0] || {};
    return Object.keys(firstRow);
}

function renderTables(results) {
    const tables = results.extractions?.tables?.tables || [];
    const target = document.getElementById("tables-content");

    if (!tables.length) {
        target.innerHTML = '<div class="empty-pane">No tables were extracted for this run.</div>';
        return;
    }

    target.innerHTML = tables.map((table) => {
        const headers = getTableHeaders(table);
        const rows = table.data || [];

        return `
            <section class="table-wrap">
                <h4>Table ${escapeHtml(table.table_number)} - ${escapeHtml(table.rows)} rows, ${escapeHtml(table.columns)} columns</h4>
                <div class="table-scroll">
                    <table>
                        <thead>
                            <tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("")}</tr>
                        </thead>
                        <tbody>
                            ${rows.map((row) => `
                                <tr>
                                    ${headers.map((header) => `<td>${escapeHtml(row[header])}</td>`).join("")}
                                </tr>
                            `).join("")}
                        </tbody>
                    </table>
                </div>
            </section>
        `;
    }).join("");
}

function renderRecords(results) {
    const records = results.extractions?.records?.records || [];
    const target = document.getElementById("records-content");

    if (!records.length) {
        target.innerHTML = '<div class="empty-pane">No elector records were parsed for this run. (Try OCR, and/or limit to pages that contain elector entries.)</div>';
        return;
    }

    const header = `
        <div class="records-toolbar">
            <div>
                <h4>Elector records</h4>
                <p>${records.length.toLocaleString()} parsed rows</p>
            </div>
        </div>
    `;

    const cols = ["page", "serial_no", "epic_id", "name", "relation_type", "relation_name", "house_number", "age", "gender"];
    const thead = `<tr>${cols.map((c) => `<th>${escapeHtml(c.replaceAll("_", " "))}</th>`).join("")}</tr>`;
    const rows = records.slice(0, 1000).map((r) => {
        return `<tr>${cols.map((c) => `<td>${escapeHtml(r?.[c] ?? "")}</td>`).join("")}</tr>`;
    }).join("");

    target.innerHTML = `
        ${header}
        <div class="table-scroll">
            <table>
                <thead>${thead}</thead>
                <tbody>${rows}</tbody>
            </table>
        </div>
        ${records.length > 1000 ? `<div class="hint">Showing first 1000 rows in UI. Export to Excel for the full table.</div>` : ""}
    `;
}

function renderImages(results) {
    const images = results.extractions?.images?.images || [];
    const target = document.getElementById("images-content");

    if (!images.length) {
        target.innerHTML = '<div class="empty-pane">No images were extracted for this run.</div>';
        return;
    }

    target.innerHTML = `
        <div class="image-grid">
            ${images.map((image) => `
                <figure class="image-item">
                    <img src="/extracted-image/${encodeURIComponent(image.filename)}" alt="Extracted image ${escapeHtml(image.image_number)} from page ${escapeHtml(image.page)}">
                    <figcaption class="image-caption">
                        <strong>${escapeHtml(image.filename)}</strong>
                        <span>Page ${escapeHtml(image.page)} - ${escapeHtml(image.width)} x ${escapeHtml(image.height)} ${escapeHtml(String(image.format).toUpperCase())}</span>
                    </figcaption>
                </figure>
            `).join("")}
        </div>
    `;
}

function renderRaw(results) {
    const target = document.getElementById("raw-content");
    const pretty = JSON.stringify(results, null, 2);
    target.innerHTML = `
        <article class="page-text">
            <h4>Raw response</h4>
            <pre>${escapeHtml(pretty)}</pre>
        </article>
    `;
}

function renderResults(results) {
    currentResults = results;
    document.getElementById("resultTitle").textContent = results.filename || "Document summary";

    renderSummary(results);
    renderWarnings(results);
    renderMetadata(results);
    renderText(results);
    renderRecords(results);
    renderTables(results);
    renderImages(results);
    renderRaw(results);

    // Be extra defensive about visibility in case browser extensions/styles
    // interfere with the `hidden` attribute.
    emptyState.hidden = true;
    emptyState.style.display = "none";

    resultsSection.hidden = false;
    resultsSection.removeAttribute("hidden");
    resultsSection.style.display = "block";

    resultsSection.scrollIntoView({ block: "start", behavior: "smooth" });
}

async function exportData(format) {
    if (!currentResults) {
        setStatus("Run an extraction before exporting.", "error");
        return;
    }

    setStatus(`Preparing ${format.toUpperCase()} export...`, "busy");

    try {
        const response = await fetch(`/export/${format}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(currentResults),
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({ error: "Export failed" }));
            throw new Error(error.error || "Export failed");
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `pdf-extraction.${format === "excel" ? "xlsx" : format}`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.URL.revokeObjectURL(url);
        setStatus(`${format.toUpperCase()} export downloaded.`);
    } catch (error) {
        setStatus(error.message, "error");
    }
}

pdfFile.addEventListener("change", () => {
    updateFileDisplay(pdfFile.files[0]);
});

["dragenter", "dragover"].forEach((eventName) => {
    dropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        dropZone.classList.add("is-dragging");
    });
});

["dragleave", "drop"].forEach((eventName) => {
    dropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        dropZone.classList.remove("is-dragging");
    });
});

dropZone.addEventListener("drop", (event) => {
    const file = event.dataTransfer.files[0];
    if (!file) return;

    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
        setStatus("Please select a PDF file.", "error");
        return;
    }

    const transfer = new DataTransfer();
    transfer.items.add(file);
    pdfFile.files = transfer.files;
    updateFileDisplay(file);
});

uploadForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    if (!pdfFile.files.length) {
        setStatus("Choose a PDF before extracting.", "error");
        return;
    }

    setLoading(true);
    setStatus("Uploading and extracting document data...", "busy");

    try {
        const response = await fetch("/upload", {
            method: "POST",
            body: buildFormData(),
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || "Extraction failed");
        }

        renderResults(data);
        setStatus("Extraction complete.");
    } catch (error) {
        setStatus(error.message, "error");
    } finally {
        setLoading(false);
    }
});

document.querySelectorAll(".tab-btn").forEach((button) => {
    button.addEventListener("click", () => {
        const tab = button.dataset.tab;

        document.querySelectorAll(".tab-btn").forEach((tabButton) => {
            const isActive = tabButton === button;
            tabButton.classList.toggle("active", isActive);
            tabButton.setAttribute("aria-selected", String(isActive));
        });

        document.querySelectorAll(".tab-pane").forEach((pane) => {
            pane.classList.toggle("active", pane.id === `${tab}-content`);
        });
    });
});

document.querySelectorAll("[data-export]").forEach((button) => {
    button.addEventListener("click", () => exportData(button.dataset.export));
});
