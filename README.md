# viewmd

Local markdown viewer. Python standard library only, no additional installs required.

## AI Disclosure

Claude was used to create this.

## Why Make This?

I work in a locked down enterprise environment and I'm not allowed to install things.
I am, however, allowed to use Python. So I created this to let me view markdown
files from the CLI. It'll pop open my web browser, I can view the doc, close the
browser window, and jump back to terminal quickly.

It handles syntax highlighting and Mermaid diagrams. Just the bare minimum to meet
my requirements from day to day.

I tried to keep security in mind so the external libraries packaged with the script
are pinned and checksum-verified on start. You also can't display external images
and the viewer won't run any embedded scripts found in the markdown files.

## What It Is

A small HTTP server on `127.0.0.1` serves markdown files and opens the default
browser. Rendering runs in the browser using libraries vendored in this repo,
so it works without internet access.

## Requirements

- Python 3.10 or newer
- A modern browser (JavaScript enabled)

## Usage

```bash
python viewmd.py                 # current folder
python viewmd.py README.md       # single file
python viewmd.py path/to/docs    # folder with sidebar
python viewmd.py docs -p 8765    # fixed port
python viewmd.py docs --no-browser
```

Stop with `Ctrl+C`.

## Features

- GitHub-flavored markdown (tables, task lists, strikethrough, autolinks)
- Mermaid diagrams from fenced `mermaid` code blocks
- Syntax highlighting for fenced code blocks
- Folder sidebar; relative links between `.md` files navigate in place
- Relative images resolve against the current file
- Live reload when the open file changes on disk
- Light and dark themes follow the OS setting

## Layout

```
viewmd.py   server and CLI
web/        index.html, app.js, app.css
vendor/     third-party browser libraries
```

## Security

- Listens on `127.0.0.1` only. The URL includes a random token, so other
  users or programs on the machine cannot read your documents.
- Serves only markdown files and images from the opened folder.
- Scripts embedded in markdown do not run, and pages cannot contact other
  hosts. As a result, remote images are not displayed.
- Bundled libraries are checksum-verified at startup; viewmd exits if one
  has been modified.

## Vendored libraries

| File                                           | Package             | Version | License      |
| ---------------------------------------------- | ------------------- | ------- | ------------ |
| `vendor/marked.umd.js`                         | marked              | 18.1.1  | MIT          |
| `vendor/mermaid.min.js`                        | mermaid             | 12.2.0  | MIT          |
| `vendor/highlight.min.js`, `vendor/hljs-*.css` | highlight.js        | 11.11.1 | BSD-3-Clause |
| `vendor/github-markdown.css`                   | github-markdown-css | 5.9.0   | MIT          |

To update a library, replace the file, then regenerate the checksums and
update the table above:

```bash
cd vendor && sha256sum *.js *.css > SHA256SUMS
```

See `vendor/README.md` for how to check a new file before trusting it.
