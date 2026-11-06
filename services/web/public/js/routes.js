// Rutas de la app (spec 011, plan "Pantallas y datos").
//
// `access`: "guest" solo sin sesión (entrar, crear cuenta), "member" con
// sesión, "any" con o sin ella (unirse por enlace, decisión 19).

const ROUTES = [
  { pattern: /^\/entrar$/, view: "login", access: "guest" },
  { pattern: /^\/crear-cuenta$/, view: "register", access: "guest" },
  { pattern: /^\/registrar$/, view: "record", access: "member" },
  { pattern: /^\/gastos$/, view: "expenses", access: "member" },
  { pattern: /^\/gastos\/(?<id>\d+)$/, view: "edit", access: "member" },
  { pattern: /^\/espacio$/, view: "space", access: "member" },
  { pattern: /^\/unirse\/(?<token>[\w-]+)$/, view: "join", access: "any" },
];

export function matchRoute(pathname) {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  for (const { pattern, view, access } of ROUTES) {
    const match = pattern.exec(path);
    if (!match) continue;
    const params = { ...match.groups };
    if (params.id !== undefined) params.id = Number(params.id);
    return { view, params, access };
  }
  return { redirect: "/registrar" };
}
