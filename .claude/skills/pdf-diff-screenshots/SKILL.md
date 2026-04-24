---
name: pdf-diff-screenshots
description: Produce focused before/after PDF screenshot pairs that illustrate the visual changes made by a git branch in this doc build project. Use when asked to screenshot branch changes, visualize diff rendering, or generate cropped before/after PNGs from built diff PDFs.
---

# PDF Before/After Screenshot Approach

Guide for a Claude Code agent asked to produce before/after screenshot pairs that
illustrate the changes made by a git branch.

---

## Overview

The goal is to produce focused, meaningful screenshots - not a blind pixel-diff of
every page.  The recommended workflow is:

1. Read the branch diff and predict which document sections will look different.
2. Build the before/after PDFs in isolated worktrees (in parallel).
3. Use the `Read` tool on the built PDFs to find which page numbers contain the
   predicted sections.
4. Render only those pages at screen resolution.
5. Crop both before and after PNGs to a region that highlights the affected area.
6. View the cropped before/after PNGs and confirm the visual change matches the prediction.

---

Note: record the start and finish time for the entire task, and for each sub-step, and report at the end.


## Task structure and delegation

The work naturally splits into sequential phases with parallelism opportunities
within each phase.

**Phase 1 - Commit analysis (parent agent, sequential)**

Do this inline before spawning any subagents.  The parent agent must:

- Verify git state and resolve the branch reference
- Determine the diff-before-commit and diff-after-commit
- Predict which document section will change

These steps require judgment and iteration; delegating them introduces coordination
overhead without benefit.

**Phase 2 - PDF builds (two parallel subagents)**

Once the before/after commits are known, launch two subagents simultaneously - one
for the "before" state and one for the "after" state.  Each subagent:

- Gets its own worktree (`isolation: "worktree"`)
- Writes fixture content from its assigned commit
- Builds the PDF and copies it to the shared output directory

The two builds are fully independent and should always run in parallel.

**Phase 3 - Page identification and rendering (parent agent)**

Once both PDFs are available, the parent agent reads them to locate the relevant
page numbers, then renders just those pages.  Reading both PDFs can be done in
parallel.  Rendering may involve a few iterations - render, inspect, render
additional pages if needed.

**Phase 4 - Verification (parent agent)**

The parent agent views the final before/after PNGs and confirms the visual change
matches the prediction from phase 1.

---

## Prerequisites

The following tools must be available:

- `pdftoppm` (from `poppler-utils`) - renders PDF pages to PNG
- `pixi` - the project build system
- `uv` - runs the helper scripts in `scripts/` (auto-resolves their PEP 723
  inline dependency declarations; no manual venv setup required)

Check with:

```bash
pdftoppm -v
uv --version
```

`convert` (ImageMagick) is no longer required.  Pixel-diff bounding-box
cropping and side-by-side compositing both run through the Python helpers
in `scripts/`, which use Pillow + numpy declared inline via PEP 723.

---

## Helper scripts

This skill bundles four uv-runnable helper scripts under
``.claude/skills/pdf-diff-screenshots/scripts/``.  Each script has a PEP
723 ``# /// script`` header that declares its dependencies, so just call
``uv run path/to/script.py ...`` and uv will spin up an ephemeral env on
first invocation.

| Script                     | Purpose                                                                | Phase   |
|----------------------------|------------------------------------------------------------------------|---------|
| `build_diff_at_commit.py`  | Detached-checkout a commit in a worktree and build the diff PDF.       | 2       |
| `render_pages.py`          | Render specified pages from a before/after PDF pair to PNGs.           | 4       |
| `crop_changed_regions.py`  | Crop before/after PNGs to agent-supplied y-ranges (or auto-cluster).   | 5       |
| `summarize.py`             | Build side-by-side composites and a minimal top-level README.          | 6       |

Run any of them with `--help` to see all options.  Examples appear inline
in the steps below.

**Why this project's pixi env may not work for the cropping scripts.**
The doc_build pixi environment does not declare numpy/Pillow as
dependencies, so `pixi run python crop_changed_regions.py ...` will fail
with `ModuleNotFoundError`.  Either run with system `python3` (which
typically has both), or use `uv run` (the recommended path - the inline
metadata makes dependencies explicit).

---

## Step 1 - Understand the branch changes

**Verify the actual current state before doing anything.**  Session-start git status
snapshots can be stale if the user changed branches in another terminal.  Always run:

```bash
git status
git log --oneline -5
```

