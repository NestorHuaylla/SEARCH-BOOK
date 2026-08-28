import { normalizeText, parseSearchQuery, searchBooks } from "./search-engine.js";
import {
  discoverOpenLibraryBilingual,
  externalCatalogLinks,
  mergeCatalogRecords,
} from "./open-library-live.js";
import { discoverGutendexBilingual } from "./gutendex-live.js";
import { discoverInternetArchive } from "./internet-archive-live.js";
import { discoverOpenStax } from "./openstax-live.js";

const $ = (selector) => document.querySelector(selector);
const catalogCount = $("#catalog-count");
const catalogDate = $("#catalog-date");
const searchForm = $("#search-form");
const searchInput = $("#search-input");
const status = $("#status");
const outsideFilters = $("#outside-filters");
const outsideFiltersMessage = $("#outside-filters-message");
const outsideFiltersResults = $("#outside-filters-results");
const externalSearches = $("#external-searches");
const workspace = $("#search-workspace");
const welcome = $("#welcome");
const resultsContainer = $("#results");
const resultsSummary = $("#results-summary");
const resultsTitle = $("#results-title");
const loadMoreButton = $("#load-more");
const template = $("#book-card-template");
const sortSelect = $("#sort-results");
const queryInterpretation = $("#query-interpretation");
const queryInterpretationChips = $("#query-interpretation-chips");
const languageSummary = $("#language-summary");
const spanishAvailability = $("#spanish-availability");

const filterElements = {
  title: $("#filter-title"),
  exactTitle: $("#filter-exact-title"),
  author: $("#filter-author"),
  identifier: $("#filter-identifier"),
  subject: $("#filter-subject"),
  publisher: $("#filter-publisher"),
  edition: $("#filter-edition"),
  resourceType: $("#filter-resource-type"),
  yearFrom: $("#filter-year-from"),
  yearTo: $("#filter-year-to"),
  language: $("#filter-language"),
  format: $("#filter-format"),
  availability: $("#filter-availability"),
  access: $("#filter-access"),
  source: $("#filter-source"),
};

const URL_FILTER_PARAMS = {
  title: "title",
  exactTitle: "exact",
  author: "author",
  identifier: "id",
  subject: "subject",
  publisher: "publisher",
  edition: "edition",
  resourceType: "type",
  yearFrom: "from",
  yearTo: "to",
  language: "lang",
  format: "format",
  availability: "available",
  access: "access",
  source: "source",
};

const ACCESS_LABELS = {
  public_domain: "Dominio público",
  open_access: "Open Access",
  creative_commons: "Creative Commons",
  author_free: "Distribución gratuita",
  digital_lending: "Préstamo",
  preview: "Preview",
  metadata_only: "Sólo ficha",
  unknown: "Acceso no confirmado",
};

const ACCESS_CLASSES = {
  public_domain: "public-domain",
  open_access: "open-access",
  creative_commons: "cc",
  author_free: "open-access",
  digital_lending: "lending",
  preview: "preview",
  metadata_only: "metadata",
  unknown: "unknown",
};

const LANGUAGE_LABELS = {
  ar: "Árabe", de: "Alemán", en: "Inglés", es: "Español", fr: "Francés",
  it: "Italiano", ja: "Japonés", la: "Latín", pl: "Polaco", pt: "Portugués",
  ru: "Ruso", zh: "Chino", und: "Sin identificar",
};

const RESOURCE_LABELS = {
  book: "Libro",
  textbook: "Texto universitario",
  article: "Artículo",
  thesis: "Tesis",
  other: "Otro",
};

const QUERY_FIELD_LABELS = {
  title: "Título",
  author: "Autor",
  isbn: "ISBN",
  doi: "DOI",
  publisher: "Editorial",
  subject: "Tema",
  language: "Idioma",
  format: "Formato",
  source: "Fuente",
  access: "Acceso",
  year: "Año",
  edition: "Edición",
  resourceType: "Tipo",
};

