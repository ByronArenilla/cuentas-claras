// Pestaña Espacio (spec 011): la cuenta con cerrar sesión (decisión 22). Los
// espacios, compartir, salir y la guía para fijar la app llegan en T10 y T11.
import { logOut } from "../account.js";
import { h } from "../dom.js";

function accountSection(app) {
  const button = h(
    "button",
    {
      type: "button",
      class: "button button--quiet",
      onClick: async () => {
        button.disabled = true;
        const notice = await logOut(app).catch((error) => error.message);
        app.me = null;
        app.navigate("/entrar", { replace: true });
        if (notice) app.notices.show({ text: notice, seconds: 0 });
      },
    },
    "Cerrar sesión",
  );
  return h(
    "section",
    { class: "stack", "aria-labelledby": "account-title" },
    h("h2", { id: "account-title" }, "Tu cuenta"),
    h("p", { class: "muted" }, app.me.email),
    h("div", {}, button),
  );
}

export function renderSpace(main, app) {
  main.append(h("div", { class: "screen" }, h("h1", {}, "Espacio"), accountSection(app)));
}
