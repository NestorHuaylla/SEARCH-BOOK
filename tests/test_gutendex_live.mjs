import assert from "node:assert/strict";
import test from "node:test";

import {
  buildGutendexSearchUrl,
  discoverGutendexBilingual,
  mapGutendexBook,
} from "../assets/js/gutendex-live.js";

const publicDomainBook = {
  id: 123,
  title: "Don Quijote",
  authors: [{ name: "Cervantes Saavedra, Miguel de" }],
  languages: ["es"],
  copyright: false,
  subjects: ["Knights and knighthood -- Fiction"],
  bookshelves: ["Best Books Ever Listings"],
  formats: {
    "text/html": "https://www.gutenberg.org/ebooks/123.html.images",
    "application/epub+zip": "https://www.gutenberg.org/ebooks/123.epub3.images",
    "image/jpeg": "https://www.gutenberg.org/cache/epub/123/pg123.cover.medium.jpg",
  },
};

test("builds language-restricted public-domain discovery URLs", () => {
  const url = new URL(buildGutendexSearchUrl("Don Quijote", { language: "es" }));
  assert.equal(url.searchParams.get("search"), "Don Quijote");
  assert.equal(url.searchParams.get("languages"), "es");
  assert.equal(url.searchParams.get("copyright"), "false");
});

test("maps only explicitly public-domain downloads", () => {
  const book = mapGutendexBook(publicDomainBook);
  assert.equal(book.language, "es");
  assert.equal(book.access, "public_domain");
  assert.deepEqual(book.formats.map((format) => format.type), ["html", "epub"]);

  const uncertain = mapGutendexBook({ ...publicDomainBook, id: 124, copyright: null });
  assert.equal(uncertain.access, "metadata_only");
  assert.deepEqual(uncertain.formats, []);
  assert.equal(mapGutendexBook(publicDomainBook, { language: "en" }), null);
});

test("queries Spanish and English independently and removes duplicate works", async () => {
  const urls = [];
  const books = await discoverGutendexBilingual("Cervantes", {
    fetchImpl: async (url) => {
      urls.push(new URL(url));
      return { ok: true, json: async () => ({ results: [publicDomainBook] }) };
    },
  });
  assert.equal(urls.length, 2);
  assert.equal(urls[0].searchParams.get("languages"), "es");
  assert.equal(urls[1].searchParams.get("languages"), "en");
  assert.equal(books.length, 1);
});
