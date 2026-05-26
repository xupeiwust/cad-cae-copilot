# Screenshot Rendering

Use this reference whenever an iteration must generate visual review screenshots. Screenshots are required review evidence, not decoration.

## Required Outputs

Each iteration must attempt to create:

```text
exports/pipeline/<iteration>/render_views/front.png
exports/pipeline/<iteration>/render_views/side.png
exports/pipeline/<iteration>/render_views/top.png
exports/pipeline/<iteration>/render_views/iso.png
```

Diagnostic views are recommended for complex iterations:

```text
exports/pipeline/<iteration>/render_views/wire_iso.png
exports/pipeline/<iteration>/render_views/section.png
exports/pipeline/<iteration>/render_views/detail_contact_sheet.png
```

## Renderer Priority

Use this order:

1. Python offscreen renderer from STL, preferably `pyvista`/VTK.
2. Three.js with browser automation, for example Playwright or Puppeteer.
3. Blender CLI if already installed.
4. `render_unavailable.json` only after the attempted renderer and failure reason are recorded.

Do not silently install dependencies. If `pyvista`, VTK, Playwright, Puppeteer, or Blender is missing, ask before installing.

## Python Offscreen Rendering

Preferred automatic path:

1. Export the iteration to STL.
2. Load the STL with `pyvista`.
3. Render deterministic front, side, top, and iso cameras.
4. Write PNGs under `render_views/`.
5. Record generated screenshot paths in `review_packet.json` and `review_packet.md`.

Check availability:

```powershell
python -c "import pyvista, vtk; print('pyvista renderer ok')"
```

If this command fails, do not pretend screenshots were generated. Either use another installed renderer or write `render_unavailable.json`.

## Three.js Screenshot Reality

Three.js can render the model in `visual_review.html`, but a static HTML file alone does not reliably write PNG files to disk.

Three.js can generate screenshots only when one of these is true:

- A human opens the page and downloads a canvas image.
- Browser automation opens the page and saves screenshots.
- The page is served by a local HTTP server and automation captures the canvas or viewport.

Therefore:

- Keep Three.js in `visual_review.html` for interactive inspection.
- Do not count Three.js as generated screenshot evidence unless automation actually writes `front.png`, `side.png`, `top.png`, and `iso.png`.
- If using browser automation, record the attempted renderer as `threejs-playwright` or `threejs-puppeteer`.

Example browser automation flow:

```powershell
python -m http.server 8000 --directory exports/pipeline/iteration_02_surface_refine
```

Then automation opens `http://127.0.0.1:8000/visual_review.html`, sets camera views, and saves screenshots.

## Blender CLI Fallback

If Blender is already installed, it can load STL and render views in background mode:

```powershell
blender --background --python scripts/render_iteration_blender.py -- exports/pipeline/iteration_02_surface_refine/iteration_02_surface_refine.stl exports/pipeline/iteration_02_surface_refine/render_views
```

Use Blender only if available or the user approves installing/configuring it.

## Failure Rules

If all renderers fail:

- Write `exports/pipeline/<iteration>/render_unavailable.json`.
- Include attempted renderer, command or import attempted, failure reason, and fallback mode.
- Still create template-compliant `visual_review.html`.
- Do not claim screenshot inspection was performed.
- Do not mark `export_ready` when visual confidence depends on missing screenshots.
