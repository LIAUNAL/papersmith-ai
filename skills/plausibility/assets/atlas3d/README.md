# atlas3d — the 3D viewer behind `sota-pool/atlas.html`

`viewer.js` is the source of the WebGL viewer that draws the SOTA
constellation in three dimensions (three.js + OrbitControls). It is bundled
into `../atlas3d.bundle.js`, a single minified IIFE that
`scripts/render_atlas.py` inlines verbatim, so the atlas opens with no network
and the renderer stays Python stdlib-only.

## Rebuild

```bash
npm install                 # pinned three and esbuild devDependencies
npm run build:atlas-viewer  # writes ../atlas3d.bundle.js and prints its sha256
```

Commit the rebuilt bundle together with the `viewer.js` change. The build
refuses output containing `</script` (it could not be inlined) and is
reproducible: same sources and pins, same bytes.

## Division of labour

The default layout is never computed in the browser. `render_atlas.py`
computes every position, orbital frame, edge and family tie deterministically
and writes them into a `<script type="application/json" id="atlas-data">`
island; the viewer draws them as they come. "Same atlas, same sky" therefore
stays a property of the Python renderer, and the starfield uses a fixed-seed
generator, never `Math.random`.

The one client-side rearrangement is opt-in: `setLayout('groups')` (the page's
"Group layout" button) rigidly translates each whole system — planets,
rings and label together, its orbital plane untouched — so systems of one
family (its family planet's label, the rule `_family_of` uses) pack around a
family center, and family centers sit on a flat grid (`z = 0`), ordered by
sorted family label then system id: deterministic, never `Math.random`, never
written back to the data island. `setLayout('sky')` restores the precomputed
positions exactly.

## Scene contract (`version: 1`)

```text
{
  "version": 1,
  "atlas": <the atlas.json object, verbatim>,
  "positions": { "<system>.<planet>": [x, y, z], ... },
  "frames": { "<system>": { "center": [x, y, z], "u": [x, y, z], "v": [x, y, z] } },
  "edges": [ { "from": key, "to": key, "rel": str, "color": "#rrggbb", "inter": bool } ],
  "ties": [ { "family": str, "from": key, "to": key } ],
  "slot_colors": { "<slot>": "#rrggbb" },
  "orbit_radii": { "<orbit>": radius }
}
```

`u` and `v` are the orthonormal basis of a system's tilted orbital plane: a
planet on orbit `r` at angle `a` sits at `center + r·cos(a)·u + r·sin(a)·v`, and
its rings are drawn in that same plane.

## Page surface

`window.AtlasViewer.mount(container, scene, hooks)` returns a handle with
`setDim(keep | null)`, `zoom(factor)`, `reset()`, `focus(key)`,
`setLayout('sky' | 'groups')` (animates the switch, then reframes the camera;
returns the mode) and `layout()` (the current mode). `reset()` returns to the
home view of the current layout and clears dimming. `hooks.onSelect(key)` fires
on a planet click and `hooks.onHover(key | null)` on hover. The handle also
offers `rotating()` / `rotate(on?)`, `spin(angle)` / `tilt(angle)` (radians),
`project(keys)` (screen positions `{x, y, z, on}` in CSS pixels), `refresh()`,
`pause()` / `resume()` and `dispose()` (releases the WebGL context, geometries
and textures). A planet may carry a short `tip`, shown on hover instead of
`label [slot]`.

The home view fits the planets themselves: it keeps the viewing direction and
takes the least distance that keeps every planet inside both fields of view,
then centers the projected extent, so a tall or wide frame never crops the sky.
The canvas renders at least one pixel per CSS pixel (a zoomed-out browser keeps
visible points). Orbit rings and family ties are one geometry each, and a frame
is drawn only when something changed or the camera moved by about a tenth of a
pixel, so an idle sky with rotation off costs no rendering.

The page's inline script owns the side panel (a clicked planet's or paper
name's summary — topics, problem, application, novelty, contributions,
results, conclusions, family — and its linked papers), the family chips, the toolbar (zoom,
turn, tilt, rotation, names, reset, the "Group layout" toggle with
class `on` while grouped, and the 2D/3D view button) and the system names.
System names are not sprites: the page places them in an HTML layer (3D) or
on the canvas (2D), by priority, skipping any that would overlap one already
placed, so zooming in reveals more of them.

**2D constellation.** The page opens a canvas 2D view of the same scene, with
the same handle, only when the 3D sky cannot run or hangs: no WebGL at all,
or, in its first seconds, one frame longer than 1 s or an average under
5 fps. A machine without a GPU keeps the 3D sky: a software renderer
(`failIfMajorPerformanceCaveat`, or a SwiftShader / llvmpipe renderer name)
draws it at roughly 10 to 30 fps and stays usable, so it is watched like any
automatic pick instead of being sent to 2D up front; reported memory and core
counts do not matter either. `#gpunote` says why. The hang fallback is not
remembered: the next visit tries the 3D sky again. `?view=2d`
or `?view=3d` overrides the choice, and so does the view button (remembered
in `localStorage` where the frame allows it). The 2D view draws on demand,
one frame per change, and nothing at rest unless rotation is on. Either view
stops drawing while the page is hidden (`visibilitychange`) or the dashboard
paused it.

Framed by the dashboard (an `allow-scripts` sandbox, opaque origin), the page
talks to its parent with `postMessage`, and only when `window.parent !== window`:

```text
parent -> atlas  { type: 'atlas-command',
                   command: 'group-layout' | 'sky-layout' | 'toggle-layout' | 'reset'
                            | 'pause' | 'resume'     pause stops drawing until resume
                            | 'view-2d' | 'view-3d' }  switch the view (remembered)
                 { type: 'atlas-command', command: 'focus', key }
                                             fly to that paper and open its side panel
                 accepted only when event.source === window.parent; anything else is ignored
atlas -> parent  { type: 'atlas-layout', mode: 'sky' | 'groups' }      on load and on every layout command
                 { type: 'atlas-planet-selected', key, label, slot,
                   system: { id, title } }                              on a planet click (plain strings)
                 { type: 'atlas-focused', key, system: { id, title } } after a focus command
```
