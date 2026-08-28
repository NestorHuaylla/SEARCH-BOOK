import { normalizeText, searchBooks } from "./search-engine.js";

const API_URL = "https://openstax.org/apps/cms/api/books";
let catalogPromise = null;

function safeUrl(value) {
  try {
    const url = new URL(String(value || ""));
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
}

export function mapOpenStaxSummary(item) {
  const sourceId = String(item?.id || item?.slug || "").trim();
  const slug = String(item?.slug || "").replace(/^\/+|\/+$/g, "");
  const title = String(item?.title || "").trim();
  if (!sourceId || !slug || !title) return null;

  const sourceUrl = `https://openstax.org/details/${slug}`;
  const formats = [];
  const pdfUrl = safeUrl(item.pdf_url);
  const readUrl = safeUrl(item.webview_rex_link || item.webview_link);
  if (pdfUrl) formats.push({ type: "pdf", url: pdfUrl });
  if (readUrl) formats.push({ type: "read", url: readUrl });
  const provider = {
    source: "OpenStax",
    source_id: sourceId,
    source_url: sourceUrl,
    language: "en",
    formats,
    access: "open_access",
    license: "Openly licensed; see official book page",
    verified_legal: true,
  };

  return {
    id: `live:openstax:${sourceId}`,
    title,
    authors: [],
    language: "en",
    available_languages: ["en"],
    year: null,
    publisher: "OpenStax, Rice University",
    isbn: [],
    doi: "",
    subjects: [
      ...(Array.isArray(item.subjects) ? item.subjects : []),
      ...(Array.isArray(item.subject_categories) ? item.subject_categories : []),
    ].filter(Boolean),
    description: "",
    source: "OpenStax",
    source_url: sourceUrl,
    cover_url: safeUrl(item.cover_url),
    formats,
    access: provider.access,
    license: provider.license,
    verified_legal: true,
    resource_type: "textbook",
    identifiers: { source_id: sourceId, openstax_slug: slug.replace(/^books\//, ""), live_discovery: "true" },
    providers: [provider],
    live_discovery: true,
  };
}

async function loadOpenStaxCatalog(fetchImpl, signal) {
  if (!catalogPromise) {
    catalogPromise = fetchImpl(API_URL, { headers: { Accept: "application/json" }, signal })
      .then((response) => {
        if (!response.ok) throw new Error(`OpenStax: HTTP ${response.status}`);
        return response.json();
      })
      .then((payload) => (Array.isArray(payload.books) ? payload.books : [])
        .map(mapOpenStaxSummary).filter(Boolean))
      .catch((error) => {
        catalogPromise = null;
        throw error;
      });
  }
  return catalogPromise;
}

export async function discoverOpenStax(query, {
  fetchImpl = globalThis.fetch,
  limit = 12,
  signal,
} = {}) {
  if (!normalizeText(query)) return [];
  const catalog = await loadOpenStaxCatalog(fetchImpl, signal);
  return searchBooks(catalog, query).slice(0, Math.max(1, Math.min(Number(limit) || 12, 20)));
}