**Resolve the branch reference.**  By default, use the local branch
(`refs/heads/<branch>`), not the remote tracking branch (`refs/remotes/origin/<branch>`).
Exceptions:

- If the local branch does not exist but exists on exactly one remote, use that remote.
- If explicitly told to use `origin/<branch>`, use the remote.
- If the local branch is in the direct history of the remote (a fast-forward of the
  remote onto local would be a no-op), ask the user whether to fast-forward first.

For the main branch, always use `origin/main` unless a local `main` exists that is
strictly ahead of `origin/main`.

Use `git log --oneline` and `git branch -a` to confirm the branch exists:

```bash
git log --oneline <branch-name> -5
```

**Find the branch-before-commit.**  The "before commit" is the last commit that should
NOT be considered part of the branch (i.e., `git log <before-commit>..<branch-name>`
lists exactly the commits on the branch).  The "first commit" is the first commit
after the before commit.

Start by finding the merge-base with `origin/main`:

```bash
git merge-base <branch-name> origin/main
```

Then check whether any commits in the range from that merge-base to the branch tip are
also the tip of another local branch.  For each commit in the range (excluding the
branch tip itself):

```bash
git branch --points-at <commit>
```

If another branch head appears in the range, the most recent one becomes the
before-commit.  For example, if the history looks like:

```
<merge-base> >>> <branch-A tip> >>> <branch-B tip> >>> <my-branch tip>
```

...use `branch-B tip` as the before-commit, so the diff covers only the commits added
on top of branch-B.

**Determine the diff-before-commit and diff-after-commit.**

- The **diff-after-commit** is nearly always the branch tip.
- The **diff-before-commit** starts as the branch-before-commit found above, but should
  be advanced forward (to a later commit within the branch) if early commits only:
  - Add test infrastructure or fixture content needed to expose the feature being
    demonstrated, without changing core functionality.  For example, if the first commit
    adds Feature A usage to the test spec so that later commits can show improved
    handling of it, that setup commit should be included in the before state.
  - Fix rendering issues required to produce a valid "before" PDF at all.

  In both cases, advance the diff-before-commit past the last such setup commit so the
  visual diff shows only the meaningful change.

Get the exact diff once both commits are determined:

```bash
git diff <diff-before-commit>..<diff-after-commit> --stat          # which files changed
git diff <diff-before-commit>..<diff-after-commit> -- <key-files>  # full diff of relevant files
```

Read the changed source files to understand the nature of the change.  For this
project, diff test fixture files live under `tests/diff_specification/` and the
built diff PDF reflects how the diff algorithm renders changes between
`before_commit/` and `after_commit/` source content.

**Predict the affected document section.**  Based on the diff:

- Which top-level section heading covers the changed content?
- Is the change an addition, deletion, or modification?
- What surrounding context (unchanged paragraphs, headings) will appear nearby?

Write down your prediction before building.  You will verify it against the actual
rendered PDF in step 5.

---

## Step 2 - Build before/after PDFs in isolated worktrees

Spawn one subagent per unique commit, all with `isolation: "worktree"`,
all in a single message so they run in parallel.  Each subagent runs the
bundled `build_diff_at_commit.py` helper, which handles detached
checkout, stale-PDF cleanup, the build, the one-PDF assertion, and
copying the result out to a shared persistent path.

**Use explicit commit hashes, not branch names.**  Branch names can
move; commit hashes are stable.

**Why one subagent per unique commit, not per branch.**  Adjacent
branches in a chain share endpoints (the after-PDF for branch K is
typically the before-PDF for branch K+1).  Track the unique
`(diff-before-commit, diff-after-commit)` pairs and dedupe before
spawning subagents - for N stacked branches you usually need only N+1
builds.

**Tell each subagent exactly this:**

```
Find your worktree root: git rev-parse --show-toplevel
Then run:
  uv run /abs/path/to/scripts/build_diff_at_commit.py \
    --repo-root <your-worktree-root> \
    --commit <commit-hash> \
    --label <unique-label> \
    --out-dir <shared-output-dir>
Use YOUR OWN worktree path; do NOT pass /src/aousd/doc_build or any
other hardcoded path.  Use --out-dir from the parent (it must be
outside any worktree, since worktrees are cleaned up when you finish).
```

The output PDF lands at
`<shared-output-dir>/<label>__aousd_doc_build.diff_<beforehash>_to_<afterhash>.pdf`.

**Diagnostic - matching filenames mean fixtures did not change.**  The
filename encodes the short git hashes of the temp-repo before/after
commits.  If two of your builds (intended to differ) produce the same
filename, the checkout did not actually change content.  Re-verify the
commit hash you passed and the worktree's HEAD before continuing.

