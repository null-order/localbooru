const searchBox = document.getElementById("search");
const searchClearBtn = document.getElementById("search-clear");
const gridEl = document.getElementById("grid");
const statusEl = document.getElementById("status");
const sidebarEl = document.getElementById("sidebar");
const sidebarToggleBtn = document.getElementById("sidebar-toggle");
const statusCardEl = document.getElementById("status-card");
const statusWrapperEl = document.getElementById("status-wrapper");
const clipStatusSection = document.getElementById("clip-status");
const clipSummary = document.getElementById("clip-summary");
const clipProgressBar = document.getElementById("clip-progress-bar");
const clipToggleBtn = document.getElementById("clip-toggle");
const clipSearchInput = document.getElementById("clip-query");
const clipSearchClear = document.getElementById("clip-clear");
const autoStatusSection = document.getElementById("auto-status");
const autoSummary = document.getElementById("auto-summary");
const autoErrorsList = document.getElementById("auto-errors");
const autoProgressBar = document.getElementById("auto-progress-bar");
const ratingStatusSection = document.getElementById("rating-status");
const ratingSummary = document.getElementById("rating-summary");
const ratingProgressBar = document.getElementById("rating-progress-bar");
const ratingErrorsList = document.getElementById("rating-errors");
const ratingCardEl = document.getElementById("rating-card");
const ratingFilterInputs = ratingCardEl
  ? Array.from(
      ratingCardEl.querySelectorAll("input[type=\"checkbox\"]"),
    )
  : [];
const ratingFilterMeta = ratingFilterInputs.map((input) => {
  const label = input.closest("label");
  return {
    input,
    label,
    value: String(input.value || "").toLowerCase(),
    nameEl: label ? label.querySelector(".rating-name") : null,
    countEl: label ? label.querySelector(".rating-count") : null,
  };
});
const detailRatingSection = document.getElementById("detail-rating");
const detailRatingLabel = detailRatingSection
  ? detailRatingSection.querySelector(".rating-label")
  : null;
const ratingBarsContainer = document.getElementById("rating-bars");
const toastStack = document.getElementById("toast-stack");
const dropOverlay = document.getElementById("drop-overlay");
const loadMoreBtn = document.getElementById("load-more");
const suggestionsEl = document.getElementById("tag-suggestions");
const facetListEl = document.getElementById("facet-tags");
const detailOverlay = document.getElementById("detail-overlay");
const detailTitle = document.getElementById("detail-title");
const detailImage = document.getElementById("detail-image");
const detailInfo = document.getElementById("detail-info");
const detailTags = document.getElementById("detail-tags");
const detailNegTags = document.getElementById("detail-neg-tags");
const detailNegSection = document.getElementById("detail-neg-section");
const detailCharSection = document.getElementById("detail-char-section");
const detailCharacters = document.getElementById("detail-characters");
const detailPromptsSection = document.getElementById("detail-prompts");
const detailPrevBtn = document.getElementById("detail-prev");
const detailNextBtn = document.getElementById("detail-next");
const detailCounter = document.getElementById("detail-counter");
const detailCloseBtn = document.getElementById("detail-close");
const detailSimilarBtn = document.getElementById("detail-similar");
if (detailSimilarBtn) detailSimilarBtn.disabled = true;
const hideUCToggleBtn = document.getElementById("toggle-uc");
const sentinel = document.getElementById("scroll-sentinel");
const detailHotspots = document.getElementById("detail-hotspots");
const copyPositiveBtn = document.getElementById("copy-positive");
const copyNegativeBtn = document.getElementById("copy-negative");
const positivePreview = document.getElementById("positive-preview");
const negativePreview = document.getElementById("negative-preview");
const positiveBlock = document.getElementById("prompt-positive-block");
const negativeBlock = document.getElementById("prompt-negative-block");
const copyAllNaiBtn = document.getElementById("copy-all-nai");
const copyAllDanbooruBtn = document.getElementById("copy-all-danbooru");
const copyEmbeddedNaiBtn = document.getElementById("copy-embedded-nai");
const copyEmbeddedDanbooruBtn = document.getElementById(
  "copy-embedded-danbooru",
);
const copyAutoNaiBtn = document.getElementById("copy-auto-nai");
const copyAutoDanbooruBtn = document.getElementById("copy-auto-danbooru");
if (autoProgressBar) {
  autoProgressBar.style.width = "0%";
  autoProgressBar.dataset.label = "0%";
}
const facetLookup = new Map();
const tagToCards = new Map();
const cardElements = new Map();
let suggestionItems = [];
let suggestionIndex = -1;
const headerEl = document.querySelector(".app-header");
const PAGE_SIZE = 40;
const TAG_FETCH_BATCH_SIZE = 80;
let currentHistoryState = { query: "", detail: null, pos: 0, clip: null };
let pendingScrollIndex = null;
let scrollRestorePending = false;
let scrollSaveScheduled = false;
let lastAnchorIndex = 0;

const searchState = {
  query: "",
  images: [],
  index: new Map(),
  imageTags: new Map(),
  total: 0,
  loading: false,
  done: false,
};

let clipEnabled = true;
let clipModeActive = false;
let lastClipPayload = null;
let clipTotal = 0;
let clipOffset = 0;
let currentClipToken = null;

let currentDetailId = null;
let currentDetailIndex = -1;
let hideUCTags = true;
let facetCache = [];
let autoObserver = null;
let currentPrompts = { positive: "", negative: "" };
let currentHotspotCenters = null;
let currentHotspotDots = [];
let lastQuery = "";
let pendingDetailId = null;
let clipSearchTimer = null;
const CLIP_SEARCH_DEBOUNCE = 400;
let dragCounter = 0;
const desktopMediaQuery = window.matchMedia("(min-width: 1101px)");
let sidebarVisible = desktopMediaQuery.matches;
let statusCardVisible = true;

updateRatingFilterCounts();

function getActiveClipToken() {
  if (!clipModeActive) {
    return null;
  }
  if (currentClipToken) {
    return currentClipToken;
  }
  if (lastClipPayload && typeof lastClipPayload === "object") {
    if (
      typeof lastClipPayload.clipToken === "string" &&
      lastClipPayload.clipToken
    ) {
      currentClipToken = lastClipPayload.clipToken;
      return lastClipPayload.clipToken;
    }
    const encoded = encodeClipState(lastClipPayload);
    if (encoded) {
      currentClipToken = encoded;
      return encoded;
    }
  }
  return null;
}

function normalizeDetail(value) {
  if (value === null || value === undefined) return null;
  const num = Number(value);
  if (!Number.isFinite(num)) return null;
  const intVal = Math.trunc(num);
  return intVal >= 0 ? intVal : null;
}

function normalizeIndex(value) {
  if (value === null || value === undefined) return null;
  const num = Number(value);
  if (!Number.isFinite(num)) return null;
  const intVal = Math.trunc(num);
  return intVal >= 0 ? intVal : null;
}

function encodeClipState(payload) {
  if (!payload) return null;
  if (payload.positiveImages && payload.positiveImages.length) {
    const id = Number(payload.positiveImages[0]);
    if (Number.isFinite(id)) {
      return `image:${id}`;
    }
  }
  if (payload.query && payload.query.trim()) {
    return `text:${encodeURIComponent(payload.query.trim())}`;
  }
  return null;
}

function decodeClipState(value) {
  if (typeof value !== "string" || !value) {
    return null;
  }
  if (value.startsWith("image:")) {
    const id = Number(value.slice(6));
    if (Number.isFinite(id)) {
      return { mode: "image", id };
    }
    return null;
  }
  if (value.startsWith("text:")) {
    try {
      const query = decodeURIComponent(value.slice(5));
      return { mode: "text", query };
    } catch (err) {
      console.error("Failed to decode clip text state", err);
      return null;
    }
  }
  return null;
}

function buildClipFacetSummaryFromImageTags(imageTagMap) {
  const buckets = new Map();
  if (!(imageTagMap instanceof Map)) {
    return [];
  }
  imageTagMap.forEach((tagList) => {
    const tags = Array.isArray(tagList) ? tagList : [];
    const seen = new Set();
    tags.forEach((tag) => {
      if (!tag || typeof tag !== "object") return;
      const norm = typeof tag.norm === "string" ? tag.norm : "";
      if (!norm) return;
      const kind = typeof tag.kind === "string" ? tag.kind : "prompt";
      const key = `${kind}|${norm}`;
      if (seen.has(key)) return;
      seen.add(key);
      if (!buckets.has(key)) {
        buckets.set(key, {
          tag: typeof tag.tag === "string" && tag.tag ? tag.tag : norm,
          norm,
          kind,
          freq: 0,
        });
      }
      const entry = buckets.get(key);
      entry.freq += 1;
    });
  });
  return Array.from(buckets.values()).sort((a, b) => {
    if (b.freq !== a.freq) {
      return b.freq - a.freq;
    }
    return a.tag.localeCompare(b.tag);
  });
}

const activeToasts = new Map();
const toastSuppressions = new Map();

function toastFingerprint(title, body) {
  return `${title || ""}|${body || ""}`;
}

function isToastSuppressed(key, fingerprint) {
  const state = toastSuppressions.get(key);
  return !!state && state.suppressed && state.fingerprint === fingerprint;
}

function showToast(
  key,
  { title, body, variant = "info", autoDismiss = 0, onDismiss = null } = {},
) {
  if (!toastStack) return;
  const fingerprint = toastFingerprint(title, body);
  if (isToastSuppressed(key, fingerprint)) {
    return;
  }
  toastSuppressions.set(key, { suppressed: false, fingerprint });
  let toastEntry = activeToasts.get(key);
  if (!toastEntry) {
    const toastEl = document.createElement("div");
    toastEl.className = `toast${variant === "error" ? " toast-error" : ""}`;
    toastEl.dataset.key = key;
    toastEl.innerHTML = `
            <div class="toast-title">
                <span>${title || ""}</span>
                <button type="button" class="toast-dismiss" aria-label="Dismiss">×</button>
            </div>
            <div class="toast-body">${body || ""}</div>
        `;
    toastStack.appendChild(toastEl);
    const dismissBtn = toastEl.querySelector(".toast-dismiss");
    if (dismissBtn) {
      dismissBtn.addEventListener("click", () =>
        dismissToast(key, { manual: true }),
      );
    }
    toastEntry = { element: toastEl, timer: null, onDismiss, fingerprint };
    activeToasts.set(key, toastEntry);
  } else {
    toastEntry.element.classList.toggle("toast-error", variant === "error");
    const titleEl = toastEntry.element.querySelector(".toast-title span");
    if (titleEl) titleEl.textContent = title || "";
    const bodyEl = toastEntry.element.querySelector(".toast-body");
    if (bodyEl) bodyEl.textContent = body || "";
    toastEntry.onDismiss = onDismiss;
    toastEntry.fingerprint = fingerprint;
  }
  if (toastEntry.timer) {
    clearTimeout(toastEntry.timer);
    toastEntry.timer = null;
  }
  if (autoDismiss > 0) {
    toastEntry.timer = setTimeout(() => dismissToast(key), autoDismiss);
  }
}

function dismissToast(key, options = {}) {
  const { manual = false } = options;
  const toastEntry = activeToasts.get(key);
  if (!toastEntry) {
    if (!manual) {
      toastSuppressions.delete(key);
    }
    return;
  }
  if (toastEntry.timer) {
    clearTimeout(toastEntry.timer);
  }
  toastEntry.element.classList.add("toast-leave");
  const removalDelay = 160;
  setTimeout(() => {
    if (toastEntry.element && toastEntry.element.parentElement) {
      toastEntry.element.parentElement.removeChild(toastEntry.element);
    }
  }, removalDelay);
  activeToasts.delete(key);
  if (manual) {
    toastSuppressions.set(key, {
      suppressed: true,
      fingerprint: toastEntry.fingerprint || "",
    });
  } else {
    toastSuppressions.delete(key);
  }
  if (typeof toastEntry.onDismiss === "function") {
    toastEntry.onDismiss();
  }
}

function truncateLabel(label, maxLength = 42) {
  if (typeof label !== "string") return "";
  if (label.length <= maxLength) return label;
  const head = label.slice(0, Math.max(0, maxLength - 10));
  const tail = label.slice(-8);
  return `${head}…${tail}`;
}

function deriveFilename(item) {
  if (!item) return "";
  if (typeof item.name === "string" && item.name) {
    const parts = item.name.split(/[\\/]/);
    return parts.pop() || item.name;
  }
  if (typeof item.path === "string" && item.path) {
    const segments = item.path.split(/[\\/]/);
    return segments.pop() || item.path;
  }
  return "";
}

function getFallbackLabel(item) {
  const filename = deriveFilename(item);
  return truncateLabel(filename || "untitled", 38);
}

function syncClearButton(input, button) {
  if (!button) return;
  if (input && input.value && input.value.trim()) {
    button.classList.add("input-action-visible");
  } else {
    button.classList.remove("input-action-visible");
  }
}

function applySidebarState({ syncStatus = true } = {}) {
  if (!sidebarEl) return;
  const isDesktop = desktopMediaQuery.matches;
  if (isDesktop) {
    sidebarVisible = true;
    sidebarEl.classList.remove("sidebar-open");
    sidebarEl.classList.remove("collapsed");
  } else {
    sidebarEl.classList.remove("collapsed");
    sidebarEl.classList.toggle("sidebar-open", sidebarVisible);
  }
  if (syncStatus) {
    setStatusCardExpanded(statusCardVisible, { animate: false });
  }
  if (sidebarToggleBtn) {
    const expanded = isDesktop ? statusCardVisible : sidebarVisible;
    sidebarToggleBtn.setAttribute("aria-expanded", expanded ? "true" : "false");
    sidebarToggleBtn.classList.toggle("is-open", expanded);
  }
}