const FILTER_LABELS = {
  title: "Título",
  exactTitle: "Título exacto",
  author: "Autor",
  identifier: "ISBN/DOI",
  subject: "Tema",
  publisher: "Editorial",
  edition: "Edición",
  resourceType: "Tipo",
  yearFrom: "Desde",
  yearTo: "Hasta",
  language: "Idioma",
  format: "Formato",
  availability: "Disponibilidad",
  access: "Acceso",
  source: "Fuente",
};

const RESULT_GROUPS = [
  { key: "es", title: "Fichas en español", description: "Ediciones o fichas cuyo idioma declarado es español." },
  { key: "en", title: "English records", description: "Editions or records declared in English." },
  { key: "other", title: "Otros idiomas", description: "Fichas declaradas en otros idiomas o sin identificar." },
];

let metadata = null;
let catalogPromise = null;
let books = [];
let matches = [];
let languageBaseMatches = [];
let outsideFilterMatches = [];
let visiblePerGroup = 8;
let currentQuery = "";
let hasSearched = false;
let searchGeneration = 0;
const discoveryCache = new Map();

function safeExternalUrl(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
}

async function loadMetadata() {
  try {
    const response = await fetch("data/metadata.json", { cache: "no-cache" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    metadata = await response.json();
    catalogCount.textContent = Number(metadata.total_records || 0).toLocaleString("es");
    catalogDate.textContent = metadata.generated_at
      ? `Actualizado ${new Intl.DateTimeFormat("es", { dateStyle: "medium" }).format(new Date(metadata.generated_at))}`
      : "Catálogo pendiente de sincronización";
    return metadata;
  } catch {
    catalogCount.textContent = "0";
    catalogDate.textContent = "No se pudo leer el estado del catálogo";
    return { total_records: 0, shards: [] };
  }
}

async function fetchJson(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}

async function loadCatalog() {
  metadata ||= await loadMetadata();
  const shardEntries = Array.isArray(metadata.shards) ? metadata.shards : [];
  if (!shardEntries.length) {
    const catalog = await fetchJson("data/books.json");
    return Array.isArray(catalog.books) ? catalog.books : [];
  }

  const paths = shardEntries.map((entry) => typeof entry === "string" ? entry : entry.path).filter(Boolean);
  const loaded = new Array(paths.length);
  let nextIndex = 0;
  async function worker() {
    while (nextIndex < paths.length) {
      const index = nextIndex;
      nextIndex += 1;
      const payload = await fetchJson(paths[index]);
      loaded[index] = Array.isArray(payload) ? payload : payload.books || [];
    }
  }
  await Promise.all(Array.from({ length: Math.min(6, paths.length) }, () => worker()));
  return loaded.flat();
}

function ensureCatalog() {
  if (!catalogPromise) {
    catalogPromise = loadCatalog().then((loadedBooks) => {
      books = loadedBooks;
      populateFilters();
      return books;
    });
  }
  return catalogPromise;
}

function discoveryQuery(query, filters) {
  return [query, filters.title, filters.author, filters.identifier, filters.subject]
    .filter(Boolean).join(" ").trim();
}

function ensureDiscovery(query) {
  const key = normalizeText(query);
  if (!key) return Promise.resolve({ books: [], failedSources: [] });
  if (!discoveryCache.has(key)) {
    const withTimeout = (task, timeoutMs) => {
      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
      return task(controller.signal).finally(() => window.clearTimeout(timeout));
    };
    const request = Promise.allSettled([
      withTimeout((signal) => discoverOpenLibraryBilingual(query, { signal, limit: 10 }), 16000),
      withTimeout((signal) => discoverGutendexBilingual(query, { signal }), 8000),
      withTimeout((signal) => discoverOpenStax(query, { signal, limit: 12 }), 12000),
      withTimeout((signal) => discoverInternetArchive(query, { signal, limit: 8 }), 16000),
    ]).then((settled) => {
      const sourceNames = ["Open Library", "Project Gutenberg", "OpenStax", "Internet Archive"];
      const failedSources = settled.flatMap((result, index) => {
        if (result.status === "fulfilled") return [];
        console.warn(`No se pudo consultar ${sourceNames[index]}`, result.reason);
        return [sourceNames[index]];
      });
      const discoveredBooks = settled.flatMap((result) => result.status === "fulfilled" ? result.value : []);
      if (failedSources.length === settled.length) discoveryCache.delete(key);
      return { books: discoveredBooks, failedSources };
    });
    discoveryCache.set(key, request);
  }
  return discoveryCache.get(key);
}

function addOptions(select, values, labeler = (value) => value) {
  const fragment = document.createDocumentFragment();
  [...values].filter(Boolean).sort((a, b) => labeler(a).localeCompare(labeler(b), "es")).forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = labeler(value);
    fragment.append(option);
  });
  select.append(fragment);
}

