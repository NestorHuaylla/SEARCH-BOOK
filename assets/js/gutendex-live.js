import { normalizeText, parseSearchQuery } from "./search-engine.js";

const MIME_FORMATS = new Map([
  ["application/epub+zip", "epub"],
  ["application/pdf", "pdf"],
  ["application/x-mobipocket-ebook", "mobi"],
  ["text/html", "html"],
  ["text/plain", "text"],
]);

function safeUrl(value) {
  try {
    const url = new URL(String(value || ""));
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
}

function discoveryQuery(query) {
  const parsed = parseSearchQuery(query);
  return [
    ...(parsed.fields.title || []),
    ...(parsed.fields.author || []),
    ...(parsed.fields.subject || []),
    ...parsed.terms,
    ...parsed.phrases,
  ].join(" ").trim() || String(query || "").trim();
}

export function buildGutendexSearchUrl(query, { language = "", topic = false } = {}) {
  const url = new URL("https://gutendex.com/books/");
  url.searchParams.set(topic ? "topic" : "search", discoveryQuery(query));
  if (language) url.searchParams.set("languages", language);
  url.searchParams.set("copyright", "false");
  return url.href;
}

function mappedFormats(rawFormats, mayExposeFiles) {
  if (!mayExposeFiles || !rawFormats || typeof rawFormats !== "object") return [];
  const formats = [];
  const seenTypes = new Set();
  for (const [mimeType, rawUrl] of Object.entries(rawFormats)) {
    const type = MIME_FORMATS.get(String(mimeType).split(";", 1)[0].toLocaleLowerCase());
    const url = safeUrl(rawUrl);
    if (!type || !url || seenTypes.has(type)) continue;
    seenTypes.add(type);
    formats.push({ type, url });
  }
  return formats;
}

export function mapGutendexBook(item, { language = "" } = {}) {
  const id = String(item?.id || "").trim();
  const title = String(item?.title || "").trim();
  if (!/^\d+$/.test(id) || !title) return null;

  const itemLanguages = (Array.isArray(item.languages) ? item.languages : []).filter(Boolean);
  if (language && itemLanguages.length && !itemLanguages.includes(language)) return null;
  const detectedLanguage = language || itemLanguages[0] || "und";
  const isPublicDomain = item.copyright === false;
  const formats = mappedFormats(item.formats, isPublicDomain);
  const sourceUrl = `https://www.gutenberg.org/ebooks/${id}`;
  const coverUrl = safeUrl(item.formats?.["image/jpeg"]);
  const provider = {
    source: "Project Gutenberg",
    source_id: id,
    source_url: sourceUrl,
    language: detectedLanguage,
    formats,
    access: isPublicDomain ? "public_domain" : "metadata_only",
    license: isPublicDomain ? "Public domain in the United States" : "",
    verified_legal: isPublicDomain,
  };

  return {
    id: `live:gutenberg:${id}`,
    title,
    authors: (Array.isArray(item.authors) ? item.authors : [])
      .map((author) => String(author?.name || "").trim()).filter(Boolean).slice(0, 8),
    language: detectedLanguage,
    available_languages: [detectedLanguage],
    year: null,
    publisher: "Project Gutenberg",
    isbn: [],
    doi: "",
    subjects: [
      ...(Array.isArray(item.subjects) ? item.subjects : []),
      ...(Array.isArray(item.bookshelves) ? item.bookshelves : []),
    ].filter(Boolean).slice(0, 30),
    description: String(Array.isArray(item.summaries) ? item.summaries.find(Boolean) || "" : "").trim(),
    source: "Project Gutenberg",
    source_url: sourceUrl,
    cover_url: coverUrl,
    formats,
    access: provider.access,
    license: provider.license,
    verified_legal: provider.verified_legal,
    resource_type: "book",
    identifiers: { source_id: id, gutenberg_id: id, live_discovery: "true" },
    providers: [provider],
    live_discovery: true,
  };
}

export async function discoverGutendex(query, {
  fetchImpl = globalThis.fetch,
  language = "",
  signal,
  topic = false,
} = {}) {
  if (!normalizeText(query)) return [];
  const response = await fetchImpl(buildGutendexSearchUrl(query, { language, topic }), {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) throw new Error(`Gutendex: HTTP ${response.status}`);
  const payload = await response.json();
  return (Array.isArray(payload.results) ? payload.results : [])
    .map((item) => mapGutendexBook(item, { language }))
    .filter(Boolean);
}

export async function discoverGutendexBilingual(query, options = {}) {
  const languages = options.languages || ["es", "en"];
  const batches = await Promise.all(languages.map((language) =>
    discoverGutendex(query, { ...options, language })
  ));
  const known = new Set();
  return batches.flat().filter((book) => {
    if (known.has(book.id)) return false;
    known.add(book.id);
    return true;
  });
}
