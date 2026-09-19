# NSFW Cover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mark X videos that X flags as sensitive, and show them covered: a blurred tile with red "NSFW", a paused, blurred player until a tap, and no picture in link previews.

**Architecture:** yt-dlp's `age_limit` (18 for X's `possibly_sensitive`) becomes `MediaInfo.nsfw` → `JobResult.nsfw` → `"nsfw"` in the job JSON. `pages.render_watch` drops `og:image` for NSFW reels. The board tile (`board.js`) and the shared player (`player.js`, markup in `app.html` and `watch.html`) draw the cover with CSS. `dev_board.py` gets an NSFW seed and an `nsfw` word so it can be tried by hand.

**Tech Stack:** Python 3.12, FastAPI, yt-dlp, pytest; plain HTML/CSS/ES modules (no build, no JS tests).

**Spec:** `docs/superpowers/specs/2026-09-18-nsfw-cover-design.md`

## Global Constraints

- The job JSON change is additive: `"nsfw": true | false` on done jobs only.
- NSFW means yt-dlp `age_limit` ≥ 18. Missing or non-numeric is not NSFW. There is no manual marking.
- The label text is exactly `NSFW`, colour `var(--danger-text)`.
- The preview description is exactly `NSFW · ` + the normal description, e.g. `NSFW · X · 0:19`.
- The player markup exists in `app.html` and `watch.html`: mirror every change.
- No new JS modules, no JS dependencies, no requests to other sites.
- Run tests with `.venv\Scripts\python.exe -m pytest` (Windows; ffmpeg is not installed locally).
- Commits: small, prefixed `feat:` / `docs:`, ending with the `Co-Authored-By` line.

---

### Task 1: The nsfw flag, from yt-dlp to the job JSON

**Files:**
- Modify: `reels_api/models.py` (`MediaInfo`, `JobResult`, `job_to_dict`)
- Modify: `reels_api/downloader.py` (`download`)
- Modify: `reels_api/pipeline.py` (`Pipeline.run`)
- Test: `tests/test_downloader.py`, `tests/test_pipeline.py`, `tests/test_models.py`

**Interfaces:**
- Produces: `MediaInfo.nsfw: bool = False`, `JobResult.nsfw: bool = False` (last field), and `job_to_dict(job)["nsfw"]` for done jobs.

- [ ] **Step 1: Write the failing tests**

`tests/test_downloader.py` (append):
```python
@pytest.mark.parametrize("age_limit,nsfw", [(18, True), (21, True), ("18", True), (0, False), (None, False), ("junk", False)])
def test_download_marks_adult_content_nsfw(tmp_path, fake_ydl, age_limit, nsfw):
    fake_ydl.info = {"title": "Hello", "age_limit": age_limit}
    result = downloader.download(X_URL, tmp_path)
    assert result.info.nsfw is nsfw
```

`tests/test_pipeline.py` (append; also add `assert result.nsfw is False` at the end of `test_pipeline_success`):
```python
def test_pipeline_passes_nsfw(tmp_path):
    settings = make_settings(tmp_path)
    calls = []

    def download_nsfw(url, dest_dir, cookies_file=None, item=1):
        p = dest_dir / "source.mp4"
        p.write_bytes(b"\x00" * 10)
        return DownloadedMedia(p, MediaInfo("Title", 10.0, 720, 1280, nsfw=True))

    p = Pipeline(
        settings=settings,
        downloader=download_nsfw,
        prober=fake_probe_factory(calls),
        converter=fake_convert_factory(calls),
        thumbnailer=fake_thumbnail_factory(calls),
    )
    assert p.run(make_job(), lambda s: None).nsfw is True
```

`tests/test_models.py` (append):
```python
def test_job_to_dict_nsfw():
    job = Job(id="abc", url="u", source=Source.X, status=JobStatus.DONE)
    job.result = _result(10)
    assert job_to_dict(job)["nsfw"] is False
    job.result.nsfw = True
    assert job_to_dict(job)["nsfw"] is True
    assert "nsfw" not in job_to_dict(Job(id="q", url="u", source=Source.X))
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_downloader.py tests/test_pipeline.py tests/test_models.py`
Expected: FAIL (`MediaInfo` has no `nsfw`, `KeyError: 'nsfw'`).

