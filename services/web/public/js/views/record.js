// Pantalla Registrar (spec 011, RF-6 a RF-16): monto, tipo de pago, tarjeta y
// cuotas, "¿Estaba en el plan?", "Qué fue" con los rubros del mes, categoría
// y fecha. La lógica vive en `expense-form.js`; aquí solo se arma el DOM y se
// llama a la API.
import { h } from "../dom.js";
import {
  QUICK_INSTALLMENTS,
  afterRecord,
  buildChanges,
  buildExpense,
  changeDate,
  chooseItem,
  formFromExpense,
  formPeriod,
  kindOf,
  lockFor,
  missing,
  newForm,
  parseInstallments,
  simulationRequest,
  simulationSummary,
  suggestItems,
  typeDescription,
  usesItems,
} from "../expense-form.js";
import {
  formatDay,
  formatNumber,
  formatPesos,
  monthName,
  parseAmount,
  periodOf,
} from "../format.js";
import { OFFLINE_SAVE, clearErrors, field, formError, setBusy, showErrors } from "./form.js";

const DRAFT = "record";

/** Datos del espacio para el formulario: categorías y tarjetas activas y, por
 * mes, los rubros del resumen con el nombre de su categoría. */
export function createData(app) {
  const base = `/spaces/${app.space.id}`;
  const itemsByPeriod = new Map();
  const categoryNames = new Map();
  let currentPeriod = null;
  let categories = [];
  let cards = [];

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
    get cards() {
      return cards;
    },
    categoryName: (id) => categoryNames.get(id) ?? "",
    async load() {
      const [summary, activeCategories, activeCards] = await Promise.all([
        loadSummary(null),
        app.api.get(`${base}/categories`),
        app.api.get(`${base}/cards`),
      ]);
      // El mes actual en `TZ` lo dice la API (decisión 12).
      currentPeriod = summary.period;
      categories = activeCategories;
      cards = activeCards;
      for (const category of activeCategories) categoryNames.set(category.id, category.name);
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

/** Botones de una sola elección (`aria-pressed`). */
function choice(options, { full = false, label, onPick }) {
  const buttons = options.map(({ value, text }) =>
    h("button", { type: "button", "aria-pressed": "false", onClick: () => onPick(value) }, text),
  );
  const group = h(
    "div",
    { class: full ? "seg seg--full" : "seg", role: "group", "aria-label": label },
    buttons,
  );
  return {
    element: group,
    buttons,
    select(value) {
      options.forEach(({ value: option }, index) => {
        buttons[index].setAttribute("aria-pressed", String(option === value));
      });
    },
  };
}

/**
 * Arma el formulario. `mode` es "new" (Registrar) o "edit" (T9). Devuelve el
 * elemento y las funciones que usa la edición.
 */
export async function buildRecordForm(app, data, { initial, onSubmit, submitLabel, busyLabel, locked = null }) {
  let form = initial;
  const isLocked = (name) => locked?.fields.has(name) ?? false;
  const period = () => formPeriod(form, data.currentPeriod);
  let simulationTimer = null;
  let simulationCount = 0;

  // --- Monto (RF-7) ---
  const amount = h("input", {
    class: "amount__input",
    name: "amount",
    inputmode: "numeric",
    autocomplete: "off",
    enterkeyhint: "next",
    "aria-label": "Monto en pesos",
    placeholder: "0",
    disabled: isLocked("amount"),
    value: form.amount === null ? "" : formatNumber(form.amount),
    onInput: () => {
      update({ amount: parseAmount(amount.value) });
      amount.value = form.amount === null ? "" : formatNumber(form.amount);
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

  // --- Tipo de pago ---
  const payment = choice(
    [
      { value: "debit", text: "Débito" },
      { value: "credit", text: "Crédito" },
    ],
    {
      label: "Tipo de pago",
      onPick: (paymentType) => {
        const cardId = form.cardId ?? data.cards[0]?.id ?? null;
        update({ paymentType, cardId: paymentType === "credit" ? cardId : form.cardId });
      },
    },
  );
  const paymentRow = h(
    "div",
    { class: "row", dataset: { field: "payment_type" } },
    h("span", { class: "label" }, "Pago"),
    payment.element,
    h("p", { class: "row__error", hidden: true }),
  );

  // --- Tarjeta y cuotas (RF-10, RF-12) ---
  const card = h(
    "select",
    {
      class: "select",
      name: "card_id",
      onChange: () => update({ cardId: card.value ? Number(card.value) : null }),
    },
    data.cards.map((item) => h("option", { value: item.id }, `${item.name} · corte ${item.cutoff_day}`)),
  );
  const cardRow = field({ id: "record-card", label: "Tarjeta", control: card });
  const noCards = h(
    "p",
    { class: "row row--block muted" },
    "Este espacio todavía no tiene tarjetas. Por ahora se crean con la API (README, «Tarjetas»).",
  );

  const otherInstallments = h("input", {
    name: "installments",
    inputmode: "numeric",
    autocomplete: "off",
    placeholder: "otra",
    "aria-label": "Otra cantidad de cuotas, de 1 a 48",
    onInput: () => update({ installments: parseInstallments(otherInstallments.value) }),
  });
  const quick = QUICK_INSTALLMENTS.map((count) =>
    h(
      "button",
      {
        type: "button",
        "aria-pressed": "false",
        "aria-label": `${count} ${count === 1 ? "cuota" : "cuotas"}`,
        onClick: () => {
          otherInstallments.value = "";
          update({ installments: count });
        },
      },
      String(count),
    ),
  );
  const installmentsRow = h(
    "div",
    { class: "row", dataset: { field: "installments" } },
    h("span", { class: "label", id: "installments-label" }, "Cuotas"),
    h(
      "div",
      { class: "chips", role: "group", "aria-labelledby": "installments-label" },
      quick,
      otherInstallments,
    ),
    h("p", { class: "row__error", hidden: true }),
  );

  // --- ¿Estaba en el plan? (decisión 26): las dos respuestas a la vista ---
  const plan = choice(
    [
      { value: true, text: "Sí, es del mes" },
      { value: false, text: "No, es una deuda" },
    ],
    { full: true, label: "¿Estaba en el plan de este mes?", onPick: (inPlan) => update({ inPlan }) },
  );
  const planRow = h(
    "div",
    { class: "row row--block", dataset: { field: "is_debt" } },
    h("span", { class: "label" }, "¿Estaba en el plan de este mes?"),
    plan.element,
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
    onInput: () => update(typeDescription(form, what.value)),
    onFocus: () => paintSuggestions(true),
  });
  const itemInfo = h("p", { class: "row__hint", id: "item-info", hidden: true });
  const whatRow = field({ id: "record-what", label: "Qué fue", control: what });
  whatRow.append(itemInfo);
  const suggestions = h("ul", { class: "suggestions", id: "suggestions", hidden: true });
  const suggestionsStatus = h("p", { class: "sr-only", "aria-live": "polite" });

  // --- Categoría ---
  const category = h(
    "select",
    {
      class: "select",
      name: "category_id",
      onChange: () => update({ categoryId: category.value ? Number(category.value) : null }),
    },
    h("option", { value: "" }, "Elige la categoría"),
    data.categories.map((item) => h("option", { value: item.id }, item.name)),
  );
  const categoryRow = field({ id: "record-category", label: "Categoría", control: category });

  // --- Fecha (RF-13): "Hoy" no se envía (decisión 12) ---
  const dateLabel = h("span", {});
  const dateInput = h("input", {
    class: "input",
    id: "record-date",
    type: "date",
    name: "spent_on",
    hidden: true,
    // Solo una ayuda: la regla de no aceptar fechas futuras es de la API.
    max: new Date().toLocaleDateString("en-CA"),
    onChange: () => update(changeDate(form, dateInput.value || null, data.currentPeriod)),
  });
  const dateToggle = h("button", {
    type: "button",
    class: "button button--link",
    onClick: () => {
      if (form.date) {
        dateInput.value = "";
        update(changeDate(form, null, data.currentPeriod));
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

  // --- Mes de pago y cuotas antes de guardar (RF-11) ---
  const simulation = h("p", { class: "note", "aria-live": "polite", hidden: true });

  // --- Enviar ---
  const errors = formError();
  const submit = h("button", { class: "button button--block", type: "submit", "data-sends": true }, submitLabel);
  const lockNote = locked && h("p", { class: "error" }, locked.reason);

  const element = h(
    "form",
    {
      class: "screen record",
      novalidate: true,
      onSubmit: async (event) => {
        event.preventDefault();
        clearErrors(element);
        if (!app.connection.online()) return showErrors(element, { message: OFFLINE_SAVE });
        const lacks = missing(form, { hasCards: data.cards.length > 0 });
        if (lacks.length) return showErrors(element, { message: lacks.join(" ") });
        setBusy(submit, true, busyLabel);
        try {
          await onSubmit(form, controller);
        } catch (error) {
          showErrors(element, error);
        } finally {
          setBusy(submit, false, busyLabel);
        }
      },
    },
    errors,
    lockNote,
    amountField,
    h("div", { class: "rows" }, paymentRow, cardRow, noCards, installmentsRow, planRow, whatRow, suggestionsStatus),
    suggestions,
    h("div", { class: "rows" }, categoryRow, dateRow),
    simulation,
    h("div", { class: "submit" }, submit),
  );

  function update(changes) {
    form = { ...form, ...changes };
    controller.onChange?.(form);
    paint();
  }

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
                update(chooseItem(form, item, period()));
                what.value = form.description;
                dateToggle.focus();
              },
            },
            h("b", {}, item.name),
            h("span", { class: item.remaining < 0 ? "figure over" : "figure" }, remainingText(item)),
            h("small", {}, `${data.categoryName(item.category_id)} · planeado ${formatPesos(item.planned)}`),
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

  function scheduleSimulation() {
    clearTimeout(simulationTimer);
    const request = simulationRequest(form);
    if (!request || !app.connection.online()) {
      simulation.hidden = true;
      return;
    }
    const count = ++simulationCount;
    // Espera a que se deje de escribir el monto antes de preguntar.
    simulationTimer = setTimeout(async () => {
      try {
        const result = await app.api.post(`${data.base}/cards/${request.cardId}/simulate`, request.body);
        if (count !== simulationCount) return;
        const summary = simulationSummary(result);
        const cardName = data.cards.find((item) => item.id === request.cardId)?.name ?? "la tarjeta";
        const when =
          summary.count === 1
            ? `Se paga en ${summary.firstMonth} con ${cardName}.`
            : `Primera cuota en ${summary.firstMonth}, la última en ${summary.lastMonth}.`;
        const detail =
          summary.count === 1
            ? `1 cuota · ${formatPesos(summary.first)}`
            : `${summary.count} cuotas · la primera ${formatPesos(summary.first)} · intereses est. ${formatPesos(summary.interest)}`;
        simulation.replaceChildren(when, h("br"), h("span", { class: "figure" }, detail));
        simulation.hidden = false;
      } catch {
        // La simulación es una ayuda: si falla, el formulario sigue igual.
        simulation.hidden = true;
      }
    }, 350);
  }

  function paint() {
    app.setMonth(period());
    const credit = form.paymentType === "credit";
    const kind = kindOf(form);
    payment.select(form.paymentType);

    const hasCards = data.cards.length > 0;
    cardRow.hidden = !credit || !hasCards;
    noCards.hidden = !credit || hasCards;
    installmentsRow.hidden = !credit || !hasCards;
    card.value = form.cardId === null ? "" : String(form.cardId);
    for (const button of quick) {
      button.setAttribute("aria-pressed", String(Number(button.textContent) === form.installments));
    }
    planRow.hidden = !credit || !hasCards || form.installments !== 1;
    plan.select(form.inPlan);

    what.placeholder = kind === "debt" ? "Nombre de la deuda" : "";
    categoryRow.hidden = !(kind === "debt" || (usesItems(form) && form.itemId === null));
    category.value = form.categoryId === null ? "" : String(form.categoryId);

    dateLabel.textContent = form.date ? formatDay(form.date) : "Hoy";
    dateLabel.hidden = false;
    dateInput.hidden = true;
    dateToggle.textContent = form.date ? "Volver a hoy" : "Cambiar fecha";

    data.items(period()).then((items) => {
      const item = usesItems(form) ? items.find((candidate) => candidate.id === form.itemId) : null;
      itemInfo.hidden = !item;
      if (item) {
        itemInfo.textContent = `Rubro de ${monthName(period())} · ${data.categoryName(item.category_id)} · ${remainingText(item)}`;
      }
      paintSuggestions(document.activeElement === what);
    });
    scheduleSimulation();

    // Una compra con abonos solo cambia qué fue y categoría (decisión 24).
    if (locked) {
      for (const button of [...payment.buttons, ...quick, ...plan.buttons]) button.disabled = true;
      for (const control of [card, otherInstallments, dateInput, dateToggle]) control.disabled = true;
    }
  }

  const controller = {
    element,
    focus: () => amount.focus(),
    get form() {
      return form;
    },
    reset(next) {
      form = next;
      amount.value = form.amount === null ? "" : formatNumber(form.amount);
      what.value = form.description;
      otherInstallments.value = "";
      paint();
    },
    paint,
    onChange: null,
  };
  paint();
  return controller;
}

export async function renderRecord(main, app) {
  const data = createData(app);
  await data.load();
  const initial = app.drafts.get(DRAFT) ?? newForm({ cardId: data.cards[0]?.id ?? null });

  const recordForm = await buildRecordForm(app, data, {
    initial,
    submitLabel: "Registrar gasto",
    busyLabel: "Registrando…",
    onSubmit: async (form) => {
      const expense = await app.api.post(`${data.base}/expenses`, buildExpense(form));
      const name = form.description.trim() || data.categoryName(expense.category_id);
      announce(app, data, expense, name);
      const recordedPeriod = formPeriod(form, data.currentPeriod);
      await data.refresh(recordedPeriod);
      recordForm.reset(afterRecord(form));
      app.drafts.set(DRAFT, recordForm.form);
      recordForm.focus();
    },
  });
  recordForm.onChange = (form) => app.drafts.set(DRAFT, form);
  main.append(recordForm.element);
  recordForm.element.prepend(h("h1", { class: "sr-only" }, "Registrar un gasto"));
  recordForm.focus();
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

/** Editar un gasto (RF-20, RF-21): el mismo formulario, que envía solo lo
 * que cambió, y borrar con confirmación (decisión 23). */
export async function renderEdit(main, app, { id }) {
  const data = createData(app);
  await data.load();
  const url = `${data.base}/expenses/${id}`;
  const expense = await app.api.get(url);
  const items = await data.items(periodOf(expense.spent_on));
  let lock = null;
  if (expense.card_id !== null) {
    const schedule = await app.api.get(`${url}/installments`);
    lock = lockFor(schedule.prepayments.length > 0);
  }
  const backToList = () => {
    app.drafts.set("expenses-period", periodOf(expense.spent_on));
    app.navigate("/gastos");
  };

  const controller = await buildRecordForm(app, data, {
    initial: formFromExpense(expense, items),
    submitLabel: "Guardar cambios",
    busyLabel: "Guardando…",
    locked: lock,
    onSubmit: async (form) => {
      const changes = buildChanges(expense, form);
      if (Object.keys(changes).length) {
        await app.api.patch(url, changes);
        app.notices.show({ text: "Cambios guardados.", seconds: 6 });
      }
      backToList();
    },
  });

  const name = controller.form.description || data.categoryName(expense.category_id);
  const remove = h(
    "button",
    {
      type: "button",
      class: "button button--danger button--block",
      "data-sends": true,
      onClick: async () => {
        const confirmed = await app.confirm({
          title: "¿Borrar este gasto?",
          body: `${name} · ${formatPesos(expense.amount)} · ${formatDay(expense.spent_on)}. No se puede deshacer.`,
          confirmLabel: "Borrar gasto",
          danger: true,
        });
        if (!confirmed) return;
        try {
          await app.api.del(url, { confirm: "true" });
          app.notices.show({ text: `Borrado: ${name}.`, seconds: 6 });
          backToList();
        } catch (error) {
          app.notices.show({ text: error.message, kind: "error", seconds: 0 });
        }
      },
    },
    "Borrar gasto",
  );

  main.append(
    h(
      "div",
      { class: "screen__head edit-head" },
      h("h1", {}, "Editar gasto"),
      h("a", { href: "/gastos", onClick: () => app.drafts.set("expenses-period", periodOf(expense.spent_on)) }, "Volver a Gastos"),
    ),
    controller.element,
    h("div", { class: "submit" }, remove),
  );
  controller.focus();
}
