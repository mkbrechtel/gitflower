/* gitflower web components: htmx-like fragment navigation + interactive
   graph, in vanilla JS. Fragments arrive as <gf-view> elements carrying a
   declarative shadow root, so their styles are scoped by the browser; this
   file only adds behavior on top. Everything degrades: without JS the same
   URLs serve full pages with real links. */

const main = () => document.getElementById("gf-main");

/* ---------------------------------------------------------- SPA nav */

async function loadFragment(url, push) {
  const target = main();
  if (!target) { location.href = url; return; }
  target.classList.add("gf-loading");
  let response;
  try {
    response = await fetch(url, { headers: { "GF-Fragment": "1" } });
  } catch {
    location.href = url; return;
  }
  if (!response.ok && response.status !== 404) { location.href = url; return; }
  const html = await response.text();
  const swap = () => {
    target.setHTMLUnsafe(html); // parses declarative shadow DOM
    target.classList.remove("gf-loading");
    enhance(target);
    if (push) history.pushState({}, "", url);
    window.scrollTo(0, 0);
  };
  if (document.startViewTransition) document.startViewTransition(swap);
  else swap();
}

function internalLink(event) {
  if (event.defaultPrevented || event.button !== 0) return null;
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return null;
  const anchor = event.composedPath().find((el) => el.tagName === "A");
  if (!anchor || anchor.target || anchor.hasAttribute("download")) return null;
  const href = anchor.getAttribute("href");
  if (!href || !href.startsWith("/")) return null;
  if (href.startsWith("/static/") || href.startsWith("/api")) return null;
  if (href.includes("format=raw")) return null;
  return href;
}

document.addEventListener("click", (event) => {
  const href = internalLink(event);
  if (href === null) return;
  event.preventDefault();
  loadFragment(href, true);
});

window.addEventListener("popstate", () => {
  loadFragment(location.pathname + location.search, false);
});

/* ------------------------------------------------ graph interaction */

/* Hovering a commit row highlights its lane's paths in the SVG. Rows carry
   data-lane, edges data-lanes="0 1"; both live inside the view's shadow
   root, which is open — enhance() wires them after every load. */
function enhanceGraph(root) {
  for (const graphBox of root.querySelectorAll(".graph")) {
    const svg = graphBox.querySelector(".graph-svg");
    if (!svg) continue;
    const paths = [...svg.querySelectorAll("path[data-lanes]")];
    for (const row of graphBox.querySelectorAll(".graph-row")) {
      const lane = row.dataset.lane;
      row.addEventListener("mouseenter", () => {
        svg.classList.add("focused");
        for (const path of paths) {
          const lanes = path.dataset.lanes.split(" ");
          path.classList.toggle("hot", lanes.includes(lane));
        }
      });
      row.addEventListener("mouseleave", () => {
        svg.classList.remove("focused");
        for (const path of paths) path.classList.remove("hot");
      });
    }
  }
}

function enhance(container) {
  for (const viewEl of container.querySelectorAll("gf-view")) {
    if (viewEl.shadowRoot) enhanceGraph(viewEl.shadowRoot);
  }
}

/* <gf-view> needs no class of its own — the declarative shadow root does the
   scoping — but registering it makes the element inspectable and future-
   proofs upgrades. */
customElements.define("gf-view", class extends HTMLElement {});

enhance(document);
