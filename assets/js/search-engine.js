const documentCache = new WeakMap();

const LANGUAGE_ALIASES = new Map([
  ["es", "es"], ["spa", "es"], ["esp", "es"], ["espanol", "es"], ["castellano", "es"], ["spanish", "es"],
  ["en", "en"], ["eng", "en"], ["ingles", "en"], ["english", "en"],
  ["fr", "fr"], ["fra", "fr"], ["frances", "fr"], ["french", "fr"],
  ["pt", "pt"], ["por", "pt"], ["portugues", "pt"], ["portuguese", "pt"],
  ["de", "de"], ["deu", "de"], ["aleman", "de"], ["german", "de"],
]);

// Two-letter codes are intentionally omitted here: in Spanish, "en" is
// normally a preposition. Codes remain available through idioma:/lang:.
const IMPLICIT_LANGUAGE_ALIASES = new Map([
  ["spa", "es"], ["esp", "es"], ["espanol", "es"], ["castellano", "es"], ["spanish", "es"],
  ["eng", "en"], ["ingles", "en"], ["english", "en"],
  ["fra", "fr"], ["frances", "fr"], ["french", "fr"],
  ["por", "pt"], ["portugues", "pt"], ["portuguese", "pt"],
  ["deu", "de"], ["aleman", "de"], ["german", "de"],
]);

const FIELD_ALIASES = new Map([
  ["title", "title"], ["titulo", "title"],
  ["author", "author"], ["autor", "author"],
  ["isbn", "isbn"], ["doi", "doi"],
  ["publisher", "publisher"], ["editorial", "publisher"],
  ["subject", "subject"], ["topic", "subject"], ["tema", "subject"], ["materia", "subject"],
  ["language", "language"], ["lang", "language"], ["idioma", "language"],
  ["format", "format"], ["formato", "format"],
  ["source", "source"], ["fuente", "source"],
  ["access", "access"], ["acceso", "access"],
  ["year", "year"], ["ano", "year"],
  ["edition", "edition"], ["edicion", "edition"],
  ["type", "resourceType"], ["tipo", "resourceType"],
]);

const ACCESS_ALIASES = new Map([
  ["dominio publico", "public_domain"], ["public domain", "public_domain"], ["public_domain", "public_domain"],
  ["creative commons", "creative_commons"], ["cc", "creative_commons"], ["creative_commons", "creative_commons"],
  ["open access", "open_access"], ["oa", "open_access"], ["open_access", "open_access"],
  ["gratis autor", "author_free"], ["author free", "author_free"], ["author_free", "author_free"],
  ["prestamo", "digital_lending"], ["borrow", "digital_lending"], ["digital_lending", "digital_lending"],
  ["preview", "preview"], ["vista previa", "preview"],
  ["ficha", "metadata_only"], ["metadata", "metadata_only"], ["metadata_only", "metadata_only"],
]);

const RESOURCE_TYPE_ALIASES = new Map([
  ["book", "book"], ["libro", "book"],
  ["textbook", "textbook"], ["texto", "textbook"], ["manual", "textbook"],
  ["article", "article"], ["articulo", "article"],
  ["thesis", "thesis"], ["tesis", "thesis"],
  ["other", "other"], ["otro", "other"],
]);

const ACCESS_WEIGHT = {
  public_domain: 60,
  creative_commons: 58,
  open_access: 55,
  author_free: 48,
  digital_lending: 28,
  preview: 15,
  metadata_only: 4,
  unknown: 0,
};

const TRUSTED_CATALOG_SOURCES = new Set([
  "OpenStax",
  "Standard Ebooks",
  "Project Gutenberg",
  "OpenAlex",
  "Open Library",
]);

const STOP_WORDS = new Set([
  "a", "acerca", "al", "algo", "and", "author", "autor", "book", "busca", "buscar", "by",
  "con", "cual", "cuales", "de", "del", "detallado", "detallada", "donde", "ed", "edicion",
  "edition", "el", "en", "encuentra", "encontrar", "ese", "esta", "este", "for", "in", "la",
  "las", "libro", "los", "me", "muy", "necesito", "of", "para", "por", "que", "quiero",
  "sea", "sobre", "the", "to", "trata", "un", "una", "y",
]);