function populateFilters() {
  addOptions(filterElements.language, new Set(books.map((book) => book.language)), (value) => LANGUAGE_LABELS[value] || value.toUpperCase());
  addOptions(filterElements.format, new Set(books.flatMap((book) => (book.formats || []).map((item) => item.type))), (value) => value.toUpperCase());
  addOptions(filterElements.access, new Set(books.map((book) => book.access)), (value) => ACCESS_LABELS[value] || value);
  addOptions(filterElements.source, new Set(books.flatMap((book) => (book.providers || []).map((provider) => provider.source))));
}

function elementValue(element) {
  return element.type === "checkbox" ? element.checked : element.value.trim();
}

function activeFilters() {
  return Object.fromEntries(Object.entries(filterElements).map(([key, element]) => [key, elementValue(element)]));
}

function filtersAreActive(filters) {
  return Object.entries(filters).some(([key, value]) => value && (key !== "exactTitle" || filters.title));
}

function createBadge(access) {
  const badge = document.createElement("span");
  badge.className = `badge badge--${ACCESS_CLASSES[access] || "unknown"}`;
  badge.textContent = ACCESS_LABELS[access] || ACCESS_LABELS.unknown;
  return badge;
}

function createLanguageBadge(language) {
  const badge = document.createElement("span");
  badge.className = `badge badge--language badge--language-${["es", "en"].includes(language) ? language : "other"}`;
  badge.textContent = LANGUAGE_LABELS[language] || language?.toUpperCase() || LANGUAGE_LABELS.und;
  return badge;
}

function createAction(label, url, className = "") {
  const safeUrl = safeExternalUrl(url);
  if (!safeUrl) return null;
  const link = document.createElement("a");
  link.href = safeUrl;
  link.target = "_blank";
  link.rel = "noopener noreferrer external";
  link.textContent = label;
  if (className) link.className = className;
  return link;
}

function appendDetail(list, label, value) {
  if (!value) return;
  const term = document.createElement("dt");
  term.textContent = label;
  const description = document.createElement("dd");
  description.textContent = value;
  list.append(term, description);
}

