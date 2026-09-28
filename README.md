# Lexicon Forge

A zero-backend vocabulary learning game built from the supplied TakeTest `vocab-108` HAR capture.

## Learning flow

Lexicon Forge now separates **learning** from **review**:

1. **Word Stories** introduce a word with meaning, pronunciation, source-test relationships, etymology, and authentic/example usage when an external source provides it.
2. A low-stakes meaning check closes each learning card.
3. Introduced words become eligible for spaced retrieval practice.
4. Review progresses from recognition toward typed recall and uses expanding intervals.

The default Learn pool is the **186 actual target/answer words** represented in the 108 source items. The complete **537-word pool** remains available for exploration.

## Reliable enrichment

External enrichment is optional rather than a hard dependency:

- Wiktionary is queried through the MediaWiki Action API for definitions, etymology, and usage material.
- Dictionary API is used as a secondary definition/pronunciation/example source.
- Both requests have hard timeouts.
- Results are cached in `localStorage`.
- If both sources fail, the interface immediately falls back to relationships and definitions encoded in the source test where available. It never leaves an indefinite loading state.

## Source data

- **108 source relations/questions** from the captured TakeTest full form.
- **537 unique terms** across prompts and options.
- **186 core learning targets** derived from words that are correct answers or explicit prompt headwords.

## Run locally

```bash
python3 -m http.server 8000
```

Then open `http://localhost:8000`.

## Hosting

The repository is configured for GitHub Pages using `.github/workflows/pages.yml`. No build step or backend is required.

## Privacy

Progress, cached word enrichment, and settings stay in the browser. There is no application account or server-side learner database.