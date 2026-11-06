// Estado del formulario de Registrar y el gasto que se envía (spec 011,
// RF-6 a RF-16; criterio 1). Sin navegador.
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  afterRecord,
  buildExpense,
  changeDate,
  chooseItem,
  missing,
  nameKey,
  newForm,
  suggestItems,
  typeDescription,
} from "../public/js/expense-form.js";

// Rubros del resumen de noviembre (spec 008), con su categoría.
const ITEMS = [
  { id: 1, name: "Mercado", category_id: 2, planned: 800000, spent: 412000, remaining: 388000 },
  { id: 2, name: "Mercado mascotas", category_id: 8, planned: 120000, spent: 60000, remaining: 60000 },
  { id: 3, name: "Acción de gracias", category_id: 7, planned: 50000, spent: 0, remaining: 50000 },
  { id: 4, name: "Año nuevo", category_id: 7, planned: 90000, spent: 0, remaining: 90000 },
];

test("los nombres se comparan sin mayúsculas ni tildes, y la ñ cuenta", () => {
  assert.equal(nameKey("  Acción "), "accion");
  assert.equal(nameKey("Año"), "año");
  assert.notEqual(nameKey("Año"), nameKey("Ano"));
});

test("las sugerencias contienen lo escrito, sin mayúsculas ni tildes", () => {
  assert.deepEqual(
    suggestItems(ITEMS, "merc").map((item) => item.name),
    ["Mercado", "Mercado mascotas"],
  );
  assert.deepEqual(
    suggestItems(ITEMS, "accion").map((item) => item.name),
    ["Acción de gracias"],
  );
  assert.deepEqual(suggestItems(ITEMS, "ano"), []);
  // Sin texto, todos los rubros del mes.
  assert.equal(suggestItems(ITEMS, "  ").length, 4);
});

test("elegir un rubro lo liga y toma su nombre y su categoría", () => {
  const form = chooseItem(newForm(), ITEMS[0], "2026-11");

  assert.equal(form.itemId, 1);
  assert.equal(form.itemPeriod, "2026-11");
  assert.equal(form.description, "Mercado");
  assert.equal(form.categoryId, 2);
});

test("escribir otra cosa suelta el rubro", () => {
  const chosen = chooseItem(newForm(), ITEMS[0], "2026-11");

  const typed = typeDescription(chosen, "Mercado del barrio");

  assert.equal(typed.itemId, null);
  assert.equal(typed.description, "Mercado del barrio");
});

test("débito con rubro: sin categoría ni descripción, y sin fecha si es hoy", () => {
  const form = { ...chooseItem(newForm(), ITEMS[0], "2026-11"), amount: 52000 };

  assert.deepEqual(buildExpense(form), {
    amount: 52000,
    payment_type: "debit",
    budget_item_id: 1,
  });
});

test("débito sin rubro: categoría y descripción", () => {
  const form = {
    ...typeDescription(newForm(), "  Regalo Ana "),
    amount: 80000,
    categoryId: 5,
    date: "2026-11-03",
  };

  assert.deepEqual(buildExpense(form), {
    amount: 80000,
    payment_type: "debit",
    category_id: 5,
    description: "Regalo Ana",
    spent_on: "2026-11-03",
  });
});

test("débito sin rubro y sin descripción no manda descripción", () => {
  const form = { ...newForm(), amount: 9000, categoryId: 3 };

  assert.deepEqual(buildExpense(form), { amount: 9000, payment_type: "debit", category_id: 3 });
});

test("cambiar la fecha a otro mes suelta el rubro elegido (RF-9)", () => {
  const chosen = chooseItem(newForm(), ITEMS[0], "2026-11");

  const sameMonth = changeDate(chosen, "2026-11-02", "2026-11");
  const otherMonth = changeDate(chosen, "2026-10-30", "2026-11");
  const backToToday = changeDate(sameMonth, null, "2026-11");

  assert.equal(sameMonth.itemId, 1);
  assert.equal(otherMonth.itemId, null);
  assert.equal(otherMonth.date, "2026-10-30");
  assert.equal(backToToday.itemId, 1);
  assert.equal(backToToday.date, null);
});

test("lo que falta para poder registrar", () => {
  assert.deepEqual(missing(newForm()), [
    "Escribe el monto.",
    "Elige un rubro del mes o la categoría.",
  ]);
  assert.deepEqual(missing({ ...newForm(), amount: 0, categoryId: 2 }), ["Escribe el monto."]);
  assert.deepEqual(missing({ ...chooseItem(newForm(), ITEMS[0], "2026-11"), amount: 1 }), []);
});

test("tras registrar se limpian monto y qué fue, y se conservan pago y fecha (RF-14)", () => {
  const form = {
    ...chooseItem(newForm(), ITEMS[0], "2026-11"),
    amount: 52000,
    date: "2026-11-03",
  };

  const next = afterRecord(form);

  assert.equal(next.amount, null);
  assert.equal(next.description, "");
  assert.equal(next.itemId, null);
  assert.equal(next.categoryId, null);
  assert.equal(next.paymentType, "debit");
  assert.equal(next.date, "2026-11-03");
});
