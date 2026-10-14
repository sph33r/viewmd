"use strict";

(() => {
  const POLL_MS = 1000;
  const SCHEME = window.matchMedia("(prefers-color-scheme: dark)");

  const els = {
    sidebar: document.getElementById("sidebar"),
    rootName: document.getElementById("root-name"),
    tree: document.getElementById("tree"),
    content: document.getElementById("content"),
  };

  const state = { files: [], current: null, mtime: 0, source: "" };
  let diagramSeq = 0;

  // ---- routing: location.hash is "#/<path/to/file.md>[#<anchor>]" -------
  function parseHash() {
    const raw = decodeURIComponent(location.hash.replace(/^#\/?/, ""));
    const i = raw.indexOf("#");
    return i === -1
      ? { path: raw, anchor: "" }
      : { path: raw.slice(0, i), anchor: raw.slice(i + 1) };
  }

  function hashFor(path, anchor) {
    const encoded = path.split("/").map(encodeURIComponent).join("/");
    return "#/" + encoded + (anchor ? "#" + encodeURIComponent(anchor) : "");
  }

  // ---- path helpers ------------------------------------------------------
  function dirname(path) {
    const i = path.lastIndexOf("/");
    return i === -1 ? "" : path.slice(0, i);
  }

  // Resolve a relative reference against a file path; null if it leaves root.
  function resolveRel(fromFile, ref) {
    const parts = dirname(fromFile).split("/").filter(Boolean);
    for (const seg of ref.split("/")) {
      if (seg === "" || seg === ".") continue;
      if (seg === "..") {
        if (!parts.length) return null;
        parts.pop();
      } else {
        parts.push(seg);
      }
    }
    return parts.join("/");
  }

  const IMAGE_EXT = /\.(png|jpe?g|gif|webp|bmp|ico|svg)$/i;
  const MARKDOWN_EXT = /\.(md|markdown)$/i;

  function rawUrl(path) {
    return "raw/" + path.split("/").map(encodeURIComponent).join("/");
  }

  function isExternal(href) {
    return /^[a-z][a-z0-9+.-]*:/i.test(href) || href.startsWith("//");
  }

  function slugify(text) {
    return text
      .trim()
      .toLowerCase()
      .replace(/[^\p{L}\p{N}\s_-]/gu, "")
      .replace(/\s+/g, "-");
  }

  // ---- sidebar -----------------------------------------------------------
  function buildTreeModel(files) {
    const root = { dirs: new Map(), files: [] };
    for (const path of files) {
      const parts = path.split("/");
      const name = parts.pop();
      let node = root;
      for (const part of parts) {
        if (!node.dirs.has(part)) node.dirs.set(part, { dirs: new Map(), files: [] });
        node = node.dirs.get(part);
      }
      node.files.push({ name, path });
    }
    return root;
  }

  function renderTreeNode(node, container, prefix) {
    for (const [name, child] of node.dirs) {
      const details = document.createElement("details");
      details.open = true;
      const summary = document.createElement("summary");
      summary.textContent = name;
      const children = document.createElement("div");
      children.className = "children";
      details.append(summary, children);
      container.appendChild(details);
      renderTreeNode(child, children, prefix + name + "/");
    }
    for (const file of node.files) {
      const a = document.createElement("a");
      a.href = hashFor(file.path);
      a.textContent = file.name;
      a.dataset.path = file.path;
      container.appendChild(a);
    }
  }

  function renderTree(name, files) {
    els.rootName.textContent = name;
    els.tree.replaceChildren();
    renderTreeNode(buildTreeModel(files), els.tree, "");
    els.sidebar.hidden = files.length <= 1;
  }

  function markActive() {
    for (const a of els.tree.querySelectorAll("a")) {
      a.classList.toggle("active", a.dataset.path === state.current);
    }
  }

  // ---- rendering ---------------------------------------------------------
  function showStatus(message) {
    const div = document.createElement("div");
    div.className = "status";
    div.textContent = message;
    els.content.replaceChildren(div);
  }

  function addHeadingIds(root) {
    const seen = new Map();
    for (const h of root.querySelectorAll("h1,h2,h3,h4,h5,h6")) {
      const base = slugify(h.textContent) || "section";
      const n = seen.get(base) || 0;
      seen.set(base, n + 1);
      h.id = n ? `${base}-${n}` : base;
    }
  }

  function rewriteLinks(root, file) {
    for (const a of root.querySelectorAll("a[href]")) {
      const href = a.getAttribute("href");
      if (href.startsWith("#")) {
        a.dataset.anchor = decodeURIComponent(href.slice(1));
        continue;
      }
      if (isExternal(href)) {
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        continue;
      }
      const [pathPart, anchor = ""] = href.split("#");
      const resolved = resolveRel(file, decodeURIComponent(pathPart));
      if (resolved === null) continue;
      if (MARKDOWN_EXT.test(resolved)) {
        a.setAttribute("href", hashFor(resolved, decodeURIComponent(anchor)));
      } else if (IMAGE_EXT.test(resolved)) {
        a.setAttribute("href", rawUrl(resolved));
        a.target = "_blank";
      } else {
        // Only markdown and images are served; other local files are not.
        a.removeAttribute("href");
        a.title = "Not viewable in viewmd: " + resolved;
      }
    }
    for (const img of root.querySelectorAll("img[src]")) {
      const src = img.getAttribute("src");
      if (isExternal(src)) continue;
      const resolved = resolveRel(file, decodeURIComponent(src));
      if (resolved !== null) {
        img.setAttribute("src", rawUrl(resolved));
      }
    }
  }

  function highlightCode(root) {
    for (const code of root.querySelectorAll("pre > code")) {
      const lang = (code.className.match(/language-([\w+-]+)/) || [])[1];
      if (lang === "mermaid") continue;
      if (lang && hljs.getLanguage(lang)) hljs.highlightElement(code);
    }
  }

  function collectDiagrams(root) {
    for (const code of root.querySelectorAll("pre > code.language-mermaid")) {
      const holder = document.createElement("div");
      holder.className = "mermaid-diagram";
      holder.dataset.source = code.textContent;
      code.parentElement.replaceWith(holder);
    }
  }

  async function renderDiagrams(root) {
    const holders = root.querySelectorAll(".mermaid-diagram");
    if (!holders.length) return;
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: "strict",
      theme: SCHEME.matches ? "dark" : "default",
    });
    for (const holder of holders) {
      try {
        const { svg } = await mermaid.render(`mmd-${++diagramSeq}`, holder.dataset.source);
        holder.innerHTML = svg;
      } catch (err) {
        const pre = document.createElement("pre");
        pre.className = "mermaid-error";
        pre.textContent = "Mermaid error: " + (err && err.message ? err.message : err);
        holder.replaceChildren(pre);
      }
    }
  }

  async function draw(text, file) {
    els.content.innerHTML = marked.parse(text, { gfm: true });
    addHeadingIds(els.content);
    rewriteLinks(els.content, file);
    highlightCode(els.content);
    collectDiagrams(els.content);
    await renderDiagrams(els.content);
  }

  function scrollToAnchor(anchor) {
    if (!anchor) return;
    const target = document.getElementById(anchor);
    if (target) target.scrollIntoView();
  }

  // ---- loading -----------------------------------------------------------
  async function loadFile(path, anchor, keepScroll) {
    let data;
    try {
      const res = await fetch("api/file?path=" + encodeURIComponent(path));
      if (!res.ok) throw new Error(res.status === 404 ? "File not found: " + path : res.statusText);
      data = await res.json();
    } catch (err) {
      showStatus(err.message);
      return;
    }
    const scrollY = window.scrollY;
    state.current = path;
    state.mtime = data.mtime;
    state.source = data.text;
    document.title = path.split("/").pop() + " - viewmd";
    await draw(data.text, path);
    markActive();
    if (keepScroll) window.scrollTo(0, scrollY);
    else if (anchor) scrollToAnchor(anchor);
    else window.scrollTo(0, 0);
  }

  async function route() {
    const { path, anchor } = parseHash();
    if (!path) return;
    if (path === state.current && anchor) {
      scrollToAnchor(anchor);
      return;
    }
    await loadFile(path, anchor, false);
  }

  // ---- live reload -------------------------------------------------------
  async function poll() {
    if (state.current && !document.hidden) {
      try {
        const res = await fetch("api/mtime?path=" + encodeURIComponent(state.current));
        if (res.ok) {
          const { mtime } = await res.json();
          if (mtime !== state.mtime) await loadFile(state.current, "", true);
        }
      } catch (_) {
        /* server stopped or transient error; retry next tick */
      }
    }
    setTimeout(poll, POLL_MS);
  }

  // ---- startup -----------------------------------------------------------
  document.addEventListener("click", (event) => {
    const link = event.target.closest("a[data-anchor]");
    if (!link) return;
    event.preventDefault();
    scrollToAnchor(link.dataset.anchor);
  });

  window.addEventListener("hashchange", route);

  SCHEME.addEventListener("change", () => {
    if (state.current) draw(state.source, state.current);
  });

  async function init() {
    let tree;
    try {
      const res = await fetch("api/tree");
      tree = await res.json();
    } catch (err) {
      showStatus("Cannot reach the viewmd server.");
      return;
    }
    state.files = tree.files;
    renderTree(tree.name, tree.files);
    if (!tree.files.length) {
      showStatus("No markdown files found.");
      return;
    }
    if (!parseHash().path) location.hash = hashFor(tree.initial);
    else await route();
    poll();
  }

  init();
})();