if (sidebarToggleBtn) {
  sidebarToggleBtn.addEventListener("click", () => {
    if (desktopMediaQuery.matches) {
      setStatusCardExpanded(!statusCardVisible, { animate: true });
    } else {
      sidebarVisible = !sidebarVisible;
      if (sidebarVisible) {
        setStatusCardExpanded(true, { animate: false });
      }
    }
    applySidebarState({ syncStatus: false });
  });
}

desktopMediaQuery.addEventListener("change", (event) => {
  if (event.matches) {
    sidebarVisible = true;
  } else {
    sidebarVisible = false;
  }
  applySidebarState({ syncStatus: false });
  setStatusCardExpanded(statusCardVisible, { animate: false });
});

applySidebarState();

function updateStatusCardHeight() {
  if (!statusWrapperEl || !statusCardEl) return;
  if (!statusCardVisible) return;
  statusWrapperEl.style.maxHeight = "none";
  statusWrapperEl.style.overflow = "visible";
}

function setStatusCardExpanded(expand, { animate = true } = {}) {
  statusCardVisible = !!expand;
  if (!statusWrapperEl || !statusCardEl) return;
  const wrapper = statusWrapperEl;
  const content = statusCardEl;

  const finishTransition = (expanded) => {
    if (expanded) {
      wrapper.style.transition = "";
      wrapper.style.maxHeight = "none";
      wrapper.style.overflow = "visible";
    } else {
      wrapper.classList.add("collapsed");
      wrapper.style.transition = "";
      wrapper.style.overflow = "hidden";
    }
  };

  if (!animate) {
    wrapper.style.transition = "none";
    if (statusCardVisible) {
      wrapper.classList.remove("collapsed");
      wrapper.style.maxHeight = "none";
      wrapper.style.opacity = "1";
      wrapper.style.overflow = "visible";
    } else {
      wrapper.classList.add("collapsed");
      wrapper.style.maxHeight = "0px";
      wrapper.style.opacity = "0";
      wrapper.style.overflow = "hidden";
    }
    // force reflow then clear transition so subsequent animations work
    requestAnimationFrame(() => {
      wrapper.style.transition = "";
    });
    return;
  }

  const handler = (event) => {
    if (event.propertyName !== "max-height") {
      return;
    }
    wrapper.removeEventListener("transitionend", handler);
    finishTransition(statusCardVisible);
  };

  wrapper.removeEventListener("transitionend", handler);
  wrapper.addEventListener("transitionend", handler);

  if (statusCardVisible) {
    const target = content.scrollHeight;
    wrapper.classList.remove("collapsed");
    wrapper.style.overflow = "hidden";
    wrapper.style.transition = "none";
    wrapper.style.maxHeight = "0px";
    wrapper.style.opacity = "0";
    // force reflow
    wrapper.getBoundingClientRect();
    wrapper.style.transition = "max-height 0.28s ease, opacity 0.24s ease";
    wrapper.style.maxHeight = `${target}px`;
    wrapper.style.opacity = "1";
  } else {
    const current = wrapper.offsetHeight || content.scrollHeight;
    wrapper.style.overflow = "hidden";
    wrapper.style.transition = "none";
    wrapper.style.maxHeight = `${current}px`;
    wrapper.style.opacity = "1";
    wrapper.getBoundingClientRect();
    wrapper.style.transition = "max-height 0.24s ease, opacity 0.24s ease";
    wrapper.style.maxHeight = "0px";
    wrapper.style.opacity = "0";
  }
}

function applyTagsToCard(imageId, tags) {
  if (!cardElements.has(imageId)) {
    return;
  }
  const normalized = [];
  if (Array.isArray(tags)) {
    tags.forEach((tag) => {
      if (!tag || typeof tag !== "object") return;
      const norm = typeof tag.norm === "string" ? tag.norm : "";
      if (!norm) return;
      const kind = typeof tag.kind === "string" ? tag.kind : "prompt";
      const label = typeof tag.tag === "string" && tag.tag ? tag.tag : norm;
      const emphasis =
        typeof tag.emphasis === "string" ? tag.emphasis : "normal";
      const weight = Number.isFinite(tag.weight) ? Number(tag.weight) : 1;
      const source =
        typeof tag.source === "string" && tag.source ? tag.source : "embedded";
      normalized.push({ tag: label, norm, kind, emphasis, weight, source });
    });
  }

  const previous = searchState.imageTags.get(imageId) || [];
  const previousKeys = new Set(
    previous.map((tag) => `${tag.kind}|${tag.norm}`),
  );
  previousKeys.forEach((key) => {
    const bucket = tagToCards.get(key);
    if (bucket) {
      bucket.delete(imageId);
      if (!bucket.size) {
        tagToCards.delete(key);
      }
    }
  });

  searchState.imageTags.set(imageId, normalized);

  const newKeys = new Set();
  normalized.forEach((tag) => {
    const key = `${tag.kind}|${tag.norm}`;
    if (newKeys.has(key)) return;
    newKeys.add(key);
    if (!tagToCards.has(key)) {
      tagToCards.set(key, new Set());
    }
    tagToCards.get(key).add(imageId);
  });
}

async function loadTagsForImageIds(imageIds) {
  if (!clipModeActive) {
    return;
  }
  const uniqueIds = Array.from(
    new Set((Array.isArray(imageIds) ? imageIds : []).map(Number)),
  ).filter((id) => Number.isFinite(id) && id >= 0);
  const missing = uniqueIds.filter((id) => {
    const tags = searchState.imageTags.get(id);
    return !tags || !tags.length;
  });
  if (!missing.length) {
    return;
  }
  for (let index = 0; index < missing.length; index += TAG_FETCH_BATCH_SIZE) {
    if (!clipModeActive) {
      return;
    }
    const batch = missing.slice(index, index + TAG_FETCH_BATCH_SIZE);
    await fetchTagBatch(batch);
  }
  if (!clipModeActive) {
    return;
  }
  facetCache = buildClipFacetSummaryFromImageTags(searchState.imageTags);
  renderFacets(facetCache);
}

async function fetchTagBatch(batchIds) {
  if (!Array.isArray(batchIds) || !batchIds.length) {
    return;
  }
  try {
    const res = await fetch("/api/image-tags", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids: batchIds }),
    });
    if (!res.ok) throw new Error(`tag fetch failed: ${res.status}`);
    const payload = await res.json();
    if (!clipModeActive) {
      return;
    }
    const tagMap = payload && payload.tags;
    if (tagMap && typeof tagMap === "object") {
      Object.entries(tagMap).forEach(([idStr, tagList]) => {
        const imageId = Number(idStr);
        if (!Number.isFinite(imageId)) return;
        if (!cardElements.has(imageId)) return;
        const tags = Array.isArray(tagList) ? tagList : [];
        applyTagsToCard(imageId, tags);
      });
    }
  } catch (err) {
    console.error("Failed to load tags for images", err);
  }
}

async function startClipUploadSearch(file) {
  if (!file || !(file instanceof File)) {
    return;
  }
  if (!file.type || !file.type.toLowerCase().startsWith("image/")) {
    statusEl.textContent = "Please drop an image file";
    return;
  }
  if (searchState.loading) {
    statusEl.textContent = "Another search is in progress…";
    return;
  }

  const tagFilter = searchBox.value.trim();
  lastQuery = tagFilter;
  clipModeActive = true;
  currentClipToken = null;
  pendingDetailId = null;
  resetState(lastQuery, { clearClip: false });
  clipOffset = 0;
  clipTotal = 0;
  scrollRestorePending = true;
  pendingScrollIndex = 0;
  lastAnchorIndex = 0;
  statusEl.textContent = "Processing image…";
  searchState.loading = true;
  if (clipSearchClear) clipSearchClear.disabled = true;
  if (detailSimilarBtn) detailSimilarBtn.disabled = true;

  const formData = new FormData();
  formData.append("file", file, file.name || "upload");
  formData.append("limit", String(PAGE_SIZE));
  formData.append("offset", "0");
  if (tagFilter) formData.append("tag_query", tagFilter);
  formData.append("include_tags", "0");

  try {
    const res = await fetch("/api/search/clip/file", {
      method: "POST",
      body: formData,
    });
    if (!res.ok) throw new Error(`clip upload failed: ${res.status}`);
    const data = await res.json();
    const vector =
      typeof data.vector === "string" && data.vector ? data.vector : null;
    const uploadLabel = file.name ? `image:${file.name}` : "uploaded image";

    lastClipPayload = {
      query: "",
      positiveImages: [],
      negativeImages: [],
      tagQuery: tagFilter,
      updateInput: uploadLabel,
      positiveVector: vector,
    };

    const results = Array.isArray(data.results) ? data.results : [];
    const newImageIds = [];
    results.forEach((item) => {
      const idx = searchState.images.length;
      searchState.images.push(item);
      searchState.index.set(item.id, idx);
      const template = document.createElement("template");
      template.innerHTML = renderCard(item).trim();
      const cardEl = template.content.firstElementChild;
      registerCardElement(cardEl, item);
      gridEl.appendChild(cardEl);
      if (Number.isFinite(item.id)) {
        newImageIds.push(Number(item.id));
      }
    });

    clipTotal = data.total ?? results.length ?? 0;
    clipOffset = results.length;
    searchState.total = clipTotal;
    searchState.done = clipOffset >= clipTotal;
    loadMoreBtn.style.display = searchState.done ? "none" : "block";

    const backendFacets = Array.isArray(data.facets) ? data.facets : null;
    const computedFacets = buildClipFacetSummaryFromImageTags(
      searchState.imageTags,
    );
    if (computedFacets.length) {
      facetCache = computedFacets;
    } else if (backendFacets && backendFacets.length) {
      facetCache = backendFacets.map((facet) => ({
        tag: facet.tag,
        norm: facet.norm,
        kind: facet.kind,
        freq: facet.freq,
      }));
    } else {
      facetCache = [];
    }
    renderFacets(facetCache);

    if (clipModeActive && newImageIds.length) {
      loadTagsForImageIds(newImageIds);
    }

    if (clipSearchInput) {
      clipSearchInput.value = uploadLabel;
    }
    updateStatus();
    pushHistoryState(
      { query: lastQuery, detail: null, pos: 0, clip: null },
      { replace: true },
    );
  } catch (err) {
    console.error("Image similarity search failed", err);
    statusEl.textContent = "Image search failed";
    resetState(lastQuery, { clearClip: false });
    clipOffset = 0;
    clipTotal = 0;
    clipModeActive = false;
    lastClipPayload = null;
    currentClipToken = null;
  } finally {
    searchState.loading = false;
    if (clipSearchClear) clipSearchClear.disabled = false;
    if (detailSimilarBtn) detailSimilarBtn.disabled = false;
    scheduleScrollSave();
  }
}

function buildClipPayloadFromToken(token, tagQuery) {
  const decoded = decodeClipState(token);
  if (!decoded) return null;
  if (decoded.mode === "image" && Number.isFinite(decoded.id)) {
    const id = Number(decoded.id);
    return {
      positiveImages: [id],
      tagQuery,
      updateInput: `image:${id}`,
    };
  }
  if (decoded.mode === "text") {
    const text = (decoded.query || "").trim();
    return {
      query: text,
      tagQuery,
      updateInput: text,
    };
  }
  return null;
}

function parseStateFromLocation() {
  const params = new URLSearchParams(window.location.search);
  const query = (params.get("q") || "").trim();
  const detailParam = params.get("detail");
  const posParam = params.get("pos");
  const clipParam = params.get("clip");
  return {
    query,
    detail: normalizeDetail(detailParam),
    pos: normalizeIndex(posParam),
    clip: clipParam || null,
  };
}

function buildUrlFromState(state) {
  const params = new URLSearchParams();
  if (state.query) params.set("q", state.query);
  if (state.detail !== null && state.detail !== undefined) {
    const normalizedDetail = normalizeDetail(state.detail);
    if (normalizedDetail !== null) {
      params.set("detail", String(normalizedDetail));
    }
  }
  const normalizedPos = normalizeIndex(state.pos);
  if (normalizedPos !== null && normalizedPos > 0) {
    params.set("pos", String(normalizedPos));
  }
  if (state.clip) {
    params.set("clip", state.clip);
  }
  const search = params.toString();
  return `${window.location.pathname}${search ? `?${search}` : ""}`;
}

function pushHistoryState(state, { replace = false } = {}) {
  const queryValue = (state.query ?? currentHistoryState.query ?? "").trim();
  const detailValue =
    state.detail !== undefined
      ? normalizeDetail(state.detail)
      : normalizeDetail(currentHistoryState.detail);
  const posCandidate =
    state.pos !== undefined
      ? normalizeIndex(state.pos)
      : normalizeIndex(currentHistoryState.pos);
  const clipValue =
    state.clip !== undefined ? state.clip : (currentHistoryState.clip ?? null);
  const normalizedState = {
    query: queryValue,
    detail: detailValue,
    pos: posCandidate ?? 0,
    clip: clipValue || null,
  };
  const url = buildUrlFromState(normalizedState);
  if (replace) {
    history.replaceState(normalizedState, "", url);
  } else {
    history.pushState(normalizedState, "", url);
  }
  currentHistoryState = normalizedState;
  currentClipToken = normalizedState.clip;
}
copyPositiveBtn.disabled = true;
copyNegativeBtn.disabled = true;
detailPromptsSection.style.display = "none";

