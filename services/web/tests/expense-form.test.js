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

// --- A crédito (T8, RF-10 a RF-12; decisión 26) ---

import {
  QUICK_INSTALLMENTS,
  kindOf,
  parseInstallments,
  simulationRequest,
  simulationSummary,
  usesItems,
} from "../public/js/expense-form.js";

const credit = (fields = {}) => ({
  ...newForm({ paymentType: "credit", cardId: 1 }),
  amount: 1200000,
  ...fields,
});

test("a 1 cuota la pregunta empieza sin respuesta y no deja registrar", () => {
  const form = credit({ description: "Compra TV", categoryId: 1 });

  assert.equal(kindOf(form), "undecided");
  assert.equal(usesItems(form), false);
  assert.deepEqual(missing(form), ["Elige si estaba en el plan de este mes."]);
});

test("'Sí, es del mes' se comporta como un débito y sugiere rubros", () => {
  const form = chooseItem(credit({ inPlan: true }), ITEMS[0], "2026-11");

  assert.equal(kindOf(form), "month");
  assert.equal(usesItems(form), true);
  assert.deepEqual(missing(form), []);
  assert.deepEqual(buildExpense(form), {
    amount: 1200000,
    payment_type: "credit",
    card_id: 1,
    installments: 1,
    is_debt: false,
    budget_item_id: 1,
  });
});

test("'No, es una deuda' pide qué fue y categoría, y nunca rubro", () => {
  const form = credit({ inPlan: false });

  assert.equal(kindOf(form), "debt");
  assert.deepEqual(missing(form), [
    "Escribe qué fue: es el nombre de la deuda.",
    "Elige la categoría.",
  ]);
  assert.deepEqual(
    buildExpense({ ...form, description: " Zapatos ", categoryId: 1, date: "2026-11-04" }),
    {
      amount: 1200000,
      payment_type: "credit",
      card_id: 1,
      installments: 1,
      is_debt: true,
      category_id: 1,
      description: "Zapatos",
      spent_on: "2026-11-04",
    },
  );
});

test("a varias cuotas siempre es deuda, sin preguntar", () => {
  const form = credit({ installments: 6, inPlan: true, description: "Compra TV", categoryId: 1 });

  assert.equal(kindOf(form), "debt");
  assert.deepEqual(missing(form), []);
  assert.equal(buildExpense(form).is_debt, true);
  assert.equal(buildExpense(form).installments, 6);
});

test("a crédito hace falta tarjeta, y el espacio puede no tener ninguna", () => {
  const form = { ...credit({ inPlan: false, description: "x", categoryId: 1 }), cardId: null };

  assert.deepEqual(missing(form), ["Elige la tarjeta."]);
  assert.deepEqual(missing(form, { hasCards: false }), [
    "Este espacio todavía no tiene tarjetas. Por ahora se crean con la API (README, «Tarjetas»).",
  ]);
});

test("cuotas: opciones rápidas y escritas de 1 a 48", () => {
  assert.deepEqual(QUICK_INSTALLMENTS, [1, 2, 3, 6, 12, 24, 36]);
  assert.equal(parseInstallments("18"), 18);
  assert.equal(parseInstallments("48"), 48);
  assert.equal(parseInstallments("0"), null);
  assert.equal(parseInstallments("49"), null);
  assert.equal(parseInstallments("3.5"), null);
  assert.equal(parseInstallments(""), null);
  assert.deepEqual(missing(credit({ installments: null, description: "x", categoryId: 1 })), [
    "Las cuotas deben ser un número entero de 1 a 48.",
  ]);
});

test("la simulación se pide con monto, tarjeta y cuotas, y con la fecha si no es hoy", () => {
  assert.deepEqual(simulationRequest(credit({ installments: 6 })), {
    cardId: 1,
    body: { amount: 1200000, installments: 6 },
  });
  assert.deepEqual(simulationRequest(credit({ date: "2026-11-05" })), {
    cardId: 1,
    body: { amount: 1200000, installments: 1, spent_on: "2026-11-05" },
  });
  assert.equal(simulationRequest(credit({ amount: null })), null);
  assert.equal(simulationRequest(credit({ cardId: null })), null);
  assert.equal(simulationRequest(credit({ installments: null })), null);
  assert.equal(simulationRequest(newForm()), null);
});

test("el resumen de la simulación: mes, cuotas, primera e intereses", () => {
  const simulation = {
    first_due_period: "2026-12",
    installments: [
      { number: 1, count: 6, period: "2026-12", amount: 222800, interest: 22800 },
      { number: 2, count: 6, period: "2027-01", amount: 219000, interest: 19000 },
      { number: 6, count: 6, period: "2027-05", amount: 203800, interest: 3800 },
    ],
  };

  assert.deepEqual(simulationSummary(simulation), {
    firstMonth: "diciembre",
    lastMonth: "mayo",
    count: 6,
    first: 222800,
    interest: 45600,
  });
});

test("tras registrar a crédito se conserva la tarjeta y la pregunta vuelve a quedar sin respuesta", () => {
  const next = afterRecord(credit({ installments: 6, inPlan: false }));

  assert.equal(next.paymentType, "credit");
  assert.equal(next.cardId, 1);
  assert.equal(next.installments, 1);
  assert.equal(next.inPlan, null);
});
