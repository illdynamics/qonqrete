# TasQ: Turn Astro Sphere into the QonQrete.sh Dev Blog

## High-Level Outcome

Build a production-ready, QonQrete-branded developer blog and project hub at **https://qonqrete.sh**, using the **Astro Sphere** theme as the base.  
The result should be a minimal, fast, dark-leaning, glitchy portfolio/blog focused on:

- Explaining what QonQrete is
- Documenting architecture and agents
- Publishing devlogs and release notes
- Pointing people to the GitHub repo and docs

The output must be **fully working Astro project** in this qage, ready to build and deploy.

---

## Context

- The Astro Sphere project is located at:
  - `qodeyard/astro-sphere`
  - Treat **`astro-sphere/` as the Astro project root** (it contains `package.json`, `astro.config.*`, etc.).
- A QonQrete logo image is available at:
  - `qodeyard/qonqrete-squid.jpg`
  - As part of this tasQ, copy or move it into `astro-sphere/public/qonqrete-squid.jpg` and use it in the layout.
- There is a `Dockerfile` in:
  - `qodeyard/Dockerfile`
  - This should be updated to build and serve the QonQrete Astro site from `astro-sphere/` for production.
- This site is **not** marketing fluff — it’s aimed at devs, infra nerds, and AI/agent builders.


- This qage contains (or will contain) a fork/clone of the **Astro Sphere** theme (Astro + Tailwind + TypeScript, with a bit of SolidJS for stateful bits).
- The theme already provides:
  - Blog + projects structure
  - Light/dark theme toggle
  - Search across posts/projects
  - Code blocks with copy-to-clipboard
- A QonQrete logo image **`qonqrete-squid.jpg`** is already present in this repo (exact location may be root or `public/`; detect and keep it).

QonQrete itself lives at `https://github.com/illdynamics/qonqrete` and is a local-first, file-based “AI construction yard” with InstruQtor / ConstruQtor / InspeQtor agents, dual-core memory (Qompressor + Qontextor), and a secure Qage.

This site is **not** marketing fluff — it’s aimed at devs, infra nerds, and AI/agent builders.

---

## Goals

1. **Rebrand Astro Sphere → QonQrete**
   - Replace all “Astro Sphere” naming, titles and meta where appropriate with QonQrete branding.
   - Set canonical site URL to **`https://qonqrete.sh`**.
   - Use the **QonQrete squid logo** as visual anchor in header/hero and OG/social images.
   - Keep the theme’s minimal, performant feel, but with a darker, slightly glitchy construction-yard / terminal vibe.

2. **Create a clear information architecture**
   The site should, at minimum, expose:

   - **Home** (`/`)
     - Hero: QonQrete logo + tagline + short intro + primary CTAs.
     - Short “What is QonQrete?” blurb.
     - Quick bullets for “Plan / Build / Review” (InstruQtor, ConstruQtor, InspeQtor).
     - Highlight current version (e.g. `v0.6.0-beta`) and key feature: Dual-Core Memory.
     - Teaser list of latest 3–5 blog posts.

   - **Blog** (`/blog` or whatever Astro Sphere already uses)
     - List all posts with tags, dates, and short descriptions.
     - Search should still work across all posts.

   - **Concepts / Architecture** (page, e.g. `/concepts` or `/architecture`)
     - High-level explanation of:
       - Qage / Qrane
       - InstruQtor / ConstruQtor / InspeQtor
       - Dual-Core Memory (Qompressor + Qontextor)
       - File-based memory & context (tasQ, briQs, exeQs, reQaps, sqeleton, etc.)
     - Use headings and bullet lists — written for devs.

   - **Quickstart / Getting Started** (page, e.g. `/quickstart`)
     - Concise install + first-run flow:
       - Clone repo
       - Install dependencies
       - Configure API keys
       - Run `./qonqrete.sh init` and first `run`
     - Link textually to the full `QUICKSTART.md` and `DOCUMENTATION.md` in the GitHub repo.

   - (Optional but nice) **Roadmap / Changelog** page
     - Short overview of major releases, with focus on the latest (Dual-Core).