function copyText(text) {
  if (!text) return;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard
      .writeText(text)
      .catch((err) => console.error("Clipboard error", err));
  } else {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    try {
      document.execCommand("copy");
    } catch (err) {
      console.error("Clipboard fallback failed", err);
    }
    document.body.removeChild(textarea);
  }
}

function setActiveSuggestion(index) {
  suggestionIndex = index;
  suggestionItems.forEach((item, idx) => {
    if (!item) return;
    if (idx === index) {
      item.classList.add("active");
    } else {
      item.classList.remove("active");
    }
  });
  if (index >= 0 && suggestionItems[index]) {
    suggestionItems[index].scrollIntoView({ block: "nearest" });
  }
}

function rebuildSuggestionItems() {
  suggestionItems = Array.from(suggestionsEl.querySelectorAll("li"));
}

function formatFileSize(bytes) {
  if (!Number.isFinite(bytes)) return "–";
  const thresh = 1024;
  if (bytes < thresh) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let u = -1;
  do {
    bytes /= thresh;
    ++u;
  } while (bytes >= thresh && u < units.length - 1);
  return `${bytes.toFixed(bytes >= 10 ? 0 : 1)} ${units[u]}`;
}

const RATING_CLASSES = ["general", "sensitive", "questionable", "explicit"];
const RATING_DISPLAY_NAMES = {
  general: "General",
  sensitive: "Sensitive",
  questionable: "Questionable",
  explicit: "Explicit",
};

function getSearchTokensList() {
  const current = searchBox.value ? searchBox.value.trim() : "";
  if (!current) {
    return [];
  }
  return current
    .split(",")
    .map((token) => token.trim())
    .filter(Boolean);
}

function stripRatingTokens(tokens) {
  return tokens.filter((token) => !/^[-!]?rating:/i.test(token));
}

function syncRatingFiltersFromQuery() {
  if (!ratingFilterMeta.length) {
    return;
  }
  const tokens = getSearchTokensList();
  const positives = new Set();
  const negatives = new Set();
  tokens.forEach((token) => {
    const lowered = token.toLowerCase();
    if (lowered.startsWith("-rating:") || lowered.startsWith("!rating:")) {
      const value = lowered.slice(8);
      if (RATING_CLASSES.includes(value)) {
        negatives.add(value);
      }
    } else if (lowered.startsWith("rating:")) {
      const value = lowered.slice(7);
      if (RATING_CLASSES.includes(value)) {
        positives.add(value);
      }
    }
  });
  ratingFilterMeta.forEach(({ input, value }) => {
    if (!RATING_CLASSES.includes(value)) {
      return;
    }
    let checked;
    if (positives.size > 0) {
      checked = positives.has(value) && !negatives.has(value);
    } else {
      checked = !negatives.has(value);
    }
    input.checked = checked;
  });
}

function applyRatingFiltersToQuery(options = {}) {
  const { pushHistory = true } = options;
  if (!ratingFilterMeta.length) {
    return;
  }
  const currentTokens = getSearchTokensList();
  const baseTokens = stripRatingTokens(currentTokens);
  const unchecked = Array.from(
    new Set(
      ratingFilterMeta
        .filter((meta) => !meta.input.checked)
        .map((meta) => meta.value)
        .filter((value) => RATING_CLASSES.includes(value)),
    ),
  );
  const nextTokens = [...baseTokens];
  unchecked.forEach((value) => {
    nextTokens.push(`-rating:${value}`);
  });
  const nextQuery = nextTokens.join(", ");
  commitSearch(nextQuery, { pushHistory });
}

function updateRatingFilterCounts(countsOverride) {
  if (!ratingFilterMeta.length) {
    return;
  }
  const counts = new Map();
  if (countsOverride && typeof countsOverride === "object") {
    Object.entries(countsOverride).forEach(([key, value]) => {
      const normKey = String(key).toLowerCase();
      const numeric = Number(value);
      if (Number.isFinite(numeric)) {
        counts.set(normKey, numeric);
      }
    });
  } else {
    const facets = Array.isArray(facetCache) ? facetCache : [];
    facets.forEach((facet) => {
      if (!facet || facet.kind !== "rating") return;
      const norm = typeof facet.norm === "string" ? facet.norm.toLowerCase() : "";
      if (!norm) return;
      const freq = Number.isFinite(facet.freq) ? Number(facet.freq) : 0;
      counts.set(norm, freq);
    });
  }
  ratingFilterMeta.forEach(({ label, countEl, value }) => {
    const freq = counts.get(value) || 0;
    if (countEl) {
      countEl.textContent = freq.toLocaleString();
    }
    if (label) {
      if (freq > 0) {
        label.classList.add("rating-has-results");
      } else {
        label.classList.remove("rating-has-results");
      }
      label.setAttribute("data-count", String(freq));
    }
  });
}

const STATUS_LABELS = {
  ready: "Done",
  done: "Done",
  pending: "Queued",
  processing: "Processing",
  error: "Failed",
  failed: "Failed",
  skipped: "Done",
  disabled: "Disabled",
  missing: "Not queued",
  unknown: "Unknown",
};

const STATUS_CLASS_MAP = {
  ready: "done",
  done: "done",
  pending: "queued",
  processing: "processing",
  error: "failed",
  failed: "failed",
  skipped: "done",
  disabled: "disabled",
  missing: "missing",
  unknown: "unknown",
};

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

function normaliseStatus(state) {
  if (!state || state.enabled === false) {
    return "disabled";
  }
  const raw =
    typeof state.status === "string" ? state.status.trim().toLowerCase() : "";
  if (raw) return raw;
  if (state.has_embedding) return "ready";
  if (state.has_tags) return "ready";
  if (state.has_rating) return "ready";
  return "unknown";
}

function buildStatusChip(title, state) {
  if (!state) return "";
  const status = normaliseStatus(state);
  let label = STATUS_LABELS[status] || "Unknown";
  if (
    (status === "pending" || status === "queued") &&
    typeof state.position === "number" &&
    state.position > 0
  ) {
    label = `${label} (#${state.position})`;
  }
  if (
    status === "ready" &&
    typeof state.rating === "string" &&
    state.rating
  ) {
    const ratingText = state.rating.replace(/_/g, " ");
    label = `${label} (${ratingText})`;
  }
  const statusClass = STATUS_CLASS_MAP[status] || "unknown";
  return `<span class="status-chip status-${statusClass}">${escapeHtml(title)} • ${escapeHtml(label)}</span>`;
}

function buildStatusChips(processing) {
  const clipState =
    processing && typeof processing === "object" && processing.clip
      ? { ...processing.clip }
      : { enabled: false, status: "disabled" };
  const autoState =
    processing && typeof processing === "object" && processing.auto
      ? { ...processing.auto }
      : { enabled: false, status: "disabled" };
  const ratingState =
    processing && typeof processing === "object" && processing.rating
      ? { ...processing.rating }
      : { enabled: false, status: "disabled" };

  if (clipState && clipState.has_embedding) {
    clipState.status = clipState.status || "ready";
  }
  if (autoState && autoState.has_tags) {
    autoState.status = autoState.status || "ready";
    autoState.has_tags = true;
  }
  if (ratingState && ratingState.has_rating) {
    ratingState.status = ratingState.status || "ready";
  }

  const chips = [
    buildStatusChip("CLIP", clipState),
    buildStatusChip("Auto Tags", autoState),
    buildStatusChip("Rating", ratingState),
  ].filter(Boolean);
  return chips.join("");
}

