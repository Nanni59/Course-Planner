# Handoff: Course Planner — Study Tools polish (single-file web app)

## Project
Personal single-file web app: C:\Users\ibrah\OneDrive\Desktop\Course Planner\index.html
(~11,000 lines, vanilla HTML/CSS/JS, no build step, "claymorphism" soft-UI theme, GREEN
Study Tools accent --color-study). Owner: Ibrahim, high-school student. He tests everything
himself in the browser — do NOT browser-test or claim something works; implement cleanly and
report exactly what changed. Make minimal, targeted edits; never refactor unrelated planner
code (Day A/B board, trackers, Canvas import, Backup, expanded card view).

## Goal
A Gemini-powered "Study Tools" tab (Worksheet / Study Guide / Flashcard generators) for static
GitHub Pages hosting. This and the prior session were polish passes on look/UX/reliability.

## Where the code lives (all inside index.html)
- Study Tools = one self-contained IIFE <script> just before </body>. All classes are .st-*,
  the root is #studyTools, nav button #studyToolsBtn in the green footer pill.
- One big "STUDY TOOLS" CSS block before </style> (the .st-* rules, ~line 2800–2990).
- Gemini is called directly from the browser (REST fetch + responseSchema). Key in localStorage
  cp_gemini_api_key; model in cp_gemini_model (default gemini-2.5-flash).
- Saved content: cp_study_worksheets / cp_study_guides / cp_study_decks.
- Useful grep identifiers: gemini(, stripJSON, ensureMath, renderMath, escNL, escFlow, deBold,
  esc, LATEX_ON, renderWorksheet, sheetHTML, questionHTML, syncToggles, WS_LINES, WS_SPACE,
  WS_DATA, renderGuide, showDeck, saveDeck, courseSubjects, ddHTML, initDD, syncSubjectOptions.

## STATUS — all of the work below is DONE, edited in the working tree, NOTHING COMMITTED yet.

### Reliability / math (earlier this session)
1. gemini() now auto-retries schema calls up to 3× and runs stripJSON() (strips ``` fences) before
   JSON.parse — fixes the study-guide "Could not parse the AI response" error on YouTube-only input.
2. MathJax 3 config: single-$ inline math DISABLED. Inline = \( \) only; display = $$ … $$ and
   \[ … \]. (Stops stray/currency $ in prose from being swallowed into math.)
3. MathJax formatError added: malformed LaTeX (e.g. unbalanced \left/\right) degrades to the raw
   source text instead of a red error blob. Wrapped in try/catch so it can never break rendering.
4. escFlow(s) helper = esc + single "\n"→space, blank line→<br><br>. Used for study-guide prose
   fields (overview/concepts/example/takeaways/quiz) so inline math no longer fragments onto its
   own line. Worksheet/flashcards keep escNL (preserves answer-key step line breaks).
5. LATEX_ON prompt hardened: balanced \left/\right (or plain delimiters), inline math on the same
   line, no $$ for a lone variable, and plain italic variables (no \mathbf).
6. deBold(s) folded into esc(): strips \mathbf|\boldsymbol|\pmb|\bm|\mathbfit|\textbf|\bf so EVERY
   math variable renders in one face — plain italic Computer Modern (MathJax_Math-Italic).
   NOTE: the "font" complaint was bold-vs-italic within Computer Modern, NOT Computer Modern vs
   Latin Modern. We did NOT migrate to MathJax 4. esc is scoped to the Study Tools IIFE.

### Flashcards
7. Manual save: removed autosave-on-generate. showDeck(deck, alreadySaved) renders a "Save deck"
   button (→ "✓ Saved"); decks opened from the saved list pass alreadySaved=true (no dup).

### Worksheet
8. Defaults: WS_SPACE=false (spacing removed) and WS_LINES=false (lines hidden).
9. Toggle interdependency via syncToggles() (re-runs on every mode/spacing/lines change):
   Keep spacing → Lines enabled; Remove spacing → Lines forced Hide + disabled; Answer Key mode →
   BOTH toggles disabled. Disabled groups get the .st-ws-toggle.dim class (greyed, unclickable).
10. Header repurposed: subject top-left, grade/level top-right (reuses .st-a4-meta, flex
    space-between). Captured from the form onto WS_DATA.subject (form subject ?? AI subject) and
    WS_DATA.level; persists through Save and the printed PDF. Title pulled closer to the underline.

### UI (latest)
11. Removed the "New" buttons from worksheet, study guide, and flashcards (+ their handlers).
    Start fresh via the back arrow in each generator header (→ hub, also resets source inputs).
12. Subject is now a dropdown populated from the planner's courses: courseSubjects() reads
    .course-card[data-course-name] (Day A + Day B, de-duped) + a "General" default.
    syncSubjectOptions() re-fills it every time the worksheet generator is opened.
13. Custom themed dropdown component replaces ALL native <select>s in Study Tools (native popups
    can't be themed). API: ddHTML(id, options, selected) builds it; initDD(scope) wires it;
    closeAllDD() + a global click listener close it. Each .st-dd exposes a .value getter/setter via
    Object.defineProperty, so existing getElementById(id).value reads/writes are unchanged.
    Applied to: wsSubject, wsLevel, wsCount, fCount, stModelInput. initDD(root) runs after the UI
    builds; initDD(modal) runs after the API modal is appended. CSS is the .st-dd* block.

## Key decisions / context
- 100% static (GitHub Pages). NO backend/localhost/transcript service — never reintroduce one.
- Reference app "Formulae" (C:\Users\ibrah\OneDrive\Desktop\Formulae\static\js\renderer.js) is the
  MathJax mechanism reference. We intentionally diverged from it: single-$ inline is OFF for
  reliability.
- Native <select> .st-select rules are now dead but harmless — left in place to keep the diff tight.
- ALL_COURSE_NAMES exists in the planner's scope (not the Study Tools IIFE), so subjects are read
  from the DOM instead.

## What to AVOID
- Don't browser-test or assert it works — Ibrahim verifies manually.
- Don't reintroduce a backend, single-$ inline math, KaTeX, MathJax-4/Latin-Modern, \mathbf-bold
  math, or red MathJax error blobs.
- Don't touch unrelated planner features.
- Don't commit or push unless asked. Confirm the actual `git remote` before ANY remote op
  (memory and older handoffs disagree on the repo URL).

## VERY NEXT STEP
Ibrahim will test this session's batch in the browser (themed dropdowns open/close + values flow to
generation and the worksheet header; Subject lists his courses; toggle enable/disable logic;
header subject/grade; "New" buttons gone; the math fixes). Then: (a) decide whether to COMMIT this
Study Tools batch — ASK before committing, nothing is committed; (b) still pending from before —
enable GitHub Pages (repo Settings → Pages → Deploy from branch main /root), browser-only.