import assert from "node:assert/strict";
import test from "node:test";

import { mapOpenStaxSummary } from "../assets/js/openstax-live.js";
import {
  buildInternetArchiveSearchUrl,
  mapInternetArchiveDocument,
} from "../assets/js/internet-archive-live.js";
import { mergeCatalogRecords } from "../assets/js/open-library-live.js";

test("maps explicit OpenStax PDF and reading links", () => {
  const book = mapOpenStaxSummary({
    id: 7,
    slug: "books/calculus",
    title: "Calculus",
    subjects: ["Math"],
    pdf_url: "https://assets.openstax.org/calculus.pdf",
    webview_rex_link: "https://openstax.org/books/calculus/pages/1-introduction",
  });
  assert.equal(book.source, "OpenStax");
  assert.deepEqual(book.formats.map((format) => format.type), ["pdf", "read"]);
  assert.equal(book.verified_legal, true);
});

test("merges an OpenStax live summary with its catalog record by slug", () => {
  const catalog = [{
    id: "catalog:openstax",
    title: "Calculus",
    authors: ["Ada Author"],
    language: "en",
    identifiers: { openstax_slug: "calculus" },
    providers: [{ source: "OpenStax", source_id: "uuid-7", formats: [] }],
    formats: [],
    access: "open_access",
  }];
  const live = mapOpenStaxSummary({ id: 7, slug: "books/calculus", title: "Calculus" });
  assert.equal(mergeCatalogRecords(catalog, [live]).length, 1);
});

test("Internet Archive live search requires explicit licensing", () => {
  const url = new URL(buildInternetArchiveSearchUrl("calculus physics"));
  assert.match(url.searchParams.get("q"), /licenseurl:\*/);
  assert.match(url.searchParams.get("q"), /"calculus" AND "physics"/);
});

test("maps only explicit unrestricted Internet Archive files", () => {
  const book = mapInternetArchiveDocument(
    {
      identifier: "open-calculus",
      title: "Open Calculus",
      creator: "Ada Author",
      language: "eng",
      licenseurl: "https://creativecommons.org/licenses/by/4.0/",
    },
    {
      metadata: {},
      files: [
        { name: "open-calculus.pdf", format: "Text PDF", source: "derivative" },
        { name: "private.epub", format: "EPUB", private: "true" },
      ],
    },
  );
  assert.equal(book.access, "creative_commons");
  assert.deepEqual(book.formats, [
    { type: "pdf", url: "https://archive.org/download/open-calculus/open-calculus.pdf" },
  ]);
});
