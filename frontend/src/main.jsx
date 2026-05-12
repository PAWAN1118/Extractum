import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { gsap } from "gsap";
import "./index.css";

const formats = [
  { label: "PDF", status: "ready" },
  { label: "XLSX / CSV", status: "soon" },
  { label: "DOCX", status: "soon" },
  { label: "PNG / JPG (OCR)", status: "soon" },
  { label: "JSON", status: "soon" },
  { label: "XML / TXT", status: "soon" },
];
const supportedExtensions = [".pdf"];

const tabs = ["visuals", "text", "records", "tables", "images", "raw"];

const progressStages = [
  "Uploading file",
  "Reading metadata",
  "Extracting content",
  "Parsing records",
  "Saving results",
  "Preparing results",
];

const defaultOptions = {
  extract_text: true,
  extract_tables: false,
  extract_images: false,
  use_ocr: false,
  page_from: "1",
  page_to: "5",
  ocr_dpi: "150",
};

const presets = [
  {
    id: "fast",
    name: "Fast preview",
    detail: "Best first run. Reads pages 1-5 with text only.",
    options: defaultOptions,
  },
  {
    id: "full",
    name: "Full text",
    detail: "Reads all available text. Good for digital files.",
    options: { ...defaultOptions, page_from: "", page_to: "" },
  },
  {
    id: "scan",
    name: "Scanned PDF",
    detail: "OCR first 10 pages at fast quality.",
    options: { ...defaultOptions, use_ocr: true, page_to: "10" },
  },
  {
    id: "deep",
    name: "Deep extract",
    detail: "Text, tables, and images. Slower, use a range.",
    options: { ...defaultOptions, extract_tables: true, extract_images: true, page_to: "10", ocr_dpi: "200" },
  },
];

function formatBytes(bytes) {
  if (!bytes) return "0 KB";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function Metric({ label, value }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Toggle({ label, detail, checked, onChange }) {
  return (
    <label className="toggle-row">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span className="switch" />
      <span>
        <strong>{label}</strong>
        <small>{detail}</small>
      </span>
    </label>
  );
}

function UploadIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 3v12m0-12 4.5 4.5M12 3 7.5 7.5M5 15v4h14v-4" />
    </svg>
  );
}

function FileIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M7 3h7l4 4v14H7z" />
      <path d="M14 3v5h5M9 13h6M9 17h4" />
    </svg>
  );
}

function ParticleBackground() {
  return (
    <div className="particle-layer" aria-hidden="true">
      {Array.from({ length: 28 }).map((_, index) => (
        <span key={index} style={{ "--i": index }} />
      ))}
    </div>
  );
}

function SkeletonResults() {
  return (
    <section className="skeleton-section" aria-label="Loading extraction preview">
      <div className="skeleton-card wide" />
      <div className="skeleton-grid">
        <div className="skeleton-card" />
        <div className="skeleton-card" />
        <div className="skeleton-card" />
      </div>
      <div className="skeleton-table">
        <span />
        <span />
        <span />
        <span />
      </div>
    </section>
  );
}

