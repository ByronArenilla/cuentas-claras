// Entrar, crear cuenta y cerrar sesión, sin DOM (spec 011, RF-1 a RF-4).
// Las pantallas de `views/auth.js` y `views/space.js` los usan.

const OFFLINE_LOGOUT =
  "Cerraste sesión en este dispositivo. Como no hay conexión, la sesión en el " +
  "servidor se cerrará sola tras 90 días sin uso.";

/** Entra y devuelve la ruta a la que ir: la que se pidió antes de entrar o
 * Registrar (RF-2, decisión 16). */
export async function logIn({ api, session }, { email, password }) {
  const token = await api.post("/auth/login", { email, password });
  session.save({ token: token.access_token, email: email.trim().toLowerCase() });
  return session.takeNext() ?? "/registrar";
}

/** Crea la cuenta y entra con ella (RF-1). */
export async function signUp(context, { email, password }) {
  await context.api.post("/auth/register", { email, password });
  return logIn(context, { email, password });
}

/** Cierra la sesión en la API y borra lo del dispositivo. Sin conexión, borra
 * igual y devuelve el aviso de los 90 días (RF-4). */
export async function logOut({ api, session }) {
  try {
    await api.post("/auth/logout");
    return null;
  } catch (error) {
    if (error.offline) return OFFLINE_LOGOUT;
    // Una sesión que ya no existe (401) también cuenta como cerrada.
    if (error.status === 401) return null;
    throw error;
  } finally {
    session.clear();
  }
}