**Selective fixture writes - alternative pattern.**  The helper does a
full detached checkout, which matches the entire worktree to the target
commit.  When you instead want to keep most of the repo at HEAD and only
overwrite a small set of fixture files (e.g. running a feature change
against a specific test fixture state), do not use the helper - write
the bytes explicitly with `git show` and assert sentinels:

```python
content = subprocess.check_output(
    ["git", "show", f"{commit}:{rel_path}"], cwd=repo_root,
)
(repo_root / rel_path).write_bytes(content)
text = (repo_root / rel_path).read_text()
assert "expected phrase" in text, f"content check failed for {rel_path}"
```

`git checkout <ref> -- <file>` can silently succeed without changing the
file if the worktree is in an unexpected state, which is why we write
bytes and assert instead.

---

## Step 3 - Locate relevant pages by reading the PDF

Use the `Read` tool on the PDF copies in the shared output directory (the worktrees
are already cleaned up by this point).  It extracts text and returns page markers:

```
Read("<shared_output_dir>/before_aousd_doc_build.diff_*.pdf")
Read("<shared_output_dir>/after_aousd_doc_build.diff_*.pdf")
```

Scan the text for the section heading you predicted in step 1.  Note which page
number it appears on.  For a 6-15 page document this is usually faster than
pixel-diffing all pages.

If the section is near a page boundary, check the adjacent page too - content can
reflow between before and after builds.

---

## Step 4 - Render targeted pages

Once you know the relevant page number(s), render both PDFs in one shot
with the bundled helper:

```bash
uv run /abs/path/to/scripts/render_pages.py \
    --before-pdf <shared_output_dir>/before__...pdf \
    --after-pdf  <shared_output_dir>/after__...pdf \
    --page 9 [--page 10 ...] \
    --out-dir <branch_screenshots_dir> \
    --dpi 150
```

This produces `before_pNN.png` / `after_pNN.png` in `--out-dir` (NN is
the zero-padded 1-indexed page).  At 150 DPI a standard letter page
renders to approximately 1275 x 1650 pixels; bump to `--dpi 300` for
small-region detail.

**Page numbering off-by-one - read this before picking page numbers.**
`pdftoppm` pages are 1-indexed AND include the title/cover page, which
typically has no printed footer number.  So if the document footer reads
"Page N", the corresponding pdftoppm page is usually **N+1**.  When the
user (or a TOC) names a page by its footer number, add 1 before passing
it to `--page`, then verify by reading the rendered PNG and confirming
the section heading matches what you expected.

This step may take several iterations: render the pages you expect to be
relevant, view them, then go back to step 3 to identify additional pages
if the change extends further than predicted (content reflow can push
material onto an adjacent page, or before and after may differ in page
count).  Repeat until you have enough pages to clearly illustrate the
change.

---

## Step 5 - Crop screenshots to the affected region

Crop both the before and after PNGs to a tightly framed region that
makes the change immediately obvious without requiring the viewer to
scan a full page.

**Identify pertinent sections by reading the PDF and full-page PNGs -
NOT by pixel-diff alone.**  This is the most important rule in this
step.  Pixel-diff gives you "everywhere the rendering differs", which
includes downstream content reflow: when the change adds or removes
content, every section below it shifts on the page, and *every shifted
section produces differing pixels too*.  A naive bbox of all changed
pixels therefore over-includes whole sections that are conceptually
unrelated to the branch's change.

The right workflow:

1. **Read both PDFs** (or the rendered full-page PNGs) with the `Read`
   tool.  Identify which section(s) actually demonstrate the branch's
   change - i.e. where the BEFORE looks one way and the AFTER looks a
   conceptually different way (not "displays at a slightly different y
   because reflow above shifted it down").
2. **Note the pixel y-ranges** for those sections by inspecting the
   full-page PNG visually.  Read it inline; eyeball the y-coordinate of
   the section heading at the top and the bottom of the closing figure
   caption / paragraph.
3. **Pass those ranges** to `crop_changed_regions.py` via
   `--y-range Y0-Y1` (repeatable).  The script crops each pair to those
   exact bands and concatenates them.

```bash
uv run /abs/path/to/scripts/crop_changed_regions.py \
    --branch-dir <branch_screenshots_dir> \
    --y-range 440-1080 \
    --y-range 1300-1480 \
    --min-content-x0 130 \
    --min-content-x1 1185 \
    --readme
```

`--y-range` is repeatable; pass one per pertinent section to skip
unchanged middles.  When the change adds or removes content (so the
pertinent region has a different height in before vs after), use
`--y-range-before` and `--y-range-after` instead - each side gets its
own list of strips.  Same x-clamp applies to both.

`--min-content-x0` / `--min-content-x1` are the pixel coordinates of
the left and right edges of the document text block at the rendered
DPI (measure them once on a full-page render).  They anchor the crop
to the document's content width regardless of how narrow the diff is.

**Auto-cluster fallback for a quick first look.**  When you don't pass
`--y-range`, the script falls back to clustering the pixel-diff mask
into y-strips (merged by `--cluster-gap`, optionally trimmed by
`--max-strips`).  This is fine for a fast first-pass scan, but treat
the result as a hint - read the PDF and confirm the strips it picked
are conceptually pertinent before declaring the crop done.

If before and after are pixel-identical (e.g. for a pure refactor
branch), the helper falls back to a centered default crop so you still
get a meaningful image to compare.

**Don't crop to a sub-region of a substitution.**  In this project's
diff output, a single conceptual change is often rendered as a
multi-part *substitution unit*: a section heading, a "Diff - ..."
descriptor line, a pink panel showing the OLD content, and a green
panel showing the NEW content.  Even when only the descriptor line's
text changes (e.g. "Substitution" -> "Substitution: Image changed:
caption"), the surrounding pink/green panels are the context that
makes the descriptor meaningful - keep them in the crop.  Pick
`--y-range` so each pertinent substitution unit is included whole,
from its heading through the bottom of its last colored panel.

**Cross-page composition is allowed.**  The "before" and "after"
images don't need to come from a single page - it's fine to do basic
compositing to keep a substitution unit whole.  Most commonly: a
substitution that fit on one page in the before now spans a page
break in the after (or vice versa).  Render both pages on the
side that needs them, crop each page to the relevant slice, then
vertically join the slices into a single image for that side.  The
counterpart side stays a single-page crop.  Example:

```bash
# Render p05 and p06 of the after PDF, crop each to its slice, then
# stack them into a single after image.
uv run /abs/path/to/scripts/render_pages.py \
    --before-pdf <before.pdf> --after-pdf <after.pdf> \
    --page 5 --page 6 --out-dir <branch_dir>
convert <branch_dir>/after_p05.png -crop WxH1+X+Y1 +repage \
    <branch_dir>/_after_p05_slice.png
convert <branch_dir>/after_p06.png -crop WxH2+X+Y2 +repage \
    <branch_dir>/_after_p06_slice.png
convert <branch_dir>/_after_p05_slice.png \
        <branch_dir>/_after_p06_slice.png \
    -append <branch_dir>/after_p05_cropped.png
```

Pick the slice on each page so that, when stacked, the result reads
as the unbroken substitution unit (no duplicated headers, no orphan
caption strips).  Crop the *other* side normally with
`crop_changed_regions.py`; just make sure both final images use the
same x-range so they align side-by-side.  Name the composited output
`before_pNN_cropped.png` / `after_pNN_cropped.png` (use the page that
contains the heading) so `summarize.py` picks it up.

**Verify the crops.**  Read the `*_cropped.png` files with the `Read`
tool.  If a section that "displays the same way in both" appears in
both crops *and that section is not part of a pertinent substitution
unit*, that section is reflow noise - tighten `--y-range` to exclude
it.  If important context is missing (heading cut off, OLD or NEW
panel of a substitution missing), widen the range.

---

## Step 6 - Compare and verify

View the before and after cropped PNGs using the `Read` tool (it renders
images inline).  Confirm:

1. The visual difference matches your prediction from step 1.
2. The unchanged surrounding content (headings, nearby paragraphs) is
   identical in both versions.
3. The changed content appears where expected and is clearly legible.

If the pages look identical, either the section is on a different page
(recheck step 3) or the fixture writes did not take effect (recheck step
2 - look for identical PDF filenames as the diagnostic signal).

**Build side-by-side composites and a top-level summary.**  Run
`summarize.py` against the screenshots root (the directory containing
one subdir per branch).  It writes a `side_by_side.png` (before on left,
after on right) into each branch dir and, with `--readme`, a minimal
top-level `README.md` listing pixel-diff counts per page:

```bash
uv run /abs/path/to/scripts/summarize.py \
    --screenshots-dir <screenshots_root> \
    --readme \
    --title "Branch before/after screenshots"
```

The auto-generated README is intentionally bare-bones - it lists branch
dirs, pages, and pixel-diff counts.  Hand-edit it afterwards to add the
narrative ("what to look for") and any per-branch context (branch
reference, tip commit, summary) that you established in step 1.  That
prose is judgment-driven and task-specific; the script doesn't try to
guess it.

A pixel-diff count of 0 confirms before and after are byte-identical
(expected for a pure refactor).  A large number confirms visible change.

---

## Lessons from practice

**Pixi works correctly in worktrees.**  Each worktree gets its own
`.pixi/envs/` directory; `pixi run` finds the local `pyproject.toml` and
uses it.  No special `--manifest-path` flag is required.

**Worktree agents write fixture files but do not commit them.**  The
worktree is automatically cleaned up by the agent runner only if no
commits were made.  The modified fixture files are transient within the
worktree - they do not affect the main worktree or the git history of
the real repo.

**Page-number off-by-one - title page is pdftoppm 1.**  pdftoppm pages
are 1-indexed and include the (unfooted) title/cover page.  When the
user, a TOC, or a section reference names a page by its printed footer
number, you almost always need to add 1 before passing it to `pdftoppm`
or `--page`.  Always verify by reading the rendered PNG and confirming
the section heading matches expectation.  If you render the wrong page,
you will silently get a different section that looks plausible but is
unrelated to the change.

**The pixi env may lack PIL/numpy.**  `pixi run python crop_changed_regions.py`
fails because the doc_build pixi environment doesn't declare those deps.
Use `uv run` instead - the inline PEP 723 metadata in each script makes
its own dependencies explicit, and uv resolves them on first invocation.

**Pixel-diff is a hint, not the definition of "pertinent".**  Content
reflow makes pixels differ everywhere below the actual change.  A naive
bbox of all changed pixels therefore engulfs unrelated downstream
sections - the "Changed binary, format(caption)" rows that drift down
because the section above grew, for instance.  Always read the PDF (or
the full-page PNG) and pick y-ranges based on which sections are
*conceptually* part of the change being demonstrated, then pass them to
`crop_changed_regions.py` via `--y-range Y0-Y1`.  The auto-cluster
mode is fine for a quick first scan, but cluster boundaries should be
confirmed against the PDF before being trusted.

**Substitution units are atomic - don't crop to their sub-regions.**
A diff substitution renders as heading + descriptor line + pink (OLD)
panel + green (NEW) panel.  If the only literal text change is in the
descriptor line, it is tempting to crop to just that line - but in
isolation it reads as a one-line text edit with no visible referent.
Include the surrounding pink/green panels (and any sibling
substitutions you want to compare against) so the reader can see what
the descriptor is describing.  Treat the whole heading-to-last-panel
block as one atomic unit when choosing `--y-range`.

**Image-only diffs need a content-width clamp.**  When the change is
purely a small image swap, the auto-detected pixel-diff bbox covers only
the image content - excluding the surrounding section heading and figure
caption.  The cropped output is then unrecognizable.  Always pass
`--min-content-x0` / `--min-content-x1` to `crop_changed_regions.py` so
the crop spans the document's full text-block width regardless of how
narrow the diff is.

**PDF filename is a fixture-fingerprint diagnostic.**  The diff PDF is
named `aousd_doc_build.diff_<beforehash>_to_<afterhash>.pdf`, where the
hashes are commits in the temp build repo.  Two builds intended to
differ MUST produce different filenames.  If they don't, your fixture
writes didn't take effect - go back and check the `git show <commit>:<path>`
copies and the post-write `assert "expected phrase" in text` check.  Do
not proceed to rendering until the filenames diverge.

**Adjacent branches in a chain share endpoints - dedupe builds.**  When
generating screenshots for a chain of N stacked branches, the after-PDF
for branch K is the before-PDF for branch K+1.  Don't build 2N PDFs;
build N+1 (or fewer if some branches share extra fixture-setup
endpoints), then pair them.  Track which `(diff-before-commit,
diff-after-commit)` pairs you actually need and dedupe before spawning
build subagents.

**Spawn one build subagent per unique commit, not per branch.**  Each
unique commit needs exactly one worktree+build invocation.  After
deduping in the previous bullet, launch all unique builds in parallel
(one Agent call per commit, single message).  The parent agent then
pairs the resulting PDFs into per-branch (before, after) tuples for
rendering.

**Use system `python3` if `uv` is unavailable.**  The cropping and
summarize scripts only need PIL and numpy, both of which are usually
present in the system Python.  As a fallback you can run
`python3 scripts/crop_changed_regions.py ...` directly - it will work as
long as those modules import.