function renderCard(book) {
  const card = template.content.firstElementChild.cloneNode(true);
  const badges = card.querySelector(".book-card__badges");
  badges.append(createBadge(book.access), createLanguageBadge(book.language));
  card.querySelector(".book-card__title").textContent = book.title;
  card.querySelector(".book-card__authors").textContent = book.authors?.length ? book.authors.join(", ") : "Autor no identificado";

  const metaParts = [];
  if (book.year) metaParts.push(String(book.year));
  if (book.publisher) metaParts.push(book.publisher);
  if (book.resource_type) metaParts.push(RESOURCE_LABELS[book.resource_type] || book.resource_type);
  card.querySelector(".book-card__meta").textContent = metaParts.filter(Boolean).join(" · ");
  card.querySelector(".book-card__subjects").textContent = (book.subjects || []).slice(0, 5).join(" · ");
  const description = String(book.description || "").trim();
  const descriptionElement = card.querySelector(".book-card__description");
  descriptionElement.textContent = description.length > 320 ? `${description.slice(0, 317).trim()}…` : description;
  descriptionElement.hidden = !description;
  card.querySelector(".book-card__providers").textContent = `Fuentes: ${(book.providers || [{ source: book.source }]).map((provider) => provider.source).join(", ")}`;

  const details = card.querySelector(".book-card__details");
  const detailList = details.querySelector("dl");
  appendDetail(detailList, "Idioma", (book.available_languages || [book.language])
    .map((language) => LANGUAGE_LABELS[language] || language.toUpperCase()).join(", "));
  appendDetail(detailList, "Editorial", book.publisher);
  appendDetail(detailList, "Año", book.year ? String(book.year) : "");
  appendDetail(detailList, "ISBN", (book.isbn || []).slice(0, 5).join(", "));
  appendDetail(detailList, "DOI", book.doi);
  appendDetail(detailList, "Licencia", book.license);
  appendDetail(detailList, "Tipo", RESOURCE_LABELS[book.resource_type] || book.resource_type);
  if (!detailList.childElementCount) details.hidden = true;

  const coverUrl = safeExternalUrl(book.cover_url);
  if (coverUrl) {
    const image = card.querySelector(".book-cover");
    image.src = coverUrl;
    image.alt = `Portada de ${book.title}`;
    image.hidden = false;
    image.addEventListener("error", () => { image.hidden = true; }, { once: true });
  }

  const actions = card.querySelector(".book-card__actions");
  const seen = new Set();
  const formatPriority = { pdf: 0, epub: 1, read: 2, html: 3, azw3: 4, mobi: 5, text: 6 };
  const providerFormats = (book.providers || []).flatMap((provider) =>
    (provider.formats || []).map((format) => ({ ...format, source: provider.source }))
  ).sort((left, right) => (formatPriority[left.type] ?? 9) - (formatPriority[right.type] ?? 9));

  providerFormats.slice(0, 6).forEach((format) => {
    const key = `${format.type}:${format.url}`;
    if (seen.has(key)) return;
    seen.add(key);
    const label = format.type === "pdf" ? "Descargar PDF"
      : format.type === "epub" ? "Descargar EPUB"
        : ["read", "html"].includes(format.type) ? "Leer online"
          : `Descargar ${format.type.toUpperCase()}`;
    const isDownload = !["read", "html"].includes(format.type);
    const action = createAction(label, format.url, isDownload ? "download-action" : "read-action");
    if (action) {
      action.title = `${label} en ${format.source}`;
      actions.append(action);
    }
  });

  (book.providers || [{ source: book.source, source_url: book.source_url, access: book.access }]).slice(0, 4).forEach((provider) => {
    const prefix = provider.access === "digital_lending" ? "Préstamo"
      : provider.access === "preview" ? "Preview"
        : ["metadata_only", "unknown"].includes(provider.access) ? "Ver ficha" : "Fuente";
    const action = createAction(`${prefix}: ${provider.source}`, provider.source_url, "source-action");
    if (action) actions.append(action);
  });
  return card;
}

function renderBookList(container, items) {
  const fragment = document.createDocumentFragment();
  items.forEach((book) => fragment.append(renderCard(book)));
  container.replaceChildren(fragment);
}

function groupKey(book) {
  if (book.language === "es") return "es";
  if (book.language === "en") return "en";
  return "other";
}

function groupedBooks(items) {
  const grouped = { es: [], en: [], other: [] };
  items.forEach((book) => grouped[groupKey(book)].push(book));
  return grouped;
}

