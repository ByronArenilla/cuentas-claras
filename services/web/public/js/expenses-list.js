// Gastos del mes, sin DOM (spec 011, RF-17 a RF-19): agrupar por día, total,
// "solo los míos" y el texto de cada gasto.
import { formatMonthShort } from "./format.js";

/** Agrupa por día conservando el orden de la API (del día más reciente al
 * más antiguo; a igual día, el registrado después primero). */
export function groupByDay(expenses) {
  const groups = [];
  for (const expense of expenses) {
    const last = groups[groups.length - 1];
    if (last?.day === expense.spent_on) last.expenses.push(expense);
    else groups.push({ day: expense.spent_on, expenses: [expense] });
  }
  return groups;
}

export function totalOf(expenses) {
  return expenses.reduce((total, expense) => total + expense.amount, 0);
}

/** Los que registró quien usa la app (RF-19). */
export function onlyMine(expenses, userId) {
  return expenses.filter((expense) => expense.created_by === userId);
}

function shortMonth(period) {
  return formatMonthShort(period).split(" ")[0];
}

function paidWith(expense, names) {
  if (expense.payment_type === "debit") return "Débito";
  if (expense.card_id === null) return "Crédito";
  const card = names.cards.get(expense.card_id) ?? "Tarjeta";
  const month = shortMonth(expense.first_due_period);
  if (!expense.is_debt) return `${card} · del mes · se paga en ${month}`;
  return expense.installments > 1
    ? `${card} · deuda · ${expense.installments} cuotas desde ${month}`
    : `${card} · deuda · 1 cuota en ${month}`;
}

/** Nombre (rubro, descripción o categoría) y la línea de abajo: categoría,
 * cómo se pagó y si lo registró otro miembro (RF-18). */
export function describeExpense(expense, names, userId) {
  const category = names.categories.get(expense.category_id) ?? "Sin categoría";
  const name =
    (expense.budget_item_id !== null && names.items.get(expense.budget_item_id)) ||
    expense.description ||
    category;
  const parts = [category, paidWith(expense, names)];
  if (expense.created_by !== userId) parts.push("registró otro miembro");
  return { name, meta: parts.join(" · ") };
}