function uniqueStrings(items) {
  const seen = new Set();
  return items
    .map((item) => (typeof item === "string" ? item.trim() : ""))
    .filter((item) => {
      if (!item) return false;
      const key = item.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

function buildTagStrings(tagList, style) {
  const results = [];
  tagList.forEach((tag) => {
    if (!tag || typeof tag !== "object") return;
    if (tag.kind === "negative" || tag.kind === "rating") return;
    const label = typeof tag.tag === "string" ? tag.tag : "";
    if (!label) return;
    if (style === "danbooru") {
      results.push(label.replace(/\s+/g, "_").trim());
    } else {
      const source = tag.source || "embedded";
      if (source === "auto") {
        results.push(label.replace(/_/g, " ").trim());
      } else {
        const raw =
          typeof tag.raw === "string" && tag.raw.trim() ? tag.raw : label;
        results.push(raw.replace(/_/g, " ").trim());
      }
    }
  });
  return uniqueStrings(results);
}

function buildAllNaiString(positivePrompt, embeddedStrings, autoStrings) {
  const basePrompt =
    typeof positivePrompt === "string" ? positivePrompt.trim() : "";
  const embedList = uniqueStrings(embeddedStrings);
  const autoList = uniqueStrings(autoStrings);
  if (!basePrompt && !embedList.length && !autoList.length) {
    return "";
  }
  if (!basePrompt) {
    return uniqueStrings([...embedList, ...autoList]).join(", ");
  }
  const extraAuto = autoList.filter(
    (token) => !basePrompt.toLowerCase().includes(token.toLowerCase()),
  );
  if (!extraAuto.length) {
    return basePrompt;
  }
  return `${basePrompt}${basePrompt.trim().endsWith(",") ? " " : ", "}${extraAuto.join(", ")}`;
}

function buildDanbooruString(embeddedStrings, autoStrings) {
  return uniqueStrings([...embeddedStrings, ...autoStrings]).join(" ");
}

function setCopyButton(button, value, description) {
  if (!button) return;
  const trimmed = typeof value === "string" ? value.trim() : "";
  if (!trimmed) {
    button.disabled = true;
    button.onclick = null;
    if (description) {
      button.title = `${description} (unavailable)`;
    }
    return;
  }
  button.disabled = false;
  if (description) {
    button.title = description;
  }
  button.onclick = () => copyText(trimmed);
}

function updateCopyButtons({ positivePrompt, tags }) {
  const buttons = [
    copyAllNaiBtn,
    copyAllDanbooruBtn,
    copyEmbeddedNaiBtn,
    copyEmbeddedDanbooruBtn,
    copyAutoNaiBtn,
    copyAutoDanbooruBtn,
  ];
  if (!buttons.some(Boolean)) {
    return;
  }
  const tagList = Array.isArray(tags) ? tags : [];
  const nonNegative = tagList.filter(
    (tag) => tag && tag.kind !== "negative" && tag.kind !== "rating",
  );
  const embeddedTags = nonNegative.filter(
    (tag) => (tag.source || "embedded") !== "auto",
  );
  const autoTags = nonNegative.filter(
    (tag) => (tag.source || "embedded") === "auto",
  );

  const naiEmbedded = buildTagStrings(embeddedTags, "nai");
  const naiAuto = buildTagStrings(autoTags, "nai");
  const danEmbedded = buildTagStrings(embeddedTags, "danbooru");
  const danAuto = buildTagStrings(autoTags, "danbooru");

  const allNai = buildAllNaiString(positivePrompt, naiEmbedded, naiAuto);
  const allDan = buildDanbooruString(danEmbedded, danAuto);
  const embeddedNai = naiEmbedded.join(", ");
  const embeddedDan = danEmbedded.join(" ");
  const autoNai = naiAuto.join(", ");
  const autoDan = danAuto.join(" ");

  setCopyButton(copyAllNaiBtn, allNai, "Copy all tags (NovelAI)");
  setCopyButton(copyAllDanbooruBtn, allDan, "Copy all tags (Danbooru)");
  setCopyButton(
    copyEmbeddedNaiBtn,
    embeddedNai,
    "Copy embedded tags (NovelAI)",
  );
  setCopyButton(
    copyEmbeddedDanbooruBtn,
    embeddedDan,
    "Copy embedded tags (Danbooru)",
  );
  setCopyButton(copyAutoNaiBtn, autoNai, "Copy auto tags (NovelAI)");
  setCopyButton(copyAutoDanbooruBtn, autoDan, "Copy auto tags (Danbooru)");
}

function renderCard(item) {
  const width = Number.isFinite(item.width) ? item.width : "–";
  const height = Number.isFinite(item.height) ? item.height : "–";
  const fallback = getFallbackLabel(item);
  const metaParts = [`${width}×${height}`];
  if (item.seed) {
    metaParts.push(`Seed ${item.seed}`);
  } else {
    metaParts.push(fallback);
  }
  if (item.model) {
    metaParts.push(item.model);
  } else if (item.seed) {
    metaParts.push(fallback);
  }
  const meta = metaParts.join(" • ");
  const thumb = item.thumb_url || item.file_url;
  const ratio =
    item.width && item.height ? `${item.width} / ${item.height}` : "2 / 3";
  const scoreLine =
    typeof item.score === "number"
      ? `<div class="clip-score">score ${item.score.toFixed(3)}</div>`
      : "";
  return `
    <article class="card" data-id="${item.id}">
        <div class="image-wrap" style="aspect-ratio:${ratio};">
            <img src="${thumb}" data-full="${item.file_url}" loading="lazy" alt="${fallback}">
        </div>
        <div class="info">
            <div class="info-row">
                <div class="meta">${meta}</div>
                <button class="similar-button" data-id="${item.id}" title="Find similar" aria-label="Find similar">
                    <span class="icon" aria-hidden="true">≈</span>
                    <span class="sr-only">Find similar</span>
                </button>
            </div>
            ${scoreLine}
        </div>
    </article>`;
}

function registerCardElement(cardEl, item) {
  cardEl.tabIndex = 0;
  cardElements.set(item.id, cardEl);
  applyTagsToCard(item.id, Array.isArray(item.tags) ? item.tags : []);
  cardEl.addEventListener("mouseenter", () => {
    highlightFromCard(item.id);
  });
  cardEl.addEventListener("mouseleave", () => {
    clearHighlights();
  });
  cardEl.addEventListener("focus", () => {
    highlightFromCard(item.id);
  });
  const similarBtn = cardEl.querySelector(".similar-button");
  if (similarBtn) {
    similarBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      const imageId = Number(similarBtn.dataset.id);
      if (!Number.isFinite(imageId)) return;
      if (!clipEnabled) return;
      runClipSearch({
        positiveImages: [imageId],
        tagQuery: searchBox.value.trim(),
        updateInput: `image:${imageId}`,
      });
    });
  }
  cardEl.addEventListener("blur", () => {
    clearHighlights();
  });
}

const activeFacetKeys = new Set();
const activeCardIds = new Set();

function clearHighlights() {
  activeFacetKeys.forEach((key) => {
    const facet = facetLookup.get(key);
    if (facet) facet.classList.remove("facet-highlight");
  });
  activeFacetKeys.clear();
  activeCardIds.forEach((id) => {
    const card = cardElements.get(id);
    if (card) card.classList.remove("card-highlight");
  });
  activeCardIds.clear();
}

function highlightFromCard(cardId) {
  clearHighlights();
  const tags = searchState.imageTags.get(cardId) || [];
  const tagKeys = Array.from(
    new Set(
      tags
        .map((tag) => {
          if (!tag || typeof tag !== "object") return null;
          const norm = typeof tag.norm === "string" ? tag.norm : "";
          if (!norm) return null;
          const kind = typeof tag.kind === "string" ? tag.kind : "prompt";
          return `${kind}|${norm}`;
        })
        .filter(Boolean),
    ),
  );
  tagKeys.forEach((key) => {
    const facet = facetLookup.get(key);
    if (facet) {
      facet.classList.add("facet-highlight");
      activeFacetKeys.add(key);
    }
  });
  const card = cardElements.get(cardId);
  if (card) {
    card.classList.add("card-highlight");
    activeCardIds.add(cardId);
  }
}

function highlightFromFacet(key) {
  clearHighlights();
  const facet = facetLookup.get(key);
  if (facet) {
    facet.classList.add("facet-highlight");
    activeFacetKeys.add(key);
  }
  const ids = tagToCards.get(key);
  if (ids) {
    ids.forEach((id) => {
      const card = cardElements.get(id);
      if (card) {
        card.classList.add("card-highlight");
        activeCardIds.add(id);
      }
    });
  }
}

function updateStatus() {
  if (clipModeActive) {
    const total = clipTotal || searchState.total || 0;
    statusEl.textContent = total
      ? `CLIP ${searchState.images.length}/${total}`
      : `CLIP ${searchState.images.length}`;
  } else {
    statusEl.textContent = `${searchState.images.length}/${searchState.total}`;
  }
}

function resetState(query, { clearClip = true } = {}) {
  if (clearClip) {
    clipModeActive = false;
    lastClipPayload = null;
    currentClipToken = null;
    clipOffset = 0;
    clipTotal = 0;
  }
  searchState.query = query;
  searchState.images = [];
  searchState.index = new Map();
  searchState.imageTags = new Map();
  searchState.total = 0;
  searchState.done = false;
  gridEl.innerHTML = "";
  facetLookup.clear();
  tagToCards.clear();
  cardElements.clear();
  suggestionItems = [];
  suggestionIndex = -1;
  clearHighlights();
  updateStatus();
}

async function fetchImages(reset = false) {
  if (searchState.loading) return;
  if (reset) {
    resetState(lastQuery);
  } else if (clipModeActive) {
    return;
  }
  if (searchState.done && !reset) return;
  searchState.loading = true;
  statusEl.textContent = "Loading…";
  let queueMoreForScroll = false;
  try {
    const params = new URLSearchParams({
      q: lastQuery,
      offset: String(searchState.images.length),
      limit: String(PAGE_SIZE),
    });
    const res = await fetch(`/api/images?${params.toString()}`);
    if (!res.ok) throw new Error("Request failed");
    const data = await res.json();
    if (reset) {
      gridEl.innerHTML = "";
    }
    data.images.forEach((item) => {
      const idx = searchState.images.length;
      searchState.images.push(item);
      searchState.index.set(item.id, idx);
      searchState.imageTags.set(item.id, item.tags || []);
      const template = document.createElement("template");
      template.innerHTML = renderCard(item).trim();
      const cardEl = template.content.firstElementChild;
      registerCardElement(cardEl, item);
      gridEl.appendChild(cardEl);
    });
    if (autoObserver) {
      autoObserver.unobserve(sentinel);
      autoObserver.observe(sentinel);
    }
    clearHighlights();
    facetCache = Array.isArray(data.facets) ? data.facets : [];
    renderFacets(facetCache);
    searchState.total = data.total;
    searchState.done = searchState.images.length >= data.total;
    if (!autoObserver) {
      loadMoreBtn.style.display = searchState.done ? "none" : "block";
    }
    if (
      scrollRestorePending &&
      pendingScrollIndex !== null &&
      pendingScrollIndex > 0 &&
      searchState.images.length <= pendingScrollIndex &&
      !searchState.done
    ) {
      queueMoreForScroll = true;
    }
    updateStatus();
    maybeOpenPendingDetail();
  } catch (err) {
    console.error(err);
    statusEl.textContent = "Error";
  } finally {
    searchState.loading = false;
    if (scrollRestorePending) {
      if (queueMoreForScroll) {
        setTimeout(() => fetchImages(), 0);
      } else {
        maybeRestoreScrollPosition();
      }
    } else {
      scheduleScrollSave();
    }
  }
}

async function runClipSearch(
  {
    query = "",
    positiveImages = [],
    negativeImages = [],
    tagQuery = searchBox.value.trim(),
    updateInput,
    positiveVector = null,
  } = {},
  { append = false, updateHistory = true } = {},
) {
  if (!clipEnabled) {
    statusEl.textContent = "CLIP disabled";
    return;
  }
  if (searchState.loading) {
    return;
  }
  if (clipSearchTimer) {
    clearTimeout(clipSearchTimer);
    clipSearchTimer = null;
  }

  const originalQuery = typeof query === "string" ? query : "";
  const trimmedQuery = originalQuery.trim();
  const posIds = Array.isArray(positiveImages)
    ? positiveImages.map(Number).filter(Number.isFinite)
    : [];
  const negIds = Array.isArray(negativeImages)
    ? negativeImages.map(Number).filter(Number.isFinite)
    : [];
  if (
    !trimmedQuery &&
    posIds.length === 0 &&
    negIds.length === 0 &&
    !positiveVector
  ) {
    statusEl.textContent = "Provide CLIP input";
    return;
  }
  if (updateInput !== undefined && clipSearchInput) {
    clipSearchInput.value = updateInput;
    syncClearButton(clipSearchInput, clipSearchClear);
  }

  clipModeActive = true;
  const clipToken =
    encodeClipState({ query: trimmedQuery, positiveImages: posIds }) || null;
  if (!append) {
    clipOffset = 0;
    clipTotal = 0;
    resetState(lastQuery, { clearClip: false });
    if (!scrollRestorePending) {
      pendingScrollIndex = 0;
      scrollRestorePending = true;
      lastAnchorIndex = 0;
    }
    if (autoObserver) {
      autoObserver.unobserve(sentinel);
    }
    facetCache = [];
    renderFacets(facetCache);
  } else {
    statusEl.textContent = "Loading clip results…";
  }

  currentClipToken = clipToken ?? currentClipToken ?? null;

  searchState.loading = true;
  if (!append) {
    statusEl.textContent = "CLIP search…";
  }
  if (detailSimilarBtn) detailSimilarBtn.disabled = true;
  if (clipSearchClear) clipSearchClear.disabled = true;

  const payload = {
    limit: PAGE_SIZE,
    offset: append ? clipOffset : 0,
    include_tags: false,
  };
  const tagFilter = (tagQuery || "").trim();
  if (tagFilter) payload.tag_query = tagFilter;
  if (trimmedQuery) payload.query = trimmedQuery;
  if (posIds.length) payload.positive_images = posIds;
  if (negIds.length) payload.negative_images = negIds;
  if (positiveVector) payload.positive_vector = positiveVector;

  lastClipPayload = {
    query: trimmedQuery,
    positiveImages: posIds.slice(),
    negativeImages: negIds.slice(),
    tagQuery: tagFilter,
    updateInput:
      updateInput !== undefined
        ? updateInput
        : originalQuery !== ""
          ? originalQuery
          : posIds.length
            ? `image:${posIds[0]}`
            : "",
    positiveVector: positiveVector || null,
  };
  if (clipToken) {
    lastClipPayload.clipToken = clipToken;
  } else {
    delete lastClipPayload.clipToken;
  }

  let queueMoreForScroll = false;

  try {
    const res = await fetch("/api/search/clip", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`clip search failed: ${res.status}`);
    const data = await res.json();
    const results = Array.isArray(data.results) ? data.results : [];

    if (!append) {
      gridEl.innerHTML = "";
      searchState.images = [];
      searchState.index = new Map();
      searchState.imageTags = new Map();
      requestAnimationFrame(() =>
        window.scrollTo({ top: 0, behavior: "auto" }),
      );
    }

    const newImageIds = [];
    results.forEach((item) => {
      const idx = searchState.images.length;
      searchState.images.push(item);
      searchState.index.set(item.id, idx);
      const template = document.createElement("template");
      template.innerHTML = renderCard(item).trim();
      const cardEl = template.content.firstElementChild;
      registerCardElement(cardEl, item);
      gridEl.appendChild(cardEl);
      if (Number.isFinite(item.id)) {
        newImageIds.push(Number(item.id));
      }
    });

    clipTotal = data.total ?? clipTotal ?? 0;
    clipOffset += results.length;

    const backendFacets = Array.isArray(data.facets) ? data.facets : null;
    const computedFacets = buildClipFacetSummaryFromImageTags(
      searchState.imageTags,
    );
    if (computedFacets.length) {
      facetCache = computedFacets;
    } else if (backendFacets && backendFacets.length) {
      facetCache = backendFacets.map((facet) => ({
        tag: facet.tag,
        norm: facet.norm,
        kind: facet.kind,
        freq: facet.freq,
      }));
    } else {
      facetCache = [];
    }
    renderFacets(facetCache);
    searchState.total = clipTotal;
    searchState.done = clipOffset >= clipTotal;

    loadMoreBtn.style.display = searchState.done ? "none" : "block";
    if (autoObserver) {
      autoObserver.unobserve(sentinel);
      if (!searchState.done) {
        autoObserver.observe(sentinel);
      }
    }

    if (!append && updateHistory) {
      const anchorIndexForHistory =
        scrollRestorePending && pendingScrollIndex !== null
          ? pendingScrollIndex
          : 0;
      pushHistoryState({
        query: lastQuery,
        detail: null,
        pos: anchorIndexForHistory,
        clip: clipToken ?? null,
      });
    }

    if (clipModeActive && newImageIds.length) {
      loadTagsForImageIds(newImageIds);
    }

    if (
      scrollRestorePending &&
      pendingScrollIndex !== null &&
      pendingScrollIndex > 0 &&
      searchState.images.length <= pendingScrollIndex &&
      !searchState.done
    ) {
      queueMoreForScroll = true;
    }

    updateStatus();
    maybeOpenPendingDetail();
  } catch (err) {
    console.error(err);
    statusEl.textContent = "CLIP search failed";
  } finally {
    searchState.loading = false;
    if (clipSearchClear) clipSearchClear.disabled = false;
    if (detailSimilarBtn) detailSimilarBtn.disabled = false;
    updateStatus();
    if (scrollRestorePending) {
      if (queueMoreForScroll && lastClipPayload) {
        setTimeout(() => {
          runClipSearch(lastClipPayload, {
            append: true,
            updateHistory: false,
          });
        }, 0);
      } else {
        maybeRestoreScrollPosition();
      }
    } else if (!append) {
      scheduleScrollSave();
    }
  }
}

function rerunLastClipSearch() {
  if (lastClipPayload) {
    runClipSearch(lastClipPayload, { append: false, updateHistory: false });
  }
}

function maybeOpenPendingDetail() {
  if (pendingDetailId === null || pendingDetailId === undefined) {
    return;
  }
  const targetId = Number(pendingDetailId);
  if (!Number.isFinite(targetId)) {
    pendingDetailId = null;
    return;
  }
  const normalizedId = Math.trunc(targetId);
  if (normalizedId < 0) {
    pendingDetailId = null;
    return;
  }
  if (
    detailOverlay.classList.contains("active") &&
    currentDetailId === normalizedId
  ) {
    pendingDetailId = null;
    return;
  }
  pendingDetailId = null;
  openDetail(normalizedId, { pushState: false }).catch((err) =>
    console.error(err),
  );
}

function getAnchorIndex() {
  if (!searchState.images.length) return 0;
  const threshold = window.scrollY + (headerEl ? headerEl.offsetHeight + 8 : 0);
  let closestIndex = 0;
  let closestTop = -Infinity;
  cardElements.forEach((card, id) => {
    const index = searchState.index.get(Number(id));
    if (index === undefined || index === null) return;
    const top = card.offsetTop;
    if (top <= threshold && top > closestTop) {
      closestTop = top;
      closestIndex = index;
    }
  });
  return closestIndex;
}

function maybeRestoreScrollPosition() {
  if (!scrollRestorePending) return;
  if (pendingScrollIndex === null) {
    scrollRestorePending = false;
    return;
  }
  if (pendingScrollIndex >= searchState.images.length) {
    if (searchState.done && searchState.images.length > 0) {
      pendingScrollIndex = searchState.images.length - 1;
    } else if (searchState.done && searchState.images.length === 0) {
      scrollRestorePending = false;
      pendingScrollIndex = null;
      requestAnimationFrame(() =>
        window.scrollTo({ top: 0, behavior: "auto" }),
      );
      return;
    } else {
      return;
    }
  }
  if (pendingScrollIndex === 0) {
    scrollRestorePending = false;
    pendingScrollIndex = null;
    requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: "auto" }));
    return;
  }
  if (pendingScrollIndex < searchState.images.length) {
    const target = searchState.images[pendingScrollIndex];
    if (!target) {
      return;
    }
    const card = cardElements.get(target.id);
    if (!card) {
      return;
    }
    scrollRestorePending = false;
    pendingScrollIndex = null;
    requestAnimationFrame(() => {
      const offset = headerEl ? headerEl.offsetHeight + 8 : 0;
      const top = card.getBoundingClientRect().top + window.scrollY - offset;
      window.scrollTo({ top: Math.max(0, top), behavior: "auto" });
    });
  }
}