- [ ] **Step 3: Implement**

`models.py`: add `nsfw: bool = False` as the last field of `MediaInfo`, and as the last field of `JobResult`. In `job_to_dict`'s done branch add `"nsfw": r.nsfw,` after `"share_key"`.

`downloader.py`: next to `_to_int`:
```python
def _is_nsfw(age_limit) -> bool:
    """X's "sensitive content" flag arrives as yt-dlp's age_limit 18 (NSFW cover spec 2)."""
    limit = _to_int(age_limit)
    return limit is not None and limit >= 18
```
and in `download`'s `MediaInfo(...)` add `nsfw=_is_nsfw(info.get("age_limit")),`.

`pipeline.py`: in `run`'s `JobResult(...)` add `nsfw=info.nsfw,`.

- [ ] **Step 4: Run the whole suite**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add reels_api/models.py reels_api/downloader.py reels_api/pipeline.py tests/test_downloader.py tests/test_pipeline.py tests/test_models.py
git commit -m "feat: nsfw flag from X's sensitive-content marking, in the job JSON"
```

---

### Task 2: No picture in an NSFW reel's link preview

**Files:**
- Modify: `reels_api/pages.py` (`render_watch`)
- Test: `tests/test_pages.py`

**Interfaces:**
- Consumes: `JobResult.nsfw` (Task 1).

- [ ] **Step 1: Write the failing test**

In `tests/test_pages.py`, give `_job` a parameter `nsfw=False` and pass `nsfw=nsfw` to `JobResult(...)`. Then append:
```python
def test_render_watch_nsfw_has_no_picture_and_says_so():
    job = _job(source=Source.X, nsfw=True)
    page = pages.render_watch(job, BASE)
    assert meta(page, "og:image") is None
    assert meta(page, "og:description") == "NSFW · X · 0:19"
    assert meta(page, "og:title") == "wait for it"
    data = reel_data(page)
    assert data["nsfw"] is True
    assert data["thumbnail_url"] == f"/files/abc123.jpg?k={job.share_key}"  # the page's own cover blurs it
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_pages.py`
Expected: FAIL on `og:image`.

- [ ] **Step 3: Implement**

In `render_watch`, replace the `image_tag` block and the `description` value:
```python
    description = preview_description(result.source, result.duration_seconds)
    image_tag = ""
    if result.nsfw:
        description = f"NSFW · {description}"  # and no picture in the chat (NSFW cover spec 3)
    elif result.thumbnail_path is not None:
        image_url = html.escape(f"{base_url}/files/{job.id}.jpg?k={key}", quote=True)
        image_tag = f'<meta property="og:image" content="{image_url}">'
```
and pass `"description": description` to `fill`.

- [ ] **Step 4: Run the whole suite** — all pass.

- [ ] **Step 5: Commit**

```bash
git add reels_api/pages.py tests/test_pages.py
git commit -m "feat: an NSFW reel's link preview has no picture and says NSFW"
```

---

### Task 3: NSFW reels in dev_board

**Files:**
- Modify: `scripts/dev_board.py` (`store_clip`, `DevPipeline.run`, `seed_jobs`, docstring)
- Test: `tests/test_dev_board.py`

**Interfaces:**
- Consumes: `JobResult.nsfw` (Task 1).
- Produces: `dev_board.NSFW_WORD = "nsfw"`, `dev_board.NSFW_SEED = 3` (the first `Source.X` seed), `store_clip(..., nsfw: bool = False)`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_dev_board.py`)

```python
def test_dev_pipeline_nsfw_word_marks_the_reel(tmp_path):
    pipeline = dev_board.DevPipeline(make_settings(tmp_path), fake_clips(tmp_path), delay=0)
    nsfw = pipeline.run(Job(id="j1", url="https://x.com/dev/status/nsfw", source=Source.X), lambda s: None)
    plain = pipeline.run(Job(id="j2", url="https://x.com/dev/status/1", source=Source.X), lambda s: None)
    assert nsfw.nsfw is True
    assert plain.nsfw is False


def test_seed_jobs_have_one_nsfw_x_reel(tmp_path):
    jobs = dev_board.seed_jobs(make_settings(tmp_path), fake_clips(tmp_path))
    nsfw = [j for j in jobs if j.result.nsfw]
    assert [j.id for j in nsfw] == [f"seed{dev_board.NSFW_SEED:02d}"]
    assert nsfw[0].source == Source.X
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_dev_board.py`
Expected: FAIL (`AttributeError: NSFW_SEED`, `nsfw` false).