export function normalizeText(value) {
  return String(value ?? "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase()
    .replace(/\b(\d+)(?:st|nd|rd|th)\b/g, "$1")
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim()
    .replace(/\s+/g, " ");
}

function normalizedAlias(map, value) {
  const normalized = normalizeText(value);
  return map.get(normalized) || normalized.replace(/\s+/g, "_");
}

export function parseSearchQuery(query) {
  const raw = String(query ?? "").trim();
  const fields = {};
  const terms = [];
  const phrases = [];
  const matcher = /(?:(?<field>[\p{L}_-]+):)?(?:"(?<quoted>[^"]+)"|(?<bare>\S+))/gu;

  for (const match of raw.matchAll(matcher)) {
    const value = String(match.groups.quoted ?? match.groups.bare ?? "").trim();
    if (!normalizeText(value)) continue;
    const rawField = normalizeText(match.groups.field || "").replace(/\s+/g, "_");
    const field = FIELD_ALIASES.get(rawField);
    if (field) {
      fields[field] ||= [];
      fields[field].push(value);
    } else if (match.groups.quoted !== undefined && !rawField) {
      phrases.push(value);
    } else {
      terms.push(rawField ? `${match.groups.field}:${value}` : value);
    }
  }

  const requestedLanguages = new Set();
  normalizeText([...terms, ...phrases].join(" ")).split(" ").forEach((token) => {
    const language = IMPLICIT_LANGUAGE_ALIASES.get(token);
    if (language) requestedLanguages.add(language);
  });
  for (const value of fields.language || []) {
    const language = LANGUAGE_ALIASES.get(normalizeText(value));
    if (language) requestedLanguages.add(language);
  }

  return {
    raw,
    fields,
    terms,
    phrases,
    text: normalizeText([...terms, ...phrases].join(" ")),
    requestedLanguages: [...requestedLanguages],
    hasStructuredFields: Object.keys(fields).length > 0,
  };
}

function bookLanguages(book) {
  return [...new Set([book.language, ...(book.available_languages || [])].filter(Boolean))];
}

function docFor(book) {
  if (documentCache.has(book)) return documentCache.get(book);
  const title = normalizeText(book.title);
  const authors = normalizeText((book.authors || []).join(" "));
  const subjects = normalizeText((book.subjects || []).join(" "));
  const description = normalizeText([book.subtitle, book.description].filter(Boolean).join(" "));
  const topics = `${subjects} ${description}`.trim();
  const publisher = normalizeText(book.publisher);
  const isbn = (book.isbn || []).map((value) => String(value).replace(/[^\dX]/gi, "").toUpperCase());
  const doi = normalizeText(book.doi).replace(/\s+/g, "");
  const sources = (book.providers || [{ source: book.source }]).map((provider) => provider.source).filter(Boolean);
  const titleTokens = [...new Set(title.split(" ").filter(Boolean))];
  const authorTokens = [...new Set(authors.split(" ").filter(Boolean))];
  const subjectTokens = [...new Set(topics.split(" ").filter(Boolean))];
  const publisherTokens = [...new Set(publisher.split(" ").filter(Boolean))];
  const tokens = [...new Set([...titleTokens, ...authorTokens, ...subjectTokens, ...publisherTokens])];
  const doc = {
    title,
    authors,
    subjects,
    description,
    topics,
    publisher,
    isbn,
    doi,
    sources,
    normalizedSources: sources.map(normalizeText),
    titleTokens,
    authorTokens,
    subjectTokens,
    publisherTokens,
    tokens,
    searchable: `${title} ${authors} ${topics} ${publisher}`.trim(),
  };
  documentCache.set(book, doc);
  return doc;
}

function trigramSimilarity(left, right) {
  if (left === right) return 1;
  if (left.length < 3 || right.length < 3) return 0;
  const grams = (text) => {
    const result = new Set();
    const padded = `  ${text} `;
    for (let index = 0; index <= padded.length - 3; index += 1) result.add(padded.slice(index, index + 3));
    return result;
  };
  const a = grams(left);
  const b = grams(right);
  let common = 0;
  a.forEach((gram) => { if (b.has(gram)) common += 1; });
  return (2 * common) / (a.size + b.size);
}