function scheduleScrollSave() {
  if (scrollRestorePending) return;
  if (scrollSaveScheduled) return;
  scrollSaveScheduled = true;
  requestAnimationFrame(() => {
    scrollSaveScheduled = false;
    if (!searchState.images.length) return;
    const anchorIndex = getAnchorIndex();
    const activeDetail = detailOverlay.classList.contains("active")
      ? currentDetailId
      : null;
    if (
      anchorIndex === (currentHistoryState.pos ?? 0) &&
      activeDetail === currentHistoryState.detail &&
      lastQuery === (currentHistoryState.query ?? "")
    ) {
      return;
    }
    lastAnchorIndex = anchorIndex;
    const clipTokenForHistory = getActiveClipToken();
    pushHistoryState(
      {
        query: lastQuery,
        detail: activeDetail,
        pos: anchorIndex,
        clip: clipTokenForHistory,
      },
      { replace: true },
    );
  });
}

function renderFacets(facets) {
  facetListEl.innerHTML = "";
  facetLookup.clear();
  clearHighlights();
  const source = Array.isArray(facets) ? facets : [];
  const filtered = source.filter((facet) =>
    hideUCTags ? facet.kind !== "negative" : true,
  );
  if (filtered.length === 0) {
    const empty = document.createElement("li");
    empty.textContent = "No tags";
    empty.style.opacity = "0.5";
    facetListEl.appendChild(empty);
    return;
  }
  filtered.slice(0, 80).forEach((facet) => {
    const li = document.createElement("li");
    li.dataset.kind = facet.kind;
    li.innerHTML = `<span>${facet.tag}</span><span class="count">${facet.freq}</span>`;
    li.addEventListener("click", () => applyFacet(facet));
    const key = `${facet.kind}|${facet.norm}`;
    facetLookup.set(key, li);
    li.dataset.key = key;
    li.tabIndex = 0;
    li.addEventListener("mouseenter", () => highlightFromFacet(key));
    li.addEventListener("mouseleave", () => clearHighlights());
    li.addEventListener("focus", () => highlightFromFacet(key));
    li.addEventListener("blur", () => clearHighlights());
    facetListEl.appendChild(li);
  });
  updateRatingFilterCounts();
}

function applyFacet(facet) {
  let token;
  if (facet.kind === "negative") {
    token = `uc:${facet.tag}`;
  } else if (facet.kind === "character") {
    token = `char:${facet.tag}`;
  } else {
    token = facet.tag;
  }
  applyToken(token, { skipSuggestions: true });
  clearHighlights();
}

function commitSearch(rawValue, { pushHistory = true } = {}) {
  const tokens = (rawValue || "")
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
  const normalized = tokens.join(", ");
  const nextQuery = normalized.trim();
  pendingDetailId = null;
  if (detailOverlay.classList.contains("active")) {
    closeDetail({ skipHistory: true });
  }
  if (searchBox.value !== normalized) {
    searchBox.value = normalized;
  }
  syncClearButton(searchBox, searchClearBtn);
  pendingScrollIndex = 0;
  scrollRestorePending = true;
  lastAnchorIndex = 0;
  requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: "auto" }));
  const sameQuery = nextQuery === lastQuery;
  lastQuery = nextQuery;
  syncRatingFiltersFromQuery();
  if (clipModeActive && lastClipPayload) {
    const payload = {
      ...lastClipPayload,
      tagQuery: nextQuery,
    };
    if (lastClipPayload.clipToken) {
      payload.clipToken = lastClipPayload.clipToken;
    }
    lastClipPayload = payload;
    const clipToken = getActiveClipToken();
    if (pushHistory) {
      pushHistoryState(
        { query: nextQuery, detail: null, pos: 0, clip: clipToken },
        { replace: sameQuery },
      );
    } else {
      pushHistoryState(
        { query: nextQuery, detail: null, pos: 0, clip: clipToken },
        { replace: true },
      );
    }
    runClipSearch(payload, { append: false, updateHistory: false });
    return;
  }
  if (sameQuery) {
    if (pushHistory) {
      pushHistoryState(
        { query: nextQuery, detail: null, pos: 0, clip: null },
        { replace: true },
      );
    }
    return;
  }
  if (pushHistory) {
    pushHistoryState({ query: nextQuery, detail: null, pos: 0, clip: null });
  } else {
    pushHistoryState(
      { query: nextQuery, detail: null, pos: 0, clip: null },
      { replace: true },
    );
  }
  fetchImages(true);
}

function applyToken(token, options = {}) {
  const { skipSuggestions = false } = options;
  const current = searchBox.value.trim();
  const tokens = current
    ? current
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean)
    : [];
  if (!tokens.includes(token)) {
    tokens.push(token);
    suggestionsEl.style.display = "none";
    suggestionItems = [];
    suggestionIndex = -1;
    commitSearch(tokens.join(", "));
    if (!skipSuggestions) {
      searchBox.focus();
    }
  }
}

searchBox.addEventListener("input", () => {
  syncClearButton(searchBox, searchClearBtn);
  maybeSuggest();
});

searchBox.addEventListener("focus", () => {
  syncClearButton(searchBox, searchClearBtn);
  maybeSuggest();
});

searchBox.addEventListener("blur", () => {
  setTimeout(() => {
    suggestionsEl.style.display = "none";
    suggestionItems = [];
    suggestionIndex = -1;
  }, 120);
});

if (searchClearBtn) {
  searchClearBtn.addEventListener("click", () => {
    suggestionsEl.style.display = "none";
    suggestionItems = [];
    suggestionIndex = -1;
    commitSearch("");
    searchBox.focus();
  });
}

if (ratingFilterMeta.length) {
  ratingFilterMeta.forEach(({ input }) => {
    input.addEventListener("change", () => {
      applyRatingFiltersToQuery();
    });
  });
}

searchBox.addEventListener("keydown", async (event) => {
  if (event.key === "ArrowDown") {
    event.preventDefault();
    if (suggestionsEl.style.display !== "block") {
      await maybeSuggest(true);
    }
    if (!suggestionItems.length) {
      suggestionItems = Array.from(suggestionsEl.querySelectorAll("li"));
      if (suggestionItems.length) {
        setActiveSuggestion(0);
        return;
      }
    }
    if (suggestionItems.length) {
      const next =
        suggestionIndex + 1 < suggestionItems.length ? suggestionIndex + 1 : 0;
      setActiveSuggestion(next);
    }
    return;
  }
  if (event.key === "ArrowUp") {
    event.preventDefault();
    if (suggestionsEl.style.display !== "block") {
      await maybeSuggest(true);
    }
    if (!suggestionItems.length) {
      suggestionItems = Array.from(suggestionsEl.querySelectorAll("li"));
      if (suggestionItems.length) {
        setActiveSuggestion(suggestionItems.length - 1);
        return;
      }
    }
    if (suggestionItems.length) {
      const prev =
        suggestionIndex > 0 ? suggestionIndex - 1 : suggestionItems.length - 1;
      setActiveSuggestion(prev);
    }
    return;
  }
  if (event.key === "Enter") {
    if (suggestionIndex >= 0 && suggestionItems[suggestionIndex]) {
      event.preventDefault();
      suggestionItems[suggestionIndex].click();
      return;
    }
    event.preventDefault();
    suggestionsEl.style.display = "none";
    suggestionItems = [];
    suggestionIndex = -1;
    commitSearch(searchBox.value);
  }
  if (event.key === "Escape") {
    suggestionsEl.style.display = "none";
    setActiveSuggestion(-1);
    suggestionItems = [];
    suggestionIndex = -1;
  }
});

const legacyClearBtn = document.getElementById("clear");
if (legacyClearBtn) {
  legacyClearBtn.addEventListener("click", () => {
    suggestionsEl.style.display = "none";
    suggestionItems = [];
    suggestionIndex = -1;
    commitSearch("");
  });
}

loadMoreBtn.addEventListener("click", () => {
  if (clipModeActive) {
    if (!searchState.loading && lastClipPayload) {
      runClipSearch(lastClipPayload, { append: true, updateHistory: false });
    }
  } else {
    fetchImages();
  }
});

if (clipSearchInput) {
  clipSearchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      if (!clipEnabled) return;
      const rawQuery = clipSearchInput.value;
      if (!rawQuery.trim() && lastClipPayload) {
        runClipSearch(lastClipPayload, { append: false });
      } else {
        runClipSearch({ query: rawQuery, tagQuery: searchBox.value.trim() });
      }
    }
  });
  clipSearchInput.addEventListener("input", () => {
    if (!clipEnabled) return;
    syncClearButton(clipSearchInput, clipSearchClear);
    if (clipSearchTimer) {
      clearTimeout(clipSearchTimer);
      clipSearchTimer = null;
    }
    const rawQuery = clipSearchInput.value;
    const trimmed = rawQuery.trim();
    if (!trimmed) {
      if (clipModeActive && !searchState.loading) {
        clipModeActive = false;
        lastClipPayload = null;
        currentClipToken = null;
        clipOffset = 0;
        clipTotal = 0;
        pushHistoryState(
          { query: lastQuery, detail: null, pos: 0, clip: null },
          { replace: true },
        );
        fetchImages(true);
      }
      return;
    }
    clipSearchTimer = setTimeout(() => {
      if (!searchState.loading) {
        runClipSearch({ query: rawQuery, tagQuery: searchBox.value.trim() });
      }
    }, CLIP_SEARCH_DEBOUNCE);
  });
  syncClearButton(clipSearchInput, clipSearchClear);
}
if (clipSearchClear) {
  clipSearchClear.addEventListener("click", () => {
    if (clipSearchInput) {
      clipSearchInput.value = "";
      syncClearButton(clipSearchInput, clipSearchClear);
    }
    if (clipModeActive && !searchState.loading) {
      if (detailOverlay.classList.contains("active")) {
        closeDetail({ skipHistory: true });
      }
      clipModeActive = false;
      lastClipPayload = null;
      currentClipToken = null;
      clipOffset = 0;
      clipTotal = 0;
      pushHistoryState({ query: lastQuery, detail: null, pos: 0, clip: null });
      fetchImages(true);
    } else {
      clipModeActive = false;
      lastClipPayload = null;
      currentClipToken = null;
      clipOffset = 0;
      clipTotal = 0;
      pushHistoryState({ clip: null }, { replace: true });
    }
    clipSearchInput?.focus();
  });
}

if (hideUCToggleBtn) {
  hideUCToggleBtn.addEventListener("click", () => {
    hideUCTags = !hideUCTags;
    hideUCToggleBtn.setAttribute("aria-pressed", hideUCTags ? "true" : "false");
    hideUCToggleBtn.textContent = hideUCTags ? "UC Hidden" : "UC Visible";
    renderFacets(facetCache);
    if (detailNegSection) {
      if (hideUCTags) {
        detailNegSection.style.display = "none";
      } else if (detailNegTags.children.length) {
        detailNegSection.style.display = "";
      }
    }
  });
  hideUCToggleBtn.textContent = hideUCTags ? "UC Hidden" : "UC Visible";
  hideUCToggleBtn.setAttribute("aria-pressed", hideUCTags ? "true" : "false");
}

facetListEl.addEventListener("mouseleave", () => clearHighlights());
gridEl.addEventListener("mouseleave", () => clearHighlights());

copyPositiveBtn.addEventListener("click", () => {
  if (!copyPositiveBtn.disabled) {
    copyText(currentPrompts.positive);
  }
});

copyNegativeBtn.addEventListener("click", () => {
  if (!copyNegativeBtn.disabled) {
    copyText(currentPrompts.negative);
  }
});

function isFileDrag(event) {
  const dt = event.dataTransfer;
  if (!dt) return false;
  return Array.from(dt.types || []).includes("Files");
}

window.addEventListener("dragenter", (event) => {
  if (!isFileDrag(event)) return;
  event.preventDefault();
  dragCounter += 1;
  if (dropOverlay) dropOverlay.classList.add("active");
});

window.addEventListener("dragover", (event) => {
  if (!isFileDrag(event)) return;
  event.preventDefault();
  event.dataTransfer.dropEffect = "copy";
  if (dropOverlay && !dropOverlay.classList.contains("active")) {
    dropOverlay.classList.add("active");
  }
});

window.addEventListener("dragleave", (event) => {
  if (!isFileDrag(event)) return;
  event.preventDefault();
  dragCounter = Math.max(0, dragCounter - 1);
  if (dragCounter === 0 && dropOverlay) {
    dropOverlay.classList.remove("active");
  }
});

