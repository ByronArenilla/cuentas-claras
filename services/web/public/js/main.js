// Arranque de la web (spec 011): sesión, cliente de la API, rutas,
// navegación y avisos. Las pantallas viven en `views/` y reciben `app`, el
// contexto compartido.
import { API_URL } from "/config.js";
import { createApi } from "./api.js";
import { h } from "./dom.js";
import { formatMonthShort } from "./format.js";
import { createConnection } from "./offline.js";
import { matchRoute } from "./routes.js";
import { createSession } from "./session.js";
import { createDrafts } from "./state.js";
import { confirmDialog, createNotices } from "./views/notices.js";

// Cada pantalla se carga cuando se visita (módulos ES, sin compilar).
const VIEWS = {
  login: () => import("./views/auth.js").then((module) => module.renderLogin),
  register: () => import("./views/auth.js").then((module) => module.renderRegister),
  record: () => import("./views/record.js").then((module) => module.renderRecord),
  edit: () => import("./views/record.js").then((module) => module.renderEdit),
  expenses: () => import("./views/expenses.js").then((module) => module.renderExpenses),
  space: () => import("./views/space.js").then((module) => module.renderSpace),
  join: () => import("./views/join.js").then((module) => module.renderJoin),
};

// Qué sección de la navegación marca cada pantalla.
const SECTIONS = { record: "record", edit: "expenses", expenses: "expenses", space: "space" };

const shell = document.getElementById("app");
const main = document.getElementById("main");
const spaceName = document.getElementById("space-name");
const monthLabel = document.getElementById("current-month");
const dialog = document.getElementById("dialog");

const session = createSession({ local: window.localStorage, temporary: window.sessionStorage });
const connection = createConnection(window);
const notices = createNotices(document.getElementById("notices"));
const drafts = createDrafts();
let renderCount = 0;

const api = createApi({
  baseUrl: API_URL,
  fetch: (...args) => window.fetch(...args),
  token: () => session.token(),
  onNetwork: (online) => connection.report(online),
  // La sesión caducó o se cerró en otro lado (RF-3, decisión 16): se pide
  // entrar de nuevo y después se vuelve a esta misma pantalla.
  onUnauthorized: (message) => {
    // Sin sesión guardada (unas credenciales malas al entrar), el 401 es solo
    // un error del formulario.
    if (!session.isLoggedIn()) return;
    session.clear();
    app.me = null;
    session.setNext(location.pathname);
    drafts.set("auth-message", message);
    navigate("/entrar", { replace: true });
  },
});

/** El contexto que reciben todas las pantallas. */
const app = {
  api,
  session,
  connection,
  drafts,
  notices,
  me: null,
  spaces: [],
  space: null,
  navigate,
  confirm: (options) => confirmDialog(dialog, options),
  /** Usuario, espacios y espacio actual (RF-23, decisión 17). */
  async loadAccount() {
    const [me, spaces] = await Promise.all([api.get("/me"), api.get("/spaces")]);
    app.me = me;
    app.spaces = spaces;
    app.space = session.chooseSpace(spaces);
    spaceName.textContent = app.space?.name ?? "";
  },
  /** Pasa a otro espacio y lo recuerda en el dispositivo. */
  useSpace(space) {
    session.setSpace(space.id);
    app.space = space;
    spaceName.textContent = space.name;
  },
  /** El mes que muestra el encabezado (`AAAA-MM`). */
  setMonth(period) {
    monthLabel.textContent = period ? formatMonthShort(period) : "";
  },
  /** Vuelve a marcar lo que envía datos según la conexión. */
  refreshSending,
};

function refreshSending() {
  const offline = !connection.online();
  document.body.toggleAttribute("data-offline", offline);
  for (const element of document.querySelectorAll("[data-sends]")) {
    element.setAttribute("aria-disabled", String(offline));
  }
}

function navigate(path, { replace = false } = {}) {
  if (replace) history.replaceState(null, "", path);
  else history.pushState(null, "", path);
  render();
}

function markSection(view) {
  const section = SECTIONS[view];
  for (const link of document.querySelectorAll(".tabs a")) {
    if (link.dataset.section === section) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
}

async function render() {
  const count = ++renderCount;
  const route = matchRoute(location.pathname);
  if (route.redirect) return navigate(route.redirect, { replace: true });

  const loggedIn = session.isLoggedIn();
  if (route.access === "member" && !loggedIn) {
    session.setNext(location.pathname);
    return navigate("/entrar", { replace: true });
  }
  if (route.access === "guest" && loggedIn) {
    return navigate(session.takeNext() ?? "/registrar", { replace: true });
  }

  const member = loggedIn && route.access !== "guest";
  shell.toggleAttribute("data-guest", !member);
  markSection(route.view);
  app.setMonth(null);
  main.replaceChildren(h("div", { class: "loading", "aria-hidden": "true" }));

  try {
    if (member && !app.me) await app.loadAccount();
    const view = await VIEWS[route.view]();
    if (count !== renderCount) return;
    main.replaceChildren();
    await view(main, app, route.params);
  } catch (error) {
    if (count !== renderCount || error.status === 401) return;
    main.replaceChildren(
      h(
        "div",
        { class: "screen" },
        h("p", { class: "error", role: "alert" }, error.message ?? "Algo salió mal."),
        h("button", { type: "button", class: "button button--quiet", onClick: render }, "Reintentar"),
      ),
    );
  }
  refreshSending();
  // Lleva el foco a la pantalla nueva si la vista no lo puso en un campo.
  if (!main.contains(document.activeElement)) main.focus({ preventScroll: true });
}

// Los enlaces internos cambian de pantalla sin recargar la página.
document.addEventListener("click", (event) => {
  const link = event.target.closest("a[href]");
  if (
    !link ||
    event.defaultPrevented ||
    event.button !== 0 ||
    event.metaKey ||
    event.ctrlKey ||
    event.shiftKey ||
    link.target ||
    link.hasAttribute("download") ||
    link.origin !== location.origin
  ) {
    return;
  }
  event.preventDefault();
  if (link.pathname !== location.pathname) navigate(link.pathname);
});

window.addEventListener("popstate", render);

connection.subscribe((online) => {
  notices.setOffline(!online);
  refreshSending();
});
notices.setOffline(!connection.online());

render();
