# vendor

Third-party browser libraries, loaded by `web/index.html`. `SHA256SUMS` is
verified by `viewmd.py` at startup; only files listed in it are served.

## Updating a library

1. Download the file from the package's npm tarball:

   ```bash
   npm pack <package>@<version>
   tar -xzf <package>-<version>.tgz package/<path-to-file>
   ```

   Using the tarball from the npm registry avoids trusting a CDN copy.
2. Copy the file into this folder under the name used in `SHA256SUMS`.
3. Regenerate the checksums:

   ```bash
   sha256sum *.js *.css > SHA256SUMS
   ```
4. Update the version table in the top-level `README.md`.

## Source files

| File | Path inside the npm package |
|------|-----------------------------|
| `marked.umd.js` | `marked`: `lib/marked.umd.js` |
| `mermaid.min.js` | `mermaid`: `dist/mermaid.min.js` |
| `highlight.min.js` | `@highlightjs/cdn-assets`: `highlight.min.js` |
| `hljs-light.css` | `@highlightjs/cdn-assets`: `styles/github.min.css` |
| `hljs-dark.css` | `@highlightjs/cdn-assets`: `styles/github-dark.min.css` |
| `github-markdown.css` | `github-markdown-css`: `github-markdown.css` |

`.gitattributes` disables line-ending conversion in this folder so the
checksums hold on Windows checkouts.
