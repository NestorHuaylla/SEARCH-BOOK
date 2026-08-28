import { normalizeText, parseSearchQuery } from "./search-engine.js";

const SEARCH_FIELDS = [
  "key",
  "title",
  "author_name",
  "first_publish_year",
  "publisher",
  "isbn",
  "language",
  "cover_i",
  "ebook_access",
  "ia",
  "public_scan_b",
  "subject",
  "first_sentence",
  "editions",
  "editions.key",
  "editions.title",
  "editions.language",
  "editions.publish_date",
  "editions.publisher",
  "editions.isbn",
  "editions.edition_name",
  "editions.ebook_access",
  "editions.ia",
].join(",");

const LANGUAGE_CODES = new Map([
  ["ara", "ar"], ["deu", "de"], ["dut", "nl"], ["eng", "en"], ["fre", "fr"],
  ["fra", "fr"], ["ger", "de"], ["ita", "it"], ["jpn", "ja"], ["lat", "la"],
  ["pol", "pl"], ["por", "pt"], ["rus", "ru"], ["spa", "es"], ["zho", "zh"],
]);

const OPEN_LIBRARY_LANGUAGE = new Map([["es", "spa"], ["en", "eng"]]);

const DISCOVERY_NOISE = new Set([
  "author", "autor", "book", "by", "ed", "edicion", "edition", "english", "espanol",
  "ingles", "libro", "por", "spanish", "descarga", "descargar", "download", "epub", "free",
  "gratis", "gratuita", "gratuito", "mobi", "pdf",
]);

const ACCESS_RANK = {
  unknown: 0,
  metadata_only: 1,
  preview: 2,
  digital_lending: 3,
  author_free: 4,
  open_access: 5,
  creative_commons: 6,
  public_domain: 7,
};

function firstValue(value, fallback = "") {
  if (Array.isArray(value)) return value.find(Boolean) || fallback;
  return value || fallback;
}

function languageCode(value) {
  const normalized = String(value || "und").toLocaleLowerCase();
  if (normalized.length === 2) return normalized;
  return LANGUAGE_CODES.get(normalized) || "und";
}

function languageCodes(values) {
  const entries = Array.isArray(values) ? values : [values];
  return [...new Set(entries.map(languageCode).filter((value) => value !== "und"))];
}

function workUrl(key) {
  return /^\/(?:works|books)\/OL[\dA-Z]+[MW]$/i.test(String(key || ""))
    ? `https://openlibrary.org${key}`
    : "";
}

function editionKey(value) {
  const raw = String(value || "");
  if (/^OL[\dA-Z]+M$/i.test(raw)) return raw;
  const match = raw.match(/\/books\/(OL[\dA-Z]+M)$/i);
  return match?.[1] || "";
}

function editionUrl(value) {
  const key = editionKey(value);
  return key ? `https://openlibrary.org/books/${key}` : "";
}

function cleanIsbn(values) {
  return [...new Set((Array.isArray(values) ? values : []).map((value) =>
    String(value).replace(/[^\dX]/gi, "").toUpperCase()
  ).filter((value) => value.length === 10 || value.length === 13))].slice(0, 30);
}

