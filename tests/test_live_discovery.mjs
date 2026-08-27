import assert from "node:assert/strict";
import test from "node:test";

import {
  buildOpenLibrarySearchUrl,
  discoverOpenLibrary,
  discoverOpenLibraryBilingual,
  externalCatalogLinks,
  mapOpenLibraryDocument,
  mergeCatalogRecords,
  relaxedBibliographicQuery,
} from "../assets/js/open-library-live.js";

const openLibraryDocument = {
  key: "/works/OL20100688W",
  title: "Software Engineering",
  author_name: ["Ian Sommerville", "Sommerville, Ian."],
  first_publish_year: 2015,
  publisher: ["Pearson"],
  isbn: ["978-0-13-394303-0"],
  language: ["eng"],
  cover_i: 123,
  ebook_access: "borrowable",
  subject: ["Software engineering"],
  editions: {
    docs: [
      {
        key: "OL50512076M",
        title: "Software Engineering",
        language: ["eng"],
        publish_date: "2015",
        publisher: ["Pearson"],
        isbn: ["9780133943030"],
        edition_name: ["10th edition"],
        ebook_access: "borrowable",
      },
      {
        key: "OL99999999M",
        title: "Ingeniería de software",
        language: ["spa"],
        publish_date: "2016",
        publisher: ["Pearson Educación"],
        isbn: ["9788490351234"],
        ebook_access: "no_ebook",
      },
    ],
  },
};

test("builds a bounded Open Library query without losing the user's words", () => {
  const url = new URL(buildOpenLibrarySearchUrl("  Ian Sommerville   Software Engineering  ", { limit: 99 }));
  assert.equal(url.origin, "https://openlibrary.org");
  assert.equal(url.pathname, "/search.json");
  assert.equal(url.searchParams.get("q"), "Ian Sommerville Software Engineering");
  assert.equal(url.searchParams.get("limit"), "20");
  assert.match(url.searchParams.get("fields"), /ebook_access/);
  assert.match(url.searchParams.get("fields"), /editions\.language/);
});

test("builds a strict language query for edition discovery", () => {
  const url = new URL(buildOpenLibrarySearchUrl("Software Engineering", { language: "es" }));
  assert.match(url.searchParams.get("q"), /language:spa/);
  assert.equal(url.searchParams.get("lang"), "es");
});

test("relaxes edition wording that would hide the matching Open Library work", () => {
  assert.equal(
    relaxedBibliographicQuery("Ian Sommerville — Software Engineering (10th Edition)"),
    "ian sommerville software engineering",
  );
  assert.equal(relaxedBibliographicQuery("Clean Code Robert Martin"), "Clean Code Robert Martin");
});

test("maps live metadata without inventing a PDF", () => {
  const book = mapOpenLibraryDocument(openLibraryDocument);
  assert.equal(book.title, "Software Engineering");
  assert.deepEqual(book.authors, ["Ian Sommerville"]);
  assert.equal(book.language, "en");
  assert.equal(book.access, "digital_lending");
  assert.deepEqual(book.formats, []);
  assert.equal(book.source_url, "https://openlibrary.org/works/OL20100688W");
});

test("only creates a read action when Open Library reports public access", () => {
  const book = mapOpenLibraryDocument({ ...openLibraryDocument, ebook_access: "public" });
  assert.equal(book.access, "open_access");
  assert.deepEqual(book.formats, [
    { type: "read", url: "https://openlibrary.org/works/OL20100688W" },
  ]);
});

test("discovers and maps API documents through an injectable fetch", async () => {
  const books = await discoverOpenLibrary("software engineering sommerville", {
    fetchImpl: async () => ({
      ok: true,
      json: async () => ({ docs: [openLibraryDocument, { title: "Missing key" }] }),
    }),
  });
  assert.equal(books.length, 1);
  assert.equal(books[0].id, "live:openlibrary:OL20100688W:en");
});

test("maps a concrete Spanish edition separately from the English edition", () => {
  const spanish = mapOpenLibraryDocument(openLibraryDocument, { language: "es" });
  const english = mapOpenLibraryDocument(openLibraryDocument, { language: "en" });
  assert.equal(spanish.title, "Ingeniería de software");
  assert.equal(spanish.language, "es");
  assert.equal(spanish.identifiers.openlibrary_edition, "OL99999999M");
  assert.equal(english.language, "en");
  assert.equal(english.identifiers.edition, "10th edition");
  assert.notEqual(spanish.id, english.id);
});

test("discovers Spanish and English editions with separate API queries", async () => {
  const urls = [];
  const books = await discoverOpenLibraryBilingual("software engineering", {
    pauseBetweenLanguagesMs: 0,
    fetchImpl: async (url) => {
      urls.push(new URL(url));
      return { ok: true, json: async () => ({ docs: [openLibraryDocument] }) };
    },
  });
  assert.equal(urls.length, 2);
  assert.match(urls[0].searchParams.get("q"), /language:spa/);
  assert.match(urls[1].searchParams.get("q"), /language:eng/);
  assert.deepEqual(new Set(books.map((book) => book.language)), new Set(["es", "en"]));
});

test("does not duplicate a live edition already present in the catalog", () => {
  const live = mapOpenLibraryDocument(openLibraryDocument);
  const catalog = [{
    ...live,
    id: "catalog:software-engineering",
    title: "Software Engineering, 10th Edition",
  }];
  assert.equal(mergeCatalogRecords(catalog, [live]).length, 1);
});

test("creates safe catalog continuation links", () => {
  const links = externalCatalogLinks("Software Engineering & testing");
  assert.match(links.openLibrary, /^https:\/\/openlibrary\.org\/search\?q=/);
  assert.match(links.googleBooks, /Software%20Engineering%20%26%20testing/);
  assert.match(links.worldCat, /^https:\/\/search\.worldcat\.org\/search\?q=/);
  assert.match(links.openLibrarySpanish, /language=spa/);
  assert.match(links.googleBooksSpanish, /lr=lang_es/);
  assert.match(links.gutenberg, /^https:\/\/www\.gutenberg\.org/);
});
