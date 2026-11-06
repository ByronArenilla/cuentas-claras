// Piezas de formulario compartidas (spec 011): renglón con rótulo, errores por
// campo y botón ocupado. Cada control tiene su <label> (RF-33) y los errores
// de la API se muestran junto a su campo (decisión 14).
import { h } from "../dom.js";

/** Un renglón: rótulo a la izquierda (o arriba en las pantallas de entrar),
 * el control y el lugar de su error. `name` es el campo de la API. */
export function field({ id, label, control, hint = null, block = false }) {
  control.id = id;
  const error = h("p", { class: "row__error", id: `${id}-error`, hidden: true });
  const describedBy = [hint && `${id}-hint`, `${id}-error`].filter(Boolean).join(" ");
  control.setAttribute("aria-describedby", describedBy);
  return h(
    "div",
    { class: block ? "row row--block" : "row", dataset: { field: control.name || id } },
    h("label", { class: "label", for: id }, label),
    control,
    hint && h("p", { class: "row__hint", id: `${id}-hint` }, hint),
    error,
  );
}

/** Caja de error general del formulario, arriba (`role="alert"`). */
export function formError() {
  return h("p", { class: "error", role: "alert", hidden: true });
}

export function clearErrors(form) {
  for (const control of form.querySelectorAll("[aria-invalid]")) {
    control.removeAttribute("aria-invalid");
  }
  for (const message of form.querySelectorAll(".row__error, .error")) {
    message.hidden = true;
    message.textContent = "";
  }
}

/** Reparte un `ApiError` por campo; lo que no tiene campo va arriba. Lleva el
 * foco al primer campo con error. */
export function showErrors(form, error) {
  clearErrors(form);
  const fields = error.fields ?? {};
  const general = [];
  let first = null;
  for (const [name, message] of Object.entries(fields)) {
    const row = form.querySelector(`[data-field="${CSS.escape(name)}"]`);
    if (!row) {
      general.push(message);
      continue;
    }
    const control = row.querySelector("input, select, textarea, button");
    control?.setAttribute("aria-invalid", "true");
    const box = row.querySelector(".row__error");
    box.textContent = message;
    box.hidden = false;
    first ??= control;
  }
  if (!Object.keys(fields).length) general.push(error.message);
  const box = form.querySelector(".error");
  if (box && general.length) {
    box.textContent = general.join(" ");
    box.hidden = false;
  }
  (first ?? box)?.focus?.();
}

/** Deshabilita el botón mientras se envía, para que dos toques no envíen dos
 * veces (RF-16). */
export function setBusy(button, busy, busyLabel) {
  button.disabled = busy;
  if (busyLabel) {
    button.dataset.label ??= button.textContent;
    button.textContent = busy ? busyLabel : button.dataset.label;
  }
}

// La explicación larga está en la franja de "Sin conexión" (notices.js); aquí
// basta decir que no se guardó.
export const OFFLINE_SAVE = "Sin conexión: todavía no se puede guardar.";
