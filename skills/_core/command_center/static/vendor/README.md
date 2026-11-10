# Dashboard vendor files

Served as-is by the command center; the dashboard page loads them with no
network.

| File | Source | sha256 (first 12) |
|------|--------|-------------------|
| `pdf.min.js` | `pdfjs-dist@3.11.174` `build/pdf.min.js` | `5b5799e6f8c6` |
| `pdf.worker.min.js` | `pdfjs-dist@3.11.174` `build/pdf.worker.min.js` | `feabdf309770` |
| `pdf_viewer.css` | `pdfjs-dist@3.11.174` `web/pdf_viewer.css` | |
| `cmaps/` | `pdfjs-dist@3.11.174` `cmaps/` (CJK character maps) | |
| `pdfjs-LICENSE` | `pdfjs-dist@3.11.174` `LICENSE` (Apache-2.0) | |
| `xterm.js`, `xterm.css`, `xterm-LICENSE` | `@xterm/xterm@5.5.0` `lib/`, `css/`, `LICENSE` (MIT) | `1f991ac3b4b2` |
| `xterm-addon-fit.js` | `@xterm/addon-fit@0.10.0` `lib/addon-fit.js` | `bdaefa370b1b` |
| `katex/katex.min.js`, `katex/katex.min.css`, `katex/fonts/*.woff2`, `katex/LICENSE` | `katex@0.16.22` `dist/` (MIT; only the woff2 fonts, which every supported browser picks first) | |
| `marked.min.js` | marked (artifact Markdown rendering) | |
| `three/three.module.min.js`, `three/three.core.min.js`, `three/LICENSE` | `three@0.183.0` `build/`, `LICENSE` (MIT); the Agents Office scene, mapped by the page's import map | `e3ec4d5d223c`, `c5f69a04c70d` |

Refresh pdf.js with `npm pack pdfjs-dist@<version>` and copy the same paths;
keep the version in step with `GlobalWorkerOptions.workerSrc` in `index.html`.