- [ ] **Step 3: Implement**

Constants next to `PARTIAL_WORD`:
```python
NSFW_WORD = "nsfw"  # a pasted link with this word gives an NSFW reel (NSFW cover spec 6)
NSFW_SEED = 3  # the first X seed
```
`store_clip` gets `nsfw: bool = False` and passes `nsfw=nsfw` to `JobResult`. `DevPipeline.run` returns `store_clip(self.settings, clip, job, f"pasted from {job.url}", nsfw=NSFW_WORD in job.url)`. `seed_jobs` passes `nsfw=i == NSFW_SEED`. Add to the docstring: `A link containing "nsfw" gives an NSFW reel, and seed 3 is one.`

- [ ] **Step 4: Run the whole suite** — all pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/dev_board.py tests/test_dev_board.py
git commit -m "feat: an NSFW seed and an nsfw word in dev_board"
```

---

### Task 4: The covered tile

**Files:**
- Modify: `reels_api/static/board.js` (`buildTile`, `updateTile`)
- Modify: `reels_api/static/style.css` (new block after the `.tile.pending` rules)

**Interfaces:**
- Consumes: `reel.nsfw` from the job JSON (Task 1).
- Produces: CSS class `.nsfw-label` (also used by the player cover in Task 5).

- [ ] **Step 1: Implement the tile**

In `buildTile`, after the thumbnail `if` block:
```js
    if (reel.nsfw) {
      // Covered, not locked: the thumbnail is blurred and labelled (NSFW cover spec 4).
      tile.classList.add("nsfw");
      const label = document.createElement("span");
      label.className = "nsfw-label";
      label.textContent = "NSFW";
      tile.append(label);
    }
```
In `updateTile`, make the label say so: `tile.setAttribute("aria-label", `${reel.nsfw ? "play NSFW reel" : "play"}, ${ago}`);`

In `style.css`, after `.tile.pending .badge`:
```css
/* ---- NSFW cover (NSFW cover spec 4, 5) ---- */

.nsfw-label {
  font: 800 15px var(--font);
  letter-spacing: 0.16em;
  color: var(--danger-text);
  text-shadow: 0 1px 10px rgba(0, 0, 0, 0.7);
}
.tile.nsfw img { filter: blur(14px) brightness(0.5); transform: scale(1.15); }
.tile.nsfw .nsfw-label {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}
```

- [ ] **Step 2: Check syntax and the suite**

Run: `node --check reels_api/static/board.js` and `.venv\Scripts\python.exe -m pytest -q`
Expected: no output from node; all tests pass.

- [ ] **Step 3: Check by hand** (dev_board in Docker, README command): the seed-3 tile is blurred with red "NSFW"; the other tiles are unchanged.

- [ ] **Step 4: Commit**

```bash
git add reels_api/static/board.js reels_api/static/style.css
git commit -m "feat: NSFW tiles are blurred with a red NSFW label"
```

---

### Task 5: The covered player

**Files:**
- Modify: `reels_api/static/app.html`, `reels_api/static/watch.html` (cover markup after `<video>`)
- Modify: `reels_api/static/player.js`
- Modify: `reels_api/static/style.css`
- Test: `tests/test_pages.py`

**Interfaces:**
- Consumes: `reel.nsfw` (Task 1), `.nsfw-label` (Task 4).
- Produces: player root class `is-covered`, action `reveal`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_pages.py`)

```python
def test_both_players_have_the_nsfw_cover():
    # The player markup lives in app.html and watch.html; the cover must be in both.
    for page in (pages.render_app(False), pages.render_watch(_job(), BASE)):
        assert page.count('<div class="nsfw-cover" hidden>') == 1
        assert page.count('data-action="reveal"') == 1
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_pages.py`
Expected: FAIL (count 0).

