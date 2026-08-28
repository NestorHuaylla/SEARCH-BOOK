import { normalizeText, parseSearchQuery } from "./search-engine.js";

const LANGUAGE_CODES = new Map([
  ["eng", "en"], ["spa", "es"], ["fre", "fr"], ["fra", "fr"], ["ger", "de"],
  ["deu", "de"], ["por", "pt"], ["ita", "it"], ["rus", "ru"], ["jpn", "ja"],
]);

const QUERY_NOISE = new Set([
  "autor", "author", "book", "ed", "edicion", "edition", "espanol", "english", "ingles", "libro",
  "descarga", "descargar", "download", "epub", "free", "gratis", "gratuita", "gratuito", "mobi", "pdf",
]);

function safeUrl(value) {
  try {
    const url = new URL(String(value || ""));
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
}

function firstValue(value, fallback = "") {
  if (Array.isArray(value)) return value.find(Boolean) || fallback;
  return value || fallback;
}

function languageCode(value) {
  const raw = String(firstValue(value, "und")).toLocaleLowerCase().split("-", 1)[0];
  return raw.length === 2 ? raw : LANGUAGE_CODES.get(raw) || "und";
}

function remoteTerms(query) {
  const parsed = parseSearchQuery(query);
  const combined = [
    ...(parsed.fields.title || []),
    ...(parsed.fields.author || []),
    ...(parsed.fields.subject || []),
    ...parsed.terms,
    ...parsed.phrases,
  ].join(" ");
  return normalizeText(combined || query).split(" ")
    .filter((token) => token.length > 1 && !QUERY_NOISE.has(token)).slice(0, 10);
}

export function buildInternetArchiveSearchUrl(query, { limit = 8 } = {}) {
  const terms = remoteTerms(query);
  const textQuery = terms.map((term) => `"${term.replace(/["\\]/g, " ")}"`).join(" AND ") || '"open access"';
  const url = new URL("https://archive.org/advancedsearch.php");
  url.searchParams.set("q", `mediatype:texts AND (${textQuery}) AND licenseurl:* AND NOT access-restricted-item:true`);
  [
    "identifier", "title", "creator", "year", "date", "language", "subject", "description",
    "publisher", "isbn", "licenseurl", "rights", "access-restricted-item", "downloads",
  ].forEach((field) => url.searchParams.append("fl[]", field));
  url.searchParams.set("rows", String(Math.max(1, Math.min(Number(limit) || 8, 12))));
  url.searchParams.set("page", "1");
  url.searchParams.set("output", "json");
  url.searchParams.append("sort[]", "downloads desc");
  return url.href;
}

function directFormats(identifier, payload) {
  const metadata = payload?.metadata && typeof payload.metadata === "object" ? payload.metadata : {};
  const blocked = payload?.is_dark === true
    || [metadata.nodownload, metadata["access-restricted-item"]]
      .some((value) => ["1", "true", "yes"].includes(String(value).toLocaleLowerCase()));
  if (blocked) return [];

  const candidates = [];
  for (const file of Array.isArray(payload?.files) ? payload.files : []) {
    if (!file || typeof file !== "object") continue;
    if ([file.private, file.login, file.restricted]
      .some((value) => [true, 1, "1", "true", "yes"].includes(value))) continue;
    const name = String(file.name || "").trim();
    const format = normalizeText(file.format);
    const lowerName = name.toLocaleLowerCase();
    let type = "";
    if (lowerName.endsWith(".pdf") || format.includes("pdf")) type = "pdf";
    else if (lowerName.endsWith(".epub") || format.includes("epub")) type = "epub";
    else if (lowerName.endsWith(".html") || lowerName.endsWith(".htm") || format === "html") type = "html";
    else if (lowerName.endsWith(".txt") && !lowerName.endsWith("_meta.txt")) type = "text";
    if (!type || !name || name.startsWith(".")) continue;
    const sourceRank = normalizeText(file.source) === "original" ? 0 : 1;
    const typeRank = { pdf: 0, epub: 1, html: 2, text: 3 }[type];
    candidates.push({ type, name, rank: typeRank * 10 + sourceRank });
  }

  const seen = new Set();
  return candidates.sort((left, right) => left.rank - right.rank).flatMap(({ type, name }) => {
    if (seen.has(type)) return [];
    seen.add(type);
    const encodedName = name.split("/").map(encodeURIComponent).join("/");
    return [{ type, url: `https://archive.org/download/${encodeURIComponent(identifier)}/${encodedName}` }];
  });
}

export function mapInternetArchiveDocument(document, payload = {}) {
  const identifier = String(document?.identifier || "").trim();
  const title = String(document?.title || "").trim();
  const licenseUrl = safeUrl(firstValue(document?.licenseurl));
  const licenseText = `${licenseUrl} ${firstValue(document?.rights)}`.trim();
  const normalizedLicense = normalizeText(licenseText);
  const restricted = document?.["access-restricted-item"] === true
    || normalizeText(document?.["access-restricted-item"]) === "true";
  const isCreativeCommons = normalizedLicense.includes("creativecommons org");
  const isPublicDomain = normalizedLicense.includes("publicdomain") || normalizedLicense.includes("public domain");
  if (!identifier || !title || restricted || (!isCreativeCommons && !isPublicDomain)) return null;

  const access = isPublicDomain ? "public_domain" : "creative_commons";
  const formats = directFormats(identifier, payload);
  const sourceUrl = `https://archive.org/details/${encodeURIComponent(identifier)}`;
  const provider = {
    source: "Internet Archive",
    source_id: identifier,
    source_url: sourceUrl,
    language: languageCode(document.language),
    formats,
    access,
    license: licenseText,
    verified_legal: true,
  };
  const creators = Array.isArray(document.creator) ? document.creator : [document.creator];
  const subjects = Array.isArray(document.subject) ? document.subject : [document.subject];
  const isbns = Array.isArray(document.isbn) ? document.isbn : [document.isbn];

  return {
    id: `live:internetarchive:${identifier}`,
    title,
    authors: creators.filter(Boolean).map(String).slice(0, 8),
    language: provider.language,
    available_languages: [provider.language],
    year: Number(String(document.year || document.date || "").match(/\d{4}/)?.[0]) || null,
    publisher: String(firstValue(document.publisher)).trim(),
    isbn: isbns.filter(Boolean).map((value) => String(value).replace(/[^\dX]/gi, "").toUpperCase()),
    doi: "",
    subjects: subjects.filter(Boolean).map(String).slice(0, 30),
    description: String(firstValue(document.description)).replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim(),
    source: "Internet Archive",
    source_url: sourceUrl,
    cover_url: `https://archive.org/services/img/${encodeURIComponent(identifier)}`,
    formats,
    access,
    license: licenseText,
    verified_legal: true,
    resource_type: "book",
    identifiers: { source_id: identifier, internet_archive: identifier, live_discovery: "true" },
    providers: [provider],
    live_discovery: true,
  };
}

export async function discoverInternetArchive(query, {
  fetchImpl = globalThis.fetch,
  limit = 8,
  signal,
} = {}) {
  if (!normalizeText(query)) return [];
  const response = await fetchImpl(buildInternetArchiveSearchUrl(query, { limit }), {
    headers: { Accept: "application/json" }, signal,
  });
  if (!response.ok) throw new Error(`Internet Archive: HTTP ${response.status}`);
  const payload = await response.json();
  const docs = Array.isArray(payload?.response?.docs) ? payload.response.docs : [];
  const detailed = await Promise.allSettled(docs.map(async (document) => {
    const identifier = String(document?.identifier || "").trim();
    if (!identifier) return null;
    const metadataResponse = await fetchImpl(`https://archive.org/metadata/${encodeURIComponent(identifier)}`, {
      headers: { Accept: "application/json" }, signal,
    });
    const item = metadataResponse.ok ? await metadataResponse.json() : {};
    return mapInternetArchiveDocument(document, item);
  }));
  return detailed.flatMap((result) => result.status === "fulfilled" && result.value ? [result.value] : []);
}
