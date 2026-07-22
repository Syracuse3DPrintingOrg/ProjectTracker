/* Attachment preview: window.SQPreview.open(id) shows any attachment in a
   full-screen dialog. Tables, text, images, PDFs inline; STL models render
   through SQStlViewer (stl-viewer.js); STEP models are tessellated in the
   browser by the vendored occt-import-js WASM build, then rendered through
   the same viewer. Everything else gets a download link. */
(function () {
  "use strict";

  let dialog = null;
  let headName = null;
  let headSize = null;
  let headDownload = null;
  let bodyEl = null;
  let stlController = null;
  let openSeq = 0;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function humanSize(n) {
    if (!isFinite(n) || n < 0) return "";
    if (n < 1024) return n + " B";
    const units = ["KB", "MB", "GB", "TB"];
    let u = -1;
    do { n /= 1024; u++; } while (n >= 1024 && u < units.length - 1);
    return (Math.round(n * 10) / 10) + " " + units[u];
  }

  function ensureDialog() {
    if (dialog) return;
    dialog = el("dialog", "preview-dialog");
    const head = el("div", "preview-head");
    headName = el("span", "preview-name");
    headSize = el("span", "preview-size muted");
    const spacer = el("span", "spacer");
    headDownload = el("a", "btn preview-download", "Download");
    headDownload.setAttribute("download", "");
    const close = el("button", "preview-close", "×");
    close.type = "button";
    close.title = "Close";
    close.addEventListener("click", () => dialog.close());
    head.append(headName, headSize, spacer, headDownload, close);
    bodyEl = el("div", "preview-body");
    dialog.append(head, bodyEl);
    dialog.addEventListener("close", cleanup);
    document.body.appendChild(dialog);
  }

  function cleanup() {
    if (stlController) {
      stlController.dispose();
      stlController = null;
    }
    if (bodyEl) bodyEl.textContent = "";
  }

  function showNote(text, fileUrl, name) {
    bodyEl.textContent = "";
    bodyEl.className = "preview-body kind-note";
    const note = el("div", "preview-note");
    note.appendChild(el("div", null, text));
    if (fileUrl) {
      const a = el("a", null, "Download " + (name || "the file"));
      a.href = fileUrl;
      a.setAttribute("download", name || "");
      note.appendChild(a);
    }
    bodyEl.appendChild(note);
  }

  function renderTable(data) {
    const wrap = el("div", "preview-table-wrap");
    const table = el("table", "preview-table");
    const thead = el("thead");
    const headRow = el("tr");
    (data.columns || []).forEach(c => headRow.appendChild(el("th", null, c == null ? "" : String(c))));
    thead.appendChild(headRow);
    const tbody = el("tbody");
    (data.rows || []).forEach(row => {
      const tr = el("tr");
      row.forEach(cell => tr.appendChild(el("td", null, cell == null ? "" : String(cell))));
      tbody.appendChild(tr);
    });
    table.append(thead, tbody);
    wrap.appendChild(table);
    bodyEl.appendChild(wrap);
    const notes = [];
    if (data.sheets && data.sheets.length > 1) {
      notes.push("Workbook sheets: " + data.sheets.join(", ") + " (showing the first).");
    }
    if (data.truncated) notes.push("Showing the first " + (data.rows || []).length + " rows.");
    if (notes.length) bodyEl.appendChild(el("div", "preview-foot-note", notes.join(" ")));
  }

  function renderText(data) {
    bodyEl.appendChild(el("pre", "preview-text", data.text || ""));
    if (data.truncated) {
      bodyEl.appendChild(el("div", "preview-foot-note", "Long file, showing the beginning."));
    }
  }

  async function renderStl(data, fileUrl) {
    const canvas = el("canvas", "stl-canvas");
    bodyEl.appendChild(canvas);
    bodyEl.appendChild(el("div", "stl-hint", "Drag to rotate. Scroll or pinch to zoom."));
    const resp = await fetch(data.url || fileUrl);
    if (!resp.ok) throw new Error("Could not fetch the model file.");
    const buf = await resp.arrayBuffer();
    // The dialog may have been closed while the model downloaded.
    if (!canvas.isConnected) return;
    stlController = window.SQStlViewer.mount(canvas, buf);
  }

  /* STEP support: the vendored occt-import-js (OpenCascade compiled to
     WASM) tessellates the solid model in the browser; the resulting
     triangles render through the same viewer STL uses. The script and its
     WASM load once, on the first STEP preview, from our own /static. */
  const OCCT_BASE = "/static/js/vendor/occt/";
  let occtPromise = null;

  function loadOcct() {
    if (!occtPromise) {
      occtPromise = new Promise((resolve, reject) => {
        if (window.occtimportjs) { resolve(); return; }
        const s = document.createElement("script");
        s.src = OCCT_BASE + "occt-import-js.js";
        s.onload = () => resolve();
        s.onerror = () => reject(new Error("Could not load the STEP converter."));
        document.head.appendChild(s);
      }).then(() => window.occtimportjs({
        locateFile: (name) => OCCT_BASE + name,
      })).catch((err) => {
        occtPromise = null; // a failed load retries on the next preview
        throw err;
      });
    }
    return occtPromise;
  }

  function stepToTriangles(result) {
    if (!result || !result.success || !result.meshes || !result.meshes.length) {
      throw new Error("STEP conversion failed; download the file to open it.");
    }
    let floats = 0;
    result.meshes.forEach((m) => { floats += m.index.array.length * 3; });
    const soup = new Float32Array(floats);
    let o = 0;
    result.meshes.forEach((m) => {
      const pos = m.attributes.position.array;
      const idx = m.index.array;
      for (let i = 0; i < idx.length; i++) {
        const v = idx[i] * 3;
        soup[o++] = pos[v];
        soup[o++] = pos[v + 1];
        soup[o++] = pos[v + 2];
      }
    });
    if (!soup.length) throw new Error("STEP conversion failed; download the file to open it.");
    return soup;
  }

  async function renderStep(data, fileUrl) {
    const status = el("div", "preview-note", "Converting model… (first open loads the converter, give it a few seconds)");
    bodyEl.className = "preview-body kind-note";
    bodyEl.appendChild(status);
    const fetched = fetch(data.url || fileUrl).then((resp) => {
      if (!resp.ok) throw new Error("Could not fetch the model file.");
      return resp.arrayBuffer();
    });
    const occt = await loadOcct();
    const buf = await fetched;
    // The dialog may have been closed, or another preview opened, meanwhile.
    if (!status.isConnected) return;
    let soup;
    try {
      const reader = data.format === "iges" ? occt.ReadIgesFile : occt.ReadStepFile;
      soup = stepToTriangles(reader(new Uint8Array(buf), null));
    } catch (err) {
      throw new Error("CAD conversion failed; download the file to open it.");
    }
    if (!status.isConnected) return;
    bodyEl.textContent = "";
    bodyEl.className = "preview-body kind-step";
    const canvas = el("canvas", "stl-canvas");
    bodyEl.appendChild(canvas);
    bodyEl.appendChild(el("div", "stl-hint", "Drag to rotate. Scroll or pinch to zoom."));
    stlController = window.SQStlViewer.mountMesh(canvas, soup);
  }

  async function open(attachmentId) {
    ensureDialog();
    cleanup();
    openSeq++;
    const seq = openSeq;
    const fileUrl = "/api/attachments/" + attachmentId + "/file";
    headName.textContent = "";
    headName.title = "";
    headSize.textContent = "";
    headDownload.href = fileUrl;
    headDownload.setAttribute("download", "");
    bodyEl.className = "preview-body kind-note";
    bodyEl.appendChild(el("div", "preview-note", "Loading…"));
    if (!dialog.open) dialog.showModal();

    let data;
    try {
      const resp = await fetch("/api/attachments/" + attachmentId + "/preview");
      if (!resp.ok) {
        let detail = resp.statusText;
        try { detail = (await resp.json()).detail || detail; } catch (e) { /* ignore */ }
        throw new Error(detail);
      }
      data = await resp.json();
    } catch (err) {
      if (seq === openSeq && dialog.open) showNote("Preview failed: " + err.message, fileUrl, "");
      return;
    }
    if (seq !== openSeq || !dialog.open) return;

    headName.textContent = data.name || "";
    headName.title = data.name || "";
    headSize.textContent = humanSize(data.size);
    headDownload.setAttribute("download", data.name || "");
    bodyEl.textContent = "";
    bodyEl.className = "preview-body kind-" + (data.kind || "unknown");

    try {
      switch (data.kind) {
        case "table":
          renderTable(data);
          break;
        case "text":
          renderText(data);
          break;
        case "image": {
          const img = el("img", "preview-image");
          img.src = data.url;
          img.alt = data.name || "";
          bodyEl.appendChild(img);
          if (data.note) bodyEl.appendChild(el("div", "preview-note", data.note));
          break;
        }
        case "video": {
          const video = el("video", "preview-media");
          video.src = data.url;
          video.controls = true;
          bodyEl.appendChild(video);
          break;
        }
        case "audio": {
          const audio = el("audio", "preview-media-audio");
          audio.src = data.url;
          audio.controls = true;
          bodyEl.appendChild(audio);
          bodyEl.appendChild(el("div", "preview-note", data.name || ""));
          break;
        }
        case "pdf": {
          const frame = el("iframe", "preview-frame");
          frame.src = data.url;
          frame.title = data.name || "PDF preview";
          bodyEl.appendChild(frame);
          break;
        }
        case "stl":
          await renderStl(data, fileUrl);
          break;
        case "step":
          await renderStep(data, fileUrl);
          break;
        default:
          // model-unsupported, binary, error, and anything new.
          showNote(data.note || "No inline preview for this file type.", fileUrl, data.name);
      }
    } catch (err) {
      if (seq === openSeq && dialog.open) {
        showNote(err.message || "Preview failed.", fileUrl, data.name);
      }
    }
  }

  window.SQPreview = { open };
})();