function boundedDamerauLevenshtein(left, right, limit) {
  if (Math.abs(left.length - right.length) > limit) return limit + 1;
  let previousPrevious = null;
  let previous = Array.from({ length: right.length + 1 }, (_, index) => index);
  for (let row = 1; row <= left.length; row += 1) {
    const current = [row];
    let rowMin = row;
    for (let column = 1; column <= right.length; column += 1) {
      const cost = left[row - 1] === right[column - 1] ? 0 : 1;
      let value = Math.min(
        current[column - 1] + 1,
        previous[column] + 1,
        previous[column - 1] + cost,
      );
      if (
        previousPrevious
        && row > 1
        && column > 1
        && left[row - 1] === right[column - 2]
        && left[row - 2] === right[column - 1]
      ) {
        value = Math.min(value, previousPrevious[column - 2] + 1);
      }
      current[column] = value;
      rowMin = Math.min(rowMin, value);
    }
    if (rowMin > limit) return limit + 1;
    previousPrevious = previous;
    previous = current;
  }
  return previous[right.length];
}

export function fuzzyTokenScore(queryToken, candidate) {
  if (queryToken === candidate) return 1;
  const shortest = Math.min(queryToken.length, candidate.length);
  if (shortest >= 3 && (candidate.startsWith(queryToken) || queryToken.startsWith(candidate))) return 0.88;
  if (shortest >= 4 && (candidate.includes(queryToken) || queryToken.includes(candidate))) return 0.72;
  if (queryToken.length < 4 || candidate.length < 4) return 0;
  const trigram = trigramSimilarity(queryToken, candidate);
  if (trigram < 0.28) return 0;
  const limit = Math.min(3, Math.max(1, Math.floor(Math.max(queryToken.length, candidate.length) / 3)));
  const distance = boundedDamerauLevenshtein(queryToken, candidate, limit);
  return distance <= limit ? Math.max(0.42, 1 - distance / Math.max(queryToken.length, candidate.length)) : 0;
}

function bestTokenScore(queryToken, candidates, { fuzzy = false } = {}) {
  let best = 0;
  for (const candidate of candidates) {
    let match = 0;
    if (queryToken === candidate) match = 1;
    else if (Math.min(queryToken.length, candidate.length) >= 3 && (candidate.startsWith(queryToken) || queryToken.startsWith(candidate))) match = 0.88;
    else if (Math.min(queryToken.length, candidate.length) >= 4 && (candidate.includes(queryToken) || queryToken.includes(candidate))) match = 0.72;
    else if (fuzzy) match = fuzzyTokenScore(queryToken, candidate);
    if (match > best) best = match;
    if (best === 1) break;
  }
  return best;
}

function looseFieldMatch(haystack, value, { exact = false } = {}) {
  const needle = normalizeText(value);
  if (!needle) return true;
  if (exact) return haystack === needle;
  if (haystack.includes(needle)) return true;
  const candidates = haystack.split(" ").filter(Boolean);
  return needle.split(" ").filter(Boolean).every((token) => bestTokenScore(token, candidates, { fuzzy: true }) >= 0.72);
}

function matchesAnyValue(haystack, values, options) {
  return !values?.length || values.some((value) => looseFieldMatch(haystack, value, options));
}

function matchesYear(bookYear, values) {
  if (!values?.length) return true;
  if (!bookYear) return false;
  return values.some((value) => {
    const years = String(value).match(/\d{3,4}/g)?.map(Number) || [];
    if (!years.length) return false;
    if (years.length === 1) return bookYear === years[0];
    const [from, to] = years.slice(0, 2).sort((a, b) => a - b);
    return bookYear >= from && bookYear <= to;
  });
}

