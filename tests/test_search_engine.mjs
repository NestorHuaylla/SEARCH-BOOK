import assert from "node:assert/strict";
import test from "node:test";

import { normalizeText, parseSearchQuery, searchBooks } from "../assets/js/search-engine.js";

const books = [
  {
    id: "1",
    title: "Algorithms",
    authors: ["Robert Sedgewick"],
    language: "en",
    year: 2011,
    publisher: "Official Press",
    isbn: ["9780321573513"],
    subjects: ["Computer Science"],
    formats: [{ type: "pdf", url: "https://example.org/algorithms.pdf" }],
    access: "open_access",
    verified_legal: true,
    source: "OpenStax",
    providers: [{ source: "OpenStax" }],
  },
  {
    id: "2",
    title: "Métodos numéricos",
    authors: ["Ana Pérez"],
    language: "es",
    year: 2024,
    publisher: "Universidad Abierta",
    isbn: ["9780306406157"],
    subjects: ["Matemáticas"],
    formats: [{ type: "epub", url: "https://example.org/metodos.epub" }],
    access: "creative_commons",
    verified_legal: true,
    source: "Open Library",
    providers: [{ source: "Open Library" }],
  },
  {
    id: "3",
    title: "An unrelated title",
    authors: ["Different Author"],
    language: "en",
    year: 2020,
    publisher: "Publisher",
    isbn: [],
    subjects: ["Sedguivx"],
    formats: [],
    access: "metadata_only",
    verified_legal: false,
    source: "Source",
    providers: [{ source: "Source" }],
  },
  {
    id: "4",
    title: "Software Engineering, 10th Edition",
    authors: ["Ian Sommerville"],
    language: "en",
    year: 2015,
    publisher: "Pearson",
    isbn: ["9780133943030", "013242701X"],
    subjects: ["Software engineering"],
    formats: [],
    access: "metadata_only",
    verified_legal: false,
    source: "Open Library",
    providers: [{ source: "Open Library" }],
  },
  {
    id: "5",
    title: "Python para ciencia de datos",
    authors: ["Lucía Torres"],
    language: "es",
    year: 2022,
    publisher: "Universidad Abierta",
    isbn: ["9781491912058"],
    doi: "10.1234/python.data",
    subjects: ["Aprendizaje automático", "Visualización estadística", "Análisis de datos"],
    description: "Incluye modelos predictivos, preparación de datos y evaluación reproducible.",
    formats: [{ type: "pdf", url: "https://example.org/python-data.pdf" }],
    access: "open_access",
    verified_legal: true,
    source: "OpenStax",
    resource_type: "textbook",
    identifiers: { edition: "2" },
    providers: [{ source: "OpenStax" }],
  },
];

test("normalizes accents and case", () => {
  assert.equal(normalizeText(" MÉTODOS Numéricos "), "metodos numericos");
  assert.equal(normalizeText("10th Edition"), "10 edition");
});

test("finds a misspelled author", () => {
  assert.deepEqual(searchBooks(books, "sedguivk").map((book) => book.id), ["1"]);
});

test("finds exact ISBN", () => {
  assert.equal(searchBooks(books, "978-0-306-40615-7")[0]?.id, "2");
  assert.equal(searchBooks(books, "0-13-242701-X")[0]?.id, "4");
  assert.equal(searchBooks(books, "isbn:013242701X")[0]?.id, "4");
});

test("understands a requested language", () => {
  assert.equal(searchBooks(books, "métodos numéricos español")[0]?.id, "2");
});

test("deduces a title, author and edition despite punctuation or typos", () => {
  assert.equal(
    searchBooks(books, "Ian Sommerville — Software Engineering (10th Edition)")[0]?.id,
    "4",
  );
  assert.equal(
    searchBooks(books, "Ian Somervile sofware enginering 10th edtion")[0]?.id,
    "4",
  );
});

test("keeps a bibliographic trace outside an incompatible PDF filter", () => {
  assert.deepEqual(searchBooks(books, "Ian Sommerville Software Engineering", { format: "pdf" }), []);
  assert.equal(searchBooks(books, "Ian Sommerville Software Engineering")[0]?.id, "4");
});

test("applies format and subject filters", () => {
  assert.deepEqual(
    searchBooks(books, "métodos", { format: "epub", subject: "matem" }).map((book) => book.id),
    ["2"],
  );
  assert.deepEqual(searchBooks(books, "métodos", { format: "pdf" }), []);
});

test("parses quoted field operators in Spanish and English", () => {
  const parsed = parseSearchQuery('titulo:"Software Engineering" author:Sommerville idioma:en edicion:10');
  assert.deepEqual(parsed.fields.title, ["Software Engineering"]);
  assert.deepEqual(parsed.fields.author, ["Sommerville"]);
  assert.deepEqual(parsed.fields.language, ["en"]);
  assert.deepEqual(parsed.fields.edition, ["10"]);
});

test("uses structured fields as strict constraints", () => {
  assert.deepEqual(
    searchBooks(books, 'titulo:"Software Engineering" autor:Sommerville idioma:en edicion:10')
      .map((book) => book.id),
    ["4"],
  );
  assert.deepEqual(searchBooks(books, "titulo:Algorithms idioma:es"), []);
});

test("finds a relevant book from a long natural-language description", () => {
  const results = searchBooks(
    books,
    "quiero un libro detallado sobre python para ciencia de datos aprendizaje automático y visualización estadística",
  );
  assert.equal(results[0]?.id, "5");
  assert.equal(
    searchBooks(books, "necesito modelos predictivos con preparación y evaluación reproducible")[0]?.id,
    "5",
  );
});

test("matches DOI exactly and supports advanced-filter-only searches", () => {
  assert.equal(searchBooks(books, "doi:10.1234/python.data")[0]?.id, "5");
  assert.deepEqual(searchBooks(books, "", { author: "Lucia Torres" }).map((book) => book.id), ["5"]);
  assert.deepEqual(searchBooks(books, "", { title: "Python", exactTitle: true }), []);
});