window.addEventListener("drop", (event) => {
  if (!isFileDrag(event)) return;
  event.preventDefault();
  dragCounter = 0;
  if (dropOverlay) dropOverlay.classList.remove("active");
  const files = event.dataTransfer
    ? Array.from(event.dataTransfer.files || [])
    : [];
  if (!files.length) return;
  startClipUploadSearch(files[0]);
});

gridEl.addEventListener("click", (event) => {
  const card = event.target.closest(".card");
  if (!card) return;
  const id = Number(card.dataset.id);
  if (!Number.isFinite(id)) return;
  openDetail(id);
});

if (detailSimilarBtn) {
  detailSimilarBtn.addEventListener("click", () => {
    const imageId = Number(currentDetailId);
    if (!Number.isFinite(imageId)) return;
    if (!clipEnabled) return;
    const tagFilter = searchBox.value.trim();
    closeDetail({ skipHistory: true });
    runClipSearch({
      positiveImages: [imageId],
      tagQuery: tagFilter,
      updateInput: `image:${imageId}`,
    });
  });
}

detailCloseBtn.addEventListener("click", () => closeDetail());

detailOverlay.addEventListener("click", (event) => {
  if (event.target === detailOverlay) {
    closeDetail();
  }
});

detailPrevBtn.addEventListener("click", () => showSibling(-1));
detailNextBtn.addEventListener("click", () => showSibling(1));
detailImage.addEventListener("click", () => {
  if (!detailImage.src) return;
  window.open(detailImage.src, "_blank", "noopener");
});

window.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if (detailOverlay.classList.contains("active")) {
      closeDetail();
      event.preventDefault();
      return;
    }
    if (desktopMediaQuery.matches) {
      if (statusCardVisible) {
        statusCardVisible = false;
        applySidebarState();
        event.preventDefault();
        return;
      }
    } else if (sidebarVisible) {
      sidebarVisible = false;
      applySidebarState();
      event.preventDefault();
      return;
    }
  }
  if (!detailOverlay.classList.contains("active")) return;
  if (event.key === "ArrowLeft") {
    showSibling(-1);
  } else if (event.key === "ArrowRight") {
    showSibling(1);
  }
});

window.addEventListener("scroll", () => {
  scheduleScrollSave();
});

async function maybeSuggest(selectFirst = false) {
  const value = searchBox.value;
  const atComma = value.lastIndexOf(",");
  const prefix = atComma >= 0 ? value.slice(atComma + 1).trim() : value.trim();
  const base = atComma >= 0 ? value.slice(0, atComma + 1).trim() : "";
  const leadingNegMatch = prefix.match(/^[!-]+/);
  const leadingNegation = leadingNegMatch ? leadingNegMatch[0] : "";
  let remainder = prefix.slice(leadingNegation.length).trimStart();
  let kind = "";
  let kindPrefix = "";
  const lowered = remainder.toLowerCase();
  if (lowered.startsWith("uc:")) {
    kind = "negative";
    kindPrefix = "uc:";
    remainder = remainder.slice(3).trimStart();
  } else if (lowered.startsWith("char:")) {
    kind = "character";
    kindPrefix = "char:";
    remainder = remainder.slice(5).trimStart();
  } else if (lowered.startsWith("character:")) {
    kind = "character";
    kindPrefix = "char:";
    remainder = remainder.slice(10).trimStart();
  } else if (lowered.startsWith("prompt:")) {
    kind = "prompt";
    kindPrefix = "prompt:";
    remainder = remainder.slice(7).trimStart();
  }
  const innerNegMatch = remainder.match(/^[!-]+/);
  const innerNegation = innerNegMatch ? innerNegMatch[0] : "";
  remainder = remainder.slice(innerNegation.length).trimStart();
  const allowEmptyLookup = Boolean(kindPrefix);
  const lookupLength =
    leadingNegation.length + innerNegation.length + remainder.length;
  if (!allowEmptyLookup && (lookupLength < 2 || remainder.length === 0)) {
    suggestionsEl.style.display = "none";
    suggestionItems = [];
    suggestionIndex = -1;
    return;
  }
  let lookup = remainder;
  const res = await fetch(
    `/api/tags?q=${encodeURIComponent(lookup)}&kind=${kind}`,
  );
  if (!res.ok) {
    suggestionsEl.style.display = "none";
    suggestionItems = [];
    suggestionIndex = -1;
    return;
  }
  const data = await res.json();
  if (!Array.isArray(data.tags) || data.tags.length === 0) {
    suggestionsEl.style.display = "none";
    suggestionItems = [];
    suggestionIndex = -1;
    return;
  }
  suggestionsEl.innerHTML = "";
  suggestionItems = [];
  suggestionIndex = -1;
  data.tags.forEach((tag, idx) => {
    const li = document.createElement("li");
    li.innerHTML = `<span>${tag.tag}</span><span class="kind">${tag.kind} • ${tag.freq}</span>`;
    li.addEventListener("click", () => {
      let prefixPart = kindPrefix;
      if (!prefixPart) {
        if (tag.kind === "negative") {
          prefixPart = "uc:";
        } else if (tag.kind === "character") {
          prefixPart = "char:";
        } else {
          prefixPart = "";
        }
      }
      const decorated = `${leadingNegation}${prefixPart}${innerNegation}${tag.tag}`;
      const newValue = base ? `${base} ${decorated}`.trim() : decorated;
      suggestionsEl.style.display = "none";
      suggestionItems = [];
      suggestionIndex = -1;
      commitSearch(newValue);
      searchBox.focus();
    });
    li.addEventListener("mouseenter", () => setActiveSuggestion(idx));
    li.addEventListener("mouseleave", () => setActiveSuggestion(-1));
    suggestionsEl.appendChild(li);
    suggestionItems.push(li);
  });
  const rect = searchBox.getBoundingClientRect();
  suggestionsEl.style.left = `${rect.left + window.scrollX}px`;
  suggestionsEl.style.top = `${rect.bottom + window.scrollY}px`;
  suggestionsEl.style.display = "block";
  setActiveSuggestion(selectFirst && suggestionItems.length ? 0 : -1);
}

async function openDetail(id, options = {}) {
  const detailId = Number(id);
  if (!Number.isFinite(detailId)) {
    return;
  }
  const { pushState = true, replaceState = false } = options;
  const clipTokenForHistory = getActiveClipToken();
  if (
    detailOverlay.classList.contains("active") &&
    currentDetailId === detailId
  ) {
    if (pushState) {
      pushHistoryState(
        { query: lastQuery, detail: detailId, clip: clipTokenForHistory },
        { replace: true },
      );
    } else if (replaceState) {
      pushHistoryState(
        { query: lastQuery, detail: detailId, clip: clipTokenForHistory },
        { replace: true },
      );
    }
    return;
  }
  pendingDetailId = null;
  try {
    const res = await fetch(`/api/images/${detailId}`);
    if (!res.ok) throw new Error("Failed to load image");
    const data = await res.json();
    const item = data.image;
    currentPrompts = data.prompts || { positive: "", negative: "" };
    copyPositiveBtn.disabled = !currentPrompts.positive;
    copyNegativeBtn.disabled = !currentPrompts.negative;
    const hasPositive = !!(
      currentPrompts.positive && currentPrompts.positive.trim()
    );
    const hasNegative = !!(
      currentPrompts.negative && currentPrompts.negative.trim()
    );
    detailPromptsSection.style.display =
      hasPositive || hasNegative ? "block" : "none";
    positiveBlock.style.display = hasPositive ? "block" : "none";
    negativeBlock.style.display = hasNegative ? "block" : "none";
    copyPositiveBtn.disabled = !hasPositive;
    copyNegativeBtn.disabled = !hasNegative;
    positivePreview.textContent = hasPositive ? currentPrompts.positive : "—";
    negativePreview.textContent = hasNegative ? currentPrompts.negative : "—";
    const fallbackLabel = getFallbackLabel(item);
    const displayModel = item.model || fallbackLabel;
    const displaySeed = item.seed || fallbackLabel;
    const titleParts = [];
    if (item.model) titleParts.push(item.model);
    if (item.seed) titleParts.push(`Seed ${item.seed}`);
    if (!titleParts.length) {
      titleParts.push(fallbackLabel);
    }
    detailTitle.textContent = titleParts.join(" • ");
    detailImage.src = item.file_url;
    detailImage.alt = fallbackLabel;
    detailImage.parentElement.style.removeProperty("--image-aspect");
    detailImage.parentElement.style.removeProperty("aspect-ratio");
    detailImage.style.removeProperty("aspect-ratio");
    let infoFields = [];
    if (item.model) infoFields.push({ label: "Model", value: item.model });
    if (item.seed) infoFields.push({ label: "Seed", value: item.seed });
    infoFields.push(
      {
        label: "Dimensions",
        value: `${Number.isFinite(item.width) ? item.width : "–"}×${Number.isFinite(item.height) ? item.height : "–"}`,
      },
      { label: "File Size", value: formatFileSize(item.size) },
    );
    const statusChipsHtml = buildStatusChips(data.processing || null);
    detailInfo.innerHTML = `
            <div class="info-card">
                <div class="info-fields">
                    ${infoFields
                      .map(
                        (field) =>
                          `<div class="info-chip"><span>${escapeHtml(field.label)}</span><strong>${escapeHtml(field.value)}</strong></div>`,
                      )
                      .join("")}
                </div>
                ${statusChipsHtml ? `<div class="status-chips">${statusChipsHtml}</div>` : ""}
              </div>
            `;
    const tagList = Array.isArray(data.tags) ? data.tags : [];
    updateDetailRating(data.rating || null);
    renderDetailTags(tagList);
    renderCharacterDetails(data.characters || []);
    updateCopyButtons({
      positivePrompt: currentPrompts.positive,
      tags: tagList,
    });
    currentDetailId = detailId;
    if (detailSimilarBtn) {
      detailSimilarBtn.disabled = !clipEnabled;
      detailSimilarBtn.dataset.id = String(detailId);
    }
    currentDetailIndex = searchState.index.has(detailId)
      ? searchState.index.get(detailId)
      : -1;
    updateDetailControls();
    detailOverlay.classList.add("active");
    detailOverlay.setAttribute("aria-hidden", "false");
    const anchorIndexForHistory =
      scrollRestorePending && pendingScrollIndex !== null
        ? pendingScrollIndex
        : getAnchorIndex();
    if (pushState) {
      pushHistoryState({
        query: lastQuery,
        detail: detailId,
        pos: anchorIndexForHistory,
        clip: clipTokenForHistory,
      });
    } else if (replaceState) {
      pushHistoryState(
        {
          query: lastQuery,
          detail: detailId,
          pos: anchorIndexForHistory,
          clip: clipTokenForHistory,
        },
        { replace: true },
      );
    }
  } catch (err) {
    console.error(err);
  }
}

function updateDetailRating(ratingData) {
  if (!detailRatingSection || !detailRatingLabel) {
    return;
  }
  const scoreMapRaw =
    ratingData && typeof ratingData === "object" && ratingData.scores
      ? ratingData.scores
      : null;
  const scoreMap = {};
  if (scoreMapRaw && typeof scoreMapRaw === "object") {
    Object.entries(scoreMapRaw).forEach(([key, value]) => {
      const normKey = String(key).toLowerCase();
      const numeric = Number(value);
      if (Number.isFinite(numeric)) {
        scoreMap[normKey] = Math.max(0, Math.min(1, numeric));
      }
    });
  }

  let value =
    ratingData && typeof ratingData.value === "string"
      ? ratingData.value
      : "";
  let confidence =
    ratingData && typeof ratingData.confidence === "number"
      ? ratingData.confidence
      : null;

  if ((!value || !value.trim()) && Object.keys(scoreMap).length) {
    const best = RATING_CLASSES.map((key) => ({
      key,
      score: scoreMap[key] ?? -1,
    })).reduce((prev, current) => (current.score > prev.score ? current : prev), {
      key: "",
      score: -1,
    });
    if (best.key) {
      value = best.key;
      confidence = best.score;
    }
  }

  if (!value) {
    detailRatingSection.style.display = "none";
    detailRatingLabel.textContent = "";
    detailRatingLabel.className = "rating-label";
    detailRatingLabel.removeAttribute("title");
    if (ratingBarsContainer) {
      ratingBarsContainer.style.display = "none";
      ratingBarsContainer.innerHTML = "";
    }
    return;
  }

  const normalized = value.toLowerCase();
  const displayName = RATING_DISPLAY_NAMES[normalized] || value;
  detailRatingSection.style.display = "flex";
  detailRatingLabel.textContent = displayName;
  detailRatingLabel.className = "rating-label";
  detailRatingLabel.classList.add(`rating-${normalized}`);

  if (typeof confidence === "number" && Number.isFinite(confidence)) {
    const pct = Math.round(confidence * 1000) / 10;
    detailRatingLabel.title = `Confidence ${pct.toFixed(1)}%`;
    detailRatingLabel.textContent = `${displayName} (${pct.toFixed(1)}%)`;
  } else {
    detailRatingLabel.removeAttribute("title");
  }

  if (ratingBarsContainer) {
    const rows = RATING_CLASSES.map((key) => {
      const score = scoreMap[key] ?? 0;
      return { key, score };
    });
    if (rows.some((row) => row.score > 0)) {
      ratingBarsContainer.style.display = "flex";
      ratingBarsContainer.innerHTML = "";
      rows.forEach(({ key, score }) => {
        const rowEl = document.createElement("div");
        rowEl.className = "rating-bar";

        const labelEl = document.createElement("span");
        labelEl.className = "rating-bar-label";
        labelEl.textContent = RATING_DISPLAY_NAMES[key] || key;

        const trackEl = document.createElement("div");
        trackEl.className = "rating-bar-track";

        const fillEl = document.createElement("div");
        fillEl.className = "rating-bar-fill";
        const width = Math.max(0, Math.min(100, Math.round(score * 100)));
        fillEl.style.width = `${width}%`;

        const scoreEl = document.createElement("span");
        scoreEl.className = "rating-bar-score";
        scoreEl.textContent = `${width}%`;

        trackEl.appendChild(fillEl);
        rowEl.appendChild(labelEl);
        rowEl.appendChild(trackEl);
        rowEl.appendChild(scoreEl);
        ratingBarsContainer.appendChild(rowEl);
      });
    } else {
      ratingBarsContainer.style.display = "none";
      ratingBarsContainer.innerHTML = "";
    }
  }
}