3. **Seed the blog with real QonQrete content**
   Create at least **three concrete posts** (markdown/MDX, matching whatever structure Astro Sphere uses):

   1. **Post 1 – “What is QonQrete?”**
      - Audience: people hitting the site from GitHub / HN / Reddit.
      - Content:
        - Short origin story (local-first, file-based, frustration with opaque provider UIs).
        - Explain “construction yard” metaphor.
        - Emphasize: secure sandbox (Qage), file-based memory, reproducible runs.

   2. **Post 2 – “The Dual-Core Memory System: Qompressor + Qontextor”**
      - Describe:
        - Problem: huge repos vs token limits.
        - Qompressor: AST/skeleton view (classes, functions, signatures, comments, no heavy bodies).
        - Qontextor: symbol map / index built from skeleton.
        - Rough example of token savings (e.g. going from full repo prompts to ~4% of tokens for the skeleton + targeted context).

   3. **Post 3 – “Why Local-First Agents?”**
      - Explain:
        - Provider drift / memory regressions.
        - Importance of having reasoning + memory on disk.
        - How tasQ/briQ/exeQ/reQap logs make runs auditable, greppable, versionable.
        - How QonQrete plays with multiple providers (OpenAI, Gemini, Anthropic, DeepSeek, Qwen, etc.) but keeps memory local.

   For each post:
   - Include title, description/summary, date, and tags.
   - Use clear headings and short sections; no lorem ipsum.

4. **Wire up QonQrete-specific CTAs and social links**
   - Global header/footer should provide:
     - Link to **GitHub repo**: `https://github.com/illdynamics/qonqrete`
     - Link to **project documentation** (README, QUICKSTART, DOCUMENTATION on GitHub).
     - Optional: link to `r/QonQrete` subreddit (noted as “community (when Reddit behaves)”).
   - Primary CTA buttons on hero section:
     - “View on GitHub”
     - “Read the Quickstart”
   - Ensure these CTAs are visually prominent but still consistent with theme.

5. **Update SEO & meta**
   - Set site-wide metadata:
     - Title: `QonQrete – Local-First Agent Construction Yard`
     - Description: a concise dev-friendly summary of what QonQrete is.
     - Author: `illdynamics` (or the name already used for the project).
   - Configure open-graph / social preview image to use the **qonqrete-squid** art on a dark background.
   - Keep sitemap and RSS feed features intact and working.

6. **Preserve performance and cleanliness**
   - Keep pages small, fast, and accessible; avoid heavy libraries beyond what Astro Sphere already uses.
   - Ensure dark/light theme toggle still works.
   - Make sure new color choices keep good contrast (WCAG-friendly).

7. **Respect original theme license & attribution**
   - Add a short attribution in the footer or an “About this site” section, e.g.:
     - “Site built with the Astro Sphere theme by Mark Horn (MIT-licensed).”

---

## Inputs & Assumptions

- The qage already contains:
  - An Astro Sphere-based project (copied or forked).
  - The image: `qonqrete-squid.jpg` somewhere in the repo (preferably `public/`).
- Node/PNPM/NPM tooling exists in this environment and `npm install` / `npm run build` will work.
- QonQrete can read the QonQrete GitHub README/QUICKSTART locally or from a checked-out version if needed for content.

If any of the above inputs are missing, the system should:
- Prefer to **reuse/inspect what’s already here**.
- Clearly document missing assumptions in the final `reQap`.

---

## Visual / Branding Direction

Target vibe: **dark, minimal, glitch-adjacent**, but not so noisy that it kills readability.

### Color palette (suggested)

Define or use Tailwind theme tokens so everything stays consistent:

- Background main: `#050712` (near-black with a hint of blue)
- Surface card background: `#0B1020`
- Primary accent (QonQrete “warning stripe”): `#ffb300` (amber / construction)
- Secondary accent (neon line / detail): `#00e5ff`
- Text primary: `#E5F0FF`
- Muted text: `#9CA3AF` (or similar gray)
- Error/glitch accent: `#ff2bd6` (for subtle highlights or tiny glitch details only)