function renderGroupedResults() {
  const grouped = groupedBooks(matches);
  const fragment = document.createDocumentFragment();
  let hasMore = false;
  for (const group of RESULT_GROUPS) {
    const items = grouped[group.key];
    if (!items.length) continue;
    const section = document.createElement("section");
    section.className = `result-group result-group--${group.key}`;
    section.setAttribute("aria-labelledby", `result-group-${group.key}`);
    const heading = document.createElement("div");
    heading.className = "result-group__heading";
    const headingText = document.createElement("div");
    const title = document.createElement("h3");
    title.id = `result-group-${group.key}`;
    title.textContent = group.title;
    const description = document.createElement("p");
    description.textContent = group.description;
    headingText.append(title, description);
    const count = document.createElement("span");
    count.textContent = items.length.toLocaleString("es");
    count.setAttribute("aria-label", `${items.length} resultados`);
    heading.append(headingText, count);
    const list = document.createElement("div");
    list.className = "result-group__list";
    items.slice(0, visiblePerGroup).forEach((book) => list.append(renderCard(book)));
    section.append(heading, list);
    fragment.append(section);
    if (items.length > visiblePerGroup) hasMore = true;
  }
  resultsContainer.replaceChildren(fragment);
  loadMoreButton.hidden = !hasMore;
}

function updateExternalSearches(query) {
  const links = externalCatalogLinks(query);
  externalSearches.querySelector('[data-catalog="open-library"]').href = links.openLibrary;
  externalSearches.querySelector('[data-catalog="open-library-es"]').href = links.openLibrarySpanish;
  externalSearches.querySelector('[data-catalog="google-books"]').href = links.googleBooks;
  externalSearches.querySelector('[data-catalog="google-books-es"]').href = links.googleBooksSpanish;
  externalSearches.querySelector('[data-catalog="gutenberg"]').href = links.gutenberg;
  externalSearches.querySelector('[data-catalog="oapen"]').href = links.oapen;
  externalSearches.querySelector('[data-catalog="doab"]').href = links.doab;
  externalSearches.querySelector('[data-catalog="internet-archive"]').href = links.internetArchive;
  externalSearches.querySelector('[data-catalog="openstax"]').href = links.openStax;
  externalSearches.querySelector('[data-catalog="worldcat"]').href = links.worldCat;
  externalSearches.hidden = false;
}

function renderInterpretation(query, filters) {
  const parsed = parseSearchQuery(query);
  const chips = [];
  Object.entries(parsed.fields).forEach(([field, values]) => values.forEach((value) => {
    chips.push(`${QUERY_FIELD_LABELS[field] || field}: ${value}`);
  }));
  parsed.phrases.forEach((value) => chips.push(`Frase exacta: ${value}`));
  Object.entries(filters).forEach(([field, value]) => {
    if (!value || (field === "exactTitle" && !filters.title)) return;
    const displayValue = value === true ? "sí" : String(value);
    chips.push(`${FILTER_LABELS[field] || field}: ${displayValue}`);
  });

  queryInterpretation.hidden = !chips.length;
  const fragment = document.createDocumentFragment();
  [...new Set(chips)].forEach((text) => {
    const chip = document.createElement("span");
    chip.textContent = text;
    fragment.append(chip);
  });
  queryInterpretationChips.replaceChildren(fragment);
}

function languageCounts(items) {
  const counts = { all: items.length, es: 0, en: 0, other: 0 };
  items.forEach((book) => { counts[groupKey(book)] += 1; });
  return counts;
}

function renderLanguageSummary() {
  const counts = languageCounts(languageBaseMatches);
  Object.entries(counts).forEach(([key, value]) => {
    const target = document.querySelector(`[data-language-count="${key}"]`);
    if (target) target.textContent = value.toLocaleString("es");
  });
  document.querySelectorAll("[data-result-language]").forEach((button) => {
    const active = button.dataset.resultLanguage === filterElements.language.value;
    button.setAttribute("aria-pressed", String(active));
  });
  spanishAvailability.textContent = counts.es
    ? `${counts.es.toLocaleString("es")} ${counts.es === 1 ? "ficha coincide" : "fichas coinciden"} en español.`
    : "No encontramos una ficha en español con estos criterios; puedes revisar las ediciones en inglés y continuar en los catálogos enlazados.";
  languageSummary.hidden = counts.all === 0;
}

