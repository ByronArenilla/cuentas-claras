// Avisos de la app (spec 011, "Estados"): registrado con "Deshacer", errores,
// sin conexión y el diálogo de confirmación. El contenedor `#notices` tiene
// `aria-live`, así que un lector de pantalla los anuncia (RF-33).
import { h } from "../dom.js";

const OFFLINE_TEXT =
  "Sin conexión. Lo que escribiste se queda aquí; podrás guardarlo cuando vuelva la conexión.";

export function createNotices(container) {
  let current = null;
  let timer = null;
  const offlineBar = h("p", { class: "offline", role: "status" }, OFFLINE_TEXT);

  function dismiss() {
    clearTimeout(timer);
    current?.remove();
    current = null;
  }

  return {
    /** Un aviso con acción opcional que se va solo tras `seconds`. */
    show({ text, kind = "info", action = null, seconds = 10 }) {
      dismiss();
      current = h(
        "div",
        { class: kind === "error" ? "notice notice--error" : "notice" },
        h("span", {}, text),
        action &&
          h(
            "button",
            {
              type: "button",
              class: "button button--link",
              onClick: () => {
                dismiss();
                action.onClick();
              },
            },
            action.label,
          ),
      );
      container.append(current);
      if (seconds) timer = setTimeout(dismiss, seconds * 1000);
    },
    dismiss,
    setOffline(offline) {
      if (offline) container.prepend(offlineBar);
      else offlineBar.remove();
    },
  };
}

/** Pide confirmación en un `<dialog>` propio (decisión 23): atrapa el foco y
 * se cierra con Escape sin código extra. Resuelve `true` solo si se confirma. */
export function confirmDialog(dialog, { title, body, confirmLabel, danger = false }) {
  return new Promise((resolve) => {
    const cancel = h(
      "button",
      { type: "button", class: "button button--quiet", onClick: () => dialog.close("cancel") },
      "Cancelar",
    );
    const confirm = h(
      "button",
      {
        type: "button",
        class: danger ? "button button--danger" : "button",
        onClick: () => dialog.close("confirm"),
      },
      confirmLabel,
    );
    dialog.replaceChildren(
      h("h2", { id: "dialog-title" }, title),
      h("p", { class: "muted" }, body),
      h("div", { class: "dialog__actions" }, cancel, confirm),
    );
    dialog.returnValue = "";
    dialog.addEventListener("close", () => resolve(dialog.returnValue === "confirm"), {
      once: true,
    });
    dialog.showModal();
    cancel.focus();
  });
}
