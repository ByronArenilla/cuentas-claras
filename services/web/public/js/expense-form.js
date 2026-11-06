// Estado del formulario de Registrar y el gasto que se envía a la API (spec
// 011, RF-6 a RF-16, decisiones 10 a 13). Sin DOM: se prueba con
// `node --test`. Cada función devuelve un estado nuevo y no cambia el que
// recibe.
//
// Un gasto se nombra con un solo campo, "Qué fue" (decisión 26 de la 009). En
// un gasto del mes (débito, o tarjeta a 1 cuota que estaba en el plan) sugiere
// los rubros del mes; elegir uno lo liga al rubro y la categoría sale de él.
// Si no se elige ninguno, se pide la categoría y el texto es la descripción.

import { monthName, periodOf } from "./format.js";

/** Cuotas que se eligen con un toque (RF-12); las demás, de 1 a 48, se
 * escriben. */
export const QUICK_INSTALLMENTS = [1, 2, 3, 6, 12, 24, 36];
export const MAX_INSTALLMENTS = 48;

/** Cuotas escritas: entero de 1 a 48, o `null`. */
export function parseInstallments(text) {
  const trimmed = String(text).trim();
  if (!/^\d+$/.test(trimmed)) return null;
  const value = Number(trimmed);
  return value >= 1 && value <= MAX_INSTALLMENTS ? value : null;
}

const TILDE = "̃";

/** La clave con la que la API compara nombres (`category_key`, ADR 0006):
 * sin mayúsculas, tildes ni diéresis, y sin espacios alrededor. La ñ cuenta:
 * "Año" y "Ano" son distintos. */
export function nameKey(name) {
  const decomposed = name.trim().toLowerCase().normalize("NFD");
  let kept = "";
  for (const char of decomposed) {
    const combining = /\p{Mn}/u.test(char);
    const enye = char === TILDE && kept.endsWith("n");
    if (combining && !enye) continue;
    kept += char;
  }
  return kept.normalize("NFC");
}

/** Un formulario vacío. "Hoy" es `date: null`: la web no calcula hoy
 * (decisión 12). */
export function newForm({ paymentType = "debit", cardId = null, date = null } = {}) {
  return {
    amount: null,
    paymentType,
    description: "",
    itemId: null,
    itemPeriod: null,
    categoryId: null,
    date,
    cardId,
    installments: 1,
    // Solo a crédito y a 1 cuota: ¿estaba en el plan del mes? Sin respuesta
    // hasta que se elige (decisión 26).
    inPlan: null,
  };
}

/** Los rubros cuyo nombre contiene lo escrito (RF-8). Sin texto, todos. */
export function suggestItems(items, text) {
  const key = nameKey(text);
  if (!key) return items;
  return items.filter((item) => nameKey(item.name).includes(key));
}

export function chooseItem(form, item, period) {
  return {
    ...form,
    itemId: item.id,
    itemPeriod: period,
    description: item.name,
    categoryId: item.category_id,
  };
}

/** Escribir en "Qué fue": si ya no es el nombre del rubro elegido, lo suelta. */
export function typeDescription(form, text) {
  const keepsItem = form.itemId !== null && text === form.description;
  return keepsItem ? { ...form, description: text } : { ...form, description: text, itemId: null, itemPeriod: null };
}

/** El mes del gasto: el de la fecha elegida, o el actual si es "Hoy". */
export function formPeriod(form, currentPeriod) {
  return form.date ? periodOf(form.date) : currentPeriod;
}

/** Cambia la fecha (`null` es "Hoy"); un rubro de otro mes se suelta (RF-9). */
export function changeDate(form, date, currentPeriod) {
  const next = { ...form, date };
  if (next.itemId !== null && next.itemPeriod !== formPeriod(next, currentPeriod)) {
    return { ...next, itemId: null, itemPeriod: null };
  }
  return next;
}

/** Qué clase de gasto es: "debit", "month" (tarjeta, del mes), "debt"
 * (tarjeta, deuda) o "undecided" (tarjeta a 1 cuota sin responder). */
export function kindOf(form) {
  if (form.paymentType === "debit") return "debit";
  if (form.installments > 1) return "debt";
  if (form.inPlan === true) return "month";
  if (form.inPlan === false) return "debt";
  return "undecided";
}

/** Un gasto del mes, a débito o con tarjeta, se liga a un rubro o lleva
 * categoría, como en la 008. */
export function usesItems(form) {
  const kind = kindOf(form);
  return kind === "debit" || kind === "month";
}

const NO_CARDS =
  "Este espacio todavía no tiene tarjetas. Por ahora se crean con la API (README, «Tarjetas»).";

/** Lo que falta para poder registrar, en el orden del formulario.
 * `hasCards: false` si el espacio no tiene tarjetas activas (RF-10). */