function App() {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState("Ready. Fast preview is selected by default.");
  const [activeTab, setActiveTab] = useState("text");
  const [results, setResults] = useState(null);
  const [options, setOptions] = useState(defaultOptions);
  const [progressStep, setProgressStep] = useState(-1);

  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.from(".topbar", { y: -18, opacity: 0, duration: 0.7, ease: "power3.out" });
      gsap.from(".hero .kicker, .hero h1, .hero .lede, .hero-stats", {
        y: 30,
        opacity: 0,
        duration: 0.75,
        stagger: 0.1,
        ease: "power3.out",
      });
      gsap.from(".drop-target, .format-strip, .preset-grid, .recommendation-grid, .control-grid", {
        y: 34,
        opacity: 0,
        duration: 0.75,
        stagger: 0.08,
        delay: 0.25,
        ease: "power3.out",
      });
      gsap.to(".gradient-orb", {
        y: -22,
        x: 18,
        duration: 5,
        repeat: -1,
        yoyo: true,
        ease: "sine.inOut",
        stagger: 0.5,
      });
    });

    return () => ctx.revert();
  }, []);

  const summary = useMemo(() => {
    const textPages = results?.extractions?.text?.total_pages || 0;
    const chars = (results?.extractions?.text?.pages || []).reduce((sum, page) => sum + Number(page.char_count || 0), 0);
    return {
      pages: results?.metadata?.total_pages || textPages || 0,
      chars: chars.toLocaleString(),
      records: results?.extractions?.records?.total_records || 0,
      tables: results?.extractions?.tables?.total_tables || 0,
      time: results?.timing_ms?.total ? `${(results.timing_ms.total / 1000).toFixed(1)}s` : "N/A",
    };
  }, [results]);

  const speedHint = useMemo(() => {
    const heavy = [options.extract_tables, options.extract_images, options.use_ocr].filter(Boolean).length;
    const hasRange = options.page_from || options.page_to;

    if (heavy === 0 && hasRange) return "Fast: limited-page text extraction.";
    if (heavy === 0) return "Moderate: full-document text extraction.";
    if (options.use_ocr && !hasRange) return "Slow: OCR across all pages. Add a page range.";
    if (heavy >= 2) return "Slow: multiple heavy extractors enabled.";
    return "Balanced: one heavy extractor enabled.";
  }, [options]);

  const recommendations = useMemo(() => {
    const notes = [];
    const hasRange = options.page_from || options.page_to;
    const rangeText = hasRange ? `Processing pages ${options.page_from || "1"}-${options.page_to || "end"}.` : "No page range selected.";

    if (!file) {
      notes.push({ title: "Start here", detail: "Choose a file, then run Fast preview first.", tone: "info" });
    } else {
      notes.push({ title: "Ready", detail: `${file.name} selected. ${rangeText}`, tone: "good" });
    }

    if (options.use_ocr) {
      notes.push({
        title: hasRange ? "OCR range set" : "OCR needs a range",
        detail: hasRange ? "Good. OCR is much faster with limited pages." : "Add From/To pages before OCR to avoid long waits.",
        tone: hasRange ? "good" : "warn",
      });
    } else {
      notes.push({ title: "Fast text mode", detail: "OCR is off, so text/table extraction should be faster.", tone: "good" });
    }

    if (options.extract_tables || options.extract_images) {
      notes.push({ title: "Heavy options on", detail: "Tables/images can be slow. Keep a page range for best speed.", tone: hasRange ? "info" : "warn" });
    } else {
      notes.push({ title: "Fast settings", detail: "Tables and images are off. This is the fastest path.", tone: "good" });
    }

    return notes;
  }, [file, options]);

  function setOption(key, value) {
    setOptions((current) => ({ ...current, [key]: value }));
  }

  function applyPreset(preset) {
    setOptions(preset.options);
    setStatus(`${preset.name} selected.`);
  }

  function chooseFile(nextFile) {
    if (!nextFile) return;
    const lowerName = nextFile.name.toLowerCase();
    if (!supportedExtensions.some((extension) => lowerName.endsWith(extension))) {
      setStatus("Only PDF is available now. Other file types are coming soon.");
      return;
    }
    setFile(nextFile);
    setStatus(`${nextFile.name} selected. Use Fast preview first for best speed.`);
  }

  function buildFormData() {
    const formData = new FormData();
    formData.append("file", file);
    Object.entries(options).forEach(([key, value]) => {
      if (typeof value === "boolean") {
        formData.append(key, value ? "true" : "false");
      } else if (String(value).trim()) {
        formData.append(key, value);
      }
    });
    return formData;
  }

  async function submitExtraction(event) {
    event.preventDefault();
    if (!file) {
      setStatus("Drop or browse a supported file before extracting.");
      return;
    }

    setLoading(true);
    setProgressStep(0);
    setStatus(options.use_ocr ? "Starting OCR job. Limited pages are much faster..." : "Starting extraction job...");

    let stage = 0;
    const progressTimer = window.setInterval(() => {
      stage = Math.min(stage + 1, progressStages.length - 1);
      setProgressStep(stage);
    }, options.use_ocr || options.extract_tables || options.extract_images ? 2200 : 900);

    try {
      const response = await fetch("/upload", {
        method: "POST",
        body: buildFormData(),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Extraction failed");

      const finalData = data.job_id ? await pollJob(data.job_id) : data;
      setResults(finalData);
      setActiveTab("visuals");
      setProgressStep(progressStages.length - 1);
      setStatus("Extraction complete. Review results below or export data.");
    } catch (error) {
      setStatus(error.message);
    } finally {
      window.clearInterval(progressTimer);
      setLoading(false);
      window.setTimeout(() => setProgressStep(-1), 900);
    }
  }

  async function pollJob(jobId) {
    const started = Date.now();

    while (Date.now() - started < 20 * 60 * 1000) {
      const response = await fetch(`/jobs/${encodeURIComponent(jobId)}`);
      const job = await response.json();
      if (!response.ok) throw new Error(job.error || "Could not read extraction job");

      if (job.message) setStatus(job.message);
      if (job.status === "complete") return job.result;
      if (job.status === "failed") throw new Error(job.error || "Extraction failed");

      await new Promise((resolve) => window.setTimeout(resolve, 1200));
    }

    throw new Error("Extraction is taking longer than expected. Try a smaller page range or disable OCR/images.");
  }

  async function exportData(format) {
    if (!results) return;
    setStatus(`Preparing ${format.toUpperCase()} export...`);
    try {
      const response = await fetch(`/export/${format}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(results),
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({ error: "Export failed" }));
        throw new Error(error.error || "Export failed");
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `extractum-export.${format === "excel" ? "xlsx" : format}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setStatus(`${format.toUpperCase()} export downloaded.`);
    } catch (error) {
      setStatus(error.message);
    }
  }

  return (
    <main className="site-shell">
      <ParticleBackground />
      <div className="gradient-orb orb-one" aria-hidden="true" />
      <div className="gradient-orb orb-two" aria-hidden="true" />

      <header className="topbar">
        <a className="brand" href="#ingest" aria-label="Extractum home">
          <span className="brand-icon"><FileIcon /></span>
          <span>
            <strong>EXTRACTUM</strong>
            <small>DATA EXTRACTOR - V1</small>
          </span>
        </a>
        <p className="built-with">BUILT WITH <span>PyMuPDF - pandas - tesseract - supabase - react</span></p>
      </header>

      <section className="hero">
        <p className="kicker">A FAST PDF DATA EXTRACTOR</p>
        <h1>Turn files into <span>clean structured data.</span></h1>
        <p className="lede">
          Start with a fast preview, then enable OCR, tables, or images only when needed.
          Export extracted text, tables, image OCR, and elector records to CSV, Excel, or JSON.
        </p>
        <div className="hero-stats">
          <article><span>01</span><strong>Async jobs</strong><small>Large files keep running after upload.</small></article>
          <article><span>02</span><strong>Fast preview</strong><small>Start with pages 1-5 by default.</small></article>
          <article><span>03</span><strong>Excel ready</strong><small>Extracted data opens first.</small></article>
        </div>
      </section>

      <section className="ingest" id="ingest">
        <div className="section-label">
          <span>01 - INGEST</span>
          <span>ASYNC - SUPABASE - FAST</span>
        </div>
        <h2>Drop a file. Choose speed first.</h2>

        <form onSubmit={submitExtraction}>
          <label
            className={`drop-target ${dragging ? "is-dragging" : ""}`}
            onDragEnter={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragOver={(event) => event.preventDefault()}
            onDragLeave={(event) => {
              event.preventDefault();
              setDragging(false);
            }}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              chooseFile(event.dataTransfer.files[0]);
            }}
          >
            <input
              ref={inputRef}
              type="file"
              accept={supportedExtensions.join(",")}
              onChange={(event) => chooseFile(event.target.files[0])}
            />
            <span className="upload-card"><UploadIcon /></span>
            <strong>{file ? file.name : "Drag a file here"}</strong>
            <small>{file ? `${formatBytes(file.size)} ready to extract` : "Or click to browse. PDF is available now; other formats are coming soon."}</small>
            <button type="button" onClick={() => inputRef.current?.click()}>Browse files</button>
          </label>

          <div className="format-strip">
            {formats.map((format) => (
              <span key={format.label} className={format.status === "soon" ? "is-soon" : "is-ready"}>
                <FileIcon />{format.label}<em>{format.status === "ready" ? "ready" : "soon"}</em>
              </span>
            ))}
          </div>

          <div className="preset-grid" aria-label="Extraction presets">
            {presets.map((preset) => (
              <button type="button" key={preset.id} onClick={() => applyPreset(preset)}>
                <strong>{preset.name}</strong>
                <span>{preset.detail}</span>
              </button>
            ))}
          </div>

          <div className="recommendation-grid" aria-label="Smart recommendations">
            {recommendations.map((note) => (
              <article className={`recommendation-card ${note.tone}`} key={note.title}>
                <strong>{note.title}</strong>
                <span>{note.detail}</span>
              </article>
            ))}
          </div>

          <div className="control-grid">
            <div className="panel">
              <p className="panel-label">EXTRACT</p>
              <Toggle label="Text" detail="Fast. Required for elector parsing." checked={options.extract_text} onChange={(value) => setOption("extract_text", value)} />
              <Toggle label="Tables" detail="Use for spreadsheets or tabular PDFs." checked={options.extract_tables} onChange={(value) => setOption("extract_tables", value)} />
              <Toggle label="Images" detail="Slow. Extracts embedded assets." checked={options.extract_images} onChange={(value) => setOption("extract_images", value)} />
              <Toggle label="OCR" detail="Use for scanned PDFs or images." checked={options.use_ocr} onChange={(value) => setOption("use_ocr", value)} />
            </div>

            <div className="panel">
              <p className="panel-label">SPEED CONTROLS</p>
              <div className="field-row">
                <label>From<input type="number" min="1" value={options.page_from} onChange={(event) => setOption("page_from", event.target.value)} placeholder="1" /></label>
                <label>To<input type="number" min="1" value={options.page_to} onChange={(event) => setOption("page_to", event.target.value)} placeholder="5" /></label>
              </div>
              <label className="select-field">OCR Quality
                <select value={options.ocr_dpi} onChange={(event) => setOption("ocr_dpi", event.target.value)}>
                  <option value="150">Fast - 150 DPI</option>
                  <option value="200">Balanced - 200 DPI</option>
                  <option value="300">High - 300 DPI</option>
                </select>
              </label>
              <button className="extract-button" disabled={loading}>{loading ? "Extracting..." : "Extract data"}</button>
              <p className="status-line">{status}</p>
              <p className={`speed-hint ${speedHint.startsWith("Slow") ? "is-slow" : ""}`}>{speedHint}</p>
            </div>
          </div>

          {progressStep >= 0 && (
            <div className="progress-panel" aria-label="Extraction progress">
              {progressStages.map((stage, index) => (
                <div className={index <= progressStep ? "done" : ""} key={stage}>
                  <span>{index + 1}</span>
                  <strong>{stage}</strong>
                </div>
              ))}
            </div>
          )}
        </form>
      </section>

      {loading && <SkeletonResults />}

      <Results results={results} summary={summary} activeTab={activeTab} setActiveTab={setActiveTab} exportData={exportData} />
    </main>
  );
}

function Results({ results, summary, activeTab, setActiveTab, exportData }) {
  if (!results) {
    return (
      <section className="how-it-works">
        <p className="kicker">HOW IT WORKS</p>
        <div className="steps">
          <div><strong>01</strong><span>Choose Fast preview first</span></div>
          <div><strong>02</strong><span>Enable OCR or tables only if needed</span></div>
          <div><strong>03</strong><span>Export records to CSV or Excel</span></div>
        </div>
      </section>
    );
  }

  return (
    <section className="results" id="results">
      <div className="results-head">
        <div>
          <p className="kicker">02 - RESULTS</p>
          <h2>{results.filename}</h2>
        </div>
        <div className="exports">
          <button onClick={() => exportData("json")}>JSON</button>
          <button onClick={() => exportData("excel")}>Excel</button>
          <button onClick={() => exportData("csv")}>CSV</button>
        </div>
      </div>

      <div className="metrics">
        <Metric label="Pages" value={summary.pages} />
        <Metric label="Chars" value={summary.chars} />
        <Metric label="Records" value={summary.records} />
        <Metric label="Tables" value={summary.tables} />
        <Metric label="Time" value={summary.time} />
      </div>

      {!!results.warnings?.length && (
        <div className="warnings">
          {results.warnings.map((warning) => <p key={warning}>{warning}</p>)}
        </div>
      )}

      <div className="result-tabs">
        {tabs.map((tab) => (
          <button key={tab} className={activeTab === tab ? "active" : ""} onClick={() => setActiveTab(tab)}>
            {tab}
          </button>
        ))}
      </div>

      <div className="result-body">
        {activeTab === "text" && <TextView pages={results.extractions?.text?.pages || []} />}
        {activeTab === "visuals" && <VisualsView results={results} />}
        {activeTab === "records" && <RecordView records={results.extractions?.records?.records || []} />}
        {activeTab === "tables" && <TableView tables={results.extractions?.tables?.tables || []} />}
        {activeTab === "images" && <ImageView images={results.extractions?.images?.images || []} />}
        {activeTab === "raw" && <pre>{JSON.stringify(results, null, 2)}</pre>}
      </div>
    </section>
  );
}

function BarChart({ title, subtitle, data }) {
  const max = Math.max(...data.map((item) => Number(item.value) || 0), 1);
  return (
    <section className="chart-card">
      <div className="chart-head">
        <h3>{title}</h3>
        {subtitle && <p>{subtitle}</p>}
      </div>
      <div className="bar-list">
        {data.map((item) => {
          const value = Number(item.value) || 0;
          return (
            <div className="bar-row" key={item.label}>
              <div className="bar-label">
                <span>{item.label}</span>
                <strong>{item.display ?? value}</strong>
              </div>
              <div className="bar-track">
                <span style={{ width: `${Math.max((value / max) * 100, value ? 4 : 0)}%` }} />
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function DonutChart({ title, subtitle, data }) {
  const total = data.reduce((sum, item) => sum + (Number(item.value) || 0), 0);
  let offset = 25;
  const segments = data.map((item, index) => {
    const value = Number(item.value) || 0;
    const dash = total ? (value / total) * 100 : 0;
    const segment = { ...item, dash, offset, color: item.color || ["#0645b8", "#16a34a", "#f59e0b", "#64748b"][index % 4] };
    offset -= dash;
    return segment;
  });

  return (
    <section className="chart-card">
      <div className="chart-head">
        <h3>{title}</h3>
        {subtitle && <p>{subtitle}</p>}
      </div>
      <div className="donut-layout">
        <div className="donut-wrap">
          <svg className="donut" viewBox="0 0 42 42" role="img" aria-label={title}>
            <circle cx="21" cy="21" r="15.915" />
            {segments.map((segment) => (
              <circle
                key={segment.label}
                cx="21"
                cy="21"
                r="15.915"
                stroke={segment.color}
                strokeDasharray={`${segment.dash} ${100 - segment.dash}`}
                strokeDashoffset={segment.offset}
              />
            ))}
          </svg>
          <div className="donut-total">
            <strong>{total}</strong>
            <span>total</span>
          </div>
        </div>
        <div className="legend">
          {data.map((item, index) => (
            <div key={item.label}>
              <span style={{ background: item.color || ["#0645b8", "#16a34a", "#f59e0b", "#64748b"][index % 4] }} />
              <strong>{item.label}</strong>
              <em>{item.value}</em>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function VisualsView({ results }) {
  const pages = results.extractions?.text?.pages || [];
  const records = results.extractions?.records?.records || [];
  const tables = results.extractions?.tables?.tables || [];
  const images = results.extractions?.images?.images || [];
  const timing = results.timing_ms || {};

  const composition = [
    { label: "Text pages", value: pages.length, color: "#0645b8" },
    { label: "Records", value: records.length, color: "#16a34a" },
    { label: "Tables", value: tables.length, color: "#f59e0b" },
    { label: "Images", value: images.length, color: "#64748b" },
  ];

  const timingData = Object.entries(timing)
    .filter(([key, value]) => key !== "total" && Number(value) > 0)
    .map(([key, value]) => ({
      label: key.toUpperCase(),
      value: Number(value),
      display: `${(Number(value) / 1000).toFixed(2)}s`,
    }));

  const pageChars = pages.slice(0, 12).map((page) => ({
    label: `Page ${page.page}`,
    value: Number(page.char_count || 0),
    display: Number(page.char_count || 0).toLocaleString(),
  }));

  const genderCounts = records.reduce((acc, record) => {
    const key = record.gender || "Unknown";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});

  const genderData = Object.entries(genderCounts).map(([label, value], index) => ({
    label,
    value,
    color: ["#0645b8", "#16a34a", "#f59e0b", "#64748b"][index % 4],
  }));

  const ageBuckets = [
    { label: "18-25", min: 18, max: 25 },
    { label: "26-40", min: 26, max: 40 },
    { label: "41-60", min: 41, max: 60 },
    { label: "60+", min: 61, max: 200 },
    { label: "Unknown", min: null, max: null },
  ].map((bucket) => {
    const value = records.filter((record) => {
      const age = Number(record.age);
      if (bucket.min === null) return !age;
      return age >= bucket.min && age <= bucket.max;
    }).length;
    return { label: bucket.label, value };
  });

  const tableSizes = tables.map((table) => ({
    label: `Table ${table.table_number}`,
    value: Number(table.rows || 0),
    display: `${Number(table.rows || 0).toLocaleString()} rows`,
  }));

  const tableColumns = tables.map((table) => ({
    label: `Table ${table.table_number}`,
    value: Number(table.columns || 0),
    display: `${Number(table.columns || 0).toLocaleString()} cols`,
  }));

  const imageSizes = images.slice(0, 12).map((image) => {
    const pixels = Number(image.width || 0) * Number(image.height || 0);
    return {
      label: image.filename || `Page ${image.page}`,
      value: pixels,
      display: pixels ? `${(pixels / 1000000).toFixed(2)} MP` : "N/A",
    };
  });

  if (!pages.length && !records.length && !tables.length && !images.length) {
    return <p className="empty">No visual data yet. Run extraction with text, records, tables, or images enabled.</p>;
  }

  return (
    <div className="visual-grid">
      <DonutChart title="Extraction mix" subtitle="What was found in this run" data={composition} />
      <BarChart title="Processing time" subtitle="Which stage took the longest" data={timingData.length ? timingData : [{ label: "TOTAL", value: timing.total || 0, display: `${((timing.total || 0) / 1000).toFixed(2)}s` }]} />
      {pageChars.length > 0 && (
        <BarChart title="Text density" subtitle="Character count by page, first 12 pages" data={pageChars} />
      )}
      {records.length > 0 && (
        <>
          <DonutChart title="Gender split" subtitle="Parsed elector records" data={genderData} />
          <BarChart title="Age groups" subtitle="Parsed elector records" data={ageBuckets} />
        </>
      )}
      {tables.length > 0 && (
        <>
          <BarChart title="Table rows" subtitle="Rows found in each extracted table" data={tableSizes} />
          <BarChart title="Table columns" subtitle="Column count by extracted table" data={tableColumns} />
        </>
      )}
      {images.length > 0 && (
        <BarChart title="Image sizes" subtitle="Image megapixels, first 12 images" data={imageSizes} />
      )}
    </div>
  );
}

function TextView({ pages }) {
  if (!pages.length) return <p className="empty">No text extracted. If this is scanned, use the Scanned PDF preset.</p>;
  return pages.map((page) => (
    <article className="text-page" key={page.page}>
      <h3>Page {page.page}</h3>
      <pre>{page.text || "No text found on this page."}</pre>
    </article>
  ));
}

function RecordView({ records }) {
  const [query, setQuery] = useState("");
  const [gender, setGender] = useState("all");
  const [quality, setQuality] = useState("all");
  const cols = ["page", "serial_no", "epic_id", "name", "relation_type", "relation_name", "house_number", "age", "gender"];

  const genderOptions = useMemo(() => {
    const values = Array.from(new Set(records.map((record) => record.gender).filter(Boolean)));
    return ["all", ...values];
  }, [records]);

  const filteredRecords = useMemo(() => {
    const needle = query.trim().toLowerCase();

    return records.filter((record) => {
      const matchesQuery = !needle || cols.some((col) => String(record[col] ?? "").toLowerCase().includes(needle));
      const matchesGender = gender === "all" || record.gender === gender;
      const matchesQuality =
        quality === "all" ||
        (quality === "missing_epic" && !record.epic_id) ||
        (quality === "missing_age" && !record.age) ||
        (quality === "missing_gender" && !record.gender);

      return matchesQuery && matchesGender && matchesQuality;
    });
  }, [records, query, gender, quality]);

  if (!records.length) return <p className="empty">No elector records parsed. Try OCR or a smaller page range with elector entries.</p>;
  return (
    <>
      <div className="record-tools">
        <label>
          Search records
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Name, EPIC, house, age..." />
        </label>
        <label>
          Gender
          <select value={gender} onChange={(event) => setGender(event.target.value)}>
            {genderOptions.map((option) => <option value={option} key={option}>{option === "all" ? "All genders" : option}</option>)}
          </select>
        </label>
        <label>
          Data quality
          <select value={quality} onChange={(event) => setQuality(event.target.value)}>
            <option value="all">All records</option>
            <option value="missing_epic">Missing EPIC</option>
            <option value="missing_age">Missing age</option>
            <option value="missing_gender">Missing gender</option>
          </select>
        </label>
        <div className="record-count">
          <strong>{filteredRecords.length.toLocaleString()}</strong>
          <span>of {records.length.toLocaleString()} records</span>
        </div>
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr>{cols.map((col) => <th key={col}>{col.replaceAll("_", " ")}</th>)}</tr></thead>
          <tbody>
            {filteredRecords.slice(0, 1000).map((record, index) => (
              <tr key={`${record.epic_id || record.name}-${index}`}>
                {cols.map((col) => <td key={col}>{record[col] ?? ""}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {filteredRecords.length > 1000 && <p className="table-note">Showing first 1000 filtered rows. Export CSV/Excel for the complete set.</p>}
      {!filteredRecords.length && <p className="empty">No records match your current filters.</p>}
    </>
  );
}

function TableView({ tables }) {
  if (!tables.length) return <p className="empty">No tables extracted. Turn on Tables and use a page range for faster results.</p>;
  return tables.map((table) => {
    const headers = table.headers?.length ? table.headers : Object.keys(table.data?.[0] || {});
    return (
      <div className="table-wrap" key={table.table_number}>
        <h3>Table {table.table_number}</h3>
        <table>
          <thead><tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr></thead>
          <tbody>
            {(table.data || []).map((row, index) => (
              <tr key={index}>{headers.map((header) => <td key={header}>{row[header]}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  });
}

function ImageView({ images }) {
  if (!images.length) return <p className="empty">No images extracted. Turn on Images and run again.</p>;
  return (
    <div className="image-grid">
      {images.map((image) => (
        <figure key={image.filename}>
          <img src={image.url || `/extracted-image/${encodeURIComponent(image.filename)}`} alt={image.filename} />
          <figcaption>{image.filename}</figcaption>
        </figure>
      ))}
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