function matchesStructuredFields(book, doc, fields) {
  if (!matchesAnyValue(doc.title, fields.title)) return false;
  if (!matchesAnyValue(doc.authors, fields.author)) return false;
  if (!matchesAnyValue(doc.topics, fields.subject)) return false;
  if (!matchesAnyValue(doc.publisher, fields.publisher)) return false;

  if (fields.isbn?.length) {
    const requested = fields.isbn.map((value) => String(value).replace(/[^\dX]/gi, "").toUpperCase()).filter(Boolean);
    if (!requested.some((value) => doc.isbn.includes(value))) return false;
  }
  if (fields.doi?.length) {
    const requested = fields.doi.map((value) => normalizeText(value).replace(/^doi\s*/, "").replace(/\s+/g, ""));
    if (!requested.includes(doc.doi)) return false;
  }
  if (fields.language?.length) {
    const requested = fields.language.map((value) => LANGUAGE_ALIASES.get(normalizeText(value))).filter(Boolean);
    if (!requested.length || !requested.some((value) => bookLanguages(book).includes(value))) return false;
  }
  if (fields.format?.length) {
    const formats = new Set((book.formats || []).map((item) => normalizeText(item.type)));
    if (!fields.format.some((value) => formats.has(normalizeText(value)))) return false;
  }
  if (fields.source?.length && !fields.source.some((value) =>
    doc.normalizedSources.some((source) => looseFieldMatch(source, value)))) return false;
  if (fields.access?.length) {
    const requested = fields.access.map((value) => normalizedAlias(ACCESS_ALIASES, value));
    if (!requested.includes(book.access)) return false;
  }
  if (fields.resourceType?.length) {
    const requested = fields.resourceType.map((value) => normalizedAlias(RESOURCE_TYPE_ALIASES, value));
    if (!requested.includes(book.resource_type)) return false;
  }
  if (!matchesYear(book.year, fields.year)) return false;
  if (fields.edition?.length) {
    const editionText = `${doc.title} ${normalizeText(book.identifiers?.edition || "")}`;
    if (!fields.edition.some((value) => looseFieldMatch(editionText, value))) return false;
  }
  return true;
}

function queryIdentifierMatches(parsed, doc) {
  const isbnCandidates = parsed.raw.split(/\s+/).map((value) => value.replace(/[^\dX]/gi, "").toUpperCase())
    .filter((value) => value.length === 10 || value.length === 13);
  const exactIsbn = isbnCandidates.some((value) => doc.isbn.includes(value));
  const doiCandidate = parsed.raw.match(/10\.\d{4,9}\/[-._;()/:A-Z0-9]+/i)?.[0] || "";
  const exactDoi = doiCandidate && normalizeText(doiCandidate).replace(/\s+/g, "") === doc.doi;
  return { exactIsbn, exactDoi };
}

function scoreBook(book, parsed) {
  const doc = docFor(book);
  if (!matchesStructuredFields(book, doc, parsed.fields)) return 0;

  const phraseValues = parsed.phrases.map(normalizeText).filter(Boolean);
  let score = parsed.hasStructuredFields ? 35 : 0;
  for (const phrase of phraseValues) {
    if (!doc.searchable.includes(phrase)) return 0;
    if (doc.title.includes(phrase)) score += 260;
    else if (doc.authors.includes(phrase)) score += 190;
    else if (doc.topics.includes(phrase)) score += 120;
    else score += 70;
  }

  const queryTokens = [...new Set(parsed.text.split(" ").filter(Boolean))];
  const contentQueryTokens = queryTokens.filter((token) =>
    !IMPLICIT_LANGUAGE_ALIASES.has(token) && !STOP_WORDS.has(token)
  );
  const normalizedQuery = contentQueryTokens.join(" ");
  const { exactIsbn, exactDoi } = queryIdentifierMatches(parsed, doc);

  if (normalizedQuery && doc.title === normalizedQuery) score += 600;
  else if (normalizedQuery && doc.title.startsWith(normalizedQuery)) score += 330;
  else if (normalizedQuery && doc.title.includes(normalizedQuery)) score += 250;

  const titleHits = contentQueryTokens.filter((token) => doc.titleTokens.includes(token)).length;
  const authorHits = contentQueryTokens.filter((token) => doc.authorTokens.includes(token)).length;
  const meaningfulTitleTokens = doc.titleTokens.filter((token) => !STOP_WORDS.has(token));
  const fullTitleInQuery = meaningfulTitleTokens.length > 0
    && meaningfulTitleTokens.every((token) => contentQueryTokens.includes(token));
  if (fullTitleInQuery && authorHits) score += 520;
  else if (titleHits && authorHits) score += 300;
  if (exactIsbn) score += 700;
  if (exactDoi) score += 760;

  let matchedTokens = 0;
  for (const token of contentQueryTokens) {
    const fieldMatches = [
      { value: bestTokenScore(token, doc.titleTokens, { fuzzy: true }), weight: 118 },
      { value: bestTokenScore(token, doc.authorTokens, { fuzzy: true }), weight: 96 },
      { value: bestTokenScore(token, doc.subjectTokens), weight: 72 },
      { value: bestTokenScore(token, doc.publisherTokens), weight: 44 },
    ];
    const best = fieldMatches.reduce((current, candidate) =>
      candidate.value * candidate.weight > current.value * current.weight ? candidate : current,
    { value: 0, weight: 0 });
    if (best.value >= 0.42) {
      matchedTokens += 1;
      score += best.value * best.weight;
    }
  }

  if (contentQueryTokens.length && matchedTokens === 0 && !exactIsbn && !exactDoi) return 0;
  if (contentQueryTokens.length >= 2 && contentQueryTokens.length <= 4
    && matchedTokens / contentQueryTokens.length < 0.5 && !exactIsbn && !exactDoi) return 0;
  if (contentQueryTokens.length >= 5
    && matchedTokens < Math.max(2, Math.ceil(contentQueryTokens.length * 0.3))
    && !exactIsbn && !exactDoi) return 0;
  if (!contentQueryTokens.length && !phraseValues.length && !parsed.hasStructuredFields && parsed.raw) return 0;
  if (!contentQueryTokens.length && !phraseValues.length && !parsed.hasStructuredFields && !parsed.raw) score = 1;

  if (parsed.requestedLanguages.some((language) => bookLanguages(book).includes(language))) score += 90;
  score += ACCESS_WEIGHT[book.access] || 0;
  if (doc.sources.some((source) => TRUSTED_CATALOG_SOURCES.has(source))) score += 22;
  return score;
}

