/* Desglosa — visor interactivo. Sin dependencias externas.
 * Seguridad: todo texto que viene del código analizado se pinta con textContent o
 * atributos de createElementNS; nunca se interpreta como HTML.
 */
(() => {
  "use strict";

  const SVG_NS = "http://www.w3.org/2000/svg";
  const DATA = JSON.parse(document.getElementById("desglosa-data").textContent);
  // Se llenan al abrir el índice comprimido (ver openIndex al final).
  let SYMBOLS = {};
  let MAP = null;

  /** Texto base64 url-safe de zlib → objeto JSON (DecompressionStream, sin librerías). */
  function inflate(text) {
    if (typeof DecompressionStream === "undefined") return Promise.reject(new Error("navegador-antiguo"));
    const bin = atob(text.replace(/-/g, "+").replace(/_/g, "/"));
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("deflate"));
    return new Response(stream).text().then((json) => JSON.parse(json));
  }

  const OLD_BROWSER = "Tu navegador no puede abrir los diagramas comprimidos. Usa Chrome, Edge, Firefox o Safari actualizados.";

  // ------------------------------------------------------------------ paquetes por archivo
  // Los flujos, secuencias y el código de cada archivo vienen comprimidos (zlib + base64)
  // y se abren solo cuando hacen falta: así un proyecto grande abre rápido.
  const PACKS = {};
  const loading = {};

  function hasFlow(sid) {
    return !!(SYMBOLS[sid] && SYMBOLS[sid].flow);
  }

  function packOf(sid) {
    const sym = SYMBOLS[sid];
    return sym ? PACKS[sym.file] || null : null;
  }

  function flowOf(sid) {
    const p = packOf(sid);
    return p && p.flows ? p.flows[sid] || null : null;
  }

  function sequenceOf(sid) {
    const p = packOf(sid);
    return p && p.sequence ? p.sequence[sid] || null : null;
  }

  function sourceOf(file) {
    const p = PACKS[file];
    return p && typeof p.source === "string" ? p.source : null;
  }

  function loadPack(file) {
    if (PACKS[file]) return Promise.resolve(PACKS[file]);
    if (loading[file]) return loading[file];
    const text = DATA.packs && DATA.packs[file];
    if (!text) {
      PACKS[file] = { flows: {}, sequence: {}, source: null };
      return Promise.resolve(PACKS[file]);
    }
    loading[file] = inflate(text).then(
      (pack) => {
        PACKS[file] = pack;
        delete loading[file];
        return pack;
      },
      (err) => {
        delete loading[file];
        throw err;
      },
    );
    return loading[file];
  }
  const LINE_H = 16;
  const $ = (id) => document.getElementById(id);

  const NODE_NAMES = {
    terminal: "Inicio / Fin",
    proceso: "Proceso",
    subproceso: "Subproceso (clic para abrir)",
    decision: "Decisión",
    es: "Entrada / salida (archivo)",
    teclado: "Lectura de teclado",
    pantalla: "Salida en pantalla",
    documento: "Escritura de archivo",
    externo: "Llamada externa",
    conector: "Conector",
    excepcion: "Excepción",
    modulo: "Módulo / carpeta",
    clase: "Clase o archivo",
    interfaz: "Interfaz",
    funcion: "Función / método",
    entrada: "Punto de entrada",
    otros: "Agrupados",
    tabla: "Tabla",
    bd: "Base de datos",
  };
  const CONF_NAMES = {
    exacta: "Relación exacta",
    probable: "Relación probable",
    ambigua: "Relación ambigua",
    externa: "Externa",
  };

  const state = {
    mode: "facil",
    theme: "oscuro",
    view: null,
    id: null,
    focus: null,
    trail: [],
    pendingTrail: null,
    transform: { k: 1, x: 0, y: 0 },
    size: { w: 0, h: 0 },
    keepTransform: false,
    dragged: false,
    selectedNode: null,
    showExternal: false,
    legendClosed: false,
    route: null, // vista "Trazar ruta": cadena dibujada y controles
    routeStep: null,
    routeTimer: null,
  };

  // ------------------------------------------------------------------ utilidades DOM

  function h(tag, attrs, ...children) {
    const el = document.createElement(tag);
    setAttrs(el, attrs);
    appendAll(el, children);
    return el;
  }

  function s(tag, attrs, ...children) {
    const el = document.createElementNS(SVG_NS, tag);
    setAttrs(el, attrs);
    appendAll(el, children);
    return el;
  }

  function setAttrs(el, attrs) {
    if (!attrs) return;
    for (const [k, v] of Object.entries(attrs)) {
      if (v === null || v === undefined || v === false) continue;
      if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : String(v));
    }
  }

  function appendAll(el, children) {
    for (const c of children.flat()) {
      if (c === null || c === undefined || c === false) continue;
      el.appendChild(typeof c === "string" || typeof c === "number" ? document.createTextNode(String(c)) : c);
    }
  }

  function clear(el) {
    while (el.firstChild) el.removeChild(el.firstChild);
  }

  // ------------------------------------------------------------------ rutas (#/vista/id?param)

  function parseHash() {
    let raw = location.hash.replace(/^#/, "");
    try {
      raw = decodeURIComponent(raw);
    } catch (_e) {
      /* hash mal formado: se usa tal cual */
    }
    const [path, query] = raw.split("?");
    const parts = path.split("/").filter(Boolean);
    return { view: parts[0] || null, id: parts.slice(1).join("/") || null, params: new URLSearchParams(query || "") };
  }

  function buildHash(view, id, focus) {
    let out = "#/" + view + (id ? "/" + id : "");
    const p = new URLSearchParams();
    if (focus) p.set("focus", focus);
    if (state.mode !== "facil") p.set("modo", state.mode);
    if (state.theme !== "oscuro") p.set("tema", state.theme);
    const q = p.toString();
    return q ? out + "?" + q : out;
  }

  function go(view, id, opts) {
    const target = buildHash(view, id, opts && opts.focus);
    if (opts && opts.trail) state.pendingTrail = opts.trail;
    if (location.hash === target) render();
    else location.hash = target;
  }

  function syncHash() {
    history.replaceState(null, "", buildHash(state.view, state.id, state.focus));
  }

  function startRoute() {
    const start = (DATA.meta && DATA.meta.start) || "#/mapa";
    const tmp = start.replace(/^#\//, "").split("/");
    return { view: tmp[0], id: tmp.slice(1).join("/") || null };
  }

  // ------------------------------------------------------------------ render principal

  function render() {
    const r = parseHash();
    state.mode = r.params.get("modo") === "tecnico" ? "tecnico" : "facil";
    state.theme = r.params.get("tema") === "claro" ? "claro" : "oscuro";
    state.focus = r.params.get("focus");
    document.documentElement.dataset.tema = state.theme;
    let view = r.view;
    let id = r.id;
    if (!view) {
      const st = startRoute();
      view = st.view;
      id = st.id;
    }
    const sameView = view === state.view && id === state.id;
    state.keepTransform = sameView;
    state.view = view;
    state.id = id;
    if (["flujo", "secuencia", "codigo"].includes(view) && id) updateTrail(id);
    if (!sameView) { state.selectedNode = null; state.routeStep = null; }
    if (view !== "ruta") { stopRoutePlay(); state.route = null; }

    renderToolbar();
    // Vistas de una función: primero se abre el paquete de su archivo.
    const file = ["flujo", "secuencia", "codigo"].includes(view) && SYMBOLS[id] ? SYMBOLS[id].file : null;
    if (file && !PACKS[file]) {
      renderCrumbs();
      showEmpty("Cargando " + file + "…");
      const want = location.hash;
      loadPack(file).then(
        () => { if (location.hash === want) { state.view = null; render(); } },
        (err) => showEmpty(err && err.message === "navegador-antiguo"
          ? OLD_BROWSER
          : "No se pudo abrir los datos de " + file + "."),
      );
      return;
    }
    if (view === "mapa") renderMap(id);
    else if (view === "flujo") renderFlow(id);
    else if (view === "secuencia") renderSequence(id);
    else if (view === "codigo") renderCodeView(id);
    else if (view === "er") renderER();
    else if (view === "galaxia") renderGalaxy();
    else if (view === "arquitectura") renderArch();
    else if (view === "ruta") renderRoute(id);
    else renderMap(null);
    renderCrumbs();
  }

  function updateTrail(id) {
    if (state.pendingTrail) {
      state.trail = state.pendingTrail;
      state.pendingTrail = null;
      return;
    }
    const i = state.trail.indexOf(id);
    if (i >= 0) state.trail = state.trail.slice(0, i + 1);
    else state.trail = [id];
  }

  // ------------------------------------------------------------------ barra: herramientas

  let toolbarBuilt = false;
  const tools = {};

  function renderToolbar() {
    const bar = $("herramientas");
    if (!toolbarBuilt) {
      toolbarBuilt = true;
      const search = buildSearch();
      tools.mode = h("button", { class: "boton", type: "button", title: "Modo fácil / técnico (m)", onclick: toggleMode });
      tools.theme = h("button", { class: "boton", type: "button", title: "Tema claro / oscuro (t)", onclick: toggleTheme });
      const zoomOut = h("button", { class: "boton", type: "button", title: "Alejar (-)", "aria-label": "Alejar", onclick: () => zoomBy(1 / 1.25) }, "−");
      const zoomIn = h("button", { class: "boton", type: "button", title: "Acercar (+)", "aria-label": "Acercar", onclick: () => zoomBy(1.25) }, "+");
      const fitBtn = h("button", { class: "boton", type: "button", title: "Encuadrar (f)", onclick: () => { fit(); apply(); } }, "Encuadrar");
      tools.exportSvg = h("button", { class: "boton", type: "button", title: "Exportar la vista como SVG", onclick: exportSVG }, "SVG");
      tools.exportPng = h("button", { class: "boton", type: "button", title: "Exportar la vista como PNG", onclick: exportPNG }, "PNG");
      const helpBtn = h("button", { class: "boton", type: "button", title: "Ayuda y atajos de teclado (?)", "aria-label": "Ayuda", onclick: showHelp }, "?");
      appendAll(bar, [search, tools.mode, tools.theme, zoomOut, zoomIn, fitBtn, tools.exportSvg, tools.exportPng, helpBtn]);
    }
    tools.mode.textContent = state.mode === "facil" ? "Modo: fácil" : "Modo: técnico";
    tools.mode.setAttribute("aria-pressed", state.mode === "tecnico" ? "true" : "false");
    tools.theme.textContent = state.theme === "oscuro" ? "Tema: oscuro" : "Tema: claro";
  }

  // ------------------------------------------------------------------ ayuda

  const HELP = [
    ["Clic", "Entrar a un elemento del mapa o abrir el flujo de un subproceso"],
    ["Alt+clic o E", "Enfocar: resalta de qué depende un elemento y qué depende de él"],
    ["Esc", "Quitar el enfoque o subir un nivel"],
    ["/", "Buscar una función, clase o archivo"],
    ["+  −  0", "Acercar, alejar y tamaño real"],
    ["F", "Encuadrar el diagrama en la pantalla"],
    ["Arrastrar / rueda", "Mover y hacer zoom"],
    ["M", "Modo fácil (español) o técnico (código)"],
    ["Trazar ruta", "Botón del panel de una función: el camino de llamadas hasta otra función o la base de datos"],
    ["←  →  espacio", "En «Trazar ruta»: paso anterior, siguiente y reproducir"],
    ["T", "Tema claro u oscuro"],
    ["?", "Mostrar esta ayuda"],
  ];
  let helpDialog = null;

  function showHelp() {
    if (!helpDialog) {
      const rows = HELP.map(([k, v]) => h("tr", null, h("th", { scope: "row" }, h("kbd", null, k)), h("td", null, v)));
      const close = h("button", { class: "boton", type: "button", onclick: () => helpDialog.close() }, "Cerrar");
      helpDialog = h("dialog", { class: "ayuda", "aria-labelledby": "ayuda-titulo" },
        h("h2", { id: "ayuda-titulo" }, "Cómo usar Desglosa"),
        h("p", null, "Mapa → clic para bajar de nivel → flujo de cada función. Las migas de arriba sirven para volver."),
        h("table", null, h("tbody", null, ...rows)),
        h("p", { class: "nota" }, "Las líneas punteadas o grises son relaciones menos seguras (probable, ambigua o externa)."),
        close);
      document.body.appendChild(helpDialog);
    }
    if (!helpDialog.open) helpDialog.showModal();
  }

  function toggleFocus(nid) {
    state.focus = state.focus === nid ? null : nid;
    syncHash();
    rerender();
  }

  function toggleMode() {
    state.mode = state.mode === "facil" ? "tecnico" : "facil";
    syncHash();
    rerender();
  }

  function toggleTheme() {
    state.theme = state.theme === "oscuro" ? "claro" : "oscuro";
    document.documentElement.dataset.tema = state.theme;
    syncHash();
    renderToolbar();
  }

  function rerender() {
    state.keepTransform = true;
    const keep = state.selectedNode;
    renderToolbar();
    if (state.view === "flujo") renderFlow(state.id);
    else if (state.view === "mapa" || !state.view) renderMap(state.id);
    else if (state.view === "secuencia") renderSequence(state.id);
    else if (state.view === "galaxia") renderGalaxy();
    else if (state.view === "arquitectura") renderArch();
    else if (state.view === "ruta") renderRoute(state.id);
    state.selectedNode = keep;
  }

  // ------------------------------------------------------------------ buscador

  let searchIndex = null;

  function buildIndex() {
    const out = [];
    for (const [id, sym] of Object.entries(SYMBOLS)) {
      if (sym.kind === "module") continue;
      out.push({ id, label: sym.qualname, name: sym.name.toLowerCase(), q: sym.qualname.toLowerCase(), kind: sym.kind, file: sym.file });
    }
    for (const t of (DATA.er && DATA.er.tables) || []) {
      out.push({ id: t.id, label: t.name, name: t.name.toLowerCase(), q: t.name.toLowerCase(), kind: "tabla", file: t.file });
    }
    out.sort((a, b) => a.label.localeCompare(b.label));
    return out;
  }

  function buildSearch() {
    const box = h("div", { class: "buscador" });
    const input = h("input", { type: "search", id: "buscar", placeholder: "Buscar (/)", "aria-label": "Buscar funciones, clases y tablas", autocomplete: "off" });
    const list = h("ul", { class: "resultados", role: "listbox", hidden: true });
    let results = [];
    let active = 0;
    const close = () => { list.hidden = true; };
    const choose = (item) => {
      close();
      input.value = "";
      input.blur();
      openItem(item);
    };
    const paint = () => {
      clear(list);
      results.forEach((r, i) => {
        list.appendChild(h("li", { role: "option", "aria-selected": i === active ? "true" : "false", onmousedown: (e) => { e.preventDefault(); choose(r); } },
          r.label, h("small", null, kindLabel(r.kind) + " · " + (r.file || ""))));
      });
      list.hidden = results.length === 0;
    };
    input.addEventListener("input", () => {
      if (!searchIndex) searchIndex = buildIndex();
      const q = input.value.trim().toLowerCase();
      active = 0;
      if (!q) { results = []; paint(); return; }
      const starts = searchIndex.filter((r) => r.name.startsWith(q));
      const contains = searchIndex.filter((r) => !r.name.startsWith(q) && r.q.includes(q));
      results = starts.concat(contains).slice(0, 12);
      paint();
    });
    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { active = Math.min(active + 1, results.length - 1); paint(); e.preventDefault(); }
      else if (e.key === "ArrowUp") { active = Math.max(active - 1, 0); paint(); e.preventDefault(); }
      else if (e.key === "Enter" && results[active]) { choose(results[active]); e.preventDefault(); }
      else if (e.key === "Escape") { close(); input.blur(); e.stopPropagation(); }
    });
    input.addEventListener("blur", () => setTimeout(close, 120));
    appendAll(box, [input, list]);
    return box;
  }

  function kindLabel(kind) {
    return { function: "función", method: "método", class: "clase", interface: "interfaz", module: "archivo", tabla: "tabla" }[kind] || kind;
  }

  function openItem(item) {
    if (item.kind === "tabla") { go("er", null, { focus: item.id }); return; }
    const sym = SYMBOLS[item.id];
    if (!sym) return;
    if (sym.kind === "function" || sym.kind === "method") { go("flujo", item.id, { trail: [item.id] }); return; }
    const owner = MAP && MAP.owner ? MAP.owner[item.id] : null;
    const target = MAP && MAP.groups[item.id] ? item.id : owner;
    go("mapa", target || null, { focus: item.id });
  }

  // ------------------------------------------------------------------ migas de pan

  function groupChain(gid) {
    const chain = [];
    let cur = gid;
    const seen = new Set();
    while (MAP && cur && MAP.groups[cur] && !seen.has(cur)) {
      seen.add(cur);
      chain.unshift(cur);
      cur = MAP.groups[cur].parent;
    }
    return chain;
  }

  function renderCrumbs() {
    const nav = $("migas");
    clear(nav);
    const items = [];
    const rootName = (DATA.meta && DATA.meta.name) || "Proyecto";
    const rootGid = MAP ? MAP.root : null;
    items.push({ label: rootName, hash: buildHash("mapa", null) });
    if (state.view === "mapa" && state.id) {
      for (const g of groupChain(state.id)) {
        if (g === rootGid) continue;
        items.push({ label: MAP.groups[g].name, hash: buildHash("mapa", g) });
      }
    } else if (["flujo", "secuencia", "codigo"].includes(state.view) && state.trail.length) {
      const base = state.trail[0];
      const owner = MAP && MAP.owner ? MAP.owner[base] : null;
      for (const g of groupChain(owner)) {
        if (g === rootGid) continue;
        items.push({ label: MAP.groups[g].name, hash: buildHash("mapa", g) });
      }
      state.trail.forEach((sid, i) => {
        const sym = SYMBOLS[sid];
        if (!sym) return;
        items.push({ label: sym.name + "()", hash: buildHash(state.view, sid), trail: state.trail.slice(0, i + 1) });
      });
    } else if (state.view === "er") {
      items.push({ label: "Diagrama entidad-relación", hash: buildHash("er", null) });
    } else if (state.view === "galaxia") {
      items.push({ label: "Galaxia", hash: buildHash("galaxia", null) });
    } else if (state.view === "arquitectura") {
      items.push({ label: "Arquitectura", hash: buildHash("arquitectura", null) });
    } else if (state.view === "ruta") {
      items.push({ label: "Trazar ruta", hash: buildHash("ruta", state.id) });
    }
    items.forEach((it, i) => {
      if (i > 0) nav.appendChild(h("span", { class: "sep", "aria-hidden": "true" }, "›"));
      if (i === items.length - 1) nav.appendChild(h("span", { class: "actual", "aria-current": "page" }, it.label));
      else {
        const a = h("a", { href: it.hash }, it.label);
        if (it.trail) a.addEventListener("click", () => { state.pendingTrail = it.trail; });
        nav.appendChild(a);
      }
    });
  }

  function goUp() {
    if (["flujo", "secuencia", "codigo"].includes(state.view)) {
      if (state.trail.length > 1) {
        const prev = state.trail.slice(0, -1);
        go(state.view, prev[prev.length - 1], { trail: prev });
        return;
      }
      const owner = MAP && MAP.owner ? MAP.owner[state.id] : null;
      go("mapa", owner && owner !== (MAP && MAP.root) ? owner : null);
      return;
    }
    if (state.view === "mapa" && state.id && MAP && MAP.groups[state.id]) {
      const parent = MAP.groups[state.id].parent;
      go("mapa", parent && parent !== MAP.root ? parent : null);
      return;
    }
    if (state.view === "ruta") {
      const from = (state.id || "").split("/")[0];
      if (SYMBOLS[from]) go("flujo", from, { trail: [from] });
      else go("mapa", null);
      return;
    }
    if (["er", "galaxia", "arquitectura"].includes(state.view)) go("mapa", null);
  }

  // ------------------------------------------------------------------ pestañas e info

  function renderTabs(sid) {
    const tabs = $("pestanas");
    clear(tabs);
    if (!sid) {
      const hasER = DATA.er && DATA.er.tables && DATA.er.tables.length;
      if (hasER || DATA.galaxy || DATA.arch) {
        tabs.appendChild(tabButton("Mapa", state.view === "mapa" || !state.view, () => go("mapa", null)));
        if (DATA.arch) tabs.appendChild(tabButton("Arquitectura", state.view === "arquitectura", () => go("arquitectura", null)));
        if (DATA.galaxy) tabs.appendChild(tabButton("Galaxia", state.view === "galaxia", () => go("galaxia", null)));
        if (hasER) tabs.appendChild(tabButton("Entidad-relación", state.view === "er", () => go("er", null)));
      }
      return;
    }
    tabs.appendChild(tabButton("Flujo", state.view === "flujo", () => go("flujo", sid, { trail: state.trail })));
    tabs.appendChild(tabButton("Secuencia", state.view === "secuencia", () => go("secuencia", sid, { trail: state.trail })));
    tabs.appendChild(tabButton("Código", state.view === "codigo", () => go("codigo", sid, { trail: state.trail })));
  }

  function tabButton(label, selected, onclick) {
    return h("button", { role: "tab", type: "button", "aria-selected": selected ? "true" : "false", onclick }, label);
  }

  function renderInfo(parts) {
    const info = $("info");
    clear(info);
    appendAll(info, parts);
  }

  function showEmpty(message) {
    const lienzo = $("lienzo");
    clear(lienzo);
    lienzo.appendChild(h("div", { class: "vacio" }, message));
  }

  // ------------------------------------------------------------------ lienzo: zoom y arrastre

  let currentGroup = null;

  function mount(svg, group, w, hgt, legendKinds) {
    const lienzo = $("lienzo");
    clear(lienzo);
    svg.appendChild(group);
    lienzo.appendChild(svg);
    if (legendKinds && legendKinds.length) lienzo.appendChild(buildLegend(legendKinds));
    currentGroup = group;
    state.size = { w, h: hgt };
    if (!state.keepTransform) fit();
    apply();
  }

  function fit() {
    const r = $("lienzo").getBoundingClientRect();
    const w = Math.max(state.size.w, 1);
    const hh = Math.max(state.size.h, 1);
    const k = Math.min((r.width - 40) / w, (r.height - 60) / hh, 1.25);
    const kk = Math.max(Math.min(k, 4), 0.08);
    state.transform = { k: kk, x: Math.max(10, (r.width - w * kk) / 2), y: Math.max(10, Math.min((r.height - hh * kk) / 2, 40)) };
  }

  function apply() {
    if (!currentGroup) return;
    const t = state.transform;
    currentGroup.setAttribute("transform", "translate(" + t.x.toFixed(1) + "," + t.y.toFixed(1) + ") scale(" + t.k.toFixed(4) + ")");
  }

  function zoomBy(f, cx, cy) {
    const r = $("lienzo").getBoundingClientRect();
    const px = cx === undefined ? r.width / 2 : cx;
    const py = cy === undefined ? r.height / 2 : cy;
    const t = state.transform;
    const k = Math.max(0.08, Math.min(4, t.k * f));
    const ratio = k / t.k;
    state.transform = { k, x: px - (px - t.x) * ratio, y: py - (py - t.y) * ratio };
    apply();
  }

  function installCanvasEvents() {
    const lienzo = $("lienzo");
    lienzo.addEventListener("wheel", (e) => {
      e.preventDefault();
      const r = lienzo.getBoundingClientRect();
      zoomBy(Math.exp(-e.deltaY * 0.0015), e.clientX - r.left, e.clientY - r.top);
    }, { passive: false });
    let start = null;
    lienzo.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      start = { x: e.clientX, y: e.clientY, tx: state.transform.x, ty: state.transform.y };
      state.dragged = false;
    });
    window.addEventListener("pointermove", (e) => {
      if (!start) return;
      const dx = e.clientX - start.x;
      const dy = e.clientY - start.y;
      if (!state.dragged && Math.abs(dx) + Math.abs(dy) > 4) {
        state.dragged = true;
        lienzo.classList.add("arrastrando");
      }
      if (state.dragged) {
        state.transform.x = start.tx + dx;
        state.transform.y = start.ty + dy;
        apply();
      }
    });
    window.addEventListener("pointerup", () => {
      start = null;
      lienzo.classList.remove("arrastrando");
      setTimeout(() => { state.dragged = false; }, 0);
    });
    lienzo.addEventListener("dblclick", (e) => {
      if (e.target.closest && e.target.closest(".nodo")) return;
      goUp();
    });
  }

  // ------------------------------------------------------------------ SVG comunes

  function markers() {
    return s("defs", null,
      marker("punta", "punta"),
      marker("punta-exc", "punta-exc"),
      marker("punta-foco", "punta-foco"));
  }

  function marker(id, cls) {
    return s("marker", { id, viewBox: "0 0 10 10", refX: "9", refY: "5", markerWidth: "8", markerHeight: "8", orient: "auto-start-reverse", markerUnits: "userSpaceOnUse" },
      s("path", { d: "M0,0 L10,5 L0,10 z", class: cls }));
  }

  function pathFrom(points) {
    let d = "";
    for (let i = 0; i < points.length; i += 2) d += (i === 0 ? "M" : "L") + points[i] + "," + points[i + 1];
    return d;
  }

  const MIX_NAMES = {
    exacta: ["exacta", "exactas"],
    probable: ["probable", "probables"],
    ambigua: ["ambigua", "ambiguas"],
    externa: ["externa", "externas"],
    rutas: ["ruta", "rutas"],
  };

  /** Texto del tooltip de una flecha del mapa: de dónde a dónde y su desglose. */
  function edgeTip(src, dst, mix) {
    const name = (id) => {
      const n = MAP && MAP.groups[id];
      if (n) return n.name;
      return SYMBOLS[id] ? SYMBOLS[id].qualname : id;
    };
    const parts = [];
    for (const k of ["exacta", "probable", "ambigua", "externa", "rutas"]) {
      const n = mix && mix[k];
      if (n) parts.push(n + " " + MIX_NAMES[k][n === 1 ? 0 : 1]);
    }
    return name(src) + " → " + name(dst) + (parts.length ? "\n" + parts.join(" · ") : "");
  }

  function drawLabel(text, x, y, w, hh, extraClass) {
    return s("g", { class: "etiqueta" + (extraClass ? " " + extraClass : "") },
      s("rect", { x, y, width: w, height: hh, rx: 3 }),
      s("text", { x: x + 4, y: y + hh / 2 + 0.5 }, text));
  }

  function textBlock(lines, cx, cy) {
    const t = s("text", { x: cx, y: cy, "text-anchor": "middle" });
    const n = lines.length;
    lines.forEach((ln, i) => {
      t.appendChild(s("tspan", { x: cx, dy: i === 0 ? (-(n - 1) / 2) * LINE_H : LINE_H }, ln));
    });
    return t;
  }

  function flowShape(kind, x, y, w, hh) {
    const r = x + w;
    const b = y + hh;
    switch (kind) {
      case "terminal":
        return [s("rect", { class: "forma", x, y, width: w, height: hh, rx: hh / 2 })];
      case "decision":
        return [s("polygon", { class: "forma", points: [x + w / 2, y, r, y + hh / 2, x + w / 2, b, x, y + hh / 2].join(" ") })];
      case "subproceso":
        return [
          s("rect", { class: "forma", x, y, width: w, height: hh }),
          s("line", { class: "linea-interna", x1: x + 8, y1: y, x2: x + 8, y2: b }),
          s("line", { class: "linea-interna", x1: r - 8, y1: y, x2: r - 8, y2: b }),
        ];
      case "es":
        return [s("polygon", { class: "forma", points: [x + 12, y, r, y, r - 12, b, x, b].join(" ") })];
      case "pantalla":
        return [s("path", { class: "forma", d: "M" + (x + 16) + "," + y + " L" + (r - 18) + "," + y + " C" + (r + 4) + "," + y + " " + (r + 4) + "," + b + " " + (r - 18) + "," + b + " L" + (x + 16) + "," + b + " L" + x + "," + (y + hh / 2) + " Z" })];
      case "teclado":
        return [s("polygon", { class: "forma", points: [x, y + 10, r, y, r, b, x, b].join(" ") })];
      case "documento": {
        const wy = b - 8;
        return [s("path", { class: "forma", d: "M" + x + "," + y + " L" + r + "," + y + " L" + r + "," + wy + " Q" + (x + w * 0.75) + "," + (wy - 10) + " " + (x + w / 2) + "," + wy + " T" + x + "," + wy + " Z" })];
      }
      default:
        return [s("rect", { class: "forma", x, y, width: w, height: hh, rx: kind === "externo" ? 4 : 2 })];
    }
  }

  function textOffset(kind) {
    if (kind === "teclado") return 5;
    if (kind === "documento") return -4;
    return 0;
  }

  // ------------------------------------------------------------------ leyenda

  function buildLegend(kinds) {
    const box = h("div", { class: "leyenda", role: "list", "aria-label": "Leyenda" });
    for (const k of kinds) {
      const icon = s("svg", { viewBox: "0 0 26 16", "aria-hidden": "true" });
      if (CONF_NAMES[k]) {
        icon.appendChild(s("line", { x1: 1, y1: 8, x2: 25, y2: 8, class: "arista c-" + k }));
      } else if (k === "excepcion") {
        icon.appendChild(s("line", { x1: 1, y1: 8, x2: 25, y2: 8, class: "arista k-excepcion" }));
      } else if (k === "conector") {
        icon.appendChild(s("g", { class: "nodo k-conector" }, s("circle", { class: "forma", cx: 13, cy: 8, r: 6 })));
      } else {
        const g = s("g", { class: "nodo k-" + k });
        appendAll(g, flowShape(k === "funcion" || k === "entrada" ? "terminal" : k, 2, 2, 22, 12));
        icon.appendChild(g);
      }
      box.appendChild(h("div", { class: "item", role: "listitem", "data-tipo": k }, icon, NODE_NAMES[k] || CONF_NAMES[k] || k));
    }
    return box;
  }

  // ------------------------------------------------------------------ vista: flujo

  function renderFlow(sid) {
    const sym = SYMBOLS[sid];
    renderTabs(sid);
    if (!sym) {
      renderInfo([]);
      showEmpty("No se encontró la función.");
      hidePanel();
      return;
    }
    const flow = flowOf(sid);
    const infoParts = [h("code", null, sym.signature), "  ·  " + sym.file + ":" + sym.line_start];
    if (sym.doc) infoParts.push(h("div", { class: "doc" }, sym.doc));
    if (flow && flow.truncated) infoParts.push(h("div", null, "Función muy grande: algunos bloques se muestran colapsados (clic para ver el código)."));
    renderInfo(infoParts);
    renderPanel(sid);
    if (!flow) {
      const impl = (DATA.impl && DATA.impl[sid]) || [];
      if (impl.length) {
        const lienzo = $("lienzo");
        clear(lienzo);
        const box = h("div", { class: "vacio" }, "Método sin cuerpo (abstracto o de interfaz). Posibles implementaciones:");
        const ul = h("ul");
        for (const id of impl) {
          const t = SYMBOLS[id];
          if (t) ul.appendChild(h("li", null, h("a", { href: buildHash("flujo", id) }, t.qualname)));
        }
        box.appendChild(ul);
        lienzo.appendChild(box);
      } else {
        showEmpty("Esta función no tiene cuerpo para dibujar (declaración, abstracta o externa).");
      }
      return;
    }
    const lay = flow.layout;
    const svg = s("svg", { role: "img", "aria-label": "Diagrama de flujo de " + sym.qualname });
    svg.appendChild(markers());
    const g = s("g", { class: "vista" });
    for (const [pts, kind, arrow] of lay.lines) {
      g.appendChild(s("path", { class: "arista k-" + kind, d: pathFrom(pts), "marker-end": arrow ? (kind === "excepcion" ? "url(#punta-exc)" : "url(#punta)") : null }));
    }
    for (const [text, x, y, w, hh] of lay.labels) g.appendChild(drawLabel(text, x, y, w, hh));
    for (const [nid, x, y, w, hh, easy, tech] of lay.nodes) {
      g.appendChild(drawFlowNode(sid, nid, flow.nodes[nid], x, y, w, hh, state.mode === "facil" ? easy : tech));
    }
    for (const [label, cx, cy, r] of lay.connectors) {
      const cg = s("g", { class: "nodo k-conector" }, s("circle", { class: "forma", cx, cy, r }));
      cg.appendChild(s("text", { x: cx, y: cy + 0.5, "text-anchor": "middle" }, label));
      cg.appendChild(s("title", null, "Conector " + label + ": la línea continúa en el otro conector " + label));
      g.appendChild(cg);
    }
    mount(svg, g, lay.w, lay.h, lay.legend || []);
    if (state.selectedNode) selectNode(sid, state.selectedNode, false);
  }

  function drawFlowNode(sid, nid, info, x, y, w, hh, lines) {
    const clickable = !!info.target && !!SYMBOLS[info.target];
    const g = s("g", { class: "nodo k-" + info.kind + (clickable ? " clicable" : ""), "data-id": nid });
    appendAll(g, flowShape(info.kind, x, y, w, hh));
    g.appendChild(textBlock(lines, x + w / 2, y + hh / 2 + textOffset(info.kind)));
    const sym = SYMBOLS[sid];
    let tip = info.tech + "\n" + sym.file + ":" + info.a + (info.b !== info.a ? "-" + info.b : "");
    if (clickable) tip += "\nClic: abrir el flujo de " + SYMBOLS[info.target].qualname;
    g.appendChild(s("title", null, tip));
    if (clickable) {
      g.setAttribute("tabindex", "0");
      g.setAttribute("role", "button");
      g.setAttribute("aria-label", "Abrir flujo de " + SYMBOLS[info.target].qualname);
      g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openSub(info.target); } });
    }
    g.addEventListener("click", (e) => {
      if (state.dragged) return;
      e.stopPropagation();
      if (clickable) openSub(info.target);
      else selectNode(sid, nid, true);
    });
    return g;
  }

  function openSub(target) {
    const trail = state.trail.length ? state.trail.slice() : [state.id];
    const i = trail.indexOf(target);
    const next = i >= 0 ? trail.slice(0, i + 1) : trail.concat([target]);
    go("flujo", target, { trail: next });
  }

  function selectNode(sid, nid, scroll) {
    state.selectedNode = nid;
    const flow = flowOf(sid);
    if (!flow || !flow.nodes[nid]) return;
    document.querySelectorAll(".nodo.seleccionado").forEach((n) => n.classList.remove("seleccionado"));
    const el = document.querySelector('.nodo[data-id="' + nid + '"]');
    if (el) el.classList.add("seleccionado");
    const info = flow.nodes[nid];
    highlightLines(info.a, info.b, scroll);
  }

  // ------------------------------------------------------------------ panel lateral

  function hidePanel() {
    $("panel").hidden = true;
  }

  function linkList(title, entries) {
    if (!entries || !entries.length) return null;
    const ul = h("ul");
    for (const [id, conf] of entries) {
      const sym = SYMBOLS[id];
      if (!sym) continue;
      ul.appendChild(h("li", null, h("a", { href: buildHash("flujo", id), title: CONF_NAMES[conf] || "" }, sym.qualname), conf && conf !== "exacta" ? " (" + conf + ")" : ""));
    }
    return h("div", { class: "seccion" }, h("h3", null, title), ul);
  }

  let panelFile = null;

  function renderPanel(sid) {
    const panel = $("panel");
    const sym = SYMBOLS[sid];
    clear(panel);
    panel.hidden = false;
    const m = sym.metrics || {};
    const meta = h("div", { class: "meta" }, h("code", null, sym.file + ":" + sym.line_start + "-" + sym.line_end), " · " + sym.lang);
    const metrics = h("div", { class: "meta" },
      "Complejidad: " + (m.cc !== undefined ? m.cc : "–") + " · Líneas: " + (sym.line_end - sym.line_start + 1) +
      " · Llamadas entrantes: " + (m.calls_in || 0) + " · salientes: " + (m.calls_out || 0));
    appendAll(panel, [h("h2", null, sym.qualname), meta, metrics]);
    if (sym.kind === "function" || sym.kind === "method") {
      const acts = h("div", { class: "acciones" },
        h("a", { class: "boton", href: buildHash("ruta", sid), title: "Elegir un destino y ver el camino de llamadas" }, "Trazar ruta…"));
      if (state.view !== "ruta" && tracePath(sid, ANY_TABLE)) {
        acts.appendChild(h("a", { class: "boton", href: buildHash("ruta", sid + "/" + encodeURIComponent(ANY_TABLE)), title: "El camino más corto hasta una función que lee o escribe una tabla" }, "¿Cómo llega a la base de datos?"));
      }
      panel.appendChild(acts);
    }
    const route = DATA.routes && DATA.routes[sid];
    if (route) panel.appendChild(h("div", { class: "meta" }, "Ruta: ", h("code", null, route)));
    const tables = DATA.tables_of && DATA.tables_of[sid];
    if (tables && tables.length) {
      const ul = h("ul");
      for (const [table, mode] of tables) {
        ul.appendChild(h("li", null, (mode === "lee" ? "Lee " : "Escribe ") , h("a", { href: buildHash("er", null, null) }, table)));
      }
      panel.appendChild(h("div", { class: "seccion" }, h("h3", null, "Tablas (probable)"), ul));
    }
    const notes = DATA.notes_of && DATA.notes_of[sid];
    if (notes && notes.length) {
      const ul = h("ul", { class: "notas" });
      for (const [line, tag, text] of notes) {
        const li = h("li", { tabindex: "0", title: "Ver la línea " + line },
          h("span", { class: "nota-tag t-" + tag.toLowerCase() }, tag), " línea " + line + (text ? ": " + text : ""));
        const show = () => highlightLines(line, line, true);
        li.addEventListener("click", show);
        li.addEventListener("keydown", (e) => { if (e.key === "Enter") show(); });
        ul.appendChild(li);
      }
      panel.appendChild(h("div", { class: "seccion" }, h("h3", null, "Notas en el código"), ul));
    }
    const incoming = linkList("Llamado por", DATA.calls_in && DATA.calls_in[sid]);
    const outgoing = linkList("Llama a", DATA.calls_out && DATA.calls_out[sid]);
    const impl = DATA.impl && DATA.impl[sid] ? linkList("Posibles implementaciones", DATA.impl[sid].map((i) => [i, "probable"])) : null;
    appendAll(panel, [incoming, outgoing, impl]);
    const source = sourceOf(sym.file);
    const pre = h("div", { class: "codigo", id: "codigo", role: "region", "aria-label": "Código fuente" });
    if (source === null || source === undefined) {
      pre.appendChild(h("div", { class: "vacio" }, "El código fuente no se incluyó (opción --no-source)."));
    } else {
      const lines = source.split("\n");
      lines.forEach((ln, i) => {
        pre.appendChild(h("div", { class: "ln", "data-n": i + 1 }, h("span", { class: "num" }, String(i + 1)), ln));
      });
    }
    panel.appendChild(pre);
    panelFile = sym.file;
    highlightLines(sym.line_start, sym.line_end, true);
  }

  function highlightLines(a, b, scroll) {
    const pre = $("codigo");
    if (!pre) return;
    pre.querySelectorAll(".ln.marcada").forEach((n) => n.classList.remove("marcada"));
    let first = null;
    for (let n = a; n <= b; n++) {
      const el = pre.querySelector('.ln[data-n="' + n + '"]');
      if (el) {
        el.classList.add("marcada");
        if (!first) first = el;
      }
    }
    if (first && scroll) {
      // Posiciones reales en pantalla: offsetTop se mide desde el panel e incluía las
      // secciones de arriba, así que la línea quedaba fuera de la vista.
      const delta = first.getBoundingClientRect().top - pre.getBoundingClientRect().top;
      pre.scrollTop = Math.max(0, pre.scrollTop + delta - pre.clientHeight / 3);
    }
  }

  // ------------------------------------------------------------------ vista: código

  function renderCodeView(sid) {
    renderTabs(sid);
    const sym = SYMBOLS[sid];
    if (!sym) { showEmpty("No se encontró la función."); return; }
    renderInfo([h("code", null, sym.signature), "  ·  " + sym.file + ":" + sym.line_start]);
    renderPanel(sid);
    const lienzo = $("lienzo");
    clear(lienzo);
    const source = sourceOf(sym.file);
    if (source === null || source === undefined) { showEmpty("El código fuente no se incluyó (opción --no-source)."); return; }
    const pre = h("div", { class: "codigo", style: "position:absolute;inset:0;" });
    source.split("\n").slice(sym.line_start - 1, sym.line_end).forEach((ln, i) => {
      pre.appendChild(h("div", { class: "ln" }, h("span", { class: "num" }, String(sym.line_start + i)), ln));
    });
    lienzo.appendChild(pre);
  }

  // ------------------------------------------------------------------ vista: mapa

  function renderMap(gid) {
    renderTabs(null);
    if (!MAP) {
      renderInfo([]);
      hidePanel();
      const first = Object.keys(SYMBOLS).find(hasFlow);
      if (first) { go("flujo", first); return; }
      showEmpty("No hay nada que mostrar.");
      return;
    }
    const id = gid && MAP.groups[gid] ? gid : MAP.root;
    const group = MAP.groups[id];
    const lay = group.layout;
    const focus = lay && state.focus && lay.nodes.some((n) => n[0] === state.focus) ? state.focus : null;
    const infoParts = [h("strong", null, group.name), group.summary ? "  ·  " + group.summary : ""];
    if (group.doc) infoParts.push(h("div", { class: "doc", title: "Del README de esta carpeta" }, group.doc));
    if (focus) {
      const node = lay.nodes.find((n) => n[0] === focus);
      const off = h("button", { class: "boton", type: "button", onclick: () => toggleFocus(focus) }, "Quitar enfoque");
      infoParts.push(h("div", { class: "aviso-foco" }, "Enfocado: ", h("strong", null, node[6]), " — se resalta lo que usa y lo que lo usa. ", off));
    } else if (lay && lay.edges.length) {
      infoParts.push(h("div", { class: "pista" }, "Clic para entrar · Alt+clic (o tecla E) para enfocar · ? ayuda"));
    }
    if (lay && lay.hidden) {
      const total = lay.edges.length + lay.hidden;
      infoParts.push(h("div", { class: "pista" }, "Nivel muy conectado: se dibujan las " + lay.edges.length + " relaciones más fuertes de " + total + "."));
    }
    renderInfo(infoParts);
    hidePanel();
    if (!lay || !lay.nodes.length) { showEmpty("Este nivel no tiene elementos."); return; }
    const svg = s("svg", { role: "img", "aria-label": "Mapa: " + group.name });
    svg.appendChild(markers());
    const g = s("g", { class: "vista" });
    const lit = focus ? neighborhood(lay.edges, focus) : null;
    for (const [src, dst, pts, conf, label, lx, ly, lw, lh, mix] of lay.edges) {
      const dim = lit && !(lit.has(src) && lit.has(dst)) ? " atenuado" : "";
      const lightEdge = lit && !dim ? " resaltada" : "";
      const tip = edgeTip(src, dst, mix);
      g.appendChild(s("path", { class: "arista c-" + conf + dim + lightEdge, d: pathFrom(pts), "marker-end": lightEdge ? "url(#punta-foco)" : "url(#punta)" }));
      // Trazo invisible y ancho encima: así es fácil pasar el mouse y ver el desglose.
      g.appendChild(s("path", { class: "arista-hit", d: pathFrom(pts) }, s("title", null, tip)));
      if (label) {
        const lg = drawLabel(label, lx, ly, lw, lh, dim.trim());
        lg.appendChild(s("title", null, tip));
        g.appendChild(lg);
      }
    }
    for (const [nid, kind, x, y, w, hh, label, sub, link] of lay.nodes) {
      const dim = lit && !lit.has(nid) ? " atenuado" : "";
      const ng = s("g", { class: "nodo k-" + kind + (link ? " clicable" : "") + dim + (nid === focus ? " seleccionado" : ""), "data-id": nid });
      const rx = kind === "funcion" || kind === "entrada" ? hh / 2 : kind === "modulo" ? 10 : 4;
      ng.appendChild(s("rect", { class: "forma", x, y, width: w, height: hh, rx }));
      if (kind === "interfaz") ng.appendChild(s("line", { class: "linea-interna", x1: x, y1: y + 6, x2: x + w, y2: y + 6 }));
      const lines = sub ? [label, sub] : [label];
      ng.appendChild(textBlock(lines, x + w / 2, y + hh / 2));
      const doc = MAP.groups[nid] && MAP.groups[nid].doc ? "\n" + MAP.groups[nid].doc : "";
      ng.appendChild(s("title", null, label + (sub ? "\n" + sub : "") + doc + (link ? "\nClic: entrar · Alt+clic o E: enfocar" : "\nClic o E: enfocar")));
      ng.setAttribute("tabindex", "0");
      ng.setAttribute("role", "button");
      ng.setAttribute("aria-label", label + (link ? "" : " (enfocar)"));
      ng.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && link) { e.preventDefault(); location.hash = withParams(link); }
        else if (e.key === "e" || e.key === "E" || (e.key === "Enter" && !link)) {
          e.preventDefault();
          e.stopPropagation();
          toggleFocus(nid);
          const again = document.querySelector('.nodo[data-id="' + CSS.escape(nid) + '"]');
          if (again) again.focus();
        }
      });
      ng.addEventListener("click", (e) => {
        if (state.dragged) return;
        e.stopPropagation();
        if (e.altKey || e.shiftKey || !link) { toggleFocus(nid); return; }
        location.hash = withParams(link);
      });
      g.appendChild(ng);
    }
    mount(svg, g, lay.w, lay.h, lay.legend || []);
  }

  function withParams(link) {
    const tmp = link.replace(/^#\//, "").split("/");
    const id = tmp.slice(1).join("/") || null;
    // Entrar a una función desde el mapa empieza un recorrido nuevo de migas.
    if (tmp[0] === "flujo" && id) state.pendingTrail = [id];
    return buildHash(tmp[0], id);
  }

  function neighborhood(edges, start) {
    const down = new Map();
    const up = new Map();
    for (const [a, b] of edges) {
      if (!down.has(a)) down.set(a, []);
      if (!up.has(b)) up.set(b, []);
      down.get(a).push(b);
      up.get(b).push(a);
    }
    const lit = new Set([start]);
    for (const graph of [down, up]) {
      const stack = [start];
      const seen = new Set([start]);
      while (stack.length) {
        const cur = stack.pop();
        for (const nxt of graph.get(cur) || []) {
          if (!seen.has(nxt)) { seen.add(nxt); lit.add(nxt); stack.push(nxt); }
        }
      }
    }
    return lit;
  }

  // ------------------------------------------------------------------ vista: secuencia

  function renderSequence(sid) {
    renderTabs(sid);
    const sym = SYMBOLS[sid];
    if (!sym) { showEmpty("No se encontró la función."); return; }
    renderInfo([h("code", null, sym.signature), "  ·  " + sym.file + ":" + sym.line_start]);
    renderPanel(sid);
    const seq = sequenceOf(sid);
    if (!seq) { showEmpty("No hay diagrama de secuencia para esta función (no llama a otras funciones del proyecto)."); return; }
    if (seq.layout_all) {
      const btn = h("button", { class: "boton", type: "button", "aria-pressed": state.showExternal ? "true" : "false", onclick: () => { state.showExternal = !state.showExternal; state.keepTransform = false; renderSequence(sid); } },
        state.showExternal ? "Ocultar llamadas externas" : "Mostrar llamadas externas");
      $("info").appendChild(h("div", { style: "margin-top:4px" }, btn));
    }
    const lay = state.showExternal && seq.layout_all ? seq.layout_all : seq.layout;
    const svg = s("svg", { role: "img", "aria-label": "Diagrama de secuencia de " + sym.qualname });
    svg.appendChild(markers());
    const g = s("g", { class: "vista" });
    for (const [x, y, w, hh, label, kind, divider] of lay.fragments) {
      g.appendChild(s("rect", { x, y, width: w, height: hh, class: "fragmento k-frag-" + kind, rx: 3 }));
      if (divider !== null && divider !== undefined) {
        g.appendChild(s("line", { class: "fragmento-divisor", x1: x, y1: divider, x2: x + w, y2: divider }));
        g.appendChild(drawLabel("[else]", x + 4, divider + 2, 52, 15));
      }
      g.appendChild(drawLabel(label, x, y, label.length * 6.6 + 10, 16));
    }
    for (const [x, y1, y2] of lay.lifelines) {
      g.appendChild(s("line", { class: "linea-vida", x1: x, y1, x2: x, y2 }));
    }
    for (const [x, y, w, hh, label, kind] of lay.participants) {
      const pg = s("g", { class: "nodo k-" + (kind === "actor" ? "entrada" : kind === "modulo" ? "clase" : kind) });
      pg.appendChild(s("rect", { class: "forma", x, y, width: w, height: hh, rx: kind === "actor" || kind === "entrada" ? hh / 2 : 4 }));
      pg.appendChild(textBlock([label], x + w / 2, y + hh / 2));
      g.appendChild(pg);
    }
    for (const [x1, x2, y, label, kind, target, conf] of lay.messages) {
      const self = x1 === x2;
      const d = self ? "M" + x1 + "," + y + " h34 v14 h-30" : "M" + x1 + "," + y + " L" + x2 + "," + y;
      const cls = kind === "retorno" ? "arista k-retorno" : "arista c-" + (conf || "exacta");
      g.appendChild(s("path", { class: cls, d, "marker-end": "url(#punta)" }));
      const tx = self ? x1 + 40 : Math.min(x1, x2) + 6;
      const t = s("text", { x: tx, y: y - 6, class: "msg" + (kind === "retorno" ? " retorno" : "") }, label);
      if (target && hasFlow(target)) {
        t.classList.add("enlace");
        t.addEventListener("click", () => openSub(target));
        t.appendChild(s("title", null, "Abrir el flujo de " + SYMBOLS[target].qualname));
      }
      g.appendChild(t);
    }
    mount(svg, g, lay.w, lay.h, lay.confs || []);
  }

  // ------------------------------------------------------------------ vista: arquitectura

  function renderArch() {
    renderTabs(null);
    hidePanel();
    const arch = DATA.arch;
    if (!arch) { renderInfo([]); showEmpty("No se reconoció una arquitectura por capas en este proyecto."); return; }
    const names = {};
    for (const n of arch.nodes) names[n[0]] = n[6];
    const focus = state.focus && names[state.focus] !== undefined ? state.focus : null;
    const info = [h("strong", null, "Arquitectura"), "  ·  " + arch.columns.map((c) => c[0]).join(" → ")];
    if (focus) {
      const off = h("button", { class: "boton", type: "button", onclick: () => toggleFocus(focus) }, "Quitar enfoque");
      info.push(h("div", { class: "aviso-foco" }, "Enfocado: ", h("strong", null, names[focus]), " — se resalta lo que usa y lo que lo usa. ", off));
    } else {
      info.push(h("div", { class: "pista" }, "Capas detectadas por nombres y carpetas (una convención, no una certeza): pasa el mouse para ver el motivo. Clic: verlo en el mapa · Alt+clic: enfocar."));
    }
    const notes = [];
    if (arch.unclassified) {
      notes.push(arch.unclassified === 1
        ? "1 componente no sigue una convención conocida y no se muestra (está en el mapa)."
        : arch.unclassified + " componentes no siguen una convención conocida y no se muestran (están en el mapa).");
    }
    if (arch.tests) notes.push("Las pruebas no son una capa: " + arch.tests + (arch.tests === 1 ? " componente de prueba no se muestra." : " componentes de prueba no se muestran."));
    if (arch.same_layer) notes.push("Las llamadas dentro de una misma capa no se dibujan (" + arch.same_layer + ").");
    if (arch.hidden) notes.push("Muy conectado: se dibujan las " + arch.edges.length + " relaciones más fuertes de " + (arch.edges.length + arch.hidden) + ".");
    if (notes.length) info.push(h("div", { class: "pista" }, notes.join(" ")));
    renderInfo(info);
    const svg = s("svg", { role: "img", "aria-label": "Mapa de arquitectura" });
    svg.appendChild(markers());
    const g = s("g", { class: "vista" });
    // Franja y título de cada columna.
    for (const [title, cx, count] of arch.columns) {
      let minX = Infinity;
      let maxX = -Infinity;
      for (const n of arch.nodes) {
        if (Math.abs(n[2] + n[4] / 2 - cx) < 1) { minX = Math.min(minX, n[2]); maxX = Math.max(maxX, n[2] + n[4]); }
      }
      if (minX === Infinity) continue;
      g.appendChild(s("rect", { class: "columna-banda", x: minX - 14, y: 4, width: maxX - minX + 28, height: arch.h - 8, rx: 10 }));
      g.appendChild(s("text", { class: "columna-titulo", x: cx, y: 24, "text-anchor": "middle" }, title));
      g.appendChild(s("text", { class: "columna-sub", x: cx, y: 40, "text-anchor": "middle" }, count));
    }
    const lit = focus ? neighborhood(arch.edges, focus) : null;
    for (const [src, dst, pts, conf, label, lx, ly, lw, lh, mix, back, text] of arch.edges) {
      const dim = lit && !(lit.has(src) && lit.has(dst)) ? " atenuado" : "";
      const lightEdge = lit && !dim ? " resaltada" : "";
      const parts = [];
      for (const k of ["exacta", "probable", "ambigua"]) if (mix && mix[k]) parts.push(mix[k] + " " + MIX_NAMES[k][mix[k] === 1 ? 0 : 1]);
      const tip = names[src] + " → " + names[dst] + (text ? "\n" + text : "") + (parts.length ? "\n" + parts.join(" · ") : "") + (back ? "\nVa hacia una capa anterior" : "");
      g.appendChild(s("path", { class: "arista c-" + conf + dim + lightEdge + (back ? " hacia-atras" : ""), d: pathFrom(pts), "marker-end": lightEdge ? "url(#punta-foco)" : "url(#punta)" }));
      g.appendChild(s("path", { class: "arista-hit", d: pathFrom(pts) }, s("title", null, tip)));
      if (label) {
        const lg = drawLabel(label, lx, ly, lw, lh, dim.trim());
        lg.appendChild(s("title", null, tip));
        g.appendChild(lg);
      }
    }
    for (const [nid, kind, x, y, w, hh, label, sub, link, tip] of arch.nodes) {
      const dim = lit && !lit.has(nid) ? " atenuado" : "";
      const ng = s("g", { class: "nodo k-" + kind + (link ? " clicable" : "") + dim + (nid === focus ? " seleccionado" : ""), "data-id": nid, tabindex: "0", role: "button", "aria-label": label });
      ng.appendChild(s("rect", { class: "forma", x, y, width: w, height: hh, rx: kind === "entrada" ? hh / 2 : kind === "bd" ? 10 : 4 }));
      if (kind === "interfaz") ng.appendChild(s("line", { class: "linea-interna", x1: x, y1: y + 6, x2: x + w, y2: y + 6 }));
      ng.appendChild(textBlock(sub ? [label, sub] : [label], x + w / 2, y + hh / 2));
      ng.appendChild(s("title", null, tip + (link ? "\nClic: verlo en el mapa · Alt+clic o E: enfocar" : "\nClic o E: enfocar")));
      ng.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && link) { e.preventDefault(); location.hash = withParams(link); }
        else if (e.key === "e" || e.key === "E" || (e.key === "Enter" && !link)) { e.preventDefault(); e.stopPropagation(); toggleFocus(nid); }
      });
      ng.addEventListener("click", (e) => {
        if (state.dragged) return;
        e.stopPropagation();
        if (e.altKey || e.shiftKey || !link) { toggleFocus(nid); return; }
        location.hash = withParams(link);
      });
      g.appendChild(ng);
    }
    mount(svg, g, arch.w, arch.h, arch.legend || []);
  }

  // ------------------------------------------------------------------ vista: trazar una ruta

  // "¿Cómo llega esta función a otra, o a la base de datos?": el camino de llamadas más
  // corto (búsqueda en anchura sobre las llamadas resueltas), dibujado paso a paso.
  const ANY_TABLE = "t:*";

  function tablesHit(sid, goal) {
    const all = (DATA.tables_of && DATA.tables_of[sid]) || [];
    return goal === ANY_TABLE ? all : all.filter(([name]) => "t:" + name === goal);
  }

  /** Pasos [{from, to, conf, line}] de `from` a `goal` (función o tabla), o null. */
  function tracePath(from, goal) {
    const isTable = goal.startsWith("t:");
    const reached = (sid) => (isTable ? tablesHit(sid, goal).length > 0 : sid === goal);
    const prev = new Map([[from, null]]);
    const queue = [from];
    let end = null;
    while (queue.length) {
      const cur = queue.shift();
      if (reached(cur)) { end = cur; break; }
      for (const [next, conf, line] of (DATA.calls_out && DATA.calls_out[cur]) || []) {
        if (prev.has(next) || !SYMBOLS[next]) continue;
        prev.set(next, { from: cur, to: next, conf, line });
        queue.push(next);
      }
      // Un método de interfaz o abstracto "sigue" en sus implementaciones (probable).
      for (const next of (DATA.impl && DATA.impl[cur]) || []) {
        if (prev.has(next) || !SYMBOLS[next]) continue;
        prev.set(next, { from: cur, to: next, conf: "probable", line: null, impl: true });
        queue.push(next);
      }
    }
    if (end === null) return null;
    const steps = [];
    for (let s = prev.get(end); s; s = prev.get(s.from)) steps.unshift(s);
    if (isTable) {
      const [name, mode] = tablesHit(end, goal)[0];
      steps.push({ from: end, to: "t:" + name, conf: "probable", line: null, mode });
    }
    return steps;
  }

  function goalLabel(goal) {
    if (goal === ANY_TABLE) return "cualquier tabla (base de datos)";
    if (goal.startsWith("t:")) return "tabla " + goal.slice(2);
    return SYMBOLS[goal] ? SYMBOLS[goal].qualname : goal;
  }

  function routeCandidates(withTables) {
    if (!searchIndex) searchIndex = buildIndex();
    const out = searchIndex.filter((r) => r.kind === "function" || r.kind === "method" || (withTables && r.kind === "tabla"));
    return withTables ? [{ id: ANY_TABLE, label: "Cualquier tabla (base de datos)", name: "base de datos", q: "base de datos tabla", kind: "tabla", file: "" }].concat(out) : out;
  }

  /** Cuadro de búsqueda para elegir una función (o tabla) del trazado. */
  function routePicker(label, current, withTables, onChoose) {
    const box = h("div", { class: "buscador selector-ruta" });
    const input = h("input", { type: "search", placeholder: current ? current : "Elige…", "aria-label": label, autocomplete: "off" });
    const list = h("ul", { class: "resultados", role: "listbox", hidden: true });
    let results = [];
    const paint = () => {
      clear(list);
      for (const r of results) {
        list.appendChild(h("li", { role: "option", onmousedown: (e) => { e.preventDefault(); onChoose(r.kind === "tabla" && r.id !== ANY_TABLE ? "t:" + r.label : r.id); } },
          r.label, h("small", null, r.id === ANY_TABLE ? "cualquier tabla que el código lea o escriba" : kindLabel(r.kind) + " · " + (r.file || ""))));
      }
      list.hidden = results.length === 0;
    };
    input.addEventListener("input", () => {
      const q = input.value.trim().toLowerCase();
      const all = routeCandidates(withTables);
      if (!q) { results = all.slice(0, withTables ? 8 : 0); paint(); return; }
      const starts = all.filter((r) => r.name.startsWith(q));
      const contains = all.filter((r) => !r.name.startsWith(q) && r.q.includes(q));
      results = starts.concat(contains).slice(0, 12);
      paint();
    });
    input.addEventListener("focus", () => input.dispatchEvent(new Event("input")));
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && results.length) { e.preventDefault(); const r = results[0]; onChoose(r.kind === "tabla" && r.id !== ANY_TABLE ? "t:" + r.label : r.id); }
      else if (e.key === "Escape") { list.hidden = true; input.blur(); e.stopPropagation(); }
    });
    input.addEventListener("blur", () => setTimeout(() => { list.hidden = true; }, 120));
    appendAll(box, [input, list]);
    return h("label", { class: "campo-ruta" }, h("span", null, label), box);
  }

  function stopRoutePlay() {
    if (state.routeTimer) { clearInterval(state.routeTimer); state.routeTimer = null; }
  }

  function renderRoute(id) {
    renderTabs(null);
    stopRoutePlay();
    const [from, goalRaw] = (id || "").split("/");
    const goal = goalRaw ? decodeURIComponent(goalRaw) : null;
    const pick = (f, g) => go("ruta", f + (g ? "/" + encodeURIComponent(g) : ""));
    const fromName = SYMBOLS[from] ? SYMBOLS[from].qualname : null;
    const pickers = h("div", { class: "pickers-ruta" },
      routePicker("Desde", fromName, false, (f) => pick(f, goal)),
      h("span", { class: "flecha-ruta", "aria-hidden": "true" }, "→"),
      routePicker("Hasta", goal ? goalLabel(goal) : null, true, (g) => pick(from, g)));
    const info = [h("strong", null, "Trazar una ruta"), "  ·  el camino de llamadas más corto, paso a paso", pickers];
    if (!fromName) {
      renderInfo(info);
      hidePanel();
      showEmpty("Elige la función de inicio («Desde») y el destino («Hasta»): otra función, una tabla o cualquier tabla.");
      return;
    }
    if (!goal) {
      renderInfo(info);
      hidePanel();
      showEmpty("Elige el destino («Hasta»): otra función, una tabla o «Cualquier tabla» para ver cómo " + fromName + " llega a la base de datos.");
      return;
    }
    const steps = tracePath(from, goal);
    if (!steps) {
      const back = !goal.startsWith("t:") && tracePath(goal, from);
      if (back) info.push(h("div", { class: "pista" }, "Sí hay un camino al revés (" + back.length + " pasos). ", h("a", { href: buildHash("ruta", goal + "/" + from) }, "Ver al revés")));
      renderInfo(info);
      hidePanel();
      showEmpty("No hay un camino de llamadas de " + fromName + " a " + goalLabel(goal) + ". Solo se siguen llamadas resueltas (exactas o probables); las dinámicas no se ven.");
      return;
    }
    if (!steps.length) {
      renderInfo(info);
      showEmpty("Es la misma función.");
      return;
    }
    const total = steps.length;
    if (state.routeStep === null || state.routeStep > total) state.routeStep = 0;
    const controls = h("div", { class: "controles-ruta" });
    info.push(controls);
    renderInfo(info);
    // Cadena vertical: una caja por función y, si el destino es una tabla, la tabla al final.
    const chain = [from].concat(steps.map((st) => st.to));
    const labels = chain.map((sid) => (sid.startsWith("t:") ? "Tabla " + sid.slice(2) : SYMBOLS[sid].qualname));
    const subs = chain.map((sid) => (sid.startsWith("t:") ? (steps[steps.length - 1].mode === "lee" ? "la lee (SQL en el código)" : "la escribe (SQL en el código)") : SYMBOLS[sid].file + ":" + SYMBOLS[sid].line_start));
    const w = Math.max(220, ...labels.map((l) => l.length * 7.2 + 36), ...subs.map((l) => l.length * 6.6 + 36));
    const BOX_H = 52;
    const GAP = 70;
    const x = 40;
    const svg = s("svg", { role: "img", "aria-label": "Ruta de " + fromName + " a " + goalLabel(goal) });
    svg.appendChild(markers());
    const g = s("g", { class: "vista" });
    const boxes = [];
    const arrows = [];
    steps.forEach((st, i) => {
      const y1 = 40 + i * (BOX_H + GAP) + BOX_H;
      const y2 = y1 + GAP;
      const cx = x + w / 2;
      const path = s("path", { class: "arista c-" + st.conf, d: "M" + cx + "," + y1 + " L" + cx + "," + (y2 - 2), "marker-end": "url(#punta)" });
      g.appendChild(path);
      const text = st.impl ? "posible implementación · probable"
        : st.line ? "llama en la línea " + st.line + (st.conf !== "exacta" ? " · " + st.conf : "")
        : (st.mode === "lee" ? "lee" : "escribe") + " · probable";
      const lw = text.length * 6.6 + 12;
      g.appendChild(drawLabel(text, cx + 10, y1 + GAP / 2 - 8, lw, 16));
      arrows.push(path);
    });
    chain.forEach((sid, i) => {
      const y = 40 + i * (BOX_H + GAP);
      const isTable = sid.startsWith("t:");
      const kind = isTable ? "bd" : SYMBOLS[sid].is_entry ? "entrada" : "funcion";
      const node = s("g", { class: "nodo k-" + kind + (isTable ? "" : " clicable"), tabindex: "0", role: "button", "aria-label": "Paso " + (i + 1) + ": " + labels[i] });
      node.appendChild(s("rect", { class: "forma", x, y, width: w, height: BOX_H, rx: kind === "funcion" || kind === "entrada" ? BOX_H / 2 : 10 }));
      node.appendChild(textBlock([labels[i], subs[i]], x + w / 2, y + BOX_H / 2));
      node.appendChild(s("text", { class: "numero-paso", x: x - 12, y: y + BOX_H / 2 + 4, "text-anchor": "end" }, String(i + 1)));
      node.appendChild(s("title", null, labels[i] + "\n" + subs[i] + (isTable ? "" : "\nClic: ver este paso · doble clic: abrir su flujo")));
      node.addEventListener("click", (e) => { if (state.dragged) return; e.stopPropagation(); stopRoutePlay(); showRouteStep(i); });
      node.addEventListener("dblclick", (e) => { e.stopPropagation(); if (!isTable) openSub(sid); });
      node.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); if (!isTable) openSub(sid); } });
      g.appendChild(node);
      boxes.push(node);
    });
    state.route = { chain, steps, boxes, arrows, controls };
    mount(svg, g, w + 80, 40 + chain.length * (BOX_H + GAP) - GAP + 40, ["entrada", "funcion"].concat(goal.startsWith("t:") ? ["bd"] : []).concat([...new Set(steps.map((st) => st.conf))]));
    showRouteStep(state.routeStep);
  }

  function paintRouteControls() {
    const r = state.route;
    if (!r) return;
    clear(r.controls);
    const n = r.chain.length;
    const i = state.routeStep;
    const prev = h("button", { class: "boton", type: "button", title: "Paso anterior (←)", disabled: i === 0, onclick: () => { stopRoutePlay(); showRouteStep(i - 1); } }, "◀");
    const play = h("button", { class: "boton", type: "button", title: "Recorrer la ruta (espacio)", onclick: toggleRoutePlay }, state.routeTimer ? "⏸ Pausa" : "▶ Reproducir");
    const next = h("button", { class: "boton", type: "button", title: "Paso siguiente (→)", disabled: i === n - 1, onclick: () => { stopRoutePlay(); showRouteStep(i + 1); } }, "▶");
    const sid = r.chain[i];
    const what = sid.startsWith("t:") ? "llega a la tabla " + sid.slice(2) : SYMBOLS[sid].qualname + (i < n - 1 && r.steps[i].line ? " llama en la línea " + r.steps[i].line : "");
    appendAll(r.controls, [prev, play, next, h("span", { class: "paso-actual", "aria-live": "polite" }, "Paso " + (i + 1) + " de " + n + ": " + what)]);
  }

  function showRouteStep(i) {
    const r = state.route;
    if (!r) return;
    state.routeStep = Math.max(0, Math.min(i, r.chain.length - 1));
    r.boxes.forEach((b, k) => {
      b.classList.toggle("seleccionado", k === state.routeStep);
      b.classList.toggle("visitado", k < state.routeStep);
    });
    r.arrows.forEach((a, k) => {
      a.classList.toggle("resaltada", k < state.routeStep);
      a.setAttribute("marker-end", k < state.routeStep ? "url(#punta-foco)" : "url(#punta)");
    });
    paintRouteControls();
    const sid = r.chain[state.routeStep];
    if (sid.startsWith("t:")) {
      const table = DATA.er && DATA.er.tables ? DATA.er.tables.find((t) => t.name === sid.slice(2)) : null;
      if (table) renderTablePanel(table, DATA.er);
      else hidePanel();
      return;
    }
    const line = state.routeStep < r.steps.length ? r.steps[state.routeStep].line : null;
    const want = location.hash;
    loadPack(SYMBOLS[sid].file).then(() => {
      if (location.hash !== want || !state.route || r.chain[state.routeStep] !== sid) return;
      renderPanel(sid);
      if (line) highlightLines(line, line, true);
    }, () => renderPanel(sid));
  }

  function toggleRoutePlay() {
    const r = state.route;
    if (!r) return;
    if (state.routeTimer) { stopRoutePlay(); paintRouteControls(); return; }
    if (state.routeStep >= r.chain.length - 1) showRouteStep(0);
    state.routeTimer = setInterval(() => {
      if (!state.route || state.view !== "ruta") { stopRoutePlay(); return; }
      if (state.routeStep >= state.route.chain.length - 1) { stopRoutePlay(); paintRouteControls(); return; }
      showRouteStep(state.routeStep + 1);
    }, 1400);
    paintRouteControls();
  }

  // ------------------------------------------------------------------ vista: entidad-relación

  // ------------------------------------------------------------------ vista: galaxia

  const COM_COLORS = 10; // .com-0 … .com-9 en el CSS (colores del mapa semántico)

  function renderGalaxy() {
    renderTabs(null);
    hidePanel();
    const gx = DATA.galaxy;
    if (!gx) { renderInfo([]); showEmpty("El proyecto es muy pequeño para la vista galaxia."); return; }
    const [nodes, edges, comms] = [gx.nodes, gx.edges, gx.communities];
    // Enfoque: "n<i>" (un archivo y sus conexiones) o "c<k>" (un subsistema).
    const f = state.focus || "";
    const focusNode = f.startsWith("n") ? Number(f.slice(1)) : null;
    const focusCom = f.startsWith("c") ? Number(f.slice(1)) : null;
    let lit = null;
    if (focusNode !== null && nodes[focusNode]) {
      lit = new Set([focusNode]);
      for (const [a, b] of edges) {
        if (a === focusNode) lit.add(b);
        if (b === focusNode) lit.add(a);
      }
    } else if (focusCom !== null) {
      lit = new Set(nodes.map((n, i) => (n[4] === focusCom ? i : -1)).filter((i) => i >= 0));
    }
    const info = [h("strong", null, "Galaxia"), "  ·  " + nodes.length + " archivos · " + comms.length + " subsistemas"];
    if (focusNode !== null && nodes[focusNode]) {
      const off = h("button", { class: "boton", type: "button", onclick: () => { state.focus = null; syncHash(); renderGalaxy(); } }, "Quitar enfoque");
      info.push(h("div", { class: "aviso-foco" }, "Enfocado: ", h("strong", null, nodes[focusNode][0]), " y sus " + (lit.size - 1) + " conexiones. ", off));
    } else if (focusCom !== null && comms[focusCom]) {
      const off = h("button", { class: "boton", type: "button", onclick: () => { state.focus = null; syncHash(); renderGalaxy(); } }, "Quitar enfoque");
      info.push(h("div", { class: "aviso-foco" }, "Subsistema: ", h("strong", null, comms[focusCom][1]), " (" + comms[focusCom][2] + " archivos). ", off));
    } else {
      info.push(h("div", { class: "pista" }, "Cada punto es un archivo; los colores son subsistemas que se llaman mucho entre sí. Clic: verlo en el mapa · Alt+clic: sus conexiones."));
    }
    if (gx.hidden_edges) info.push(h("div", { class: "pista" }, "Se dibujan las " + edges.length + " conexiones más fuertes de " + (edges.length + gx.hidden_edges) + "."));
    renderInfo(info);
    const svg = s("svg", { role: "img", "aria-label": "Galaxia del proyecto" });
    const g = s("g", { class: "vista" });
    for (const [cid, label, size, cx, cy, r] of comms) {
      const dim = lit && focusCom !== null && cid !== focusCom ? " atenuado" : "";
      g.appendChild(s("circle", { class: "galaxia-racimo com-" + (cid % COM_COLORS) + dim, cx, cy, r }));
      g.appendChild(s("text", { class: "galaxia-titulo" + dim, x: cx, y: cy - r - 8, "text-anchor": "middle" }, label + " (" + size + ")"));
    }
    const edgeGroup = s("g", { class: "galaxia-aristas" });
    for (const [a, b, w] of edges) {
      const on = lit && lit.has(a) && lit.has(b) && (focusNode === null || a === focusNode || b === focusNode);
      const cls = "galaxia-arista" + (lit ? (on ? " resaltada" : " atenuado") : "");
      edgeGroup.appendChild(s("line", { class: cls, x1: nodes[a][1], y1: nodes[a][2], x2: nodes[b][1], y2: nodes[b][2], "stroke-width": Math.min(4, 0.6 + Math.log2(1 + w) * 0.5) }));
    }
    g.appendChild(edgeGroup);
    const gods = new Set(gx.gods || []);
    nodes.forEach(([file, x, y, r, cid, nfun, deg, link], i) => {
      const dim = lit && !lit.has(i) ? " atenuado" : "";
      const ng = s("g", { class: "galaxia-nodo com-" + (cid % COM_COLORS) + (link ? " clicable" : "") + dim + (i === focusNode ? " seleccionado" : ""), tabindex: "0", role: "button", "aria-label": file });
      ng.appendChild(s("circle", { class: "forma", cx: x, cy: y, r }));
      ng.appendChild(s("title", null, file + "\n" + nfun + " funciones · " + deg + " llamadas con otros archivos\nSubsistema: " + comms[cid][1] + (link ? "\nClic: ver en el mapa · Alt+clic o E: enfocar" : "")));
      const focusThis = () => { state.focus = state.focus === "n" + i ? null : "n" + i; syncHash(); renderGalaxy(); };
      ng.addEventListener("click", (e) => {
        if (state.dragged) return;
        e.stopPropagation();
        if (e.altKey || e.shiftKey || !link) { focusThis(); return; }
        location.hash = link;
      });
      ng.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && link) { e.preventDefault(); location.hash = link; }
        else if (e.key === "e" || e.key === "E") { e.preventDefault(); e.stopPropagation(); focusThis(); }
      });
      g.appendChild(ng);
    });
    for (const i of gods) {
      const [file, x, y, r] = nodes[i];
      const dim = lit && !lit.has(i) ? " atenuado" : "";
      g.appendChild(s("text", { class: "galaxia-central" + dim, x: x + r + 4, y: y + 4 }, file.split("/").pop()));
    }
    mount(svg, g, gx.w, gx.h, []);
    // Leyenda plegable: los subsistemas más grandes; clic en uno para enfocarlo.
    const legend = h("div", { class: "leyenda leyenda-galaxia" + (state.legendClosed ? " plegada" : "") });
    const toggle = h("button", { type: "button", class: "boton-limpio titulo-leyenda", "aria-expanded": state.legendClosed ? "false" : "true",
      onclick: () => { state.legendClosed = !state.legendClosed; renderGalaxy(); } },
      (state.legendClosed ? "▸ " : "▾ ") + "Subsistemas (" + comms.length + ")");
    legend.appendChild(toggle);
    if (!state.legendClosed) {
      const list = h("div", { role: "list", "aria-label": "Subsistemas" });
      for (const [cid, label, size] of comms.slice(0, 12)) {
        const item = h("button", { type: "button", class: "item boton-limpio" + (cid === focusCom ? " activo" : ""), role: "listitem", title: label + " (" + size + " archivos) · clic: enfocar" },
          h("span", { class: "muestra com-" + (cid % COM_COLORS) }), h("span", { class: "texto-item" }, label + " (" + size + ")"));
        item.addEventListener("click", () => { state.focus = state.focus === "c" + cid ? null : "c" + cid; syncHash(); renderGalaxy(); });
        list.appendChild(item);
      }
      legend.appendChild(list);
    }
    $("lienzo").appendChild(legend);
  }

  function renderER() {
    renderTabs(null);
    hidePanel();
    const er = DATA.er;
    if (!er || !er.tables || !er.tables.length) {
      renderInfo([]);
      showEmpty("No se encontraron tablas SQL en el proyecto.");
      return;
    }
    renderInfo([h("strong", null, "Diagrama entidad-relación"), "  ·  " + er.tables.length + " tablas, " + er.fks.length + " relaciones"]);
    const lay = er.layout;
    const svg = s("svg", { role: "img", "aria-label": "Diagrama entidad-relación" });
    svg.appendChild(markers());
    const g = s("g", { class: "vista" });
    for (const [pts, label, lx, ly, lw, lh] of lay.edges) {
      g.appendChild(s("path", { class: "arista c-exacta", d: pathFrom(pts), "marker-end": "url(#punta)" }));
      if (label) g.appendChild(drawLabel(label, lx, ly, lw, lh));
    }
    for (const [tid, x, y, w, hh, name, cols] of lay.tables) {
      const tg = s("g", { class: "nodo k-tabla" + (state.focus === tid ? " seleccionado" : ""), "data-id": tid });
      tg.appendChild(s("rect", { class: "forma", x, y, width: w, height: hh, rx: 4 }));
      tg.appendChild(s("text", { x: x + 8, y: y + 13, "font-weight": "700" }, name));
      tg.appendChild(s("line", { class: "linea-interna", x1: x, y1: y + 24, x2: x + w, y2: y + 24 }));
      cols.forEach((c, i) => {
        tg.appendChild(s("text", { x: x + 8, y: y + 24 + LINE_H * (i + 0.5) + 4 }, c));
      });
      tg.classList.add("clicable");
      tg.setAttribute("tabindex", "0");
      tg.setAttribute("role", "button");
      tg.setAttribute("aria-label", "Tabla " + name);
      const open = () => { state.focus = tid; syncHash(); renderER(); };
      tg.addEventListener("click", (e) => { if (!state.dragged) { e.stopPropagation(); open(); } });
      tg.addEventListener("keydown", (e) => { if (e.key === "Enter") open(); });
      g.appendChild(tg);
    }
    // El panel se abre antes de encuadrar, así el ajuste usa el ancho final del lienzo.
    const table = er.tables.find((t) => t.id === state.focus);
    if (table) renderTablePanel(table, er);
    mount(svg, g, lay.w, lay.h, ["tabla"]);
  }

  function renderTablePanel(table, er) {
    const panel = $("panel");
    clear(panel);
    panel.hidden = false;
    appendAll(panel, [
      h("h2", null, table.name),
      h("div", { class: "meta" }, h("code", null, table.file + ":" + table.line)),
    ]);
    const rels = er.fks.filter((f) => f.table === table.name || f.ref_table === table.name);
    if (rels.length) {
      const ul = h("ul");
      for (const f of rels) {
        ul.appendChild(h("li", null, f.table + "(" + f.columns.join(", ") + ") → " + f.ref_table + "(" + f.ref_columns.join(", ") + ")"));
      }
      panel.appendChild(h("div", { class: "seccion" }, h("h3", null, "Relaciones"), ul));
    }
    for (const [mode, title] of [["lee", "Leída por (probable)"], ["escribe", "Escrita por (probable)"]]) {
      const ids = (table.access && table.access[mode]) || [];
      if (!ids.length) continue;
      const ul = h("ul");
      for (const id of ids) {
        const sym = SYMBOLS[id];
        if (sym) ul.appendChild(h("li", null, h("a", { href: buildHash("flujo", id) }, sym.qualname)));
      }
      panel.appendChild(h("div", { class: "seccion" }, h("h3", null, title), ul));
    }
  }

  // ------------------------------------------------------------------ exportar

  function currentSVGString() {
    const svg = $("lienzo").querySelector("svg");
    if (!svg) return null;
    const clone = svg.cloneNode(true);
    const g = clone.querySelector("g.vista");
    if (g) g.removeAttribute("transform");
    clone.querySelectorAll(".atenuado").forEach((n) => n.classList.remove("atenuado"));
    clone.querySelectorAll(".seleccionado").forEach((n) => n.classList.remove("seleccionado"));
    clone.querySelectorAll(".resaltada").forEach((n) => n.classList.remove("resaltada"));
    const w = state.size.w;
    const hh = state.size.h;
    clone.setAttribute("xmlns", SVG_NS);
    clone.setAttribute("width", w);
    clone.setAttribute("height", hh);
    clone.setAttribute("viewBox", "0 0 " + w + " " + hh);
    clone.removeAttribute("style");
    // Estilos en línea: copiar los computados de cada elemento del original.
    const src = svg.querySelectorAll("*");
    const dst = clone.querySelectorAll("*");
    const props = ["fill", "fill-opacity", "stroke", "stroke-width", "stroke-dasharray", "opacity", "font-family", "font-size", "font-weight", "dominant-baseline"];
    for (let i = 0; i < src.length && i < dst.length; i++) {
      const cs = getComputedStyle(src[i]);
      const parts = [];
      for (const p of props) parts.push(p + ":" + cs.getPropertyValue(p));
      dst[i].setAttribute("style", parts.join(";"));
    }
    const bg = getComputedStyle(document.body).backgroundColor;
    const rect = document.createElementNS(SVG_NS, "rect");
    setAttrs(rect, { x: 0, y: 0, width: w, height: hh, fill: bg });
    clone.insertBefore(rect, clone.firstChild);
    return new XMLSerializer().serializeToString(clone);
  }

  function download(name, blob) {
    const url = URL.createObjectURL(blob);
    const a = h("a", { href: url, download: name });
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function exportName(ext) {
    const base = state.id && SYMBOLS[state.id] ? SYMBOLS[state.id].qualname : (state.view || "mapa");
    return "desglosa-" + String(base).replace(/[^\w.-]+/g, "_") + "." + ext;
  }

  function exportSVG() {
    const text = currentSVGString();
    if (text) download(exportName("svg"), new Blob([text], { type: "image/svg+xml" }));
  }

  function exportPNG() {
    const text = currentSVGString();
    if (!text) return;
    const img = new Image();
    const url = URL.createObjectURL(new Blob([text], { type: "image/svg+xml" }));
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = Math.ceil(state.size.w * 2);
      canvas.height = Math.ceil(state.size.h * 2);
      const ctx = canvas.getContext("2d");
      ctx.scale(2, 2);
      ctx.drawImage(img, 0, 0);
      URL.revokeObjectURL(url);
      canvas.toBlob((blob) => { if (blob) download(exportName("png"), blob); }, "image/png");
    };
    img.src = url;
  }

  // ------------------------------------------------------------------ teclado

  function installKeys() {
    document.addEventListener("keydown", (e) => {
      const tag = (e.target && e.target.tagName) || "";
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (helpDialog && helpDialog.open) return; // el diálogo maneja Esc solo
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (state.view === "ruta" && state.route && ["ArrowRight", "ArrowLeft", " "].includes(e.key)) {
        e.preventDefault();
        if (e.key === " ") toggleRoutePlay();
        else { stopRoutePlay(); showRouteStep(state.routeStep + (e.key === "ArrowRight" ? 1 : -1)); }
        return;
      }
      if (e.key === "/") { e.preventDefault(); const b = $("buscar"); if (b) b.focus(); }
      else if (e.key === "?") showHelp();
      else if (e.key === "Escape" && state.focus && (["mapa", "galaxia", "arquitectura"].includes(state.view) || !state.view)) toggleFocus(state.focus);
      else if (e.key === "Escape") goUp();
      else if (e.key === "t") toggleTheme();
      else if (e.key === "m") toggleMode();
      else if (e.key === "+" || e.key === "=") zoomBy(1.25);
      else if (e.key === "-") zoomBy(1 / 1.25);
      else if (e.key === "0") { state.transform = { k: 1, x: 20, y: 20 }; apply(); }
      else if (e.key === "f") { fit(); apply(); }
    });
  }

  // ------------------------------------------------------------------ inicio

  function openIndex() {
    if (!DATA.index) return Promise.resolve(DATA);
    return inflate(DATA.index).then((index) => Object.assign(DATA, index));
  }

  installCanvasEvents();
  installKeys();
  showEmpty("Abriendo " + ((DATA.meta && DATA.meta.name) || "el proyecto") + "…");
  openIndex().then(
    () => {
      SYMBOLS = DATA.symbols || {};
      MAP = DATA.map || null;
      window.addEventListener("hashchange", render);
      window.addEventListener("resize", () => { if (!state.keepTransform) { fit(); apply(); } });
      render();
    },
    (err) => showEmpty(err && err.message === "navegador-antiguo" ? OLD_BROWSER : "No se pudieron abrir los datos del proyecto."),
  );
})();
