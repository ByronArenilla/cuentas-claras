// Pantalla Registrar (spec 011, RF-6 a RF-16): monto, tipo de pago, "Qué
// fue" con los rubros del mes, categoría y fecha. La lógica vive en
// `expense-form.js`; aquí solo se arma el DOM y se llama a la API.
import { h } from "../dom.js";
import {
  afterRecord,
  buildExpense,
  changeDate,
  chooseItem,
  formPeriod,
  missing,
  newForm,
  suggestItems,
  typeDescription,
  usesItems,
} from "../expense-form.js";
import { formatDay, formatNumber, formatPesos, monthName, parseAmount } from "../format.js";
import { OFFLINE_SAVE, clearErrors, field, formError, setBusy, showErrors } from "./form.js";

const DRAFT = "record";

/** Datos del espacio para el formulario: categorías activas y, por mes, los
 * rubros del resumen con el nombre de su categoría. */
function createData(app) {
  const base = `/spaces/${app.space.id}`;
  const itemsByPeriod = new Map();
  const categoryNames = new Map();
  let currentPeriod = null;
  let categories = [];

  async function loadSummary(period) {
    const summary = await app.api.get(`${base}/summary`, period ? { period } : undefined);
    for (const row of summary.categories) categoryNames.set(row.category_id, row.name);
    itemsByPeriod.set(summary.period, summary.budget_items);
    return summary;
  }

  return {
    base,
    get currentPeriod() {
      return currentPeriod;
    },
    get categories() {
      return categories;
    },
    categoryName: (id) => categoryNames.get(id) ?? "",
    async load() {
      const [summary, active] = await Promise.all([
        loadSummary(null),
        app.api.get(`${base}/categories`),
      ]);
      // El mes actual en `TZ` lo dice la API (decisión 12).
      currentPeriod = summary.period;
      categories = active;
      for (const category of active) categoryNames.set(category.id, category.name);
    },
    /** Los rubros de un mes; se piden una vez por mes. */
    async items(period) {
      if (!itemsByPeriod.has(period)) await loadSummary(period);
      return itemsByPeriod.get(period) ?? [];
    },
    /** Vuelve a pedir el mes, para que "lo que queda" esté al día. */
    async refresh(period) {
      await loadSummary(period === currentPeriod ? null : period);
    },
  };
}

function remainingText(item) {
  return item.remaining < 0
    ? `excedido ${formatPesos(-item.remaining)}`
    : `quedan ${formatPesos(item.remaining)}`;
}