function matchesUiFilters(book, doc, filters) {
  if (filters.language && !bookLanguages(book).includes(filters.language)) return false;
  if (filters.format && !(book.formats || []).some((item) => item.type === filters.format)) return false;
  if (filters.access && book.access !== filters.access) return false;
  if (filters.source && !doc.sources.includes(filters.source)) return false;
  if (filters.resourceType && book.resource_type !== filters.resourceType) return false;
  if (filters.availability === "direct" && !(book.formats || []).length) return false;
  if (filters.availability === "open" && !["public_domain", "open_access", "creative_commons", "author_free"].includes(book.access)) return false;
  if (filters.title && !looseFieldMatch(doc.title, filters.title, { exact: Boolean(filters.exactTitle) })) return false;
  if (filters.author && !looseFieldMatch(doc.authors, filters.author)) return false;
  if (filters.subject && !looseFieldMatch(doc.topics, filters.subject)) return false;
  if (filters.publisher && !looseFieldMatch(doc.publisher, filters.publisher)) return false;
  if (filters.identifier) {
    const compact = String(filters.identifier).replace(/[^\dX]/gi, "").toUpperCase();
    const normalizedDoi = normalizeText(filters.identifier).replace(/^doi\s*/, "").replace(/\s+/g, "");
    if (!doc.isbn.includes(compact) && doc.doi !== normalizedDoi) return false;
  }
  if (filters.edition) {
    const editionText = `${doc.title} ${normalizeText(book.identifiers?.edition || "")}`;
    if (!looseFieldMatch(editionText, filters.edition)) return false;
  }
  if (filters.yearFrom && (!book.year || book.year < Number(filters.yearFrom))) return false;
  if (filters.yearTo && (!book.year || book.year > Number(filters.yearTo))) return false;
  return true;
}

export function searchBooks(books, query, filters = {}, sort = "relevance") {
  const parsed = parseSearchQuery(query);
  const results = [];

  for (const book of books) {
    const doc = docFor(book);
    if (!matchesUiFilters(book, doc, filters)) continue;
    const score = scoreBook(book, parsed);
    if (score > 0) results.push({ book, score });
  }

  results.sort((left, right) => {
    if (sort === "year-desc") return (right.book.year || 0) - (left.book.year || 0) || right.score - left.score;
    if (sort === "title") return left.book.title.localeCompare(right.book.title, "es", { sensitivity: "base" });
    if (sort === "availability") {
      const leftAccess = ACCESS_WEIGHT[left.book.access] || 0;
      const rightAccess = ACCESS_WEIGHT[right.book.access] || 0;
      return rightAccess - leftAccess
        || (right.book.formats?.length || 0) - (left.book.formats?.length || 0)
        || right.score - left.score;
    }
    return right.score - left.score || (Number(right.book.verified_legal) - Number(left.book.verified_legal));
  });
  return results.map((result) => result.book);
}
