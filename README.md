# OpenBook Search

OpenBook Search es un buscador web estático de libros, textos universitarios y publicaciones que una fuente legítima ofrece como dominio público, Open Access, Creative Commons, distribución gratuita, préstamo digital o preview oficial.

No aloja PDFs, no descubre mirrors y no intenta eludir paywalls. El catálogo contiene metadatos y enlaces a los proveedores originales. Si una fuente no confirma el acceso, la interfaz muestra únicamente **Ver fuente**.

## Arquitectura

```text
APIs / feeds / RAW oficiales
            │
            ▼
scripts/providers/*.py      obtención aislada por fuente
            │
            ▼
normalize.py                limpieza, URLs, ISBN, DOI, acceso
            │
            ▼
deduplicate.py              obra única + múltiples proveedores
            │
            ▼
data/books.json + shards    almacenamiento estático validado
            │
            ▼
GitHub Pages                buscador JavaScript en el navegador
```

La obtención, normalización, almacenamiento, búsqueda y UI son capas separadas. `assets/js/search-engine.js` es la frontera sustituible por Typesense, Meilisearch, OpenSearch o PostgreSQL full-text en una etapa futura; los providers no tendrían que cambiar.

## Fuentes

| Fuente | Integración | Regla de acceso |
|---|---|---|
| Free Programming Books | RAW oficial de la lista española | Recurso curado como disponible gratuitamente; licencia CC sólo cuando la lista la declara |
| Project Gutenberg | [Gutendex `/books`](https://gutendex.com/), snapshot y consulta en vivo ES/EN | Sólo expone archivos cuando Gutendex declara `copyright=false`; dominio público en Estados Unidos y sujeto a la jurisdicción del usuario |
| Open Library | [`/search.json`](https://openlibrary.org/dev/docs/api/search), snapshot y consulta en vivo | Distingue lectura pública, préstamo, preview y sólo ficha; no genera URLs PDF |
| OpenStax | API pública del CMS | PDF/lectura de OpenStax; la licencia exacta se obtiene de la ficha individual |
| Standard Ebooks | Feed Atom público de novedades | Usa únicamente enclosures y derechos del feed oficial |
| OpenAlex | [`/works`](https://developers.openalex.org/api-reference/works) | Sólo `best_oa_location` confirmada como OA; PDF sólo si esa ubicación lo proporciona |
| Internet Archive | Advanced Search | Nunca genera archivos; CC/dominio público sólo con metadatos explícitos y préstamo cuando está restringido |

Open Library solicita bajo volumen, caché y un `User-Agent` identificable. La sincronización hace pocas consultas configurables y conserva el último snapshot ante fallos. En el navegador, cada consulta nueva se busca por separado en español e inglés, de forma secuencial y con pausa entre solicitudes; los resultados se mantienen en caché durante la sesión. La integración pide metadatos de edición y no atribuye a una edición el archivo de otra.

Gutendex se consulta en vivo por separado para español e inglés. Es un proyecto comunitario que refleja el catálogo de Project Gutenberg, no una API oficial de Gutenberg; por eso funciona como descubrimiento complementario y el snapshot local sigue siendo la base estable.

Standard Ebooks publica libremente el feed de novedades; otros feeds pueden requerir membresía. Por eso la integración predeterminada no intenta descargar el catálogo completo ni hace scraping.

OpenAlex puede requerir una API key según su política vigente. La clave se lee en Python desde `OPENALEX_API_KEY`; nunca se publica en JavaScript ni en el catálogo.

## Requisitos y ejecución local

- Python 3.11 o posterior.
- Conexión a Internet sólo para sincronizar.
- Ningún Node.js, Docker, servidor de base de datos ni proceso permanente.

```bash
python -m venv .venv
```

En PowerShell:

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts/update_books.py
python -m scripts.validate
python -m pytest -q
node --test tests/*.mjs
python -m http.server 8000
```

Abre `http://localhost:8000`. No abras `index.html` directamente: los navegadores bloquean `fetch()` sobre `file://`.

Para probar una sola fuente sin borrar las demás:

```powershell
python scripts/update_books.py --provider "Project Gutenberg"
python scripts/update_books.py --list-providers
```

## Publicación inicial en GitHub

Si la carpeta todavía no es un repositorio, inicialízala y súbela a un repositorio público vacío:

```powershell
git init -b main
git add .
git commit -m "feat: initial OpenBook Search implementation"
git remote add origin https://github.com/TU_USUARIO/openbook-search.git
git push -u origin main
```

No incluyas `.venv`; ya está ignorado. Después habilita GitHub Actions y selecciona **GitHub Actions** como origen en **Settings → Pages**. No hace falta copiar archivos a una rama `gh-pages`.

## Configuración

Todas las opciones son variables de entorno y son opcionales.

| Variable | Predeterminado | Uso |
|---|---:|---|
| `OPENBOOK_CONTACT_EMAIL` | vacío | Identificación cortés ante APIs |
| `OPENBOOK_REQUEST_TIMEOUT` | `30` | Timeout HTTP en segundos |
| `OPENBOOK_SHARD_SIZE` | `1000` | Obras por fragmento web |
| `OPENBOOK_INLINE_CATALOG_LIMIT` | `5000` | Máximo antes de dejar `books.json` como manifiesto |
| `OPENBOOK_GUTENBERG_MAX_PAGES` | `10` | Páginas Gutendex por ejecución |
| `OPENBOOK_OPENLIBRARY_LIMIT` | `100` | Resultados por consulta configurada |
| `OPENBOOK_OPENLIBRARY_QUERIES` | 3 temas en español | Consultas separadas por `;` |
| `OPENBOOK_OPENSTAX_FETCH_DETAILS` | `1` | `0` evita fichas individuales y reduce precisión |
| `OPENBOOK_OPENSTAX_MAX_BOOKS` | `0` (todos) | Límite de libros OpenStax |
| `OPENBOOK_OPENALEX_LIMIT` | `25` | Resultados OA por consulta |
| `OPENBOOK_OPENALEX_QUERIES` | 4 temas | Consultas separadas por `;` |
| `OPENALEX_API_KEY` | vacío | API key, cuando OpenAlex la exija |
| `OPENBOOK_INTERNET_ARCHIVE_LIMIT` | `50` | Máximo de fichas de Archive |

Para uso responsable en un fork público, configura `OPENBOOK_CONTACT_EMAIL` como variable del repositorio. Coloca `OPENALEX_API_KEY` exclusivamente en **Settings → Secrets and variables → Actions → Secrets**.

## GitHub Actions

[`update-books.yml`](.github/workflows/update-books.yml) se ejecuta cada día a las `05:23 UTC` y mediante `workflow_dispatch`. Instala dependencias con caché, sincroniza cada provider de forma aislada, valida, prueba y crea un commit sólo si cambió el contenido del catálogo. El workflow no responde a `push`, y el commit usa `[skip ci]`, por lo que no se crea un bucle.

Si una fuente falla, el sincronizador registra `ERROR`, conserva sus registros anteriores y sigue con las demás. Una respuesta vacía inesperada tampoco borra un snapshot existente.

[`deploy-pages.yml`](.github/workflows/deploy-pages.yml) publica el sitio estático al hacer push a `main`. En GitHub abre **Settings → Pages → Build and deployment → Source** y selecciona **GitHub Actions**. La primera ejecución crea el entorno `github-pages`.

## Modelo de datos

`data/schema.json` define el contrato. Cada obra deduplicada conserva los datos de mayor calidad y una lista `providers`:

```json
{
  "id": "work:…",
  "title": "Título",
  "subtitle": "Subtítulo opcional",
  "description": "Resumen opcional para búsqueda temática",
  "authors": ["Autor"],
  "language": "es",
  "year": 2024,
  "publisher": "Editorial",
  "isbn": ["9780306406157"],
  "doi": "10.1000/example",
  "subjects": ["Algoritmos"],
  "source": "OpenStax",
  "source_url": "https://…",
  "cover_url": "https://…",
  "formats": [{ "type": "pdf", "url": "https://…" }],
  "access": "creative_commons",
  "license": "CC BY 4.0",
  "verified_legal": true,
  "resource_type": "textbook",
  "identifiers": { "source_id": "…" },
  "providers": [
    {
      "source": "OpenStax",
      "source_id": "…",
      "source_url": "https://…",
      "language": "es",
      "formats": [{ "type": "pdf", "url": "https://…" }],
      "access": "creative_commons",
      "license": "CC BY 4.0",
      "verified_legal": true
    }
  ]
}
```

Los valores de `access` son `public_domain`, `open_access`, `creative_commons`, `author_free`, `digital_lending`, `preview`, `metadata_only` y `unknown`. La normalización elimina todos los formatos si `verified_legal` es falso o si el acceso es `metadata_only`/`unknown`.

La deduplicación usa, en orden: ISBN, DOI, Open Library Work ID, título normalizado + autores, título + edición + año y, finalmente, el ID del proveedor. Todas las claves incluyen el idioma declarado, por lo que una ficha española y otra inglesa no se fusionan aunque compartan título y autor. Las variantes conservan sus proveedores y enlaces, y cada snapshot nuevo guarda su idioma.

## Añadir un provider

1. Crea `scripts/providers/nueva_fuente.py` y hereda de `BaseProvider`.
2. Implementa `fetch()` y devuelve listas de diccionarios normalizados con `clean_record()`.
3. Usa `self.get()`/`self.get_json()` para obtener reintentos, timeout y `User-Agent` comunes.
4. Declara el tipo en `PROVIDER_TYPES` dentro de `scripts/update_books.py`.
5. Añade fixtures sin red en `tests/test_parsers.py` y un test de `fetch()` con session simulada.
6. Documenta API, licencia, rate limits y cómo se determina `access`.

Un provider no debe construir enlaces de descarga a partir de suposiciones. Si sólo conoce una ficha, debe devolver `formats: []`, `access: "metadata_only"` y `verified_legal: false`.

## Búsqueda, seguridad y rendimiento

La búsqueda combina el índice local con descubrimiento en vivo de ediciones de Open Library y obras de dominio público encontradas mediante Gutendex. Usa normalización Unicode y de ordinales, coincidencias ponderadas, trigramas y distancia Damerau-Levenshtein acotada. Las consultas descriptivas largas usan una cobertura mínima dinámica en vez de exigir que coincida la mitad de todas las palabras conversacionales. El resumen, cuando una fuente lo aporta, se indexa con menor peso que título, autor y materia.

Admite frases exactas y operadores en español o inglés:

```text
titulo:"Software Engineering" autor:Sommerville edicion:10 idioma:en
tema:"métodos numéricos" idioma:es formato:pdf
isbn:9780133943030
doi:10.1000/example
```

Los campos disponibles son `titulo/title`, `autor/author`, `isbn`, `doi`, `editorial/publisher`, `tema/subject`, `idioma/lang`, `formato/format`, `fuente/source`, `acceso/access`, `año/year`, `edicion/edition` y `tipo/type`. La búsqueda avanzada visual añade título exacto, ISBN/DOI, editorial, edición, tipo de recurso y disponibilidad. Los filtros y el orden se conservan en la URL compartible.

Los resultados se clasifican en fichas en español, fichas en inglés y otros idiomas. Esa separación utiliza el idioma declarado por la fuente; no afirma que dos fichas sean traducciones de la misma obra. Open Library sólo entra en un grupo cuando la respuesta incluye una edición concreta de ese idioma. Si no se confirma una edición española, la interfaz lo dice y ofrece continuar en catálogos bibliográficos.

Una ficha encontrada en vivo no se presenta como descarga por su mera existencia. Si una edición de Open Library declara lectura pública se muestra **Leer**; si declara préstamo se clasifica como préstamo; en los demás casos se enlaza únicamente la ficha. Gutendex sólo aporta formatos cuando declara `copyright=false`. Cuando un filtro como PDF oculta una coincidencia bibliográfica, la interfaz la muestra en una sección separada y ofrece limpiar los filtros. También proporciona búsquedas de continuación generales y en español en Open Library y Google Books, además de Gutenberg y WorldCat.

La UI no usa `innerHTML` con datos externos: crea nodos y asigna `textContent`. Todos los enlaces pasan por una lista de esquemas HTTP(S), las imágenes usan lazy loading y la CSP bloquea scripts remotos, objetos y URLs ejecutables. `connect-src` sólo permite el propio sitio, Open Library y Gutendex. No existen claves en el frontend; Google Books permanece como enlace externo porque su API requiere una clave identificadora.

El frontend no descarga el catálogo al abrir la portada. En la primera búsqueda carga hasta seis shards en paralelo. Por encima de 5.000 obras, el JSON canónico también queda particionado para evitar un archivo gigante. Esta arquitectura es apropiada para una primera etapa de decenas de miles de fichas; cerca de 100.000, el tiempo/memoria dependerá del dispositivo y conviene migrar la interfaz de búsqueda a un índice dedicado manteniendo los providers.

GitHub Pages limita el sitio publicado a 1 GB y recomienda repositorios de hasta 1 GB. Este proyecto almacena sólo texto JSON y URLs; nunca portadas ni ebooks.

## Limitaciones y política de copyright

- “Dominio público” puede variar por país. Project Gutenberg y Standard Ebooks describen principalmente el estado en Estados Unidos; la interfaz no sustituye asesoría legal.
- Free Programming Books es una lista curada, pero no aporta una licencia individual para cada entrada. Sólo se muestra una licencia CC cuando aparece explícitamente en la lista.
- Open Library e Internet Archive pueden contener materiales con préstamo, preview o únicamente metadatos. Su presencia no demuestra una descarga libre.
- OpenAlex agrega señales OA de terceros. Sólo se enlaza su mejor ubicación OA declarada; el proveedor original sigue siendo la autoridad.
- La clasificación ES/EN no relaciona traducciones automáticamente. El modelo publicado sigue siendo una ficha por obra y algunas fuentes agregan varias ediciones; la edición concreta de Open Library sólo se usa en el descubrimiento en vivo cuando la API la aporta.
- Un enlace roto o un cambio de licencia debe corregirse en la fuente y, si es urgente, retirarse mediante un pull request.

No se aceptan mirrors no autorizados, bypasses, credenciales compartidas, scraping agresivo ni enlaces cuya legitimidad no pueda explicarse. Reporta cualquier problema de copyright mediante un issue con el título, URL y motivo; el recurso debe degradarse a `metadata_only` o retirarse mientras se revisa.

## Licencia

El código de este repositorio usa la [licencia MIT](LICENSE). Los metadatos y las obras enlazadas conservan las licencias y términos de cada fuente; la licencia del software no se extiende a ellos.
