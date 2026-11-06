// Pestaña Gastos (spec 011, RF-17 a RF-22): los gastos del mes por fecha de
// compra, con flechas de mes, "Solo los míos" y el total. Cada gasto abre su
// edición en `/gastos/<id>`.
import { h } from "../dom.js";
import { describeExpense, groupByDay, onlyMine, totalOf } from "../expenses-list.js";
import { formatDay, formatMonth, formatPesos, shiftPeriod } from "../format.js";

export async function renderExpenses(main, app) {
  const base = `/spaces/${app.space.id}`;
  let period = app.drafts.get("expenses-period");
  let mine = app.drafts.get("expenses-mine") ?? false;
  const cards = await app.api.get(`${base}/cards`);
  if (!period) period = (await app.api.get(`${base}/summary`)).period;

  const title = h("h2", { class: "label", "aria-live": "polite" });
  const previous = h(
    "button",
    { type: "button", "aria-label": "Mes anterior", onClick: () => move(-1) },
    "‹",
  );
  const next = h(
    "button",
    { type: "button", "aria-label": "Mes siguiente", onClick: () => move(1) },
    "›",
  );
  const filter = h(
    "button",
    {
      type: "button",
      class: "button button--quiet",
      "aria-pressed": String(mine),
      onClick: () => {
        mine = !mine;
        app.drafts.set("expenses-mine", mine);
        filter.setAttribute("aria-pressed", String(mine));
        load();
      },
    },
    "Solo los míos",
  );
  const list = h("div", { class: "stack" });

  main.classList.add("main--wide");
  main.append(
    h(
      "div",
      { class: "screen" },
      h(
        "div",
        { class: "screen__head" },
        h("h1", {}, "Gastos"),
        h("div", { class: "month-switch" }, previous, title, next),
      ),
      h("div", { class: "cluster" }, filter),
      list,
    ),
  );

  function move(months) {
    period = shiftPeriod(period, months);
    app.drafts.set("expenses-period", period);
    load();
  }

  async function load() {
    title.textContent = formatMonth(period);
    app.setMonth(period);
    list.replaceChildren(h("div", { class: "loading", "aria-hidden": "true" }));
    try {
      const [expenses, summary] = await Promise.all([
        app.api.get(`${base}/expenses`, { period }),
        app.api.get(`${base}/summary`, { period }),
      ]);
      const names = {
        items: new Map(summary.budget_items.map((item) => [item.id, item.name])),
        categories: new Map(summary.categories.map((row) => [row.category_id, row.name])),
        cards: new Map(cards.map((card) => [card.id, card.name])),
      };
      const shown = mine ? onlyMine(expenses, app.me.id) : expenses;
      paint(shown, names);
    } catch (error) {
      list.replaceChildren(h("p", { class: "error", role: "alert" }, error.message));
    }
  }

  function paint(expenses, names) {
    if (!expenses.length) {
      // Vacío: qué falta y la acción para resolverlo (RF-22).
      list.replaceChildren(
        h(
          "p",
          { class: "empty" },
          `No hay gastos${mine ? " tuyos" : ""} en ${formatMonth(period)}. `,
          h("a", { href: "/registrar" }, "Registrar uno"),
        ),
      );
      return;
    }
    list.replaceChildren(
      h(
        "div",
        { class: "total" },
        h("span", {}, `Total de ${formatMonth(period)}`),
        h("span", { class: "figure" }, formatPesos(totalOf(expenses))),
      ),
      ...groupByDay(expenses).map((group) =>
        h(
          "section",
          { "aria-label": formatDay(group.day) },
          h("h3", { class: "day label" }, formatDay(group.day)),
          group.expenses.map((expense) => {
            const { name, meta } = describeExpense(expense, names, app.me.id);
            return h(
              "a",
              { class: "entry", href: `/gastos/${expense.id}` },
              h("span", {}, name),
              h("span", { class: "figure" }, formatPesos(expense.amount)),
              h("span", { class: "entry__meta" }, meta),
            );
          }),
        ),
      ),
    );
  }

  await load();
}