Guidelines:
- Use the primary accent for buttons, links, key highlights.
- Use the secondary accent for borders / hover states / underlines.
- Use the glitch accent **sparingly**: small highlights, box-shadows, or subtle animated bits.

### Layout tweaks

- Show the **qonqrete squid** logo in the header:
  - Replace or accompany the text logo.
  - Ensure it scales well on mobile/desktop.
- Hero section:
  - Left: logo + main title + tagline.
  - Right (or below on mobile): short explanation and CTA buttons.
- Keep motion subtle:
  - If the theme includes particles / starfield, retune colors to match the palette above.
  - Avoid large, distracting animations on content pages.

---

## Content Requirements (Concrete Text to Produce)

Use this as guidance for the copy that ConstruQtor generates. Wording doesn’t have to be exact, but the **meaning** should be preserved.

### Site-wide

- **Site title**: `QonQrete`
- **Tagline (short)**: `Local-first agent construction yard`
- **Meta description (longer)**:
  - Something along the lines of:
    - “QonQrete is a local-first, file-based agentic AI ‘construction yard’ that plans, writes, and reviews your code inside a safe sandbox — with its own memory and context on disk, not trapped in a chat UI.”

### Home page copy (example structure)

- H1: `QonQrete – Local-First Agent Construction Yard`
- Short intro paragraph:
  - Explain that QonQrete:
    - runs agents in a sandboxed Qage,
    - keeps reasoning + memory in files,
    - works with multiple providers but never trusts them as the source of truth.
- Three feature blocks:
  1. **Plan with InstruQtor**
     - Splits a high-level tasQ into concrete briQs.
  2. **Build with ConstruQtor**
     - Applies briQs to the codebase inside the qage/qodeyard.
  3. **Review with InspeQtor**
     - Audits the changes and writes a reQap with next steps.

- Highlight box:
  - Title: “Dual-Core Memory”
  - Text: short explanation of Qompressor + Qontextor and the fact that they drastically shrink context while keeping structure.

### Concepts / Architecture page

At minimum sections:

1. **Architecture Overview**
   - Qage (sandbox), Qrane (orchestrator), worqspace, qodeyard.

2. **Agents**
   - InstruQtor (planning)
   - ConstruQtor (execution)
   - InspeQtor (review)
   - Qompressor (skeletonizer)
   - Qontextor (symbol mapper)
   - (Optionally mention CalQulator if relevant.)

3. **File-Based Memory**
   - tasQ.md → briQ files → exeQ summaries → reQap reviews.
   - Logs and artifacts live in version-controllable files.

4. **Providers**
   - QonQrete can talk to different models (OpenAI, Gemini, Claude, DeepSeek, Qwen, etc.), but treats them as stateless text engines behind a stable local system.

### Quickstart page

- Present a condensed flow, roughly:

  1. **Install Requirements**
     - Docker or Microsandbox
     - Python / shell basics.

  2. **Clone QonQrete**
     - `git clone` from GitHub, or mention this is documented in the repo.

  3. **Configure API Keys**
     - `OPENAI_API_KEY`, `GOOGLE_API_KEY`/`GEMINI_API_KEY`, etc.

  4. **Initialize & Run**
     - `./qonqrete.sh init`
     - Create a tasQ.md for your project.
     - `./qonqrete.sh run --tui` (or `--auto`).

  5. **Iterate**
     - Explain that each cyQle writes briQs, exeQs, and reQaps to files for inspection.

- Provide links/mentions to the full `QUICKSTART.md` and `DOCUMENTATION.md` for deeper details.

---

## Technical Tasks

These are concrete modifications the agents should plan and execute.

1. **Astro config**
   - Update `astro.config.*`:
     - Set `site` to `https://qonqrete.sh`.
   - Ensure build output remains in `dist/` and dev commands still work.

