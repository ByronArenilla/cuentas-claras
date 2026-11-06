// Entrar y crear cuenta (spec 011, RF-1 y RF-2). Se entra una sola vez: la
// sesión se renueva sola con el uso (decisión 9).
import { logIn, signUp } from "../account.js";
import { h } from "../dom.js";
import { OFFLINE_SAVE, field, formError, setBusy, showErrors } from "./form.js";

function credentials({ newPassword }) {
  const email = h("input", {
    class: "input",
    name: "email",
    type: "email",
    autocomplete: "username",
    inputmode: "email",
    autocapitalize: "none",
    spellcheck: "false",
    required: true,
  });
  const password = h("input", {
    class: "input",
    name: "password",
    type: "password",
    autocomplete: newPassword ? "new-password" : "current-password",
    required: true,
  });
  return { email, password };
}

function screen({ title, form, footer, message }) {
  return h(
    "section",
    { class: "auth" },
    h("p", { class: "wordmark", "aria-hidden": "true" }, "gastito"),
    h("h1", {}, title),
    message && h("p", { class: "error", role: "alert" }, message),
    form,
    footer,
  );
}

function authForm(app, { submitLabel, busyLabel, controls, rows, action }) {
  const submit = h(
    "button",
    { class: "button button--block", type: "submit", "data-sends": true },
    submitLabel,
  );
  const errors = formError();
  const form = h(
    "form",
    {
      class: "stack",
      novalidate: true,
      onSubmit: async (event) => {
        event.preventDefault();
        if (!app.connection.online()) {
          return showErrors(form, { message: OFFLINE_SAVE });
        }
        setBusy(submit, true, busyLabel);
        try {
          const destination = await action({
            email: controls.email.value,
            password: controls.password.value,
          });
          app.me = null;
          app.navigate(destination, { replace: true });
        } catch (error) {
          showErrors(form, error);
          setBusy(submit, false, busyLabel);
        }
      },
    },
    errors,
    h("div", { class: "rows" }, rows),
    h("div", { class: "submit" }, submit),
  );
  return form;
}

export function renderLogin(main, app) {
  // El aviso de una sesión que caducó o se cerró en otro lado (RF-3).
  const message = app.drafts.get("auth-message");
  app.drafts.clear("auth-message");
  const controls = credentials({ newPassword: false });
  const form = authForm(app, {
    submitLabel: "Entrar",
    busyLabel: "Entrando…",
    controls,
    rows: [
      field({ id: "login-email", label: "Correo", control: controls.email, block: true }),
      field({ id: "login-password", label: "Contraseña", control: controls.password, block: true }),
    ],
    action: (values) => logIn(app, values),
  });
  main.append(
    screen({
      title: "Entrar",
      message,
      form,
      footer: h(
        "p",
        { class: "muted" },
        "¿No tienes cuenta? ",
        h("a", { href: "/crear-cuenta" }, "Crear cuenta"),
      ),
    }),
  );
  controls.email.focus();
}

export function renderRegister(main, app) {
  const controls = credentials({ newPassword: true });
  const form = authForm(app, {
    submitLabel: "Crear cuenta",
    busyLabel: "Creando…",
    controls,
    rows: [
      field({ id: "register-email", label: "Correo", control: controls.email, block: true }),
      field({
        id: "register-password",
        label: "Contraseña",
        control: controls.password,
        hint: "Al menos 12 caracteres. Una frase que recuerdes sirve.",
        block: true,
      }),
    ],
    action: (values) => signUp(app, values),
  });
  main.append(
    screen({
      title: "Crear cuenta",
      form,
      footer: h("p", { class: "muted" }, "¿Ya tienes cuenta? ", h("a", { href: "/entrar" }, "Entrar")),
    }),
  );
  controls.email.focus();
}