export function missing(form, { hasCards = true } = {}) {
  const found = [];
  if (!form.amount) found.push("Escribe el monto.");
  if (form.paymentType === "credit") {
    if (!hasCards) return [...found, NO_CARDS];
    if (form.cardId === null) found.push("Elige la tarjeta.");
    if (form.installments === null) {
      found.push(`Las cuotas deben ser un número entero de 1 a ${MAX_INSTALLMENTS}.`);
      return found;
    }
  }
  const kind = kindOf(form);
  if (kind === "undecided") found.push("Elige si estaba en el plan de este mes.");
  if (usesItems(form) && form.itemId === null && form.categoryId === null) {
    found.push("Elige un rubro del mes o la categoría.");
  }
  if (kind === "debt") {
    if (!form.description.trim()) found.push("Escribe qué fue: es el nombre de la deuda.");
    if (form.categoryId === null) found.push("Elige la categoría.");
  }
  return found;
}

/** El cuerpo de `POST /expenses` (criterio 1). A crédito lleva tarjeta,
 * cuotas e `is_debt` (spec 010); una deuda, categoría y descripción, nunca
 * rubro. */
export function buildExpense(form) {
  const body = { amount: form.amount, payment_type: form.paymentType };
  const description = form.description.trim();
  if (form.paymentType === "credit") {
    body.card_id = form.cardId;
    body.installments = form.installments;
    body.is_debt = kindOf(form) === "debt";
  }
  if (form.itemId !== null && usesItems(form)) {
    body.budget_item_id = form.itemId;
  } else {
    body.category_id = form.categoryId;
    if (description) body.description = description;
  }
  if (form.date) body.spent_on = form.date;
  return body;
}

/** La petición de simulación (RF-11): solo a crédito, con monto, tarjeta y
 * cuotas válidas. */
export function simulationRequest(form) {
  if (form.paymentType !== "credit" || !form.amount || form.cardId === null) return null;
  if (form.installments === null) return null;
  const body = { amount: form.amount, installments: form.installments };
  if (form.date) body.spent_on = form.date;
  return { cardId: form.cardId, body };
}

/** Lo que se muestra antes de guardar: mes de la primera y de la última
 * cuota, número de cuotas, la primera y los intereses estimados. */
export function simulationSummary(simulation) {
  const rows = simulation.installments;
  return {
    firstMonth: monthName(simulation.first_due_period),
    lastMonth: monthName(rows[rows.length - 1].period),
    count: rows[0].count,
    first: rows[0].amount,
    interest: rows.reduce((total, row) => total + row.interest, 0),
  };
}

/** El formulario listo para el siguiente gasto: se limpian monto y qué fue, y
 * se conservan el tipo de pago, la tarjeta y la fecha (RF-14). La pregunta
 * "¿Estaba en el plan?" vuelve a quedar sin respuesta (decisión 26). */
export function afterRecord(form) {
  return newForm({ paymentType: form.paymentType, cardId: form.cardId, date: form.date });
}

// --- Editar (RF-20, decisión 24) ---

/** El formulario de un gasto que ya existe, con su fecha explícita. */
export function formFromExpense(expense, items) {
  const item = items.find((candidate) => candidate.id === expense.budget_item_id);
  const card = expense.card_id !== null;
  const installments = expense.installments ?? 1;
  return {
    amount: expense.amount,
    paymentType: expense.payment_type,
    description: item ? item.name : (expense.description ?? ""),
    itemId: expense.budget_item_id,
    itemPeriod: expense.budget_item_id !== null ? periodOf(expense.spent_on) : null,
    categoryId: expense.category_id,
    date: expense.spent_on,
    cardId: expense.card_id,
    installments,
    inPlan: card && installments === 1 ? !expense.is_debt : null,
  };
}

/** Solo lo que cambió, para `PATCH /expenses/{id}`. Quitar el rubro manda
 * `budget_item_id: null` con la categoría (RF-21 de la 008). */
export function buildChanges(original, form) {
  const target = buildExpense(form);
  const changes = {};
  const set = (key, value) => {
    if (value !== original[key]) changes[key] = value;
  };
  set("amount", target.amount);
  set("payment_type", target.payment_type);
  if (target.payment_type === "credit") {
    set("card_id", target.card_id);
    set("installments", target.installments);
    set("is_debt", target.is_debt);
  }
  if (target.budget_item_id !== undefined) {
    set("budget_item_id", target.budget_item_id);
  } else {
    if (original.budget_item_id !== null) {
      changes.budget_item_id = null;
      changes.category_id = target.category_id;
    } else {
      set("category_id", target.category_id);
    }
    const description = target.description ?? null;
    if (description !== (original.description ?? null)) changes.description = description;
  }
  if (form.date) set("spent_on", form.date);
  return changes;
}

const LOCKED_WITH_PREPAYMENTS = [
  "amount",
  "payment_type",
  "card_id",
  "installments",
  "is_debt",
  "spent_on",
];

/** Una compra con abonos solo cambia qué fue y categoría (RF-16 de la 009,
 * decisión 24). `null` si no tiene abonos. */
export function lockFor(hasPrepayments) {
  if (!hasPrepayments) return null;
  return {
    fields: new Set(LOCKED_WITH_PREPAYMENTS),
    reason:
      "Esta compra tiene abonos: solo puedes cambiar qué fue y la categoría. " +
      "Para cambiar lo demás o borrarla, primero hay que borrar sus abonos.",
  };
}