2. **Site constants**
   - Locate where the theme stores `SITE` information (typically in a `consts.ts` or similar).
   - Update:
     - `TITLE`, `DESCRIPTION`, `AUTHOR`.
   - Add/update any social/links constants:
     - GitHub: `https://github.com/illdynamics/qonqrete`
     - Optional community link: `https://www.reddit.com/r/QonQrete/`

3. **Logo integration**
   - Detect where the header/hero logo is defined.
   - Wire in `qonqrete-squid.jpg` as a primary logo graphic.
   - Ensure:
     - Proper alt text (e.g. `alt="QonQrete squid logo"`).
     - Good sizing and aspect ratio on desktop and mobile.

4. **Color & theme updates**
   - Update Tailwind config to define a small QonQrete color palette (see suggested palette above).
   - Replace existing brand colors in the theme with these tokens.
   - Confirm light theme still works (even if dark is default).
   - Keep contrast high enough for accessibility.

5. **Content structure**
   - Identify where posts and pages live in the template (e.g. `src/content/blog`, `src/pages/*.astro` or similar).
   - Create the pages and posts described in the **Content Requirements** section.
   - Use the theme’s existing layouts/components; do not reinvent the layout unless necessary.

6. **Navigation**
   - Ensure top-level nav contains:
     - Home
     - Blog
     - Concepts / Architecture
     - Quickstart
   - Footer:
     - GitHub link
     - Attribution to Astro Sphere and author.
     - Optional: link to QonQrete community/reddit.

7. **Search**
   - Confirm that the built-in search still indexes and finds the new posts.
   - If search requires frontmatter fields (title, description, tags), ensure they are correctly populated.

8. **Build & sanity check**
   - Run lints and builds (`npm run lint`, `npm run build` or equivalents).
   - Fix basic TypeScript or ESLint issues if they appear due to new imports/components.
   - Make sure dev server would start without errors.

9. **Documentation update (in this repo)**
   - Update or add a `README.qonqrete-site.md` (or update existing README) describing:
     - How to install and run this site locally.
     - How to add new posts.
     - How to deploy to production (generic: “build and upload `dist` to your static hosting / CDN” or similar).

---

## Non-Goals / Constraints

- Do **not**:
  - Add a backend, auth, comments system, or custom CMS.
  - Introduce heavy UI libraries beyond what Astro Sphere already uses.
  - Change the site’s fundamental layout grid unless necessary.
- Keep the theme:
  - Static, lightweight, and performant.
  - Easy for a human dev to tweak later without needing to understand the entire QonQrete pipeline.

---

## Guidance for the Agents

### For InstruQtor (Planning)

- Break this tasQ into clear briQs for:
  1. Theme analysis and mapping (find config, colors, content folders).
  2. Branding & palette application.
  3. Page structure (home, concepts, quickstart).
  4. Blog content creation (3 posts minimum).
  5. Nav + footer wiring and CTAs.
  6. SEO, OG metadata, and logo integration.
  7. Build & lint fixups.
  8. Final cleanup + README update.

- Each briQ should specify:
  - Which files to inspect/modify.
  - Expected output files.
  - Validation checks (e.g. “site builds without errors”, “posts visible on blog index”).

### For ConstruQtor (Execution)

- Work incrementally; don’t rewrite everything at once.
- Prefer editing existing components and config rather than replacing them.
- After each cluster of changes:
  - Ensure TypeScript/ESLint errors are addressed.
  - Keep content high-signal and technical; no lorem ipsum, no filler.

### For InspeQtor (Review)

- Confirm:
  - Branding is consistent (no leftover “Astro Sphere” references except in attribution).
  - All new pages render correctly and are reachable from nav.
  - Blog posts read clearly, accurately represent QonQrete, and are structured for devs.
  - Build succeeds and no obvious console errors should occur in dev mode.
- Write a reQap:
  - Summarize the main changes.
  - Note any TODOs or open questions for the human gateQeeper (e.g., “consider adding more posts later”, “wire real deployment instructions once hosting is chosen”).

---

