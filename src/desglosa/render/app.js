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
  const FUNC_VIEWS = ["flujo", "secuencia", "pseudo", "codigo"]; // vistas de una función
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
    "uml-hereda": "Hereda de (▷ la base)",
    "uml-implementa": "Implementa (▷ la interfaz)",
    "uml-asociacion": "Asociación: un atributo de ese tipo",
    "salta-capa": "Se salta una capa (ver Dependencias)",
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
    estilo: "moderno", // moderno | clasico | pizarra | contraste
    minimapOff: false,
    walk: null, // recorrido animado del flujo
    tour: null, // modo presentación
    tourChecked: false,
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
    if (state.estilo !== "moderno") p.set("estilo", state.estilo);
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
    state.estilo = STYLES.includes(r.params.get("estilo")) ? r.params.get("estilo") : "moderno";
    applyStyle();
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
    if (FUNC_VIEWS.includes(view) && id) updateTrail(id);
    if (!sameView) { state.selectedNode = null; state.routeStep = null; }
    if (view !== "ruta") { stopRoutePlay(); state.route = null; }
    if (state.walk && !(view === "flujo" && id === state.walk.sid)) stopWalk();
    if (!state.tourChecked) {
      state.tourChecked = true;
      const want = r.params.get("presentar");
      if (want !== null) setTimeout(() => startTour(want === "auto"), 0);
    }

    renderToolbar();
    // Vistas de una función: primero se abre el paquete de su archivo.
    const file = FUNC_VIEWS.includes(view) && SYMBOLS[id] ? SYMBOLS[id].file : null;
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
    else if (view === "pseudo") renderPseudoView(id);
    else if (view === "er") renderER();
    else if (view === "galaxia") renderGalaxy();
    else if (view === "arquitectura") renderArch();
    else if (view === "ruta") renderRoute(id);
    else if (view === "dibujo") renderDrawing();
    else if (view === "clases") renderClasses(id);
    else if (view === "dependencias") renderDeps();
    else if (view === "cambios") renderChanges();
    else if (view === "comparar") renderCompare(id);
    else renderMap(null);
    renderCrumbs();
    tourHook();
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
      tools.exportPng = h("button", { class: "boton", type: "button", title: "El diagrama completo como imagen PNG (también los muy largos)", onclick: exportPNG }, "PNG");
      tools.pdf = h("button", { class: "boton", type: "button", title: "Imprimir o guardar como PDF, en páginas sin cortar las cajas", onclick: printDiagram }, "PDF");
      tools.style = h("button", { class: "boton", type: "button", title: "Estilo visual: moderno, clásico (blanco y negro), pizarra o alto contraste (s)", onclick: cycleStyle });
      const helpBtn = h("button", { class: "boton", type: "button", title: "Ayuda y atajos de teclado (?)", "aria-label": "Ayuda", onclick: showHelp }, "?");
      const tourBtn = h("button", { class: "boton", type: "button", title: "Presentación guiada del proyecto (p)", onclick: () => (state.tour ? endTour() : startTour(false)) }, "Presentar");
      const mermaidBtn = h("button", { class: "boton", type: "button", title: "Esta vista como texto Mermaid (para README, Notion o mermaid.live)", onclick: showMermaid }, "Mermaid");
      appendAll(bar, [search, tools.mode, tools.style, tools.theme, zoomOut, zoomIn, fitBtn, tools.exportSvg, tools.exportPng, tools.pdf, mermaidBtn, tourBtn, helpBtn]);
    }
    tools.mode.textContent = state.mode === "facil" ? "Modo: fácil" : "Modo: técnico";
    tools.mode.setAttribute("aria-pressed", state.mode === "tecnico" ? "true" : "false");
    tools.theme.textContent = state.theme === "oscuro" ? "Tema: oscuro" : "Tema: claro";
    tools.theme.hidden = state.estilo !== "moderno"; // los demás estilos ya fijan su fondo
    tools.style.textContent = "Estilo: " + STYLE_NAMES[state.estilo];
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
    ["R", "En un flujo: recorrerlo paso a paso, como una prueba de escritorio"],
    ["Pseudocódigo", "Pestaña de cada función: el algoritmo estilo PSeInt, para copiar o descargar (.psc)"],
    ["P", "Presentación guiada del proyecto (con avance automático para un stand)"],
    ["T", "Tema claro u oscuro"],
    ["S", "Estilo: moderno, clásico (blanco y negro), pizarra o alto contraste"],
    ["N", "Mostrar u ocultar el minimapa"],
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
    else if (state.view === "dibujo") renderDrawing();
    else if (state.view === "clases") renderClasses(state.id);
    else if (state.view === "dependencias") renderDeps();
    else if (state.view === "cambios") renderChanges();
    else if (state.view === "comparar") renderCompare(state.id);
    state.selectedNode = keep;
    if (state.tour) paintTour();
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
    } else if (FUNC_VIEWS.includes(state.view) && state.trail.length) {
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
    } else if (state.view === "clases") {
      items.push({ label: "Clases" + (state.id && state.id !== "." ? ": " + state.id : ""), hash: buildHash("clases", state.id) });
    } else if (state.view === "dependencias") {
      items.push({ label: "Dependencias", hash: buildHash("dependencias", null) });
    } else if (state.view === "cambios" || state.view === "comparar") {
      items.push({ label: "Cambios", hash: buildHash("cambios", null) });
      const row = state.view === "comparar" ? compareRows()[Number(state.id)] : null;
      if (row) items.push({ label: row[2], hash: buildHash("comparar", state.id) });
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
    if (FUNC_VIEWS.includes(state.view)) {
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
    if (state.view === "comparar") { go("cambios", null); return; }
    if (["er", "galaxia", "arquitectura", "clases", "dependencias", "cambios"].includes(state.view)) go("mapa", null);
  }

  // ------------------------------------------------------------------ pestañas e info

  function renderTabs(sid) {
    const tabs = $("pestanas");
    clear(tabs);
    if (!sid) {
      const hasER = DATA.er && DATA.er.tables && DATA.er.tables.length;
      const hasUml = DATA.uml && Object.keys(DATA.uml).length;
      if (hasER || DATA.galaxy || DATA.arch || hasUml || DATA.deps || DATA.compare) {
        if (DATA.compare) tabs.appendChild(tabButton("Cambios (" + DATA.compare.funciones.length + ")", state.view === "cambios" || state.view === "comparar", () => go("cambios", null)));
        tabs.appendChild(tabButton("Mapa", state.view === "mapa" || !state.view, () => go("mapa", null)));
        if (DATA.arch) tabs.appendChild(tabButton("Arquitectura", state.view === "arquitectura", () => go("arquitectura", null)));
        if (hasUml) tabs.appendChild(tabButton("Clases", state.view === "clases", () => go("clases", null)));
        if (DATA.deps) {
          const n = DATA.deps.n_ciclos;
          tabs.appendChild(tabButton("Dependencias" + (n ? " (" + n + ")" : ""), state.view === "dependencias", () => go("dependencias", null)));
        }
        if (DATA.galaxy) tabs.appendChild(tabButton("Galaxia", state.view === "galaxia", () => go("galaxia", null)));
        if (hasER) tabs.appendChild(tabButton("Entidad-relación", state.view === "er", () => go("er", null)));
      }
      return;
    }
    tabs.appendChild(tabButton("Flujo", state.view === "flujo", () => go("flujo", sid, { trail: state.trail })));
    tabs.appendChild(tabButton("Secuencia", state.view === "secuencia", () => go("secuencia", sid, { trail: state.trail })));
    const flow = flowOf(sid);
    if (flow && flow.ps) tabs.appendChild(tabButton("Pseudocódigo", state.view === "pseudo", () => go("pseudo", sid, { trail: state.trail })));
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
    minimap = null;
    currentGroup = null;
    const lienzo = $("lienzo");
    clear(lienzo);
    lienzo.appendChild(h("div", { class: "vacio" }, message));
  }

  // ------------------------------------------------------------------ lienzo: zoom y arrastre

  let currentGroup = null;

  function mount(svg, group, w, hgt, legendKinds, legendNames) {
    const lienzo = $("lienzo");
    clear(lienzo);
    // El zoom va en un grupo de afuera: así el minimapa puede reusar el contenido (<use>).
    group.setAttribute("id", "contenido");
    const zoom = s("g", { class: "zoom" }, group);
    svg.appendChild(zoom);
    lienzo.appendChild(svg);
    if (legendKinds && legendKinds.length) lienzo.appendChild(buildLegend(legendKinds, legendNames));
    lienzo.appendChild(buildMinimap(w, hgt));
    currentGroup = zoom;
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
    updateMinimap();
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
      marker("punta-foco", "punta-foco"),
      // UML: triángulo hueco (herencia, implementación) y flecha abierta (asociación).
      s("marker", { id: "uml-triangulo", viewBox: "0 0 12 12", refX: "11", refY: "6", markerWidth: "12", markerHeight: "12", orient: "auto-start-reverse", markerUnits: "userSpaceOnUse" },
        s("path", { d: "M0,0 L11,6 L0,12 z", class: "uml-punta-hueca" })),
      s("marker", { id: "uml-flecha", viewBox: "0 0 12 12", refX: "11", refY: "6", markerWidth: "12", markerHeight: "12", orient: "auto-start-reverse", markerUnits: "userSpaceOnUse" },
        s("path", { d: "M0,0 L11,6 L0,12", class: "uml-punta-abierta" })));
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

  function buildLegend(kinds, names) {
    const box = h("div", { class: "leyenda", role: "list", "aria-label": "Leyenda" });
    for (const k of kinds) {
      const icon = s("svg", { viewBox: "0 0 26 16", "aria-hidden": "true" });
      if (k.startsWith("uml-") || k === "salta-capa") {
        icon.appendChild(s("line", { x1: 1, y1: 8, x2: 25, y2: 8, class: "arista " + k }));
      } else if (CONF_NAMES[k]) {
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
      box.appendChild(h("div", { class: "item", role: "listitem", "data-tipo": k }, icon, (names && names[k]) || NODE_NAMES[k] || CONF_NAMES[k] || k));
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
    const changed = DATA.compare ? compareIndexOf(sid) : -1;
    if (changed >= 0) infoParts.push(h("div", { class: "acciones-flujo" }, h("a", { class: "boton", href: buildHash("comparar", String(changed)) }, "Ver antes y después (" + DATA.compare.antes + ")")));
    if (flow && flow.edges && flow.edges.length) {
      infoParts.push(h("div", { class: "acciones-flujo" },
        h("button", { class: "boton", type: "button", id: "boton-recorrer", title: "Animación paso a paso, como una prueba de escritorio (r)", onclick: () => (state.walk ? stopWalk() : walkStart(sid, false)) }, state.walk && state.walk.sid === sid ? "✕ Terminar recorrido" : "▶ Recorrer")));
    }
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
    if (state.walk && state.walk.sid === sid) paintWalk(false);
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

  // ------------------------------------------------------------------ vista: pseudocódigo (PSeInt)

  const PS_KEYWORDS = new Set([
    "Algoritmo", "FinAlgoritmo", "Funcion", "FinFuncion", "SubProceso", "FinSubProceso",
    "Si", "Entonces", "SiNo", "FinSi", "Mientras", "Hacer", "FinMientras", "Para", "Hasta",
    "Con", "Paso", "FinPara", "Cada", "de", "Repetir", "Que", "Segun", "FinSegun", "De", "Otro",
    "Modo", "Escribir", "Sin", "Saltar", "Leer", "Definir", "Como", "Dimension", "Esperar",
    "Tecla", "Y", "O", "NO", "MOD",
  ]);
  const PS_VALUES = new Set(["Entero", "Real", "Caracter", "Logico", "Verdadero", "Falso"]);
  const PS_TOKEN = /(\/\/.*$)|("[^"]*"|'[^']*')|([A-Za-zÁÉÍÓÚÜáéíóúüÑñ_][\wÁÉÍÓÚÜáéíóúüÑñ]*)|(<-)/g;

  /** Una línea coloreada, solo con nodos de texto: el contenido viene del código analizado. */
  function psLine(text) {
    const out = [];
    let pos = 0;
    let m;
    PS_TOKEN.lastIndex = 0;
    while ((m = PS_TOKEN.exec(text))) {
      if (m.index > pos) out.push(text.slice(pos, m.index));
      if (m[1]) out.push(h("span", { class: "ps-com" }, m[1]));
      else if (m[2]) out.push(h("span", { class: "ps-cad" }, m[2]));
      else if (m[3]) out.push(PS_KEYWORDS.has(m[3]) ? h("span", { class: "ps-kw" }, m[3]) : PS_VALUES.has(m[3]) ? h("span", { class: "ps-val" }, m[3]) : m[3]);
      else out.push(h("span", { class: "ps-kw" }, m[4]));
      pos = PS_TOKEN.lastIndex;
    }
    if (pos < text.length) out.push(text.slice(pos));
    return out;
  }

  function psFileName(sym) {
    return String(sym.qualname).replace(/[^\w.-]+/g, "_") + ".psc";
  }

  function copyText(text, status) {
    const done = () => { status.textContent = "Copiado."; };
    const fallback = () => {
      const area = h("textarea", { "aria-hidden": "true", style: "position:fixed;left:-9999px;" });
      area.value = text;
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
      done();
    };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, fallback);
    else fallback();
  }

  function renderPseudoView(sid) {
    renderTabs(sid);
    const sym = SYMBOLS[sid];
    if (!sym) { showEmpty("No se encontró la función."); return; }
    renderPanel(sid);
    const flow = flowOf(sid);
    const text = flow && flow.ps;
    if (!text) {
      renderInfo([h("strong", null, "Pseudocódigo"), "  ·  " + sym.qualname]);
      showEmpty("Esta función no tiene cuerpo para traducir.");
      return;
    }
    const status = h("span", { class: "nota", "aria-live": "polite" });
    const copy = h("button", { class: "boton", type: "button", onclick: () => copyText(text, status) }, "Copiar");
    const save = h("button", { class: "boton", type: "button", title: "Archivo para abrir en PSeInt", onclick: () => download(psFileName(sym), new Blob([text], { type: "text/plain" })) }, "Descargar .psc");
    renderInfo([
      h("strong", null, "Pseudocódigo"), "  ·  estilo PSeInt  ·  ", copy, " ", save, " ", status,
      h("div", { class: "pista" }, "Traducido del código sin ejecutarlo. Lo que PSeInt no tiene (retornar a mitad, break, try, objetos) va como comentario //."),
    ]);
    const lienzo = $("lienzo");
    clear(lienzo);
    minimap = null;
    currentGroup = null;
    const pre = h("div", { class: "codigo pseudo", style: "position:absolute;inset:0;", role: "region", "aria-label": "Pseudocódigo de " + sym.qualname });
    text.replace(/\n$/, "").split("\n").forEach((ln, i) => {
      // Un solo <span> por línea: en una fila flex los espacios sueltos se perderían.
      pre.appendChild(h("div", { class: "ln" }, h("span", { class: "num" }, String(i + 1)), h("span", null, psLine(ln))));
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
    state.lastMapPath = group.path !== undefined ? group.path : group.kind === "proyecto" ? null : state.lastMapPath;
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
    // Llamadas que se saltan una capa (pestaña Dependencias): origen\u0000destino → texto.
    const skips = new Map((DATA.deps ? DATA.deps.capas : []).map((c) => [c[4] + "\u0000" + c[5], c[0]]));
    const legend = (arch.legend || []).slice();
    for (const [src, dst, pts, conf, label, lx, ly, lw, lh, mix, back, text] of arch.edges) {
      const dim = lit && !(lit.has(src) && lit.has(dst)) ? " atenuado" : "";
      const lightEdge = lit && !dim ? " resaltada" : "";
      const skip = skips.get(src + "\u0000" + dst);
      if (skip && !legend.includes("salta-capa")) legend.push("salta-capa");
      const parts = [];
      for (const k of ["exacta", "probable", "ambigua"]) if (mix && mix[k]) parts.push(mix[k] + " " + MIX_NAMES[k][mix[k] === 1 ? 0 : 1]);
      const tip = names[src] + " → " + names[dst] + (text ? "\n" + text : "") + (parts.length ? "\n" + parts.join(" · ") : "") + (back ? "\nVa hacia una capa anterior" : "") + (skip ? "\nSe salta una capa: " + skip : "");
      g.appendChild(s("path", { class: "arista c-" + conf + dim + lightEdge + (back ? " hacia-atras" : "") + (skip ? " salta-capa" : ""), d: pathFrom(pts), "marker-end": lightEdge ? "url(#punta-foco)" : "url(#punta)" }));
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
    mount(svg, g, arch.w, arch.h, legend);
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

  // ------------------------------------------------------------------ recorrer un flujo

  // Prueba de escritorio animada: avanza nodo por nodo desde Inicio. En cada decisión
  // elige la persona ("sí" / "no") o, en automático, una regla fija y explicable (ver
  // `autoChoice`): en un bucle entra una vez y sale; en un "si" sigue el camino principal.
  // Las excepciones solo se toman a mano.
  const WALK_MS = 1300;
  const WALK_MS_TOUR = 850;
  const WALK_MAX_STEPS = 400;
  const REDUCED_MOTION = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

  function walkOptions(flow, nid) {
    const rank = (e) => (e[3] === "excepcion" ? 2 : e[2] === "sí" ? 0 : 1);
    return (flow.edges || [])
      .map((e, i) => [e, i])
      .filter(([e]) => e[0] === nid)
      .sort((a, b) => rank(a[0]) - rank(b[0]) || a[1] - b[1])
      .map(([e]) => e);
  }

  /** Cuántos nodos distintos se pueden alcanzar desde `start`. Se cuentan también las
   * vueltas de los bucles: dentro de un bucle, la rama que sigue iterando llega a todo lo
   * que viene después del bucle, y la del `return` de error solo llega a Fin. */
  function stepsAhead(flow, start) {
    const seen = new Set([start]);
    const queue = [start];
    while (queue.length) {
      const cur = queue.shift();
      for (const e of flow.edges) {
        if (e[0] === cur && e[3] !== "excepcion" && !seen.has(e[1])) {
          seen.add(e[1]);
          queue.push(e[1]);
        }
      }
    }
    return seen.size;
  }

  /** Salida automática de un nodo: en la cabecera de un bucle, entrar la primera vez y salir
   * después; en un "si" o un "según", la salida con más pasos por delante (el camino
   * principal, no el `return` de un error). En empate gana "sí". */
  function autoChoice(flow, cur, opts, visits) {
    const normal = opts.filter((e) => e[3] !== "excepcion");
    let pool = normal.length ? normal : opts;
    if (pool.length === 1) return pool[0];
    const isHeader = flow.edges.some((e) => e[1] === cur && e[3] === "retorno_bucle");
    if (isHeader) {
      const enter = pool.find((e) => e[2] === "sí") || pool[0];
      const leave = pool.find((e) => e !== enter) || enter;
      return visits > 1 ? leave : enter;
    }
    const forward = pool.filter((e) => e[3] !== "retorno_bucle");
    if (forward.length) pool = forward;
    let best = pool[0];
    let most = -1;
    for (const e of pool) {
      const n = stepsAhead(flow, e[1]);
      if (n > most) { best = e; most = n; }
    }
    return best;
  }

  function walkStartNode(flow) {
    const incoming = new Set((flow.edges || []).map((e) => e[1]));
    const ids = (flow.layout.nodes || []).map((n) => n[0]);
    return ids.find((id) => flow.nodes[id] && flow.nodes[id].kind === "terminal" && !incoming.has(id)) || ids[0];
  }

  function stopWalkTimer() {
    if (state.walk && state.walk.timer) { clearInterval(state.walk.timer); state.walk.timer = null; }
  }

  function stopWalk() {
    stopWalkTimer();
    state.walk = null;
    const cap = $("recorrido");
    if (cap) cap.remove();
    $("lienzo").classList.remove("con-recorrido");
    const btn = $("boton-recorrer");
    if (btn) btn.textContent = "▶ Recorrer";
    document.querySelectorAll("#lienzo .nodo.actual, #lienzo .nodo.visitado").forEach((n) => n.classList.remove("actual", "visitado"));
  }

  function walkStart(sid, auto, fast) {
    const flow = flowOf(sid);
    if (!flow || !flow.edges || !flow.layout.nodes.length) return;
    stopWalk();
    const first = walkStartNode(flow);
    state.walk = { sid, auto: auto !== false, fast: !!fast, path: [first], visits: { [first]: 1 }, timer: null, playing: false, done: false, zoomed: false };
    paintWalk(true);
    walkPlay(true);
  }

  function walkCurrent() {
    const w = state.walk;
    return w.path[w.path.length - 1];
  }

  /** Opciones que la persona puede elegir en el nodo actual (null si no hay que elegir). */
  function walkChoices() {
    const w = state.walk;
    const flow = flowOf(w.sid);
    const opts = walkOptions(flow, walkCurrent());
    return opts.length > 1 ? opts : null;
  }

  function walkStep(choice) {
    const w = state.walk;
    if (!w || w.done) return;
    const flow = flowOf(w.sid);
    const cur = walkCurrent();
    const opts = walkOptions(flow, cur);
    if (!opts.length || w.path.length >= WALK_MAX_STEPS) {
      w.done = true;
      stopWalkTimer();
      w.playing = false;
      paintWalk(false);
      return;
    }
    const edge = (choice !== undefined && opts[choice]) || autoChoice(flow, cur, opts, w.visits[cur] || 1);
    w.path.push(edge[1]);
    w.visits[edge[1]] = (w.visits[edge[1]] || 0) + 1;
    paintWalk(true);
  }

  function walkBack() {
    const w = state.walk;
    if (!w || w.path.length < 2) return;
    const last = w.path.pop();
    w.visits[last] -= 1;
    w.done = false;
    paintWalk(true);
  }

  function walkTick() {
    const w = state.walk;
    if (!w) return;
    if (!w.auto && walkChoices()) {
      // Espera a que la persona elija; después sigue reproduciendo sola.
      stopWalkTimer();
      w.playing = false;
      w.resume = true;
      paintWalk(false);
      return;
    }
    walkStep();
  }

  function walkPlay(on) {
    const w = state.walk;
    if (!w) return;
    stopWalkTimer();
    w.playing = on && !w.done;
    if (w.playing) w.timer = setInterval(walkTick, w.fast ? WALK_MS_TOUR : WALK_MS);
    paintWalk(false);
  }

  function nodeText(flow, nid) {
    const n = (flow.layout.nodes || []).find((x) => x[0] === nid);
    if (!n) return "";
    return (state.mode === "facil" ? n[5] : n[6]).join(" ");
  }

  function paintWalk(move) {
    const w = state.walk;
    if (!w || state.view !== "flujo" || state.id !== w.sid) return;
    const flow = flowOf(w.sid);
    const cur = walkCurrent();
    const visited = new Set(w.path.slice(0, -1));
    document.querySelectorAll("#lienzo .nodo[data-id]").forEach((n) => {
      const id = n.getAttribute("data-id");
      n.classList.toggle("actual", id === cur);
      n.classList.toggle("visitado", id !== cur && visited.has(id));
    });
    selectNode(w.sid, cur, true);
    const el = document.querySelector('#lienzo .nodo[data-id="' + cur + '"]');
    if (el && move) centerOn(el);
    // Leyenda del recorrido: paso, texto del nodo y controles.
    let cap = $("recorrido");
    if (!cap) {
      cap = h("div", { class: "recorrido", id: "recorrido", role: "region", "aria-label": "Recorrido del diagrama" });
      $("lienzo").appendChild(cap);
    }
    $("lienzo").classList.add("con-recorrido");
    const btn = $("boton-recorrer");
    if (btn) btn.textContent = "✕ Terminar recorrido";
    clear(cap);
    const info = flow.nodes[cur] || {};
    const kind = NODE_NAMES[info.kind] ? NODE_NAMES[info.kind].replace(" (clic para abrir)", "") : "";
    const head = w.done
      ? "Fin del recorrido: " + w.path.length + " pasos."
      : "Paso " + w.path.length + (kind ? " · " + kind : "");
    cap.appendChild(h("div", { class: "recorrido-paso", "aria-live": "polite" }, head));
    cap.appendChild(h("div", { class: "recorrido-texto" }, nodeText(flow, cur)));
    const choices = !w.done && walkChoices();
    if (choices && !w.auto) {
      const row = h("div", { class: "recorrido-opciones" }, h("span", null, "¿Por dónde sigue? "));
      choices.forEach((e, i) => {
        const label = e[3] === "excepcion" ? "excepción" + (e[2] ? ": " + e[2] : "") : e[2] || "seguir";
        row.appendChild(h("button", { class: "boton opcion", type: "button", onclick: () => {
          const resume = w.resume;
          w.resume = false;
          walkStep(i);
          if (resume) walkPlay(true);
        } }, label));
      });
      cap.appendChild(row);
    }
    const ctl = h("div", { class: "recorrido-controles" });
    appendAll(ctl, [
      h("button", { class: "boton", type: "button", title: "Volver a empezar", onclick: () => walkStart(w.sid, w.auto, w.fast) }, "⏮"),
      h("button", { class: "boton", type: "button", title: "Paso anterior (←)", disabled: w.path.length < 2, onclick: () => { walkPlay(false); walkBack(); } }, "◀"),
      h("button", { class: "boton", type: "button", title: "Reproducir o pausar (espacio)", disabled: w.done, onclick: () => walkPlay(!w.playing) }, w.playing ? "⏸ Pausa" : "▶ Seguir"),
      h("button", { class: "boton", type: "button", title: "Paso siguiente (→)", disabled: w.done || (!w.auto && !!choices), onclick: () => { walkPlay(false); walkStep(); } }, "▶|"),
      h("button", { class: "boton", type: "button", "aria-pressed": w.auto ? "true" : "false", title: "En automático: en un bucle entra una vez y sale; en un «si» sigue el camino principal (la salida con más pasos por delante)", onclick: () => { w.auto = !w.auto; paintWalk(false); } }, w.auto ? "Decide: automático" : "Decide: yo"),
      info.target && SYMBOLS[info.target] ? h("button", { class: "boton", type: "button", title: "Abrir el flujo de la función llamada", onclick: () => openSub(info.target) }, "Entrar a " + SYMBOLS[info.target].name + "()") : null,
      h("button", { class: "boton", type: "button", title: "Terminar el recorrido (Esc)", "aria-label": "Cerrar el recorrido", onclick: stopWalk }, "✕"),
    ]);
    cap.appendChild(ctl);
  }

  /** Mueve la vista para que el nodo quede a la vista (y legible, si estaba muy lejos). */
  function centerOn(el) {
    const w = state.walk;
    const r = $("lienzo").getBoundingClientRect();
    if (w && !w.zoomed && state.transform.k < 0.75) {
      w.zoomed = true;
      state.transform.k = 0.95;
      apply();
    }
    const b = el.getBoundingClientRect();
    const margin = 50;
    const bottom = r.bottom - 150; // la leyenda del recorrido ocupa el pie
    if (b.left > r.left + margin && b.right < r.right - margin && b.top > r.top + margin && b.bottom < bottom) return;
    const dx = r.left + r.width / 2 - (b.left + b.width / 2);
    const dy = r.top + (r.height - 150) / 2 - (b.top + b.height / 2);
    tweenTo(state.transform.x + dx, state.transform.y + dy);
  }

  function tweenTo(x, y) {
    const from = { k: state.transform.k, x: state.transform.x, y: state.transform.y };
    const dur = REDUCED_MOTION ? 0 : 380;
    const t0 = performance.now();
    const frame = (now) => {
      const p = dur ? Math.min(1, (now - t0) / dur) : 1;
      const e = p * (2 - p);
      state.transform = { k: from.k, x: from.x + (x - from.x) * e, y: from.y + (y - from.y) * e };
      apply();
      if (p < 1) requestAnimationFrame(frame);
    };
    requestAnimationFrame(frame);
  }

  // ------------------------------------------------------------------ modo presentación

  // Visita guiada armada con los datos del proyecto, con un texto sencillo en cada paso.
  // En automático avanza sola y vuelve a empezar: sirve para dejarla corriendo en un stand.
  const TOUR_MS = 9000;

  function tourEntry() {
    const cands = Object.keys(SYMBOLS).filter((id) => hasFlow(id) && (SYMBOLS[id].kind === "function" || SYMBOLS[id].kind === "method"));
    const base = (id) => (DATA.routes && DATA.routes[id] ? 4 : 0) + (SYMBOLS[id].is_entry ? 2 : 0) + Math.min(((DATA.calls_out || {})[id] || []).length, 5) / 10;
    cands.sort((a, b) => base(b) - base(a) || SYMBOLS[a].qualname.localeCompare(SYMBOLS[b].qualname));
    // Entre las mejores: primero las que llegan a la base de datos (para el paso de la
    // ruta) y, de ellas, la más rica (más decisiones y llamadas) para que el recorrido luzca.
    const top = cands.slice(0, 20).map((id, i) => ({
      id, i,
      db: tracePath(id, ANY_TABLE) ? 1 : 0,
      size: ((SYMBOLS[id].metrics || {}).cc || 0) + Math.min(((DATA.calls_out || {})[id] || []).length, 5),
    }));
    top.sort((a, b) => b.db - a.db || b.size - a.size || a.i - b.i);
    return top.length ? top[0].id : null;
  }

  function buildTour() {
    const slides = [];
    const files = Object.values(DATA.files || {}).filter((f) => !f.skipped);
    const langs = [...new Set(files.map((f) => f.lang))].sort();
    const funcs = Object.values(SYMBOLS).filter((s) => s.kind === "function" || s.kind === "method").length;
    const doc = MAP && MAP.groups[MAP.root] && MAP.groups[MAP.root].doc;
    slides.push({ view: "mapa", id: null, cover: true, title: (DATA.meta && DATA.meta.name) || "Proyecto",
      text: (doc ? doc + " · " : "") + files.length + " archivos (" + langs.join(", ") + ") y " + funcs + " funciones, leídos sin ejecutarlos, sin IA y sin internet." });
    if (MAP) slides.push({ view: "mapa", id: null, title: "El mapa", text: "Cada caja es una carpeta, un archivo o una clase. Las flechas dicen quién llama a quién y cuántas veces; con clic se baja de nivel." });
    if (DATA.arch) slides.push({ view: "arquitectura", id: null, title: "La arquitectura", text: "Las capas del programa según sus nombres y carpetas (controladores → servicios → datos) y lo que usa de afuera: base de datos, correo, APIs." });
    if (DATA.galaxy) slides.push({ view: "galaxia", id: null, title: "La galaxia", text: "Todo el proyecto de un vistazo: cada punto es un archivo y los colores son grupos que se llaman mucho entre sí." });
    const entry = tourEntry();
    if (entry) {
      const name = SYMBOLS[entry].name + "()";
      slides.push({ view: "flujo", id: entry, walk: true, title: "Diagrama de flujo de " + name, text: "Así se ejecuta paso a paso. Lo recorremos como una prueba de escritorio: en cada rombo se elige «sí» o «no»." });
      if ((DATA.seq_ids || []).includes(entry)) slides.push({ view: "secuencia", id: entry, title: "Diagrama de secuencia de " + name, text: "Quién llama a quién y en qué orden, con sus bucles y condiciones." });
      if (tracePath(entry, ANY_TABLE)) slides.push({ view: "ruta", id: entry + "/" + encodeURIComponent(ANY_TABLE), route: true, title: "¿Cómo llega " + name + " a la base de datos?", text: "El camino de llamadas más corto, paso a paso, hasta la tabla que lee o escribe." });
    }
    if (DATA.er && DATA.er.tables && DATA.er.tables.length) slides.push({ view: "er", id: null, title: "La base de datos", text: "Las tablas y cómo se relacionan (claves foráneas), sacadas de los archivos .sql." });
    slides.push({ view: "mapa", id: null, cover: true, title: "Hecho con Desglosa", text: "De código a diagramas, sin IA y sin internet. Pulsa Esc para explorar por tu cuenta." });
    return slides;
  }

  function startTour(auto) {
    if (state.tour) endTour();
    document.body.classList.add("en-presentacion");
    state.tour = { slides: buildTour(), i: 0, auto: !!auto, timer: null, started: -1, since: 0 };
    showSlide(0);
  }

  function endTour() {
    const t = state.tour;
    if (!t) return;
    if (t.timer) clearInterval(t.timer);
    state.tour = null;
    document.body.classList.remove("en-presentacion");
    const box = $("presentacion");
    if (box) box.remove();
    stopWalk();
    stopRoutePlay();
  }

  function showSlide(i) {
    const t = state.tour;
    if (!t) return;
    t.i = (i + t.slides.length) % t.slides.length;
    t.started = -1;
    stopWalk();
    stopRoutePlay();
    const sl = t.slides[t.i];
    const target = buildHash(sl.view, sl.id);
    if (location.hash === target) render();
    else location.hash = target;
  }

  /** Se llama al final de cada render: pinta la leyenda y arranca la animación del paso. */
  function tourHook() {
    const t = state.tour;
    if (!t) return;
    const sl = t.slides[t.i];
    paintTour();
    if (t.started === t.i || state.view !== sl.view || (state.id || null) !== (sl.id ? decodeURIComponent(sl.id) : null)) return;
    t.started = t.i;
    t.since = performance.now();
    t.endedAt = 0;
    hidePanel();
    if (sl.walk) setTimeout(() => { if (state.tour && state.view === "flujo") walkStart(sl.id, true, true); }, 700);
    if (sl.route) setTimeout(() => { if (state.tour && state.route && !state.routeTimer) toggleRoutePlay(); }, 700);
    if (t.timer) clearInterval(t.timer);
    t.timer = setInterval(tourTick, 400);
  }

  /** En automático: un paso normal dura TOUR_MS; uno animado, hasta que termina la
   * animación (o 45 nodos del flujo) más 2,5 s para verlo. */
  function tourTick() {
    const t = state.tour;
    if (!t || !t.auto) return;
    const sl = t.slides[t.i];
    const now = performance.now();
    const elapsed = now - t.since;
    let finished = elapsed > TOUR_MS;
    if (sl.walk) {
      const w = state.walk;
      finished = w ? w.done || w.path.length >= 45 : elapsed > 3000; // sin flujo: seguir
    } else if (sl.route) {
      const r = state.route;
      finished = r ? !state.routeTimer && state.routeStep >= r.chain.length - 1 && elapsed > 1500 : elapsed > 3000;
    }
    if (!finished) return;
    if (sl.walk || sl.route) {
      if (!t.endedAt) t.endedAt = now;
      if (now - t.endedAt < 2500) return;
    }
    showSlide(t.i + 1);
  }

  /** El texto del paso va en la franja de información (o centrado y grande en la
   * portada), con los controles de la presentación. */
  function paintTour() {
    const t = state.tour;
    if (!t) return;
    const sl = t.slides[t.i];
    const old = $("presentacion");
    if (old) old.remove();
    const full = document.fullscreenElement
      ? h("button", { class: "boton", type: "button", onclick: () => { if (document.exitFullscreen) document.exitFullscreen().then(paintTour, () => {}); } }, "Salir de pantalla completa")
      : h("button", { class: "boton", type: "button", title: "Ideal para proyectar", onclick: () => { const d = document.documentElement; if (d.requestFullscreen) d.requestFullscreen().then(paintTour, () => {}); } }, "Pantalla completa");
    const controls = h("div", { class: "presentacion-controles" },
      h("span", { class: "presentacion-numero" }, (t.i + 1) + " / " + t.slides.length),
      h("button", { class: "boton", type: "button", title: "Anterior (←)", "aria-label": "Anterior", onclick: () => showSlide(t.i - 1) }, "◀"),
      h("button", { class: "boton", type: "button", title: "Siguiente (→)", "aria-label": "Siguiente", onclick: () => showSlide(t.i + 1) }, "▶"),
      h("button", { class: "boton", type: "button", "aria-pressed": t.auto ? "true" : "false", title: "Avanza sola y vuelve a empezar (espacio)", onclick: () => { t.auto = !t.auto; t.since = performance.now(); t.endedAt = 0; paintTour(); } }, t.auto ? "Automático: sí" : "Automático: no"),
      full,
      h("button", { class: "boton", type: "button", title: "Salir de la presentación (Esc)", onclick: endTour }, "Salir"));
    if (sl.cover) {
      renderInfo([]);
      document.body.appendChild(h("div", { id: "presentacion", class: "presentacion portada", role: "region", "aria-label": "Presentación" },
        h("h2", null, sl.title), h("p", null, sl.text), controls));
      return;
    }
    renderInfo([h("div", { class: "presentacion-info", role: "region", "aria-label": "Presentación", "aria-live": "polite" },
      h("h2", null, sl.title), h("p", null, sl.text), controls)]);
  }

  // ------------------------------------------------------------------ vista: dibujo (Mermaid → Desglosa)

  function renderDrawing() {
    renderTabs(null);
    hidePanel();
    const d = DATA.drawing;
    if (!d) { renderInfo([]); showEmpty("No hay ningún dibujo en este archivo."); return; }
    const info = [h("strong", null, d.title || (DATA.meta && DATA.meta.name) || "Dibujo"), "  ·  " + d.nodes.length + " nodos, " + d.edges.length + " flechas, dibujado desde Mermaid"];
    for (const w of d.warnings || []) info.push(h("div", { class: "pista" }, "Aviso: " + w));
    renderInfo(info);
    const svg = s("svg", { role: "img", "aria-label": "Diagrama " + (d.title || "") });
    svg.appendChild(markers());
    const g = s("g", { class: "vista" });
    for (const [, , pts, style, arrow, label, lx, ly, lw, lh] of d.edges) {
      g.appendChild(s("path", { class: "arista k-" + style, d: pathFrom(pts), "marker-end": arrow ? "url(#punta)" : null }));
      if (label) g.appendChild(drawLabel(label, lx, ly, lw, lh));
    }
    for (const [nid, kind, x, y, w, hh, lines] of d.nodes) {
      const ng = s("g", { class: "nodo k-" + kind, "data-id": nid });
      if (kind === "conector") ng.appendChild(s("circle", { class: "forma", cx: x + w / 2, cy: y + hh / 2, r: w / 2 }));
      else appendAll(ng, flowShape(kind, x, y, w, hh));
      ng.appendChild(textBlock(lines, x + w / 2, y + hh / 2 + textOffset(kind)));
      ng.appendChild(s("title", null, lines.join(" ") + "\n(" + nid + ")"));
      g.appendChild(ng);
    }
    // En un dibujo nada se abre con clic: la leyenda no lo promete.
    mount(svg, g, d.w, d.h, d.legend || [], { subproceso: "Subproceso", es: "Entrada / salida de datos" });
  }

  // ------------------------------------------------------------------ exportar a Mermaid

  // Mismas reglas que desglosa/mermaid.py (flow_to_mermaid): formas clásicas y, para
  // pantalla, teclado y documento, la sintaxis @{ shape } de Mermaid 11.3.
  const MM_CLASSIC = { terminal: ['(["', '"])'], proceso: ['["', '"]'], subproceso: ['[["', '"]]'], decision: ['{"', '"}'], es: ['[/"', '"/]'], conector: ['(("', '"))'], externo: ['["', '"]'] };
  const MM_NEW = { pantalla: "curv-trap", teclado: "sl-rect", documento: "doc" };
  const MM_COLORS = { terminal: "#059669", proceso: "#2563eb", subproceso: "#7c3aed", decision: "#b45309", es: "#0891b2", teclado: "#0891b2", pantalla: "#db2777", documento: "#db2777", externo: "#64748b", conector: "#64748b", modulo: "#4f46e5", clase: "#2563eb", interfaz: "#2563eb", funcion: "#7c3aed", entrada: "#059669", otros: "#64748b", bd: "#c2410c", tabla: "#c2410c" };
  const MM_ENT = { "#": "#35;", '"': "#quot;", "<": "#lt;", ">": "#gt;", ";": "#59;", "|": "#124;", "{": "#123;", "}": "#125;" };

  function mmEscape(text) {
    return String(text).split(/\s+/).filter(Boolean).join(" ").replace(/[#"<>;|{}]/g, (c) => MM_ENT[c]);
  }

  function mmNode(id, kind, text) {
    if (MM_NEW[kind]) return id + "@{ shape: " + MM_NEW[kind] + ', label: "' + mmEscape(text) + '" }';
    const [a, b] = MM_CLASSIC[kind] || MM_CLASSIC.proceso;
    return id + a + mmEscape(text) + b;
  }

  function mmClasses(kinds) {
    const by = {};
    for (const [id, kind] of Object.entries(kinds)) if (MM_COLORS[kind]) (by[kind] = by[kind] || []).push(id);
    const names = Object.keys(by).sort();
    return names.map((k) => "    classDef " + k + " fill:" + MM_COLORS[k] + "26,stroke:" + MM_COLORS[k] + ",stroke-width:2px" + (k === "externo" || k === "otros" ? ",stroke-dasharray:4 3" : ""))
      .concat(names.map((k) => "    class " + by[k].join(",") + " " + k));
  }

  function mmHeader(title, kind) {
    return ["---", 'title: "' + mmEscape(title) + '"', "---", kind];
  }

  function mermaidFlow(sid) {
    const flow = flowOf(sid);
    if (!flow || !flow.edges) return null;
    const out = mmHeader(SYMBOLS[sid].qualname, "flowchart TD");
    const kinds = {};
    for (const n of flow.layout.nodes) {
      const info = flow.nodes[n[0]];
      kinds[n[0]] = info.kind;
      out.push("    " + mmNode(n[0], info.kind, state.mode === "facil" ? n[5].join(" ") : info.tech));
    }
    for (const [a, b, label, kind] of flow.edges) {
      out.push("    " + a + (kind === "excepcion" ? " -.->" : " -->") + (label ? '|"' + mmEscape(label) + '"|' : "") + " " + b);
    }
    return out.concat(mmClasses(kinds)).join("\n") + "\n";
  }

  /** Nivel del mapa o arquitectura: cajas y flechas con su número de llamadas. */
  function mermaidBoxes(title, nodes, edges, columns) {
    const out = mmHeader(title, "flowchart LR");
    const ids = {};
    const kinds = {};
    nodes.forEach((n, i) => { ids[n[0]] = "m" + i; kinds["m" + i] = n[1]; });
    const line = (n) => {
      const text = n[6] + (n[7] ? " · " + n[7] : "");
      const round = n[1] === "funcion" || n[1] === "entrada";
      return ids[n[0]] + (round ? '(["' : '["') + mmEscape(text) + (round ? '"])' : '"]');
    };
    if (columns) {
      columns.forEach(([name, cx], ci) => {
        const inCol = nodes.filter((n) => Math.abs(n[2] + n[4] / 2 - cx) < 1);
        if (!inCol.length) return;
        out.push("    subgraph c" + ci + '["' + mmEscape(name) + '"]');
        for (const n of inCol) out.push("        " + line(n));
        out.push("    end");
      });
    } else {
      for (const n of nodes) out.push("    " + line(n));
    }
    for (const e of edges) {
      const text = columns ? e[11] : e[4];
      if (!(e[0] in ids) || !(e[1] in ids)) continue;
      out.push("    " + ids[e[0]] + (e[3] === "exacta" ? " -->" : " -.->") + (text ? '|"' + mmEscape(text) + '"|' : "") + " " + ids[e[1]]);
    }
    return out.concat(mmClasses(kinds)).join("\n") + "\n";
  }

  /** Bloque de la secuencia (etiqueta del dibujo: "loop [c]", "alt [c]", "try"…) → Mermaid. */
  function mmFrag(label) {
    const m = /^(\w+)(?:\s*\[(.*)\])?$/.exec(label) || [];
    const kw = m[1];
    const text = m[2] || "";
    if (kw === "loop" || kw === "opt") return kw + " " + mmEscape(text);
    if (kw === "try") return "alt intentar";
    if (kw === "catch") return "alt " + mmEscape(("excepción " + text).trim());
    if (kw === "alt") return "alt " + mmEscape(text === "else" ? "si no" : text);
    return "opt " + mmEscape(label);
  }

  /** La secuencia que se ve, en Mermaid, reconstruida desde su dibujo (no se guarda aparte:
   * en Laravel eran 20 MB más). Bloques por su altura: se abren arriba y se cierran abajo. La
   * CLI (`desglosa mermaid --secuencia`) usa el modelo completo; aquí un `catch` va como un
   * `alt` propio en vez de `else` del `try`. */
  function mermaidSequence(sid) {
    const seq = sequenceOf(sid);
    if (!seq) return null;
    const lay = state.showExternal && seq.layout_all ? seq.layout_all : seq.layout;
    const out = mmHeader("Secuencia de " + SYMBOLS[sid].qualname, "sequenceDiagram");
    const centers = lay.participants.map(([x, , w]) => x + w / 2);
    lay.participants.forEach(([, , , , label, kind], i) => {
      out.push("    " + (kind === "actor" ? "actor" : "participant") + " P" + i + " as " + mmEscape(label));
    });
    const who = (x) => {
      let best = 0;
      centers.forEach((c, i) => { if (Math.abs(c - x) < Math.abs(centers[best] - x)) best = i; });
      return "P" + best;
    };
    const ev = [];
    for (const [, y, , hh, label, , divider] of lay.fragments) {
      ev.push({ y, order: 0, h: hh, text: mmFrag(label) });
      if (divider !== null && divider !== undefined) ev.push({ y: divider, order: 1 });
      ev.push({ y: y + hh, order: 3, h: hh });
    }
    for (const m of lay.messages) ev.push({ y: m[2], order: 2, msg: m });
    // A la misma altura: abrir (el de afuera primero), mensajes, cerrar (el de adentro primero).
    ev.sort((a, b) => a.y - b.y || a.order - b.order || (a.order === 0 ? b.h - a.h : a.h - b.h));
    let depth = 0;
    const pad = (d) => "    ".repeat(d + 1);
    for (const e of ev) {
      if (e.order === 0) { out.push(pad(depth) + e.text); depth++; }
      else if (e.order === 1) out.push(pad(depth - 1) + "else si no");
      else if (e.order === 3) { depth = Math.max(0, depth - 1); out.push(pad(depth) + "end"); }
      else {
        const [x1, x2, , text, kind, , conf] = e.msg;
        const note = kind !== "retorno" && conf && conf !== "exacta" && conf !== "externa" ? " [" + conf + "]" : "";
        out.push(pad(depth) + who(x1) + (kind === "retorno" ? "-->>" : "->>") + who(x2) + ": " + mmEscape(text + note));
      }
    }
    return out.join("\n") + "\n";
  }

  function mermaidForView() {
    const v = state.view || "mapa";
    if (v === "flujo" && state.id) return mermaidFlow(state.id);
    if (v === "secuencia" && state.id) return mermaidSequence(state.id);
    if (v === "dibujo" && DATA.drawing) return DATA.drawing.source;
    if (v === "clases") {
      const index = DATA.uml || {};
      const folder = state.id === null || state.id === undefined ? umlDefaultFolder() : state.id === "." ? "" : state.id;
      const d = PACKS["@uml/" + folder];
      return d ? d.mermaid : null;
    }
    if (v === "arquitectura" && DATA.arch) return mermaidBoxes("Arquitectura de " + ((DATA.meta && DATA.meta.name) || "proyecto"), DATA.arch.nodes, DATA.arch.edges, DATA.arch.columns);
    if (v === "mapa" && MAP) {
      const gid = state.id && MAP.groups[state.id] ? state.id : MAP.root;
      const lay = MAP.groups[gid].layout;
      return lay ? mermaidBoxes(MAP.groups[gid].name, lay.nodes, lay.edges, null) : null;
    }
    return null;
  }

  let mermaidDialog = null;

  function showMermaid() {
    const text = mermaidForView();
    if (mermaidDialog) mermaidDialog.remove();
    const area = h("textarea", { class: "texto-mermaid", readonly: true, rows: 16, "aria-label": "Texto Mermaid", spellcheck: "false" });
    area.value = text || "";
    const status = h("span", { class: "nota", "aria-live": "polite" });
    const copy = h("button", { class: "boton", type: "button", disabled: !text, onclick: () => {
      const done = () => { status.textContent = "Copiado."; };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(area.value).then(done, () => { area.select(); document.execCommand("copy"); done(); });
      else { area.select(); document.execCommand("copy"); done(); }
    } }, "Copiar");
    const save = h("button", { class: "boton", type: "button", disabled: !text, onclick: () => download(exportName("mmd"), new Blob([area.value], { type: "text/plain" })) }, "Descargar .mmd");
    const close = h("button", { class: "boton", type: "button", onclick: () => mermaidDialog.close() }, "Cerrar");
    mermaidDialog = h("dialog", { class: "ayuda dialogo-mermaid", "aria-labelledby": "mermaid-titulo" },
      h("h2", { id: "mermaid-titulo" }, "Esta vista en Mermaid"),
      h("p", null, text
        ? "Pégalo en un README de GitHub, en mermaid.live o en Notion. Pantalla, teclado y documento usan las formas de Mermaid 11.3 o más nuevo."
        : "Esta vista no tiene exportación a Mermaid. Prueba en un flujo, una secuencia, el mapa, la arquitectura, las clases o un dibujo."),
      text ? area : null,
      h("div", { class: "acciones-dialogo" }, copy, save, close, status));
    document.body.appendChild(mermaidDialog);
    mermaidDialog.showModal();
  }

  // ------------------------------------------------------------------ vista: diagrama de clases (UML)

  const UML_LINE = 16;
  const UML_HEAD = 34;
  const UML_PAD = 8;

  /** Carpeta que se abre por defecto: la del nivel del mapa en que estabas, o la que
   * tiene más clases. */
  function umlDefaultFolder() {
    const index = DATA.uml || {};
    const folders = Object.keys(index);
    const fromMap = state.lastMapPath;
    if (fromMap !== undefined && fromMap !== null && index[fromMap]) return fromMap;
    folders.sort((a, b) => index[b].clases - index[a].clases || a.localeCompare(b));
    return folders[0];
  }

  function renderClasses(id) {
    renderTabs(null);
    hidePanel();
    const index = DATA.uml || {};
    const folders = Object.keys(index);
    if (!folders.length) { renderInfo([]); showEmpty("El proyecto no tiene clases."); return; }
    let folder = id === null || id === undefined ? umlDefaultFolder() : id === "." ? "" : id;
    if (!(folder in index)) folder = umlDefaultFolder();
    const key = "@uml/" + folder;
    if (!PACKS[key]) {
      showEmpty("Cargando el diagrama de clases…");
      const want = location.hash;
      loadPack(key).then(() => { if (location.hash === want) renderClasses(id); },
        (err) => showEmpty(err && err.message === "navegador-antiguo" ? OLD_BROWSER : "No se pudo abrir el diagrama."));
      return;
    }
    const d = PACKS[key];
    // Selector de carpeta: las que tienen más clases primero.
    const sorted = folders.slice().sort((a, b) => index[b].clases - index[a].clases || a.localeCompare(b));
    const select = h("select", { class: "selector-carpeta", "aria-label": "Carpeta del diagrama de clases",
      onchange: (e) => go("clases", e.target.value === "" ? "." : e.target.value) });
    for (const f of sorted) {
      const opt = h("option", { value: f }, (f || "(raíz)") + " — " + index[f].clases + (index[f].clases === 1 ? " clase" : " clases"));
      if (f === folder) opt.selected = true;
      select.appendChild(opt);
    }
    const info = [h("strong", null, "Diagrama de clases"), "  ·  ", select];
    info.push(h("div", { class: "pista" }, "UML: + público, − privado, # protegido, ~ paquete; subrayado = estático, cursiva = abstracto. Las clases en gris son de otra carpeta (clic para ir a la suya)."));
    if (d.hidden) info.push(h("div", { class: "pista" }, "Carpeta grande: se dibujan las " + (d.classes.filter((c) => !c[10]).length) + " clases más relacionadas; " + d.hidden + " no se muestran."));
    renderInfo(info);
    const svg = s("svg", { role: "img", "aria-label": "Diagrama de clases de " + (folder || "la raíz") });
    svg.appendChild(markers());
    const g = s("g", { class: "vista" });
    const kinds = new Set();
    for (const [, , pts, kind, label, lx, ly, lw, lh] of d.edges) {
      kinds.add("uml-" + kind);
      g.appendChild(s("path", { class: "arista uml-" + kind, d: pathFrom(pts),
        "marker-end": kind === "asociacion" ? "url(#uml-flecha)" : "url(#uml-triangulo)" }));
      if (label) g.appendChild(drawLabel(label, lx, ly, lw, lh));
    }
    for (const [cid, kind, x, y, w, hh, stereo, name, attrs, methods, ghost, ghostFolder, link, abstract, where] of d.classes) {
      const nk = kind === "interface" ? "interfaz" : "clase";
      kinds.add(nk);
      const target = ghost ? null : link;
      const cg = s("g", { class: "nodo k-" + nk + " uml-clase" + (ghost ? " uml-fantasma clicable" : link ? " clicable" : ""), "data-id": cid, tabindex: "0", role: "button",
        "aria-label": (stereo ? stereo + " " : "") + name });
      cg.appendChild(s("rect", { class: "forma", x, y, width: w, height: hh, rx: 3 }));
      const cx = x + w / 2;
      if (ghost) {
        cg.appendChild(s("text", { class: "uml-nombre", x: cx, y: y + hh / 2 + 1, "text-anchor": "middle" }, name));
      } else {
        if (stereo) cg.appendChild(s("text", { class: "uml-estereotipo", x: cx, y: y + 12, "text-anchor": "middle" }, stereo));
        cg.appendChild(s("text", { class: "uml-nombre" + (abstract || kind === "interface" ? " abstracto" : ""), x: cx, y: y + (stereo ? 26 : 19), "text-anchor": "middle" }, name));
        let ty = y + UML_HEAD;
        cg.appendChild(s("line", { class: "linea-interna", x1: x, y1: ty, x2: x + w, y2: ty }));
        ty += UML_PAD / 2;
        const block = (lines) => {
          if (!lines.length) { ty += UML_LINE; return; }
          for (const [text, flags] of lines) {
            ty += UML_LINE;
            cg.appendChild(s("text", { class: "uml-miembro" + (flags.includes("s") ? " estatico" : "") + (flags.includes("a") ? " abstracto" : ""), x: x + UML_PAD, y: ty - 4 }, text));
          }
        };
        block(attrs);
        ty += UML_PAD / 2;
        cg.appendChild(s("line", { class: "linea-interna", x1: x, y1: ty, x2: x + w, y2: ty }));
        ty += UML_PAD / 2;
        block(methods);
      }
      cg.appendChild(s("title", null, (stereo ? stereo + " " : "") + name + "\n" + where + (ghost ? "\nDe la carpeta " + (ghostFolder || "(raíz)") + ": clic para ver su diagrama" : target ? "\nClic: verla en el mapa" : "")));
      const open = () => {
        if (ghost) go("clases", ghostFolder === "" ? "." : ghostFolder);
        else if (target) location.hash = withParams(target);
      };
      cg.addEventListener("click", (e) => { if (state.dragged) return; e.stopPropagation(); open(); });
      cg.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); open(); } });
      g.appendChild(cg);
    }
    const order = ["clase", "interfaz", "uml-hereda", "uml-implementa", "uml-asociacion"];
    mount(svg, g, d.w, d.h, order.filter((k) => kinds.has(k)));
  }

  // ------------------------------------------------------------------ vista: dependencias

  /** Un paso de una dependencia: "archivo:línea  motivo", con enlace a la función. */
  function depStep(why, at, sid) {
    const sym = sid ? SYMBOLS[sid] : null;
    const text = sym && hasFlow(sid) ? h("a", { href: buildHash("flujo", sid) }, why) : why;
    return h("li", null, h("code", { class: "dep-lugar" }, at), " ", text);
  }

  function renderDeps() {
    renderTabs(null);
    hidePanel();
    const d = DATA.deps;
    if (!d) { renderInfo([]); showEmpty("No hay dependencias entre archivos para revisar."); return; }
    renderInfo([
      h("strong", null, "Dependencias"), "  ·  " + d.archivos + " archivos, " + d.relaciones + " relaciones",
      h("div", { class: "pista" }, "Un archivo depende de otro si llama a sus funciones, hereda de sus clases o las usa como tipo. Solo cuentan las llamadas exactas o probables."),
    ]);
    const lienzo = $("lienzo");
    clear(lienzo);
    minimap = null;
    currentGroup = null;
    const doc = h("div", { class: "documento", role: "region", "aria-label": "Dependencias" });
    const okCycles = !d.n_ciclos;
    doc.appendChild(h("div", { class: "resumen-deps" },
      h("div", { class: "tarjeta " + (okCycles ? "bien" : "mal") },
        h("span", { class: "cifra" }, String(d.n_ciclos)),
        h("span", null, d.n_ciclos === 1 ? "ciclo" : "ciclos")),
      h("div", { class: "tarjeta " + (d.n_capas ? "aviso" : "bien") },
        h("span", { class: "cifra" }, String(d.n_capas)),
        h("span", null, d.n_capas === 1 ? "capa que se salta" : "capas que se saltan"))));

    doc.appendChild(h("h2", null, "Ciclos"));
    if (okCycles) {
      doc.appendChild(h("p", null, "No hay ciclos: ninguna carpeta ni archivo depende, dando la vuelta, de sí mismo. Se puede entender (y probar) cada parte empezando por las de abajo."));
    } else {
      doc.appendChild(h("p", { class: "nota-deps" }, "En un ciclo, A depende de B y B (directa o indirectamente) de A: no se puede cambiar ni probar una sin la otra. Se rompe moviendo lo que comparten a un tercer lugar o invirtiendo una dependencia (una interfaz)."));
      const list = h("ol", { class: "lista-deps" });
      for (const c of d.ciclos) {
        const chips = [];
        c.camino.forEach((p, i) => {
          if (i) chips.push(h("span", { class: "flecha-dep", "aria-hidden": "true" }, "→"));
          chips.push(h("span", { class: "chip-dep" }, p || "(raíz)"));
        });
        const extra = c.nudo > c.camino.length - 1 ? h("span", { class: "nota" }, " · el nudo completo tiene " + c.nudo + (c.nivel === "carpeta" ? " carpetas" : " archivos")) : null;
        list.appendChild(h("li", null,
          h("div", { class: "camino-dep" }, h("span", { class: "nivel-dep" }, c.nivel === "carpeta" ? "carpetas" : "archivos"), chips, extra),
          h("ul", { class: "pasos-dep" }, c.pasos.map(([why, at, sid]) => depStep(why, at, sid)))));
      }
      doc.appendChild(list);
      if (d.n_ciclos > d.ciclos.length) doc.appendChild(h("p", { class: "nota" }, "… y " + (d.n_ciclos - d.ciclos.length) + " más (desglosa check --json los lista todos)."));
    }

    doc.appendChild(h("h2", null, "Capas que se saltan"));
    if (!d.n_capas) {
      doc.appendChild(h("p", null, "Ninguna. Cuando la entrada (un controlador) llama directo al acceso a datos aunque exista un servicio que ya lo usa, aparece aquí."));
    } else {
      const list = h("ul", { class: "lista-deps" });
      for (const [text, why, at, sid] of d.capas) list.appendChild(h("li", null, h("div", null, text), h("ul", { class: "pasos-dep" }, depStep(why, at, sid))));
      doc.appendChild(list);
      if (DATA.arch) doc.appendChild(h("p", { class: "nota" }, "En la pestaña Arquitectura se ven como flechas punteadas de color."));
    }
    doc.appendChild(h("h2", null, "En integración continua"));
    doc.appendChild(h("p", null, "desglosa check RUTA falla (código 5) si aparece un ciclo nuevo. Con --aceptar se guardan los de hoy como aceptados en .desglosa-check.json."));
    lienzo.appendChild(doc);
  }

  // ------------------------------------------------------------------ vista: comparar versiones

  // Fila: [estado, archivo, nombre, id antes, id después, líneas antes, líneas después,
  //        complejidad antes, complejidad después]
  function compareRows() {
    return DATA.compare ? DATA.compare.funciones : [];
  }

  function compareIndexOf(sid) {
    return compareRows().findIndex((r) => r[0] === "cambiada" && r[4] === sid);
  }

  function ccText(a, b) {
    if (a === null || a === undefined || b === null || b === undefined || a === b) return "";
    return "complejidad " + a + " → " + b;
  }

  function renderChanges() {
    renderTabs(null);
    hidePanel();
    const c = DATA.compare;
    if (!c) { renderInfo([]); showEmpty("Este HTML no es una comparación (usa desglosa comparar)."); return; }
    renderInfo([
      h("strong", null, "Cambios"), "  ·  de " + c.antes + " a " + c.despues,
      h("div", { class: "pista" }, "Una función cambió si cambió su texto (moverla no cuenta). Clic en una cambiada: su diagrama de antes y de después, lado a lado."),
    ]);
    const lienzo = $("lienzo");
    clear(lienzo);
    minimap = null;
    currentGroup = null;
    const rows = compareRows();
    const count = (st) => rows.filter((r) => r[0] === st).length;
    const card = (n, label, cls) => h("div", { class: "tarjeta " + cls }, h("span", { class: "cifra" }, String(n)), h("span", null, label));
    const files = c.archivos;
    const doc = h("div", { class: "documento", role: "region", "aria-label": "Cambios entre versiones" });
    doc.appendChild(h("div", { class: "resumen-deps" },
      card(count("cambiada"), "cambiadas", "aviso"),
      card(count("nueva"), "nuevas", "bien"),
      card(count("eliminada"), "eliminadas", "mal"),
      card(files.cambiados.length + files.nuevos.length + files.eliminados.length, "archivos tocados", "")));
    if (!rows.length) doc.appendChild(h("p", null, "Ninguna función cambió entre las dos versiones."));
    const byFile = new Map();
    rows.forEach((r, i) => {
      if (!byFile.has(r[1])) byFile.set(r[1], []);
      byFile.get(r[1]).push([r, i]);
    });
    const tag = { nueva: "nueva", eliminada: "eliminada", cambiada: "cambiada" };
    for (const [file, list] of byFile) {
      const state_ = files.nuevos.includes(file) ? " (archivo nuevo)" : files.eliminados.includes(file) ? " (archivo eliminado)" : "";
      doc.appendChild(h("h2", null, h("code", null, file), state_));
      const ul = h("ul", { class: "lista-cambios" });
      for (const [r, i] of list) {
        const [st, , name, , after, , , ccA, ccD] = r;
        let label = name;
        if (st === "nueva" && after && SYMBOLS[after] && hasFlow(after)) label = h("a", { href: buildHash("flujo", after) }, name);
        else if (st !== "nueva") label = h("a", { href: buildHash("comparar", String(i)) }, name);
        const extra = ccText(ccA, ccD);
        ul.appendChild(h("li", { class: "cambio-" + st }, h("span", { class: "marca-cambio" }, tag[st]), " ", label, extra ? h("span", { class: "nota" }, "  · " + extra) : null));
      }
      doc.appendChild(ul);
    }
    lienzo.appendChild(doc);
  }

  /** Dibuja un flujo ya armado (sin clics); `mark(tech)` dice si un nodo es nuevo o se quitó. */
  function drawFlowGroup(flow, mark) {
    const g = s("g");
    const lay = flow.layout;
    for (const [pts, kind, arrow] of lay.lines) {
      g.appendChild(s("path", { class: "arista k-" + kind, d: pathFrom(pts), "marker-end": arrow ? (kind === "excepcion" ? "url(#punta-exc)" : "url(#punta)") : null }));
    }
    for (const [text, x, y, w, hh] of lay.labels) g.appendChild(drawLabel(text, x, y, w, hh));
    for (const [nid, x, y, w, hh, easy, tech] of lay.nodes) {
      const info = flow.nodes[nid];
      const extra = mark(info.tech);
      const ng = s("g", { class: "nodo k-" + info.kind + (extra ? " " + extra : "") });
      appendAll(ng, flowShape(info.kind, x, y, w, hh));
      ng.appendChild(textBlock(state.mode === "facil" ? easy : tech, x + w / 2, y + hh / 2 + textOffset(info.kind)));
      ng.appendChild(s("title", null, info.tech + (extra === "agregado" ? "\nNuevo en esta versión" : extra === "quitado" ? "\nYa no está en la versión nueva" : "")));
      g.appendChild(ng);
    }
    for (const [label, cx, cy, r] of lay.connectors) {
      const cg = s("g", { class: "nodo k-conector" }, s("circle", { class: "forma", cx, cy, r }));
      cg.appendChild(s("text", { x: cx, y: cy + 0.5, "text-anchor": "middle" }, label));
      g.appendChild(cg);
    }
    return g;
  }

  function techCounts(flow) {
    const out = new Map();
    if (!flow) return out;
    for (const id of Object.keys(flow.nodes)) {
      const t = flow.nodes[id].tech;
      out.set(t, (out.get(t) || 0) + 1);
    }
    return out;
  }

  function renderCompare(id) {
    renderTabs(null);
    hidePanel();
    const rows = compareRows();
    const row = rows[Number(id)];
    if (!row) { renderInfo([]); showEmpty("No se encontró ese cambio."); return; }
    const [st, file, name, before, after, linesA, linesD, ccA, ccD] = row;
    const need = [];
    if (before && !PACKS["@antes/" + file]) need.push("@antes/" + file);
    if (after && !PACKS[file]) need.push(file);
    if (need.length) {
      showEmpty("Cargando las dos versiones…");
      const want = location.hash;
      Promise.all(need.map((k) => loadPack(k))).then(() => { if (location.hash === want) renderCompare(id); },
        (err) => showEmpty(err && err.message === "navegador-antiguo" ? OLD_BROWSER : "No se pudo abrir la comparación."));
      return;
    }
    const fb = before && PACKS["@antes/" + file] ? (PACKS["@antes/" + file].flows || {})[before] : null;
    const fa = after ? flowOf(after) : null;
    const c = DATA.compare;
    const info = [h("strong", null, name), "  ·  " + file];
    const extra = ccText(ccA, ccD);
    if (extra) info.push("  ·  " + extra);
    if (linesA && linesD && linesA !== linesD) info.push("  ·  " + linesA + " → " + linesD + " líneas");
    info.push(h("div", { class: "pista" }, st === "eliminada"
      ? "Esta función ya no existe en " + c.despues + ". Así era en " + c.antes + "."
      : "Izquierda: " + c.antes + ". Derecha: " + c.despues + ". En verde los pasos nuevos; en rojo, punteados, los que se quitaron."));
    if (after && SYMBOLS[after]) info.push(h("div", { class: "acciones-flujo" }, h("a", { class: "boton", href: buildHash("flujo", after) }, "Abrir el flujo actual")));
    renderInfo(info);
    if (!fb && !fa) { showEmpty("Ninguna de las dos versiones tiene cuerpo para dibujar."); return; }
    const inA = techCounts(fb);
    const inD = techCounts(fa);
    const gap = 90;
    const top = 44;
    const wB = fb ? fb.layout.w : 0;
    const wA = fa ? fa.layout.w : 0;
    const svg = s("svg", { role: "img", "aria-label": "Antes y después de " + name });
    svg.appendChild(markers());
    const g = s("g", { class: "vista comparacion" });
    let x = 0;
    if (fb) {
      g.appendChild(s("text", { class: "titulo-version", x: wB / 2, y: 24, "text-anchor": "middle" }, "Antes · " + c.antes));
      const gb = drawFlowGroup(fb, (t) => (inD.has(t) ? "" : "quitado"));
      gb.setAttribute("transform", "translate(0," + top + ")");
      g.appendChild(gb);
      x = wB + gap;
    }
    if (fa) {
      g.appendChild(s("text", { class: "titulo-version", x: x + wA / 2, y: 24, "text-anchor": "middle" }, "Después · " + c.despues));
      const ga = drawFlowGroup(fa, (t) => (!fb || inA.has(t) ? "" : "agregado"));
      ga.setAttribute("transform", "translate(" + x + "," + top + ")");
      g.appendChild(ga);
    }
    if (fb && fa) g.appendChild(s("line", { class: "separador-version", x1: wB + gap / 2, y1: 8, x2: wB + gap / 2, y2: top + Math.max(fb.layout.h, fa.layout.h) }));
    const kinds = new Set([...((fb && fb.layout.legend) || []), ...((fa && fa.layout.legend) || [])]);
    const h_ = top + Math.max(fb ? fb.layout.h : 0, fa ? fa.layout.h : 0);
    mount(svg, g, x + wA || wB, h_, [...kinds]);
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

  /** Título que acompaña a una imagen o a un PDF: qué diagrama es y de dónde sale. */
  function viewTitle() {
    const name = (DATA.meta && DATA.meta.name) || "";
    const sym = state.id && SYMBOLS[state.id];
    switch (state.view) {
      case "flujo": return sym ? "Diagrama de flujo · " + sym.qualname + " · " + sym.file + ":" + sym.line_start : name;
      case "secuencia": return sym ? "Diagrama de secuencia · " + sym.qualname : name;
      case "codigo": return sym ? sym.qualname : name;
      case "dependencias": return "Dependencias · " + name;
      case "cambios": return "Cambios · " + name;
      case "comparar": return "Antes y después · " + ((compareRows()[Number(state.id)] || [])[2] || name);
      case "pseudo": return sym ? "Pseudocódigo · " + sym.qualname : name;
      case "arquitectura": return "Arquitectura · " + name;
      case "galaxia": return "Galaxia · " + name;
      case "er": return "Entidad-relación · " + name;
      case "ruta": return "Ruta de llamadas · " + name;
      case "dibujo": return (DATA.drawing && DATA.drawing.title) || name;
      default: {
        const g = MAP && MAP.groups[state.id && MAP.groups[state.id] ? state.id : MAP.root];
        return "Mapa · " + (g ? g.name : name);
      }
    }
  }

  const EXPORT_HEAD = 40; // franja del título arriba de la imagen

  /** El diagrama completo (no solo lo que se ve) como SVG con estilos en línea y título. */
  function currentSVGString() {
    const svg = $("lienzo").querySelector("svg");
    if (!svg) return null;
    const clone = svg.cloneNode(true);
    clone.querySelectorAll(".atenuado").forEach((n) => n.classList.remove("atenuado"));
    clone.querySelectorAll(".seleccionado").forEach((n) => n.classList.remove("seleccionado"));
    clone.querySelectorAll(".resaltada").forEach((n) => n.classList.remove("resaltada"));
    clone.querySelectorAll(".actual, .visitado").forEach((n) => n.classList.remove("actual", "visitado"));
    const w = Math.ceil(state.size.w);
    const hh = Math.ceil(state.size.h) + EXPORT_HEAD;
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
    const zoom = clone.querySelector("g.zoom");
    if (zoom) zoom.setAttribute("transform", "translate(0," + EXPORT_HEAD + ")");
    const body = getComputedStyle(document.body);
    const rect = document.createElementNS(SVG_NS, "rect");
    setAttrs(rect, { x: 0, y: 0, width: w, height: hh, fill: body.backgroundColor });
    clone.insertBefore(rect, clone.firstChild);
    const title = document.createElementNS(SVG_NS, "text");
    setAttrs(title, { x: 16, y: 26, style: "font:600 15px " + body.fontFamily + ";fill:" + body.color });
    title.textContent = viewTitle();
    clone.insertBefore(title, rect.nextSibling);
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

  // Los navegadores no dibujan lienzos de más de ~16 000 px por lado ni de más de ~268
  // millones de píxeles: un flujo muy largo baja su escala en vez de fallar.
  const CANVAS_SIDE = 16000;
  const CANVAS_AREA = 2.6e8;

  function exportPNG() {
    const text = currentSVGString();
    if (!text) return;
    const w = Math.ceil(state.size.w);
    const hh = Math.ceil(state.size.h) + EXPORT_HEAD;
    const scale = Math.max(0.1, Math.min(2, CANVAS_SIDE / Math.max(w, hh), Math.sqrt(CANVAS_AREA / (w * hh))));
    const img = new Image();
    const url = URL.createObjectURL(new Blob([text], { type: "image/svg+xml" }));
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = Math.ceil(w * scale);
      canvas.height = Math.ceil(hh * scale);
      const ctx = canvas.getContext("2d");
      ctx.scale(scale, scale);
      ctx.drawImage(img, 0, 0);
      URL.revokeObjectURL(url);
      canvas.toBlob((blob) => { if (blob) download(exportName("png"), blob); }, "image/png");
    };
    img.src = url;
  }

  // PDF sin librerías: se arma una versión para imprimir, partida en páginas sin cortar
  // cajas, y el navegador la guarda como PDF ("Guardar como PDF" en el diálogo).
  const PAGE_RATIO = { portrait: 265 / 186, landscape: 178 / 273 }; // alto/ancho útil (A4)

  function pageCuts(total, slice, intervals) {
    const cuts = [0];
    let start = 0;
    while (total - start > slice) {
      let cut = start + slice;
      const blocking = (y) => intervals.find(([a, b]) => a < y && y < b);
      for (let b = blocking(cut), guard = 0; b && guard < 500; b = blocking(cut), guard++) cut = b[0] - 6;
      if (cut <= start + slice * 0.3) cut = start + slice; // una caja más alta que la página
      cuts.push(cut);
      start = cut;
    }
    cuts.push(total);
    return cuts;
  }

  function printDiagram() {
    const root = document.documentElement;
    const saved = { tema: root.dataset.tema, estilo: root.dataset.estilo };
    // En papel: fondo blanco (moderno claro, o clásico para pizarra y alto contraste).
    if (state.estilo === "moderno") root.dataset.tema = "claro";
    else if (state.estilo !== "clasico") root.dataset.estilo = "clasico";
    let text = null;
    try {
      text = currentSVGString();
    } finally {
      root.dataset.tema = saved.tema;
      if (saved.estilo === undefined) delete root.dataset.estilo;
      else root.dataset.estilo = saved.estilo;
    }
    if (!text) return;
    const w = Math.ceil(state.size.w);
    const total = Math.ceil(state.size.h) + EXPORT_HEAD;
    const orientation = w > total ? "landscape" : "portrait";
    const intervals = [];
    document.querySelectorAll("#contenido .nodo, #contenido .galaxia-nodo").forEach((n) => {
      const b = n.getBBox();
      intervals.push([b.y + EXPORT_HEAD, b.y + b.height + EXPORT_HEAD]);
    });
    const cuts = pageCuts(total, w * PAGE_RATIO[orientation], intervals);
    const base = new DOMParser().parseFromString(text, "image/svg+xml").documentElement;
    const box = h("div", { id: "impresion" }, h("style", null, "@page { size: A4 " + orientation + "; margin: 12mm; }"));
    const n = cuts.length - 1;
    for (let i = 0; i < n; i++) {
      const y0 = cuts[i];
      const sh = cuts[i + 1] - y0;
      const page = document.importNode(base, true);
      setAttrs(page, { width: w, height: sh, viewBox: "0 " + y0 + " " + w + " " + sh });
      const note = n > 1 ? "Página " + (i + 1) + " de " + n + (i < n - 1 ? " · continúa en la página " + (i + 2) : "") : "";
      box.appendChild(h("div", { class: "pagina-impresion" }, note ? h("p", null, note) : null, page));
    }
    document.body.appendChild(box);
    document.body.classList.add("imprimiendo");
    const done = () => {
      document.body.classList.remove("imprimiendo");
      box.remove();
      window.removeEventListener("afterprint", done);
    };
    window.addEventListener("afterprint", done);
    window.print();
    setTimeout(done, 0); // por si el navegador no avisa "afterprint"
  }

  // ------------------------------------------------------------------ minimapa

  let minimap = null; // { box, rect, w, h }

  function buildMinimap(w, hh) {
    const scale = Math.min(180 / w, 130 / hh);
    const mw = Math.max(40, Math.round(w * scale));
    const mh = Math.max(30, Math.round(hh * scale));
    const svg = s("svg", { viewBox: "0 0 " + w + " " + hh, style: "width:" + mw + "px;height:" + mh + "px", role: "img", "aria-label": "Minimapa" });
    svg.appendChild(s("use", { href: "#contenido" }));
    const rect = s("rect", { class: "minimapa-visor" });
    svg.appendChild(rect);
    const close = h("button", { class: "boton-limpio minimapa-cerrar", type: "button", title: "Ocultar el minimapa (n)", "aria-label": "Ocultar el minimapa",
      onclick: (e) => { e.stopPropagation(); state.minimapOff = true; updateMinimap(); } }, "×");
    const box = h("div", { class: "minimapa", title: "Minimapa: clic o arrastra para moverte" }, svg, close);
    let dragging = false;
    const moveTo = (e) => {
      const r = svg.getBoundingClientRect();
      const L = $("lienzo").getBoundingClientRect();
      const cx = ((e.clientX - r.left) / r.width) * w;
      const cy = ((e.clientY - r.top) / r.height) * hh;
      state.transform.x = L.width / 2 - cx * state.transform.k;
      state.transform.y = L.height / 2 - cy * state.transform.k;
      apply();
    };
    svg.addEventListener("pointerdown", (e) => { dragging = true; svg.setPointerCapture(e.pointerId); moveTo(e); });
    svg.addEventListener("pointermove", (e) => { if (dragging) moveTo(e); });
    svg.addEventListener("pointerup", () => { dragging = false; });
    // Que el lienzo no arrastre ni suba de nivel por un clic en el minimapa.
    for (const ev of ["pointerdown", "dblclick", "wheel"]) box.addEventListener(ev, (e) => e.stopPropagation());
    minimap = { box, rect, w, h: hh };
    return box;
  }

  /** Solo se muestra si el diagrama no entra entero en pantalla. */
  function updateMinimap() {
    if (!minimap) return;
    const L = $("lienzo").getBoundingClientRect();
    const t = state.transform;
    const vx = -t.x / t.k;
    const vy = -t.y / t.k;
    const vw = L.width / t.k;
    const vh = L.height / t.k;
    const fits = vx <= 1 && vy <= 1 && vx + vw >= minimap.w - 1 && vy + vh >= minimap.h - 1;
    minimap.box.hidden = state.minimapOff || fits;
    setAttrs(minimap.rect, { x: vx.toFixed(1), y: vy.toFixed(1), width: vw.toFixed(1), height: vh.toFixed(1) });
  }

  // ------------------------------------------------------------------ estilos visuales

  const STYLES = ["moderno", "clasico", "pizarra", "contraste"];
  const STYLE_NAMES = { moderno: "moderno", clasico: "clásico", pizarra: "pizarra", contraste: "alto contraste" };

  function cycleStyle() {
    state.estilo = STYLES[(STYLES.indexOf(state.estilo) + 1) % STYLES.length];
    applyStyle();
    syncHash();
    renderToolbar();
  }

  function applyStyle() {
    const root = document.documentElement;
    if (state.estilo === "moderno") delete root.dataset.estilo;
    else root.dataset.estilo = state.estilo;
  }

  // ------------------------------------------------------------------ teclado

  function installKeys() {
    document.addEventListener("keydown", (e) => {
      const tag = (e.target && e.target.tagName) || "";
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (helpDialog && helpDialog.open) return; // el diálogo maneja Esc solo
      if (mermaidDialog && mermaidDialog.open) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (state.tour && ["Escape", "ArrowRight", "ArrowLeft", " ", "p"].includes(e.key)) {
        e.preventDefault();
        if (e.key === "Escape" || e.key === "p") endTour();
        else if (e.key === " ") { state.tour.auto = !state.tour.auto; state.tour.since = performance.now(); state.tour.endedAt = 0; paintTour(); }
        else showSlide(state.tour.i + (e.key === "ArrowRight" ? 1 : -1));
        return;
      }
      if (state.walk && ["Escape", "ArrowRight", "ArrowLeft", " "].includes(e.key)) {
        e.preventDefault();
        if (e.key === "Escape") stopWalk();
        else if (e.key === " ") walkPlay(!state.walk.playing);
        else if (e.key === "ArrowLeft") { walkPlay(false); walkBack(); }
        else if (state.walk.auto || !walkChoices()) { walkPlay(false); walkStep(); }
        return;
      }
      if (e.key === "p") { startTour(false); return; }
      if (e.key === "r" && state.view === "flujo" && state.id) { walkStart(state.id, false); return; }
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
      else if (e.key === "s") cycleStyle();
      else if (e.key === "n") { state.minimapOff = !state.minimapOff; updateMinimap(); }
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
      window.addEventListener("resize", () => { if (!state.keepTransform) fit(); apply(); });
      render();
    },
    (err) => showEmpty(err && err.message === "navegador-antiguo" ? OLD_BROWSER : "No se pudieron abrir los datos del proyecto."),
  );
})();