function renderOutsideFilters() {
  const shouldShow = matches.length === 0 && outsideFilterMatches.length > 0;
  outsideFilters.hidden = !shouldShow;
  if (!shouldShow) {
    outsideFiltersResults.replaceChildren();
    return;
  }
  outsideFiltersMessage.textContent = `${outsideFilterMatches.length.toLocaleString("es")} ${outsideFilterMatches.length === 1 ? "ficha coincide" : "fichas coinciden"}, pero no con el formato, acceso u otro filtro seleccionado.`;
  renderBookList(outsideFiltersResults, outsideFilterMatches.slice(0, 3));
}

function renderResults({ isFinal = true } = {}) {
  renderGroupedResults();
  const rescuedByFilters = matches.length === 0 && outsideFilterMatches.length > 0;
  status.hidden = matches.length > 0 || rescuedByFilters;
  if (!matches.length && !rescuedByFilters) {
    status.textContent = isFinal
      ? "No encontramos una coincidencia directa. Revisa también los catálogos externos de abajo."
      : "No hay coincidencias locales; seguimos consultando las fuentes abiertas en vivo…";
  }
  renderOutsideFilters();
  renderLanguageSummary();
}

function updateUrlState(query, filters) {
  const url = new URL(window.location.href);
  query ? url.searchParams.set("q", query) : url.searchParams.delete("q");
  Object.entries(URL_FILTER_PARAMS).forEach(([field, parameter]) => {
    const value = filters[field];
    value ? url.searchParams.set(parameter, value === true ? "1" : String(value)) : url.searchParams.delete(parameter);
  });
  sortSelect.value === "relevance" ? url.searchParams.delete("sort") : url.searchParams.set("sort", sortSelect.value);
  history.replaceState(null, "", url);
}

async function performSearch({ updateUrl = true } = {}) {
  currentQuery = searchInput.value.trim();
  const filters = activeFilters();
  const hasCriteria = Boolean(normalizeText(currentQuery)) || filtersAreActive(filters);
  const generation = ++searchGeneration;
  hasSearched = true;
  workspace.hidden = false;
  welcome.hidden = true;
  resultsContainer.replaceChildren();
  outsideFilters.hidden = true;
  outsideFiltersResults.replaceChildren();
  externalSearches.hidden = true;
  languageSummary.hidden = true;
  loadMoreButton.hidden = true;
  status.hidden = false;
  status.textContent = "Buscando en el catálogo y en cuatro fuentes abiertas en vivo…";
  resultsSummary.textContent = "Buscando";
  resultsTitle.textContent = currentQuery ? `“${currentQuery}”` : "Búsqueda avanzada";
  renderInterpretation(currentQuery, filters);
  visiblePerGroup = 8;

  if (updateUrl) updateUrlState(currentQuery, filters);
  if (!hasCriteria) {
    status.textContent = "Escribe un título, autor, ISBN, DOI o completa un campo avanzado.";
    resultsSummary.textContent = "";
    queryInterpretation.hidden = true;
    return;
  }

  try {
    const remoteQuery = discoveryQuery(currentQuery, filters);
    const discoveryPromise = ensureDiscovery(remoteQuery);
    const loadedBooks = await ensureCatalog();
    if (generation !== searchGeneration) return;

    const updateSearchState = (discovery, { isFinal }) => {
      const combinedBooks = mergeCatalogRecords(loadedBooks, discovery.books);
      const filtersWithoutLanguage = { ...filters, language: "" };
      languageBaseMatches = searchBooks(combinedBooks, currentQuery, filtersWithoutLanguage, sortSelect.value);
      matches = filters.language
        ? searchBooks(combinedBooks, currentQuery, filters, sortSelect.value)
        : languageBaseMatches;
      const visibleIds = new Set(matches.map((book) => book.id));
      outsideFilterMatches = filtersAreActive(filters) && normalizeText(currentQuery)
        ? searchBooks(combinedBooks, currentQuery, {}, sortSelect.value)
          .filter((book) => !visibleIds.has(book.id))
          .slice(0, 6)
        : [];
      const failureSuffix = isFinal && discovery.failedSources.length
        ? ` · ${discovery.failedSources.length === 1 ? "1 fuente no respondió" : `${discovery.failedSources.length} fuentes no respondieron`}`
        : !isFinal && remoteQuery ? " · ampliando en fuentes abiertas…" : "";
      resultsSummary.textContent = outsideFilterMatches.length && !matches.length
        ? `0 con filtros · ${outsideFilterMatches.length.toLocaleString("es")} ${outsideFilterMatches.length === 1 ? "coincidencia detectada" : "coincidencias detectadas"}${failureSuffix}`
        : `${matches.length.toLocaleString("es")} ${matches.length === 1 ? "resultado" : "resultados"}${failureSuffix}`;
      renderResults({ isFinal });
    };

    updateSearchState({ books: [], failedSources: [] }, { isFinal: !remoteQuery });
    if (remoteQuery) updateExternalSearches(remoteQuery);
    if (!remoteQuery) return;

    const discovery = await discoveryPromise;
    if (generation !== searchGeneration) return;
    updateSearchState(discovery, { isFinal: true });
  } catch (error) {
    console.error(error);
    status.textContent = "No se pudo cargar el catálogo. Recarga la página o inténtalo más tarde.";
    resultsSummary.textContent = "Error de catálogo";
    updateExternalSearches(discoveryQuery(currentQuery, filters));
  }
}

