# Lexicon Forge

A zero-backend vocabulary study game built from the supplied TakeTest `vocab-108` HAR capture.

## What it contains

- **Source Mastery (108 items):** the exact extracted prompts and five options, with the intended correct synonym/meaning relation encoded for practice.
- **Full Lexicon (537 unique terms):** every unique vocabulary term extracted from the test. Definitions are fetched *lazily* from the free [Dictionary API](https://dictionaryapi.dev/) and cached in the browser.
- **Adaptive scheduling:** expanding review intervals; errors are retried sooner; stable items graduate to typed recall.
- **Local-only progress:** no server or database. Progress is stored in `localStorage` and can be exported/imported as JSON.

## Run it

### Simplest
Double-click `index.html`. The 108-item source deck works offline. The 537-word dictionary deck needs internet access when it encounters a word whose definition is not yet cached.

### More reliable local serving
From this folder:

```bash
python3 -m http.server 8000
```

Then open `http://localhost:8000`.

## Free hosting

### GitHub Pages
1. Create a public GitHub repository.
2. Upload the project files to the repository root.
3. Open **Settings → Pages**.
4. Choose **Deploy from a branch**, then select your default branch and `/ (root)`.
5. GitHub publishes it as a static site.

No build step is required.

### Cloudflare Pages
This is also a pure static asset, so it fits Cloudflare Pages' free static hosting. Upload the file or connect a Git repository; no Functions are needed.

## Learning design

The game deliberately makes retrieval—not points—the core action:

- correct retrievals move to longer intervals;
- misses receive immediate corrective feedback and a short-delay retry;
- early items use recognition/discrimination, while more stable items switch to typed production;
- the source deck preserves the test's contrast sets instead of indiscriminately mixing unrelated verbal material;
- XP rewards successful retrieval, especially after items have advanced.

The scheduling model is transparent rather than pretending to infer a precise forgetting curve from sparse data.

## Data note

The 537 terms include both target answers and distractors from the test. The source deck is fully defined by the captured test relations. For the larger 537-term deck, Lexicon Forge uses Dictionary API entries because the TakeTest page does not supply definitions for every distractor.