function renderDetailTags(tags) {
  detailTags.innerHTML = "";
  detailNegTags.innerHTML = "";
  let hasNeg = false;
  tags.forEach((tag) => {
    const span = document.createElement("span");
    span.className = "tag-pill";
    span.dataset.kind = tag.kind;
    span.dataset.emphasis = tag.emphasis;
    const source =
      typeof tag.source === "string" && tag.source ? tag.source : "embedded";
    span.dataset.source = source;
    if (Number.isFinite(tag.weight)) {
      span.dataset.weight = Number(tag.weight).toFixed(1);
    } else {
      span.dataset.weight = "";
    }
    const label = tag.count ? `${tag.tag} (${tag.count})` : tag.tag;
    span.textContent = label;
    if (source === "auto") {
      span.title = "Auto-generated tag";
    } else {
      span.title = "Embedded tag";
    }
    span.addEventListener("click", () => {
      let token;
      if (tag.kind === "negative") {
        token = `uc:${tag.tag}`;
      } else if (tag.kind === "character") {
        token = `char:${tag.tag}`;
      } else {
        token = tag.tag;
      }
      applyToken(token, { skipSuggestions: true });
    });
    if (tag.kind === "negative") {
      hasNeg = true;
      detailNegTags.appendChild(span);
    } else if (tag.kind === "character") {
      // render via character section
      return;
    } else if (tag.kind === "rating") {
      return;
    } else {
      detailTags.appendChild(span);
    }
  });
  detailNegSection.style.display = hasNeg && !hideUCTags ? "" : "none";
}

function renderCharacterDetails(characters) {
  clearHotspots();
  detailCharacters.innerHTML = "";
  if (!Array.isArray(characters) || characters.length === 0) {
    detailCharSection.style.display = "none";
    return;
  }
  detailCharSection.style.display = "";
  characters.forEach((char, idx) => {
    const block = document.createElement("div");
    block.className = "char-block";
    block.tabIndex = 0;
    const centers = (char.centers || []).map((center) => ({
      x:
        typeof center?.x === "number"
          ? center.x
          : Array.isArray(center)
            ? center[0]
            : 0.5,
      y:
        typeof center?.y === "number"
          ? center.y
          : Array.isArray(center)
            ? center[1]
            : 0.5,
    }));
    const locLabel = centers.length
      ? centers
          .map(
            (c) =>
              `${Math.round((c.x ?? 0.5) * 100)}% × ${Math.round((c.y ?? 0.5) * 100)}%`,
          )
          .join(" · ")
      : "Location unknown";
    const metaRow = document.createElement("div");
    metaRow.className = "char-meta";
    const locSpan = document.createElement("span");
    locSpan.className = "char-loc";
    locSpan.textContent = locLabel;
    const copyBtn = document.createElement("button");
    copyBtn.className = "copy-btn";
    copyBtn.innerHTML = `<span class="sr-only">Copy character ${idx + 1} prompt</span>📋`;
    copyBtn.disabled = !char.caption;
    copyBtn.setAttribute("title", "Copy character prompt");
    copyBtn.setAttribute("aria-label", `Copy character ${idx + 1} prompt`);
    copyBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      copyText(char.caption || "");
    });
    metaRow.appendChild(locSpan);
    metaRow.appendChild(copyBtn);
    block.appendChild(metaRow);

    const wrap = document.createElement("div");
    wrap.className = "tag-pills";
    (char.tags || []).forEach((tag) => {
      const span = document.createElement("span");
      span.className = "tag-pill";
      span.dataset.kind = tag.kind || "character";
      span.dataset.emphasis = tag.emphasis || "normal";
      const source =
        typeof tag.source === "string" && tag.source ? tag.source : "embedded";
      span.dataset.source = source;
      const weight = typeof tag.weight === "number" ? tag.weight : 1;
      span.dataset.weight = weight.toFixed(1);
      const label = tag.count ? `${tag.tag} (${tag.count})` : tag.tag;
      span.textContent = label;
      if (source === "auto") {
        span.title = "Auto-generated tag";
      } else {
        span.title = "Embedded tag";
      }
      span.addEventListener("click", () => {
        const token =
          tag.kind === "negative" ? `uc:${tag.tag}` : `char:${tag.tag}`;
        applyToken(token, { skipSuggestions: true });
      });
      wrap.appendChild(span);
    });
    block.appendChild(wrap);

    block.addEventListener("mouseenter", () => showHotspots(centers));
    block.addEventListener("mouseleave", () => clearHotspots());
    block.addEventListener("focus", () => showHotspots(centers));
    block.addEventListener("blur", () => clearHotspots());

    detailCharacters.appendChild(block);
  });
}

function clearHotspots() {
  currentHotspotCenters = null;
  currentHotspotDots = [];
  detailHotspots.innerHTML = "";
}

function showHotspots(centers) {
  if (!Array.isArray(centers) || centers.length === 0) {
    clearHotspots();
    return;
  }
  currentHotspotCenters = centers;
  detailHotspots.innerHTML = "";
  currentHotspotDots = centers.map(() => {
    const dot = document.createElement("div");
    dot.className = "hotspot-dot visible";
    detailHotspots.appendChild(dot);
    return dot;
  });
  positionHotspots();
  requestAnimationFrame(() => positionHotspots());
}

function positionHotspots() {
  if (!currentHotspotCenters || currentHotspotCenters.length === 0) {
    return;
  }
  const overlayRect = detailHotspots.getBoundingClientRect();
  const imageRect = detailImage.getBoundingClientRect();
  if (
    !overlayRect.width ||
    !overlayRect.height ||
    !imageRect.width ||
    !imageRect.height
  ) {
    return;
  }
  const offsetX = imageRect.left - overlayRect.left;
  const offsetY = imageRect.top - overlayRect.top;
  const displayedWidth = imageRect.width;
  const displayedHeight = imageRect.height;
  currentHotspotCenters.forEach((center, idx) => {
    const dot = currentHotspotDots[idx];
    if (!dot) return;
    const xNorm = Math.min(Math.max(center?.x ?? 0.5, 0), 1);
    const yNorm = Math.min(Math.max(center?.y ?? 0.5, 0), 1);
    const xPx = offsetX + xNorm * displayedWidth;
    const yPx = offsetY + yNorm * displayedHeight;
    dot.style.left = `${xPx}px`;
    dot.style.top = `${yPx}px`;
  });
}

async function showSibling(delta) {
  if (currentDetailIndex === -1) return;
  let targetIndex = currentDetailIndex + delta;
  if (targetIndex >= searchState.images.length && !searchState.done) {
    await fetchImages();
  }
  targetIndex = Math.min(
    Math.max(0, targetIndex),
    searchState.images.length - 1,
  );
  if (targetIndex === currentDetailIndex) return;
  const target = searchState.images[targetIndex];
  if (target) {
    await openDetail(target.id);
  }
}

function updateDetailControls() {
  detailPrevBtn.disabled = currentDetailIndex <= 0;
  detailNextBtn.disabled =
    currentDetailIndex < 0 ||
    (currentDetailIndex >= searchState.total - 1 && searchState.done);
  detailCounter.textContent =
    currentDetailIndex >= 0
      ? `${currentDetailIndex + 1} / ${searchState.total}`
      : "";
}

function closeDetail({ skipHistory = false } = {}) {
  pendingDetailId = null;
  if (!detailOverlay.classList.contains("active")) {
    return;
  }
  detailOverlay.classList.remove("active");
  detailOverlay.setAttribute("aria-hidden", "true");
  if (detailSimilarBtn) {
    detailSimilarBtn.disabled = true;
    detailSimilarBtn.dataset.id = "";
  }
  currentDetailId = null;
  currentDetailIndex = -1;
  clearHotspots();
  currentPrompts = { positive: "", negative: "" };
  copyPositiveBtn.disabled = true;
  copyNegativeBtn.disabled = true;
  detailPromptsSection.style.display = "none";
  positiveBlock.style.display = "none";
  negativeBlock.style.display = "none";
  positivePreview.textContent = "";
  negativePreview.textContent = "";
  updateDetailRating(null);
  const imageContainer = detailImage.parentElement;
  if (imageContainer) {
    imageContainer.style.removeProperty("--image-aspect");
    imageContainer.style.removeProperty("aspect-ratio");
  }
  detailImage.style.removeProperty("aspect-ratio");
  updateCopyButtons({ positivePrompt: "", tags: [] });
  if (!skipHistory) {
    const anchorIndexForHistory =
      scrollRestorePending && pendingScrollIndex !== null
        ? pendingScrollIndex
        : getAnchorIndex();
    const clipTokenForHistory = getActiveClipToken();
    pushHistoryState({
      query: lastQuery,
      detail: null,
      pos: anchorIndexForHistory,
      clip: clipTokenForHistory,
    });
  }
}

function handleHistoryState(state) {
  const safeState = state || { query: "", detail: null, pos: 0, clip: null };
  const nextQuery = (safeState.query || "").trim();
  const nextDetail = normalizeDetail(safeState.detail);
  const nextPos = normalizeIndex(safeState.pos);
  const nextClipToken =
    typeof safeState.clip === "string" && safeState.clip
      ? safeState.clip
      : null;
  const normalizedCurrentClip = currentClipToken || null;
  const clipChanged = nextClipToken !== normalizedCurrentClip;
  const queryChanged = nextQuery !== lastQuery;
  const wasClipModeActive = clipModeActive;
  const targetDetail = nextDetail;

  currentHistoryState = {
    query: nextQuery,
    detail: nextDetail,
    pos: nextPos ?? 0,
    clip: nextClipToken,
  };

  if (searchBox.value !== nextQuery) {
    searchBox.value = nextQuery;
  }
  syncClearButton(searchBox, searchClearBtn);
  syncRatingFiltersFromQuery();

  pendingDetailId = targetDetail;
  pendingScrollIndex = nextPos !== null ? nextPos : 0;
  lastAnchorIndex = pendingScrollIndex;
  scrollRestorePending = true;

  if (nextClipToken) {
    const clipPayload = buildClipPayloadFromToken(nextClipToken, nextQuery);
    if (!clipPayload) {
      clipModeActive = false;
      lastClipPayload = null;
      currentClipToken = null;
      clipOffset = 0;
      clipTotal = 0;
      if (clipSearchInput) clipSearchInput.value = "";
      syncClearButton(clipSearchInput, clipSearchClear);
      pushHistoryState({ clip: null }, { replace: true });
    } else {
      const wasClipMode = clipModeActive;
      clipModeActive = true;
      currentClipToken = nextClipToken;
      lastQuery = nextQuery;
      if (clipSearchInput) {
        clipSearchInput.value = clipPayload.updateInput || "";
        syncClearButton(clipSearchInput, clipSearchClear);
      }

      if (targetDetail === null && detailOverlay.classList.contains("active")) {
        closeDetail({ skipHistory: true });
        pendingDetailId = targetDetail;
      }

      const needFreshFetch =
        clipChanged ||
        queryChanged ||
        !wasClipMode ||
        !searchState.images.length;
      if (needFreshFetch) {
        if (detailOverlay.classList.contains("active")) {
          closeDetail({ skipHistory: true });
        }
        pendingDetailId = targetDetail;
        runClipSearch(clipPayload, { append: false, updateHistory: false });
        return;
      }

      if (targetDetail !== null) {
        if (
          !detailOverlay.classList.contains("active") ||
          currentDetailId !== targetDetail
        ) {
          pendingDetailId = targetDetail;
          maybeOpenPendingDetail();
        }
      }

      if (!searchState.images.length && !searchState.loading) {
        runClipSearch(clipPayload, { append: false, updateHistory: false });
        return;
      }

      if (scrollRestorePending) {
        if (
          pendingScrollIndex !== null &&
          pendingScrollIndex >= searchState.images.length &&
          !searchState.done &&
          !searchState.loading
        ) {
          const payloadForAppend = lastClipPayload || clipPayload;
          runClipSearch(payloadForAppend, {
            append: !!lastClipPayload,
            updateHistory: false,
          });
          return;
        }
        maybeRestoreScrollPosition();
      }
      return;
    }
  } else if (clipModeActive || currentClipToken) {
    clipModeActive = false;
    lastClipPayload = null;
    currentClipToken = null;
    clipOffset = 0;
    clipTotal = 0;
    if (clipSearchInput) clipSearchInput.value = "";
    syncClearButton(clipSearchInput, clipSearchClear);
  }

  if (targetDetail === null && detailOverlay.classList.contains("active")) {
    closeDetail({ skipHistory: true });
    pendingDetailId = targetDetail;
  }

  if (queryChanged || wasClipModeActive) {
    lastQuery = nextQuery;
    fetchImages(true);
    return;
  }

  if (!searchState.images.length && !searchState.loading) {
    fetchImages(true);
    return;
  }

  if (targetDetail !== null) {
    if (
      !detailOverlay.classList.contains("active") ||
      currentDetailId !== targetDetail
    ) {
      pendingDetailId = targetDetail;
      maybeOpenPendingDetail();
    }
  }

  if (scrollRestorePending) {
    if (
      pendingScrollIndex !== null &&
      pendingScrollIndex >= searchState.images.length &&
      !searchState.done &&
      !searchState.loading
    ) {
      fetchImages();
    } else {
      maybeRestoreScrollPosition();
    }
  }
}