function uniqueAuthors(values) {
  const seen = new Set();
  return (Array.isArray(values) ? values : []).filter((value) => {
    const key = normalizeText(value).split(" ").filter(Boolean).sort().join(" ");
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, 8);
}

function accessDetails(document, sourceUrl) {
  const ebookAccess = String(document?.ebook_access || "").toLocaleLowerCase();
  if (ebookAccess === "public") {
    return {
      access: "open_access",
      formats: [{ type: "read", url: sourceUrl }],
      verifiedLegal: true,
    };
  }
  if (ebookAccess === "borrowable") {
    return { access: "digital_lending", formats: [], verifiedLegal: true };
  }
  return { access: "metadata_only", formats: [], verifiedLegal: false };
}

function editionsFor(document) {
  const editions = document?.editions?.docs;
  return Array.isArray(editions) ? editions.filter((item) => item && typeof item === "object") : [];
}

function editionForLanguage(document, language) {
  if (!language) return null;
  return editionsFor(document).find((edition) => languageCodes(edition.language).includes(language)) || null;
}

function remoteQuery(query) {
  const parsed = parseSearchQuery(query);
  const structured = [
    ...(parsed.fields.title || []),
    ...(parsed.fields.author || []),
    ...(parsed.fields.isbn || []),
    ...(parsed.fields.doi || []),
    ...(parsed.fields.subject || []),
    ...parsed.terms,
    ...parsed.phrases,
  ].join(" ");
  return relaxedBibliographicQuery(structured || query);
}

export function buildOpenLibrarySearchUrl(query, { limit = 12, language = "" } = {}) {
  const url = new URL("https://openlibrary.org/search.json");
  const cleanedQuery = String(query ?? "").trim().replace(/\s+/g, " ");
  const languageFilter = OPEN_LIBRARY_LANGUAGE.get(language);
  url.searchParams.set("q", languageFilter ? `${cleanedQuery} AND language:${languageFilter}` : cleanedQuery);
  url.searchParams.set("fields", SEARCH_FIELDS);
  url.searchParams.set("limit", String(Math.min(20, Math.max(1, Number(limit) || 12))));
  if (language) url.searchParams.set("lang", language);
  return url.href;
}

export function relaxedBibliographicQuery(query) {
  const raw = String(query ?? "").trim().replace(/\s+/g, " ");
  const tokens = normalizeText(raw).split(" ").filter(Boolean);
  const hasEditionMarker = tokens.some((token) => ["ed", "edicion", "edition"].includes(token));
  const hasNoise = tokens.some((token) => DISCOVERY_NOISE.has(token));
  if (!hasNoise) return raw;
  return tokens.filter((token) =>
    !DISCOVERY_NOISE.has(token) && !(hasEditionMarker && /^\d{1,2}$/.test(token))
  ).join(" ") || raw;
}

export function mapOpenLibraryDocument(document, { language = "" } = {}) {
  const workSourceUrl = workUrl(document?.key);
  const edition = editionForLanguage(document, language);
  if (language && !edition) return null;

  const sourceUrl = editionUrl(edition?.key) || workSourceUrl;
  const title = String(edition?.title || document?.title || "").trim();
  if (!sourceUrl || !title) return null;

  const details = accessDetails(edition || document, sourceUrl);
  const workId = String(document.key).split("/").pop();
  const selectedEditionId = editionKey(edition?.key);
  const sourceId = selectedEditionId || workId;
  const detectedLanguages = language
    ? [language]
    : languageCodes(edition?.language || document.language);
  const primaryLanguage = detectedLanguages[0] || "und";
  const provider = {
    source: "Open Library",
    source_id: sourceId,
    source_url: sourceUrl,
    language: primaryLanguage,
    formats: details.formats,
    access: details.access,
    license: "",
    verified_legal: details.verifiedLegal,
  };

  return {
    id: `live:openlibrary:${sourceId}:${primaryLanguage}`,
    title,
    authors: uniqueAuthors(document.author_name),
    language: primaryLanguage,
    available_languages: detectedLanguages,
    year: Number(String(firstValue(edition?.publish_date || document.first_publish_year)).match(/\d{4}/)?.[0]) || null,
    publisher: String(firstValue(edition?.publisher || document.publisher)).trim(),
    isbn: cleanIsbn(edition?.isbn || document.isbn),
    doi: "",
    subjects: (Array.isArray(document.subject) ? document.subject : []).filter(Boolean).slice(0, 12),
    description: String(firstValue(document.first_sentence)).trim(),
    source: "Open Library",
    source_url: sourceUrl,
    cover_url: document.cover_i ? `https://covers.openlibrary.org/b/id/${document.cover_i}-M.jpg` : "",
    formats: details.formats,
    access: details.access,
    license: "",
    verified_legal: details.verifiedLegal,
    resource_type: "book",
    identifiers: {
      source_id: sourceId,
      openlibrary_work: workId,
      ...(selectedEditionId ? { openlibrary_edition: selectedEditionId } : {}),
      ...(edition?.edition_name ? { edition: String(firstValue(edition.edition_name)) } : {}),
      live_discovery: "true",
    },
    providers: [provider],
    live_discovery: true,
  };
}

export async function discoverOpenLibrary(query, {
  fetchImpl = globalThis.fetch,
  limit = 12,
  language = "",
  signal,
} = {}) {
  if (!normalizeText(query)) return [];
  const response = await fetchImpl(buildOpenLibrarySearchUrl(remoteQuery(query), { limit, language }), {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) throw new Error(`Open Library: HTTP ${response.status}`);
  const payload = await response.json();
  return (Array.isArray(payload.docs) ? payload.docs : [])
    .map((document) => mapOpenLibraryDocument(document, { language }))
    .filter(Boolean);
}

export async function discoverOpenLibraryBilingual(query, options = {}) {
  const languages = options.languages || ["es", "en"];
  const pauseBetweenLanguagesMs = options.pauseBetweenLanguagesMs ?? 1050;
  const results = [];
  for (const [index, language] of languages.entries()) {
    // Sequential requests are deliberate: Open Library asks anonymous clients
    // to keep request volume low. The app also caches each completed query.
    if (index && pauseBetweenLanguagesMs > 0) {
      await new Promise((resolve) => globalThis.setTimeout(resolve, pauseBetweenLanguagesMs));
    }
    results.push(...await discoverOpenLibrary(query, { ...options, language }));
  }
  return results;
}

function identityKeys(book) {
  const keys = new Set();
  const language = book.language || "und";
  const openStaxSlug = normalizeText(book.identifiers?.openstax_slug || "");
  if (openStaxSlug) keys.add(`openstax:${openStaxSlug}`);
  for (const provider of book.providers || []) {
    if (provider.source && provider.source_id) {
      keys.add(`source:${normalizeText(provider.source)}:${normalizeText(provider.source_id)}`);
    }
  }
  for (const isbn of cleanIsbn(book.isbn)) keys.add(`isbn:${isbn}|${language}`);
  const title = normalizeText(book.title)
    .replace(/\b(?:edition|edicion|ed|global)\b/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  const author = normalizeText(firstValue(book.authors)).split(" ").filter(Boolean).at(-1) || "";
  if (title && author) keys.add(`work:${title}|${author}|${language}`);
  return keys;
}

function mergeFormats(left, right) {
  const known = new Set();
  return [...left, ...right].filter((format) => {
    const key = `${format.type}:${format.url}`;
    if (known.has(key)) return false;
    known.add(key);
    return true;
  });
}

function mergeProviders(left, right) {
  const known = new Set();
  return [...left, ...right].filter((provider) => {
    const key = `${provider.source}:${provider.source_id}:${provider.source_url}`;
    if (known.has(key)) return false;
    known.add(key);
    return true;
  });
}

function mergeRecords(existing, discovered) {
  const existingRank = ACCESS_RANK[existing.access] || 0;
  const discoveredRank = ACCESS_RANK[discovered.access] || 0;
  const preferred = discoveredRank > existingRank ? discovered : existing;
  const providers = mergeProviders(existing.providers || [], discovered.providers || []);
  const formats = mergeFormats(
    existing.formats || [],
    discovered.formats || [],
  );
  return {
    ...existing,
    cover_url: existing.cover_url || discovered.cover_url,
    subjects: [...new Set([...(existing.subjects || []), ...(discovered.subjects || [])])].slice(0, 80),
    isbn: [...new Set([...(existing.isbn || []), ...(discovered.isbn || [])])],
    source: preferred.source,
    source_url: preferred.source_url,
    access: preferred.access,
    license: preferred.license || existing.license || discovered.license || "",
    verified_legal: Boolean(existing.verified_legal || discovered.verified_legal),
    formats,
    providers,
    live_discovery: Boolean(existing.live_discovery || discovered.live_discovery),
  };
}

export function mergeCatalogRecords(catalog, discovered) {
  const merged = [...catalog];
  const indexByKey = new Map();
  merged.forEach((book, index) => identityKeys(book).forEach((key) => indexByKey.set(key, index)));

  for (const book of discovered) {
    const keys = identityKeys(book);
    const existingIndex = [...keys].map((key) => indexByKey.get(key)).find((index) => index !== undefined);
    if (existingIndex !== undefined) {
      merged[existingIndex] = mergeRecords(merged[existingIndex], book);
      identityKeys(merged[existingIndex]).forEach((key) => indexByKey.set(key, existingIndex));
      continue;
    }
    const index = merged.length;
    merged.push(book);
    keys.forEach((key) => indexByKey.set(key, index));
  }
  return merged;
}

export function externalCatalogLinks(query) {
  const encoded = encodeURIComponent(String(query ?? "").trim());
  return {
    openLibrary: `https://openlibrary.org/search?q=${encoded}`,
    openLibrarySpanish: `https://openlibrary.org/search?q=${encoded}&language=spa`,
    googleBooks: `https://books.google.com/books?q=${encoded}`,
    googleBooksSpanish: `https://books.google.com/books?q=${encoded}&lr=lang_es`,
    worldCat: `https://search.worldcat.org/search?q=${encoded}`,
    gutenberg: `https://www.gutenberg.org/ebooks/search/?query=${encoded}`,
    oapen: `https://library.oapen.org/discover?query=${encoded}`,
    doab: `https://directory.doabooks.org/discover?query=${encoded}`,
    internetArchive: `https://archive.org/search?query=${encoded}`,
    openStax: "https://openstax.org/subjects",
  };
}
