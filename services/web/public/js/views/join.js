// Unirse a un espacio desde un enlace `/unirse/<token>` (spec 011, RF-27,
// decisión 19). Abrir el enlace nunca une a nadie (ADR 0005): muestra el
// espacio y pide un toque explícito.
import { h } from "../dom.js";
import { OFFLINE_SAVE, setBusy } from "./form.js";

const expiry = new Intl.DateTimeFormat("es-CO", { dateStyle: "long", timeStyle: "short" });

export async function renderJoin(main, app, { token }) {
  const wrap = h("section", { class: "auth" });
  main.append(wrap);
  const loggedIn = app.session.isLoggedIn();
  if (!loggedIn) wrap.append(h("p", { class: "wordmark", "aria-hidden": "true" }, "gastito"));

  let preview;
  try {
    preview = await app.api.get(`/invitations/${encodeURIComponent(token)}`);
  } catch (error) {
    wrap.append(
      h("h1", {}, "Este enlace ya no sirve"),
      h("p", { class: "error", role: "alert" }, error.message),
      h("p", { class: "muted" }, "Pídele a quien te invitó un enlace nuevo."),
    );
    return;
  }

  const name = preview.space_name;
  wrap.append(
    h("h1", {}, `Te invitaron a «${name}»`),
    h(
      "p",
      { class: "muted" },
      "Al unirte compartes su presupuesto con los demás miembros. El enlace es de un solo uso.",
    ),
    h("p", { class: "label" }, `Caduca el ${expiry.format(new Date(preview.expires_at))}`),
  );

  if (!loggedIn) {
    // Después de entrar o crear la cuenta, se vuelve a este enlace.
    const remember = () => app.session.setNext(location.pathname);
    wrap.append(
      h("p", {}, "Para unirte, entra o crea tu cuenta."),
      h(
        "div",
        { class: "cluster submit" },
        h("a", { class: "button", href: "/crear-cuenta", onClick: remember }, "Crear cuenta"),
        h("a", { class: "button button--quiet", href: "/entrar", onClick: remember }, "Entrar"),
      ),
    );
    return;
  }

  const status = h("p", { role: "alert", class: "error", hidden: true });
  const join = h(
    "button",
    {
      type: "button",
      class: "button button--block",
      "data-sends": true,
      onClick: async () => {
        status.hidden = true;
        if (!app.connection.online()) {
          status.textContent = OFFLINE_SAVE;
          status.hidden = false;
          return;
        }
        setBusy(join, true, "Uniéndote…");
        try {
          const space = await app.api.post(`/invitations/${encodeURIComponent(token)}/redeem`);
          await app.loadAccount();
          app.useSpace(space);
          app.drafts.clear("record");
          app.drafts.clear("expenses-period");
          app.navigate("/registrar", { replace: true });
          app.notices.show({ text: `Te uniste a «${space.name}».`, seconds: 6 });
        } catch (error) {
          status.textContent = error.message;
          status.hidden = false;
          setBusy(join, false, "Uniéndote…");
        }
      },
    },
    `Unirme a «${name}»`,
  );
  wrap.append(status, h("div", { class: "submit" }, join), h("a", { href: "/registrar" }, "Ahora no"));
}