function clearFiltersAndSearch() {
  Object.values(filterElements).forEach((element) => {
    if (element.type === "checkbox") element.checked = false;
    else element.value = "";
  });
  if (hasSearched) performSearch();
}

function restoreStateFromUrl(params) {
  searchInput.value = params.get("q") || "";
  Object.entries(URL_FILTER_PARAMS).forEach(([field, parameter]) => {
    const element = filterElements[field];
    const value = params.get(parameter);
    if (!element || value === null) return;
    if (element.type === "checkbox") element.checked = value === "1" || value === "true";
    else element.value = value;
  });
  const requestedSort = params.get("sort");
  if ([...sortSelect.options].some((option) => option.value === requestedSort)) sortSelect.value = requestedSort;
}

searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  performSearch();
});

document.querySelectorAll(".example-query").forEach((button) => {
  button.addEventListener("click", () => {
    searchInput.value = button.dataset.query || "";
    searchForm.requestSubmit();
  });
});

Object.values(filterElements).forEach((element) => {
  const eventName = ["SELECT", "INPUT"].includes(element.tagName) && ["checkbox", "number"].includes(element.type)
    ? "change"
    : element.tagName === "SELECT" ? "change" : "input";
  let debounceTimer;
  element.addEventListener(eventName, () => {
    window.clearTimeout(debounceTimer);
    debounceTimer = window.setTimeout(() => {
      if (hasSearched) performSearch();
    }, eventName === "input" ? 300 : 0);
  });
});

document.querySelectorAll("[data-result-language]").forEach((button) => {
  button.addEventListener("click", () => {
    filterElements.language.value = button.dataset.resultLanguage || "";
    performSearch();
  });
});

sortSelect.addEventListener("change", () => { if (hasSearched) performSearch(); });

$("#clear-filters").addEventListener("click", clearFiltersAndSearch);
$("#show-outside-filters").addEventListener("click", clearFiltersAndSearch);

loadMoreButton.addEventListener("click", () => {
  visiblePerGroup += 8;
  renderGroupedResults();
});

const initialParams = new URLSearchParams(window.location.search);
loadMetadata().then(async () => {
  const hasInitialState = [...initialParams.keys()].some((key) =>
    ["q", "sort", ...Object.values(URL_FILTER_PARAMS)].includes(key)
  );
  if (!hasInitialState) return;
  await ensureCatalog();
  restoreStateFromUrl(initialParams);
  performSearch({ updateUrl: false });
});
