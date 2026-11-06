// Pestaña Espacio (spec 011, RF-23 a RF-26, RF-29): el espacio actual y cómo
// cambiarlo, compartirlo, crear otro, salir de uno compartido, la cuenta con
// cerrar sesión (decisión 22) y la guía para fijar la app (T11).
import { logOut } from "../account.js";
import { h } from "../dom.js";
import { createSpace, leaveSpace, shareInvitation } from "../spaces.js";
import { OFFLINE_SAVE, field, formError, setBusy, showErrors } from "./form.js";

/** Al cambiar de espacio, lo escrito en Registrar y el mes de Gastos eran del
 * espacio anterior. */
function switchTo(app, space, message) {
  app.useSpace(space);
  app.drafts.clear("record");
  app.drafts.clear("expenses-period");
  app.navigate("/espacio", { replace: true });
  if (message) app.notices.show({ text: message, seconds: 6 });
}

function currentSection(app) {
  const others = app.spaces.filter((space) => space.id !== app.space.id);
  return h(
    "section",
    { class: "stack", "aria-labelledby": "space-title" },
    h("p", { class: "label" }, "Espacio actual"),
    h("h2", { id: "space-title" }, app.space.name),
    others.length > 0 &&
      h(
        "div",
        { class: "rows" },
        others.map((space) =>
          h(
            "div",
            { class: "row" },
            h("span", { class: "label" }, "Otro"),
            h(
              "button",
              {
                type: "button",
                class: "button button--link",
                onClick: () => switchTo(app, space, `Ahora estás en «${space.name}».`),
              },
              `Pasar a «${space.name}»`,
            ),
          ),
        ),
      ),
  );
}

function shareSection(app) {
  const status = h("p", { class: "muted", "aria-live": "polite" });
  const manual = h("input", { class: "input", readonly: true, hidden: true, "aria-label": "Enlace de invitación" });
  const button = h(
    "button",
    {
      type: "button",
      class: "button",
      "data-sends": true,
      onClick: async () => {
        if (!app.connection.online()) {
          status.textContent = OFFLINE_SAVE;
          return;
        }
        setBusy(button, true, "Preparando el enlace…");
        try {
          const { how, url } = await shareInvitation(app, app.space, {
            share: navigator.share ? (data) => navigator.share(data) : null,
            copy: (text) => navigator.clipboard.writeText(text),
          });
          manual.hidden = how !== "manual";
          manual.value = url;
          status.textContent = {
            shared: "Enlace compartido. Es de un solo uso y caduca en 24 horas.",
            copied: "Enlace copiado. Pégalo en un mensaje: es de un solo uso y caduca en 24 horas.",
            cancelled: "No se compartió. El enlace que se preparó caduca solo en 24 horas.",
            manual: "Copia este enlace y envíalo: es de un solo uso y caduca en 24 horas.",
          }[how];
          if (how === "manual") manual.select();
        } catch (error) {
          status.textContent = error.message;
        } finally {
          setBusy(button, false, "Preparando el enlace…");
        }
      },
    },
    `Compartir «${app.space.name}»`,
  );
  return h(
    "section",
    { class: "stack", "aria-labelledby": "share-title" },
    h("h2", { id: "share-title" }, "Compartir"),
    h(
      "p",
      { class: "muted" },
      "Quien abra el enlace verá el nombre del espacio y podrá unirse con su cuenta. Los miembros comparten el presupuesto.",
    ),
    h("div", {}, button),
    manual,
    status,
  );
}

function createSection(app) {
  const name = h("input", { class: "input", name: "name", autocomplete: "off", maxlength: 100 });
  const submit = h("button", { class: "button button--quiet", type: "submit", "data-sends": true }, "Crear espacio");
  const form = h(
    "form",
    {
      class: "stack",
      novalidate: true,
      onSubmit: async (event) => {
        event.preventDefault();
        if (!app.connection.online()) return showErrors(form, { message: OFFLINE_SAVE });
        setBusy(submit, true, "Creando…");
        try {
          const space = await createSpace(app, name.value.trim());
          app.spaces = [...app.spaces, space];
          switchTo(app, space, `Creaste «${space.name}» y ahora estás en él.`);
        } catch (error) {
          showErrors(form, error);
          setBusy(submit, false, "Creando…");
        }
      },
    },
    h("h2", {}, "Crear otro espacio"),
    h("p", { class: "muted" }, "Para un presupuesto aparte: un viaje, la casa de alguien más."),
    formError(),
    h("div", { class: "rows" }, field({ id: "space-name-input", label: "Nombre", control: name })),
    h("div", {}, submit),
  );
  return form;
}

function leaveSection(app) {
  const button = h(
    "button",
    {
      type: "button",
      class: "button button--danger",
      "data-sends": true,
      onClick: async () => {
        const space = app.space;
        const confirmed = await app.confirm({
          title: `¿Salir de «${space.name}»?`,
          body: "Lo que registraste se queda en el espacio. Para volver, alguien tendrá que compartirte un enlace nuevo.",
          confirmLabel: `Salir de «${space.name}»`,
          danger: true,
        });
        if (!confirmed) return;
        try {
          const next = await leaveSpace(app, space, app.spaces);
          app.spaces = app.spaces.filter((candidate) => candidate.id !== space.id);
          switchTo(app, next, `Saliste de «${space.name}». Ahora estás en «${next.name}».`);
        } catch (error) {
          app.notices.show({ text: error.message, kind: "error", seconds: 0 });
        }
      },
    },
    `Salir de «${app.space.name}»`,
  );
  return h(
    "section",
    { class: "stack", "aria-labelledby": "leave-title" },
    h("h2", { id: "leave-title" }, "Salir del espacio"),
    h("div", {}, button),
  );
}

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
        app.drafts.clear("record");
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

export async function renderSpace(main, app) {
  // La lista de espacios puede haber cambiado en otro dispositivo.
  await app.loadAccount();
  main.append(
    h(
      "div",
      { class: "screen spaced" },
      h("h1", { class: "sr-only" }, "Espacio"),
      currentSection(app),
      shareSection(app),
      createSection(app),
      app.spaces.length > 1 && leaveSection(app),
      accountSection(app),
    ),
  );
}
