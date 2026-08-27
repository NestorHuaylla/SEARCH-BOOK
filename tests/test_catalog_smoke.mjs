import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { normalizeText, searchBooks } from "../assets/js/search-engine.js";

const metadata = JSON.parse(fs.readFileSync("data/metadata.json", "utf8"));
const books = metadata.shards.flatMap(({ path }) => JSON.parse(fs.readFileSync(path, "utf8")));

function identities(results) {
  return results.slice(0, 5).map((book) => normalizeText(`${book.title} ${(book.authors || []).join(" ")}`));
}

test("published catalog matches the primary example queries", () => {
  assert.match(identities(searchBooks(books, "python"))[0], /python/);
  assert.match(identities(searchBooks(books, "métodos numéricos español"))[0], /metodos numericos/);
  assert.match(identities(searchBooks(books, "algorithms sedgewick"))[0], /algorithms.*sedgewick/);
  assert.ok(identities(searchBooks(books, "sedguivk")).some((value) => value.includes("sedgewick")));
  assert.match(identities(searchBooks(books, "fundamentos de algoritmia brassard"))[0], /fundamentos de algoritmia.*brassard/);
});

