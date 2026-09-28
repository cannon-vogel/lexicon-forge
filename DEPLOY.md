# Deploy Lexicon Forge with GitHub Pages

The repository is already configured with the official GitHub Pages Actions workflow.

## One-time repository setup

1. Create a new **public** GitHub repository named `lexicon-forge` with no starter files.
2. Push/upload this project to the repository's `main` branch.
3. In GitHub, open **Settings → Pages**.
4. Under **Build and deployment → Source**, select **GitHub Actions**.
5. Open **Actions** and run **Deploy Lexicon Forge to GitHub Pages** if it did not start automatically.

The expected public URL is:

`https://<your-github-username>.github.io/lexicon-forge/`

All application code and data needed for the core 108-item game are static and live in `index.html`. The optional full-lexicon dictionary mode fetches definitions from `https://api.dictionaryapi.dev` when online and caches successful lookups in browser localStorage.