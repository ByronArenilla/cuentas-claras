// Cliente de la API (spec 011). Recibe sus dependencias (`fetch`, el token y
// a quién avisar) para poder probarse con `node --test` sin navegador.
//
// - Manda el token en `Authorization: Bearer` (ADR 0003).
// - Un `401` avisa para borrar la sesión y pedir entrar (RF-3).
// - Un fallo de red avisa que no hay conexión (RF-30); una respuesta, que sí.
// - Los mensajes de error son los de la API, que ya están en español
//   (decisión 14); los de validación se reparten por campo.

const OFFLINE_MESSAGE =
  "Sin conexión. Lo que escribiste se queda aquí; podrás guardarlo cuando vuelva la conexión.";

// Pydantic responde algunos errores propios en inglés.
const PYDANTIC_MESSAGES = {
  missing: "Este campo es obligatorio.",
  json_invalid: "La petición no es un JSON válido.",
};

export class ApiError extends Error {
  constructor({ status, message, fields = {}, offline = false }) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fields = fields;
    this.offline = offline;
  }
}

/** Los errores de validación de FastAPI (`detail` como lista) por campo:
 * `["body", "amount"]` → `amount`; `["body"]` → `_form`. */
function fieldsFrom(detail) {
  const fields = {};
  for (const error of detail) {
    const loc = error.loc ?? [];
    const field = loc.length > 1 ? String(loc[loc.length - 1]) : "_form";
    fields[field] ??= PYDANTIC_MESSAGES[error.type] ?? error.msg;
  }
  return fields;
}

function errorFrom(status, body) {
  const detail = body?.detail;
  if (Array.isArray(detail)) {
    const fields = fieldsFrom(detail);
    return new ApiError({ status, message: Object.values(fields)[0], fields });
  }
  const message = typeof detail === "string" ? detail : "Algo salió mal. Inténtalo de nuevo.";
  return new ApiError({ status, message });
}

export function createApi({ baseUrl, fetch, token, onUnauthorized, onNetwork }) {
  async function request(method, path, { body, params } = {}) {
    const query = params ? `?${new URLSearchParams(params)}` : "";
    const headers = { Accept: "application/json" };
    const current = token();
    if (current) headers.Authorization = `Bearer ${current}`;
    if (body !== undefined) headers["Content-Type"] = "application/json";

    let response;
    try {
      response = await fetch(`${baseUrl}${path}${query}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      onNetwork(false);
      throw new ApiError({ status: 0, message: OFFLINE_MESSAGE, offline: true });
    }
    onNetwork(true);

    if (response.status === 204) return null;
    const data = await response.json().catch(() => null);
    if (response.ok) return data;

    const error = errorFrom(response.status, data);
    if (response.status === 401) onUnauthorized(error.message);
    throw error;
  }

  return {
    get: (path, params) => request("GET", path, { params }),
    post: (path, body) => request("POST", path, { body }),
    patch: (path, body) => request("PATCH", path, { body }),
    put: (path, body) => request("PUT", path, { body }),
    del: (path, params) => request("DELETE", path, { params }),
  };
}
