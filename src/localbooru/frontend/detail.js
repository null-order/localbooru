(function () {
  const pathMatch = window.location.pathname.match(/\/detail\/(\d+)/);
  if (!pathMatch) {
    showError("Invalid detail route.");
    return;
  }

  const imageId = Number(pathMatch[1]);
  if (!Number.isFinite(imageId)) {
    showError("Invalid image identifier.");
    return;
  }

  const titleEl = document.getElementById("detail-title");
  const imageEl = document.getElementById("detail-image");
  const openOriginalEl = document.getElementById("detail-open-original");
  const downloadEl = document.getElementById("detail-download");
  const infoEl = document.getElementById("detail-info");
  const ratingEl = document.getElementById("detail-rating");
  const positivePromptEl = document.getElementById("detail-positive");
  const negativePromptEl = document.getElementById("detail-negative");
  const tagsEl = document.getElementById("detail-tags");
  const charactersEl = document.getElementById("detail-characters");
  const similarStrip = document.getElementById("similar-strip");
  const similarStatus = document.getElementById("similar-status");
  const refreshSimilarBtn = document.getElementById("refresh-similar");
  const errorEl = document.getElementById("detail-error");

  let detailData = null;

  init().catch((err) => {
    console.error(err);
    showError("Failed to load image detail.");
  });

  async function init() {
    const data = await fetchJson(`/api/images/${imageId}`);
    detailData = data;
    renderDetail(data);
    await loadSimilar();
    refreshSimilarBtn?.addEventListener("click", () => {
      loadSimilar(true).catch((err) => {
        console.error(err);
        setSimilarStatus("Failed to refresh similar images.");
      });
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        window.history.back();
      }
    });
  }

  async function fetchJson(url, options) {
    const res = await fetch(url, options);
    if (!res.ok) {
      throw new Error(`Request failed: ${res.status}`);
    }
    return res.json();
  }

  function renderDetail(data) {
    const image = data.image || {};
    const prompts = data.prompts || { positive: "", negative: "" };
    const tags = Array.isArray(data.tags) ? data.tags : [];
    const characters = Array.isArray(data.characters) ? data.characters : [];
    const processing = data.processing || null;
    const ratingInfo = data.rating || {};

    const fallbackTitle = image.name || `Image ${imageId}`;
    document.title = `${fallbackTitle} • LocalBooru`;
    titleEl.textContent = fallbackTitle;

    if (imageEl) {
      imageEl.src = image.file_url;
      imageEl.alt = fallbackTitle;
    }
    if (openOriginalEl) {
      openOriginalEl.href = image.file_url;
    }
    if (downloadEl) {
      downloadEl.href = image.file_url;
      if (image.name) {
        downloadEl.setAttribute("download", image.name);
      }
    }

    if (positivePromptEl) {
      positivePromptEl.textContent =
        prompts.positive && prompts.positive.trim()
          ? prompts.positive
          : "—";
    }
    if (negativePromptEl) {
      negativePromptEl.textContent =
        prompts.negative && prompts.negative.trim()
          ? prompts.negative
          : "—";
    }

    if (infoEl) {
      infoEl.innerHTML = buildInfoCard(image, processing);
    }
    if (ratingEl) {
      ratingEl.innerHTML = buildRatingCard(ratingInfo);
    }
    if (tagsEl) {
      renderTagGroups(tags, tagsEl);
    }
    if (charactersEl) {
      renderCharacters(characters, charactersEl);
    }
  }

  function buildInfoCard(image, processing) {
    const fields = [];
    if (image.generator)
      fields.push({ label: "Generator", value: image.generator });
    if (image.model) fields.push({ label: "Model", value: image.model });
    if (image.sampler)
      fields.push({ label: "Sampler", value: image.sampler });
    if (image.scheduler)
      fields.push({ label: "Scheduler", value: image.scheduler });
    if (image.steps)
      fields.push({ label: "Steps", value: String(image.steps) });
    if (image.cfg_scale)
      fields.push({ label: "CFG Scale", value: String(image.cfg_scale) });
    if (image.seed) fields.push({ label: "Seed", value: image.seed });

    const dimensions = `${
      Number.isFinite(image.width) ? image.width : "–"
    }×${Number.isFinite(image.height) ? image.height : "–"}`;
    fields.push({ label: "Dimensions", value: dimensions });
    fields.push({
      label: "File Size",
      value: formatFileSize(image.size),
    });
    if (image.path) {
      fields.push({
        label: "Path",
        value: image.path,
      });
    }
    const infoHtml = fields
      .map(
        (field) =>
          `<div class="info-chip"><span>${escapeHtml(field.label)}</span><strong>${escapeHtml(field.value)}</strong></div>`,
      )
      .join("");

    const statusHtml = buildStatusChips(processing);

    return `
        <div class="info-card">
            <div class="info-fields">
                ${infoHtml}
            </div>
            ${statusHtml ? `<div class="status-chips">${statusHtml}</div>` : ""}
        </div>
    `;
  }

  function buildRatingCard(rating) {
    if (!rating || typeof rating !== "object") {
      return "";
    }
    const value = rating.rating || rating.value;
    const confidence =
      rating.confidence !== undefined && rating.confidence !== null
        ? `${(Number(rating.confidence) * 100).toFixed(1)}%`
        : "—";
    const status = rating.status || "unknown";
    const model = rating.model || "";
    const rows = [
      { label: "Rating", value: value || "unknown" },
      { label: "Confidence", value: confidence },
      { label: "Status", value: status },
    ];
    if (model) {
      rows.push({ label: "Model", value: model });
    }
    return `
        <div class="rating-card">
            <h2>Rating</h2>
            <dl>
                ${rows
                  .map(
                    (row) =>
                      `<div><dt>${escapeHtml(row.label)}</dt><dd>${escapeHtml(row.value)}</dd></div>`,
                  )
                  .join("")}
            </dl>
        </div>
    `;
  }

  function renderTagGroups(tags, container) {
    container.innerHTML = "";
    if (!tags.length) {
      container.innerHTML = "<p>No tags.</p>";
      return;
    }
    const groups = new Map();
    tags.forEach((tag) => {
      const kind =
        typeof tag.kind === "string" && tag.kind ? tag.kind : "prompt";
      if (!groups.has(kind)) {
        groups.set(kind, []);
      }
      groups.get(kind).push(tag);
    });
    groups.forEach((list, kind) => {
      const section = document.createElement("section");
      section.className = "detail-tag-section";
      const heading = document.createElement("h3");
      heading.textContent = kind === "prompt" ? "Tags" : kind;
      section.appendChild(heading);
      const wrap = document.createElement("div");
      wrap.className = "tag-pills";
      list.forEach((tag) => {
        const pill = document.createElement("span");
        pill.className = "tag-pill";
        pill.dataset.kind = tag.kind || "prompt";
        const label =
          tag.count && Number.isFinite(tag.count)
            ? `${tag.tag} (${tag.count})`
            : tag.tag;
        pill.textContent = label;
        wrap.appendChild(pill);
      });
      section.appendChild(wrap);
      container.appendChild(section);
    });
  }

  function renderCharacters(characters, container) {
    container.innerHTML = "";
    if (!characters.length) {
      container.innerHTML = "";
      return;
    }
    const heading = document.createElement("h2");
    heading.textContent = "Characters";
    container.appendChild(heading);
    characters.forEach((char, index) => {
      const block = document.createElement("div");
      block.className = "character-block";
      const title = document.createElement("h3");
      title.textContent = char.name || `Character ${index + 1}`;
      block.appendChild(title);
      if (char.caption) {
        const caption = document.createElement("p");
        caption.className = "character-caption";
        caption.textContent = char.caption;
        block.appendChild(caption);
      }
      if (Array.isArray(char.tags) && char.tags.length) {
        const wrap = document.createElement("div");
        wrap.className = "tag-pills";
        char.tags.forEach((tag) => {
          const pill = document.createElement("span");
          pill.className = "tag-pill";
          pill.dataset.kind = tag.kind || "character";
          pill.textContent = tag.tag;
          wrap.appendChild(pill);
        });
        block.appendChild(wrap);
      }
      container.appendChild(block);
    });
  }

  async function loadSimilar(force = false) {
    if (!detailData) return;
    if (!force) {
      setSimilarStatus("Finding similar images…");
    } else {
      setSimilarStatus("Refreshing similar images…");
    }
    similarStrip.innerHTML = "";
    try {
      const payload = {
        positive_images: [imageId],
        limit: 12,
        offset: 0,
        include_tags: false,
      };
      const res = await fetch("/api/search/clip", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        if (res.status === 400 || res.status === 503) {
          setSimilarStatus("CLIP search unavailable.");
          return;
        }
        throw new Error(`CLIP search failed: ${res.status}`);
      }
      const data = await res.json();
      const results = Array.isArray(data.results) ? data.results : [];
      if (!results.length) {
        setSimilarStatus("No similar images found.");
        return;
      }
      const hasSimilar = renderSimilar(results);
      if (hasSimilar) {
        setSimilarStatus("");
      }
    } catch (err) {
      console.error(err);
      setSimilarStatus("Failed to load similar images.");
    }
  }

  function renderSimilar(results) {
    similarStrip.innerHTML = "";
    let appended = 0;
    results.forEach((item) => {
      if (Number(item.id) === imageId) {
        return;
      }
      const card = document.createElement("a");
      card.className = "similar-card";
      card.href = `/detail/${item.id}`;
      card.dataset.id = item.id;
      const img = document.createElement("img");
      img.loading = "lazy";
      img.src = item.thumb_url || item.file_url;
      img.alt = item.name || `Image ${item.id}`;
      card.appendChild(img);
      const score = document.createElement("span");
      score.className = "similar-score";
      if (item.score !== undefined && item.score !== null) {
        score.textContent = Number(item.score).toFixed(3);
      } else {
        score.textContent = "";
      }
      card.appendChild(score);
      similarStrip.appendChild(card);
      appended += 1;
    });
    if (!appended) {
      setSimilarStatus("No similar images found.");
    }
    return appended > 0;
  }

  function setSimilarStatus(message) {
    if (!similarStatus) return;
    if (!message) {
      similarStatus.textContent = "";
      similarStatus.hidden = true;
    } else {
      similarStatus.hidden = false;
      similarStatus.textContent = message;
    }
  }

  function showError(message) {
    if (errorEl) {
      errorEl.hidden = false;
      errorEl.textContent = message;
    }
  }

  function escapeHtml(value) {
    if (value === null || value === undefined) return "";
    return String(value).replace(/[&<>"']/g, (ch) => {
      switch (ch) {
        case "&":
          return "&amp;";
        case "<":
          return "&lt;";
        case ">":
          return "&gt;";
        case '"':
          return "&quot;";
        case "'":
          return "&#39;";
        default:
          return ch;
      }
    });
  }

  function formatFileSize(bytes) {
    if (!Number.isFinite(bytes) || bytes < 0) return "–";
    const thresh = 1024;
    if (bytes < thresh) return `${bytes} B`;
    const units = ["KB", "MB", "GB", "TB"];
    let u = -1;
    do {
      bytes /= thresh;
      u += 1;
    } while (bytes >= thresh && u < units.length - 1);
    return `${bytes.toFixed(bytes >= 10 ? 0 : 1)} ${units[u]}`;
  }

  function buildStatusChips(processing) {
    if (!processing || typeof processing !== "object") {
      return "";
    }
    const clipState = processing.clip || {};
    const autoState = processing.auto || {};
    const ratingState = processing.rating || {};
    const chips = [
      renderStatusChip("CLIP", clipState),
      renderStatusChip("Auto tags", autoState),
      renderStatusChip("Rating", ratingState),
    ].filter(Boolean);
    return chips.join("");
  }

  function renderStatusChip(label, state) {
    if (!state) return "";
    const status = (state.status || "unknown").toString();
    let value = status;
    if (status === "processing" && state.position) {
      value = `${status} (#${state.position})`;
    } else if (status === "ready" && state.model) {
      value = `${status} (${state.model})`;
    }
    return `<span class="status-chip status-${escapeHtml(status)}">${escapeHtml(label)} • ${escapeHtml(value)}</span>`;
  }
})();