- [ ] **Step 3: Add the markup** to both files, right after `<video playsinline loop preload="auto"></video>`:
```html
          <div class="nsfw-cover" hidden>
            <span class="nsfw-label">NSFW</span>
            <button class="btn nsfw-reveal" type="button" data-action="reveal">tap to watch</button>
          </div>
```

- [ ] **Step 4: Run the test** — passes.

- [ ] **Step 5: Implement the player** (`player.js`)

After `const desktopFocus = …`:
```js
  const cover = root.querySelector(".nsfw-cover");
```
With the other state:
```js
  const uncovered = new Set(); // NSFW reels tapped open while this page is open (NSFW cover spec 5)
```
After `isOpen`:
```js
  const isCovered = () => root.classList.contains("is-covered");

  function setCovered(covered) {
    root.classList.toggle("is-covered", covered);
    cover.hidden = !covered;
  }
```
First line of `play()`:
```js
    if (isCovered()) return; // an NSFW reel waits for a tap
```
After `play()`:
```js
  // A tap on a covered reel: it stays uncovered while the page is open.
  function uncover() {
    uncovered.add(current().id);
    setCovered(false);
    play();
  }
```
In `show(i)`, after `video.src = reel.file_url;`:
```js
    setCovered(Boolean(reel.nsfw) && !uncovered.has(reel.id));
```
In `actions`: `reveal: uncover,`.
Desktop frame click becomes:
```js
    if (isCovered()) uncover();
    else togglePlay();
```
Phone tap in `pointerup` becomes:
```js
      setFrame(0, 0);
      if (isCovered()) uncover();
      else setChrome(!root.classList.contains("chrome-on"));
      return;
```

- [ ] **Step 6: Style it** (`style.css`, in the NSFW block from Task 4):
```css
.player.is-covered .player-frame video { filter: blur(28px) brightness(0.45); transform: scale(1.12); }
.nsfw-cover {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
}
.nsfw-cover .nsfw-label { font-size: 26px; }
.nsfw-reveal { height: 40px; background: rgba(0, 0, 0, 0.35); }
```

- [ ] **Step 7: Check syntax and the suite**

Run: `node --check reels_api/static/player.js` and `.venv\Scripts\python.exe -m pytest -q`
Expected: no output from node; all tests pass.

- [ ] **Step 8: Check by hand** (dev_board in Docker, in Chrome):
- opening the seed-3 reel shows it paused and blurred with "NSFW" and "tap to watch";
- a tap or click uncovers and plays it;
- swiping or arrowing past a covered reel moves on and doesn't play it;
- coming back to an uncovered reel keeps it uncovered;
- a pasted `https://x.com/dev/status/nsfw` lands covered;
- its share link in a private window opens covered on the view-only page;
- a reload covers it again.

- [ ] **Step 9: Commit**

```bash
git add reels_api/static/app.html reels_api/static/watch.html reels_api/static/player.js reels_api/static/style.css tests/test_pages.py
git commit -m "feat: the player opens NSFW reels covered until a tap"
```

---

### Task 6: Docs

**Files:**
- Modify: `README.md` (board bullets; `GET /jobs/{id}` row gains `nsfw`; dev_board `nsfw` word)
- Modify: `CLAUDE.md` (job JSON / frontend notes; dev_board word; "Things we learned": NSFW X tweets need x.com cookies to download at all)

- [ ] **Step 1: Write the docs**
  - README board section, a new bullet: "**NSFW**: X videos that X marks as sensitive show blurred with a red NSFW label, open paused until tapped, and their link preview has no picture. Logged out, X mostly refuses NSFW tweets altogether, so they need x.com cookies (below)."
  - The `GET /jobs/{id}` row: add `nsfw` to the list of done fields.
  - dev_board paragraphs (README and CLAUDE.md): "a link containing `nsfw` gives an NSFW reel; seed 3 is one".

- [ ] **Step 2: Run the whole suite** — all pass.

- [ ] **Step 3: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: the NSFW cover in README and CLAUDE.md"
```