export async function renderRecord(main, app) {
  const data = createData(app);
  await data.load();
  let form = app.drafts.get(DRAFT) ?? newForm();
  const save = () => app.drafts.set(DRAFT, form);
  const period = () => formPeriod(form, data.currentPeriod);

  // --- Monto (RF-7) ---
  const amount = h("input", {
    class: "amount__input",
    name: "amount",
    inputmode: "numeric",
    autocomplete: "off",
    enterkeyhint: "next",
    "aria-label": "Monto en pesos",
    placeholder: "0",
    value: form.amount === null ? "" : formatNumber(form.amount),
    onInput: () => {
      form = { ...form, amount: parseAmount(amount.value) };
      amount.value = form.amount === null ? "" : formatNumber(form.amount);
      save();
    },
  });
  const amountField = h(
    "div",
    { dataset: { field: "amount" } },
    h(
      "div",
      { class: "amount" },
      h("span", { class: "amount__currency", "aria-hidden": "true" }, "$"),
      amount,
    ),
    h("p", { class: "row__error", hidden: true }),
  );

  // --- Qué fue y sugerencias de rubros (RF-8) ---
  const what = h("input", {
    class: "input",
    name: "description",
    autocomplete: "off",
    enterkeyhint: "done",
    role: "combobox",
    "aria-autocomplete": "list",
    "aria-controls": "suggestions",
    "aria-expanded": "false",
    value: form.description,
    onInput: () => {
      form = typeDescription(form, what.value);
      save();
      paint();
    },
    onFocus: () => paintSuggestions(true),
  });
  const itemInfo = h("p", { class: "row__hint", id: "item-info", hidden: true });
  const whatRow = field({ id: "record-what", label: "Qué fue", control: what });
  whatRow.append(itemInfo);
  const suggestions = h("ul", { class: "suggestions", id: "suggestions", hidden: true });
  const suggestionsStatus = h("p", { class: "sr-only", "aria-live": "polite" });

  // --- Categoría (gasto sin rubro) ---
  const category = h(
    "select",
    {
      class: "select",
      name: "category_id",
      onChange: () => {
        form = { ...form, categoryId: category.value ? Number(category.value) : null };
        save();
      },
    },
    h("option", { value: "" }, "Elige la categoría"),
    data.categories.map((item) => h("option", { value: item.id }, item.name)),
  );
  const categoryRow = field({ id: "record-category", label: "Categoría", control: category });

  // --- Fecha (RF-13): "Hoy" no se envía (decisión 12) ---
  const dateLabel = h("span", {});
  const dateInput = h("input", {
    class: "input",
    type: "date",
    name: "spent_on",
    hidden: true,
    // Solo una ayuda: la regla de no aceptar fechas futuras es de la API.
    max: new Date().toLocaleDateString("en-CA"),
    onChange: async () => {
      form = changeDate(form, dateInput.value || null, data.currentPeriod);
      save();
      await data.items(period());
      paint();
    },
  });
  const dateToggle = h("button", {
    type: "button",
    class: "button button--link",
    onClick: async () => {
      if (form.date) {
        form = changeDate(form, null, data.currentPeriod);
        dateInput.value = "";
        save();
        paint();
      } else {
        dateInput.hidden = false;
        dateLabel.hidden = true;
        dateInput.focus();
        dateInput.showPicker?.();
      }
    },
  });
  const dateRow = h(
    "div",
    { class: "row", dataset: { field: "spent_on" } },
    h("label", { class: "label", for: "record-date" }, "Fecha"),
    h("div", { class: "cluster" }, dateLabel, dateInput, dateToggle),
    h("p", { class: "row__error", hidden: true }),
  );
  dateInput.id = "record-date";

  // --- Enviar ---
  const errors = formError();
  const submit = h(
    "button",
    { class: "button button--block", type: "submit", "data-sends": true },
    "Registrar gasto",
  );

  const formElement = h(
    "form",
    { class: "screen record", novalidate: true, onSubmit: (event) => record(event) },
    h("h1", { class: "sr-only" }, "Registrar un gasto"),
    errors,
    amountField,
    h("div", { class: "rows" }, whatRow, suggestionsStatus),
    suggestions,
    h("div", { class: "rows" }, categoryRow, dateRow),
    h("div", { class: "submit" }, submit),
  );

  async function paintSuggestions(open) {
    if (!usesItems(form)) {
      suggestions.hidden = true;
      what.setAttribute("aria-expanded", "false");
      return;
    }
    const items = suggestItems(await data.items(period()), form.description);
    const show = open !== false && form.itemId === null && items.length > 0;
    suggestions.replaceChildren(
      ...items.map((item) =>
        h(
          "li",
          {},
          h(
            "button",
            {
              type: "button",
              onClick: () => {
                form = chooseItem(form, item, period());
                what.value = form.description;
                save();
                paint();
                dateToggle.focus();
              },
            },
            h("b", {}, item.name),
            h("span", { class: item.remaining < 0 ? "figure over" : "figure" }, remainingText(item)),
            h(
              "small",
              {},
              `${data.categoryName(item.category_id)} · planeado ${formatPesos(item.planned)}`,
            ),
          ),
        ),
      ),
    );
    suggestions.hidden = !show;
    what.setAttribute("aria-expanded", String(show));
    suggestionsStatus.textContent = show
      ? `${items.length} ${items.length === 1 ? "rubro" : "rubros"} de ${monthName(period())}`
      : "";
  }

  async function paint() {
    app.setMonth(period());
    const items = await data.items(period());
    const item = items.find((candidate) => candidate.id === form.itemId);
    itemInfo.hidden = !item;
    if (item) {
      itemInfo.textContent = `Rubro de ${monthName(period())} · ${data.categoryName(item.category_id)} · ${remainingText(item)}`;
    }
    categoryRow.hidden = form.itemId !== null || !usesItems(form);
    category.value = form.categoryId === null ? "" : String(form.categoryId);
    dateLabel.textContent = form.date ? formatDay(form.date) : "Hoy";
    dateLabel.hidden = false;
    dateInput.hidden = true;
    dateToggle.textContent = form.date ? "Volver a hoy" : "Cambiar fecha";
    await paintSuggestions(document.activeElement === what);
  }

  async function record(event) {
    event.preventDefault();
    clearErrors(formElement);
    if (!app.connection.online()) return showErrors(formElement, { message: OFFLINE_SAVE });
    const lacks = missing(form);
    if (lacks.length) return showErrors(formElement, { message: lacks.join(" ") });

    setBusy(submit, true, "Registrando…");
    try {
      const expense = await app.api.post(`${data.base}/expenses`, buildExpense(form));
      const name = form.description.trim() || data.categoryName(expense.category_id);
      announce(app, data, expense, name);
      const recordedPeriod = period();
      form = afterRecord(form);
      save();
      amount.value = "";
      what.value = "";
      await data.refresh(recordedPeriod);
      await paint();
      amount.focus();
    } catch (error) {
      showErrors(formElement, error);
    } finally {
      setBusy(submit, false, "Registrando…");
    }
  }

  main.append(formElement);
  await paint();
  amount.focus();
}

/** "Registrado: Mercado · $ 52.000" con "Deshacer" durante 10 segundos
 * (decisión 13). Pulsar "Deshacer" es la confirmación del borrado. */
function announce(app, data, expense, name) {
  app.notices.show({
    text: `Registrado: ${name} · ${formatPesos(expense.amount)}`,
    seconds: 10,
    action: {
      label: "Deshacer",
      onClick: async () => {
        try {
          await app.api.del(`${data.base}/expenses/${expense.id}`, { confirm: "true" });
          app.notices.show({ text: `Borrado: ${name}.`, seconds: 6 });
        } catch (error) {
          app.notices.show({ text: error.message, kind: "error", seconds: 0 });
        }
      },
    },
  });
}

export async function renderEdit(main) {
  main.append(h("p", { class: "screen muted" }, "Editar un gasto llega en T9."));
}