const initialState = parseStateFromLocation();
const normalizedInitialState = {
  query: (initialState.query || "").trim(),
  detail: normalizeDetail(initialState.detail),
  pos: normalizeIndex(initialState.pos) ?? 0,
  clip:
    typeof initialState.clip === "string" && initialState.clip
      ? initialState.clip
      : null,
};
lastQuery = normalizedInitialState.query;
if (searchBox.value !== lastQuery) {
  searchBox.value = lastQuery;
}
syncClearButton(searchBox, searchClearBtn);
syncClearButton(clipSearchInput, clipSearchClear);
syncRatingFiltersFromQuery();
pendingDetailId = normalizedInitialState.detail;
pendingScrollIndex = normalizedInitialState.pos;
scrollRestorePending = pendingScrollIndex > 0;
lastAnchorIndex = pendingScrollIndex;
currentHistoryState = { ...normalizedInitialState };
pushHistoryState(normalizedInitialState, { replace: true });
handleHistoryState({ ...normalizedInitialState });

window.addEventListener("popstate", (event) => {
  handleHistoryState(event.state || parseStateFromLocation());
});

if ("IntersectionObserver" in window) {
  autoObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          if (clipModeActive) {
            if (!searchState.loading && !searchState.done && lastClipPayload) {
              runClipSearch(lastClipPayload, {
                append: true,
                updateHistory: false,
              });
            }
          } else {
            fetchImages();
          }
        }
      });
    },
    { rootMargin: "600px 0px" },
  );
  autoObserver.observe(sentinel);
} else {
  loadMoreBtn.style.display = "block";
}

detailImage.addEventListener("load", () => positionHotspots());
window.addEventListener("resize", () => positionHotspots());
async function pollClipStatus() {
  if (!clipSummary) return;
  try {
    const res = await fetch("/api/status/clip");
    if (!res.ok) throw new Error(`status ${res.status}`);
    const data = await res.json();
    const enabled = data.enabled !== false;
    clipEnabled = enabled;
    if (!enabled) {
      clipStatusSection?.classList.remove("status-error");
      clipStatusSection?.classList.add("status-disabled");
      clipSummary.textContent = "CLIP disabled";
      clipProgressBar.style.width = "0%";
      clipProgressBar.dataset.label = "0%";
      if (clipToggleBtn) {
        clipToggleBtn.hidden = true;
        clipToggleBtn.dataset.state = "paused";
      }
      if (clipSearchInput) clipSearchInput.disabled = true;
      if (clipSearchClear) clipSearchClear.disabled = true;
      syncClearButton(clipSearchInput, clipSearchClear);
      if (detailSimilarBtn) {
        detailSimilarBtn.disabled = true;
        detailSimilarBtn.dataset.id = "";
      }
      dismissToast("clip-error");
      requestAnimationFrame(updateStatusCardHeight);
      return;
    }

    clipStatusSection?.classList.remove("status-disabled");
    if (clipSearchInput) clipSearchInput.disabled = false;
    if (clipSearchClear && !searchState.loading)
      clipSearchClear.disabled = false;
    syncClearButton(clipSearchInput, clipSearchClear);
    if (detailSimilarBtn && Number.isFinite(currentDetailId))
      detailSimilarBtn.disabled = false;

    const total = Number(data.total) || 0;
    const completed = Number(data.completed) || 0;
    const processing = Number(data.processing) || 0;
    const queued =
      Number(data.queued) || Math.max(total - completed - processing, 0);
    const percent = total ? Math.round((completed / total) * 100) : 0;
    clipProgressBar.style.width = `${percent}%`;
    clipProgressBar.dataset.label = `${percent}%`;
    const stateLabel = typeof data.state === "string" ? data.state : "idle";
    clipSummary.textContent = `State: ${stateLabel} • ${completed}/${total} done • ${processing} processing • ${queued} queued`;
    if (clipToggleBtn) {
      clipToggleBtn.hidden = !total;
      clipToggleBtn.textContent = stateLabel === "paused" ? "Resume" : "Pause";
      clipToggleBtn.dataset.state = stateLabel;
    }

    const errors = Array.isArray(data.error_sample) ? data.error_sample : [];
    if (errors.length) {
      const latest = String(errors[errors.length - 1]);
      const fingerprint = toastFingerprint("CLIP indexer issue", latest);
      if (isToastSuppressed("clip-error", fingerprint)) {
        clipStatusSection?.classList.remove("status-error");
      } else {
        clipStatusSection?.classList.add("status-error");
        showToast("clip-error", {
          title: "CLIP indexer issue",
          body: latest,
          variant: "error",
          onDismiss: () => clipStatusSection?.classList.remove("status-error"),
        });
      }
    } else {
      clipStatusSection?.classList.remove("status-error");
      dismissToast("clip-error");
      requestAnimationFrame(updateStatusCardHeight);
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    clipSummary.textContent = "CLIP status unavailable";
    clipStatusSection?.classList.remove("status-disabled");
    clipStatusSection?.classList.add("status-error");
    showToast("clip-error", {
      title: "CLIP status unavailable",
      body: message,
      variant: "error",
      onDismiss: () => clipStatusSection?.classList.remove("status-error"),
    });
    requestAnimationFrame(updateStatusCardHeight);
  }
}

async function pollAutoStatus() {
  if (!autoStatusSection || !autoSummary || !autoErrorsList) return;
  try {
    const res = await fetch("/api/status/auto");
    autoStatusSection.hidden = false;
    if (res.status === 404) {
      autoStatusSection.classList.add("status-disabled");
      autoStatusSection.classList.remove("status-error");
      autoSummary.textContent = "Auto-tag status unavailable";
      autoErrorsList.innerHTML = "";
      if (autoProgressBar) {
        autoProgressBar.style.width = "0%";
        autoProgressBar.dataset.label = "0%";
      }
      dismissToast("auto-error");
      requestAnimationFrame(updateStatusCardHeight);
      return;
    }
    if (!res.ok) throw new Error(`status ${res.status}`);
    const data = await res.json();
    const enabled = data.enabled !== false;
    const stateLabel = typeof data.state === "string" ? data.state : "idle";
    const total = Number(data.total) || 0;
    const completed = Number(data.completed) || 0;
    const processing = Number(data.processing) || 0;
    const queued =
      Number(data.queued) || Math.max(total - completed - processing, 0);
    const errors = Array.isArray(data.error_sample) ? data.error_sample : [];

    if (!enabled) {
      autoStatusSection.classList.add("status-disabled");
      autoStatusSection.classList.remove("status-error");
      autoSummary.textContent = "Auto-tagging disabled";
      autoErrorsList.innerHTML = "";
      if (autoProgressBar) {
        autoProgressBar.style.width = "0%";
        autoProgressBar.dataset.label = "0%";
      }
      dismissToast("auto-error");
      requestAnimationFrame(updateStatusCardHeight);
      return;
    }

    autoStatusSection.classList.remove("status-disabled");

    autoSummary.textContent = `State: ${stateLabel} • ${completed}/${total} done • ${processing} processing • ${queued} queued`;
    if (autoProgressBar) {
      const autoPercent = total ? Math.round((completed / total) * 100) : 0;
      autoProgressBar.style.width = `${Math.max(0, Math.min(100, autoPercent))}%`;
      autoProgressBar.dataset.label = `${autoPercent}%`;
    }
    autoErrorsList.innerHTML = "";
    if (errors.length) {
      errors.slice(-3).forEach((errMsg) => {
        const li = document.createElement("li");
        li.textContent = String(errMsg);
        autoErrorsList.appendChild(li);
      });
      const latestAuto = String(errors[errors.length - 1]);
      const autoFingerprint = toastFingerprint(
        "Auto tagger issues",
        latestAuto,
      );
      if (isToastSuppressed("auto-error", autoFingerprint)) {
        autoStatusSection.classList.remove("status-error");
      } else {
        autoStatusSection.classList.add("status-error");
        showToast("auto-error", {
          title: "Auto tagger issues",
          body: latestAuto,
          variant: "error",
          onDismiss: () => autoStatusSection.classList.remove("status-error"),
        });
      }
    } else {
      autoStatusSection.classList.remove("status-error");
      dismissToast("auto-error");
    }
    requestAnimationFrame(updateStatusCardHeight);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    autoStatusSection.classList.add("status-error");
    autoStatusSection.classList.remove("status-disabled");
    autoSummary.textContent = "Auto-tag status unavailable";
    if (autoProgressBar) {
      autoProgressBar.style.width = "0%";
      autoProgressBar.dataset.label = "0%";
    }
    showToast("auto-error", {
      title: "Auto-tag status unavailable",
      body: message,
      variant: "error",
      onDismiss: () => autoStatusSection.classList.remove("status-error"),
    });
    requestAnimationFrame(updateStatusCardHeight);
  }
}

async function pollRatingStatus() {
  if (!ratingStatusSection) {
    return;
  }

  try {
    const response = await fetch("/api/rating_status");
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const data = await response.json();

    if (data.enabled === false) {
      ratingStatusSection.style.display = "none";
      if (ratingCardEl) {
        ratingCardEl.style.display = "none";
      }
      if (ratingProgressBar) {
        ratingProgressBar.style.width = "0%";
        ratingProgressBar.dataset.label = "0%";
      }
      requestAnimationFrame(updateStatusCardHeight);
      return;
    }

    ratingStatusSection.style.display = "";
    if (ratingCardEl) {
      ratingCardEl.style.display = "";
    }
    const {
      total,
      completed,
      processing,
      queued,
      error_count,
      state,
      rate_per_min,
      eta_seconds,
      current_path,
      errors,
    } = data;
    const errorList = Array.isArray(errors) ? errors : [];

    let summaryText = "";
    if (total === 0) {
      summaryText = "No images to rate";
    } else if (state === "idle") {
      if (completed === total) {
        summaryText = `Complete (${completed}/${total})`;
      } else {
        summaryText = `Idle (${completed}/${total})`;
      }
    } else if (state === "running") {
      const progress = Math.max(0, (completed / total) * 100);
      const etaText = eta_seconds
        ? `ETA ${Math.round(eta_seconds / 60)}min`
        : "";
      summaryText = `Processing ${processing} | ${completed}/${total} ${etaText ? "| " + etaText : ""} | ${rate_per_min.toFixed(1)}/min`;
      if (current_path) {
        summaryText += ` | ${truncateLabel(current_path, 40)}`;
      }
    }

    ratingSummary.textContent = summaryText || "Rating status unavailable";

    const progress = total > 0 ? Math.max(0, (completed / total) * 100) : 0;
    if (ratingProgressBar) {
      ratingProgressBar.style.width = `${progress}%`;
      ratingProgressBar.dataset.label = `${Math.round(progress)}%`;
    }

    if (error_count > 0) {
      ratingErrorsList.style.display = "block";
      ratingErrorsList.innerHTML = errorList
        .map((e) => `<li>${escapeHtml(e)}</li>`)
        .join("");
    } else {
      ratingErrorsList.style.display = "none";
      ratingErrorsList.innerHTML = "";
    }

    // Update section visibility or styling if needed
    if (state === "complete") {
      ratingStatusSection.classList.add("complete");
    } else {
      ratingStatusSection.classList.remove("complete");
    }
    requestAnimationFrame(updateStatusCardHeight);
  } catch (error) {
    console.error("Failed to fetch rating status:", error);
    ratingSummary.textContent = "Rating status unavailable";
    if (ratingProgressBar) {
      ratingProgressBar.style.width = "0%";
      ratingProgressBar.dataset.label = "0%";
    }
    ratingErrorsList.style.display = "none";
    ratingErrorsList.innerHTML = "";
    requestAnimationFrame(updateStatusCardHeight);
  }
}

async function pollRatingCounts() {
  if (!ratingFilterMeta.length) {
    return;
  }
  try {
    const res = await fetch("/api/rating_counts");
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const data = await res.json();
    if (data && data.counts) {
      updateRatingFilterCounts(data.counts);
    }
  } catch (err) {
    // Suppress noisy errors; counts will refresh on next successful poll
  }
}

async function toggleClipIndexer() {
  if (!clipToggleBtn) return;
  const state = clipToggleBtn.dataset.state;
  const target = state === "paused" ? "resume" : "pause";
  try {
    const res = await fetch(`/api/clip/${target}`, { method: "POST" });
    if (!res.ok) throw new Error(res.statusText);
    setTimeout(pollClipStatus, 300);
  } catch (err) {
    clipSummary.textContent = "Unable to toggle CLIP indexer";
  }
}
if (clipToggleBtn) {
  clipToggleBtn.addEventListener("click", toggleClipIndexer);
}
setInterval(() => {
  pollClipStatus();
  pollAutoStatus();
  pollRatingStatus();
  pollRatingCounts();
}, 2000);
pollClipStatus();
pollAutoStatus();
pollRatingStatus();
pollRatingCounts();
