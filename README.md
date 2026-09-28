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

Lexical enrichment is generated ahead of time and committed as `word_data.json`. Study sessions do not call a live dictionary API.

The bundled dataset contains definitions, etymology when available, examples, pronunciation metadata, dictionary relationships, course/source relationships, and modern-use ideas for the finite 537-word pool. The build script derives the lexical material from Wiktionary through Kaikki.org / Wiktextract.

## Definition quality

The static build audits all 537 entries for self-contained definitions. It penalizes secondary/context-dependent glosses, resolves inflected and spelling-variant forms into definitions of their base word, and uses curated overrides for high-risk ambiguous words such as `torpid`, `umbra`, `natty`, and `gabardine`. Modern-use suggestions are stored as short context labels rather than repeated paraphrases.

## Teaching-definition pipeline

The learning cards use a separate **teaching definition** and **quiz definition** rather than exposing raw dictionary glosses directly.

- Polysemous words are scored for a common/useful sense and high-risk ambiguous entries have curated overrides.
- Inflected and spelling-variant entries are resolved to semantic definitions rather than clues such as “past tense of …” or “variant of …”.
- Quick-check clues are automatically checked so neither the answer nor a linked base/conjugate appears in the clue.
- Examples are selected from the same sense as the teaching definition; selected ambiguous entries use reviewed examples.
- “Where you might actually encounter it” gives two concrete contexts rather than generic statements about essays or conversation.
- The generated `word_data.json` contains all of this content, so study sessions remain static and do not depend on live dictionary services.

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

Progress, XP purchases, pigeons, and settings stay in the browser. There is no application account or server-side learner database.

## Licensing and attribution

Original Lexicon Forge application code, interface logic, and pigeon artwork are licensed under the MIT License in `LICENSE`.

Bundled lexical data derived from Wiktionary/Kaikki/Wiktextract retains its upstream licensing and attribution requirements; see `THIRD_PARTY_NOTICES.md`. TakeTest-derived source-test material is not relicensed under MIT by this repository.

Lexicon Forge is an unofficial educational study tool and is not affiliated with or endorsed by TakeTest.