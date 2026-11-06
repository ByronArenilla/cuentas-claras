// Sesión en el dispositivo (spec 011, decisiones 2, 16 y 17).
//
// - El token y el correo, en `localStorage`: sobreviven a cerrar la app, así
//   que se entra una sola vez (decisión 9). Los protege la CSP.
// - El espacio actual, también en `localStorage` (RF-23).
// - La pantalla a la que volver tras entrar, en `sessionStorage`, y solo si es
//   una ruta propia: así no hay redirección abierta a otro sitio.
//
// Si el almacenamiento no está disponible (modo privado estricto), nada se
// rompe: simplemente no se recuerda.

const TOKEN = "gastito.session";
const SPACE = "gastito.space";
const NEXT = "gastito.next";

/** Solo rutas de esta web: empiezan por `/` y no por `//` ni `/\`. */
export function isSafePath(path) {
  return typeof path === "string" && /^\/(?![/\\])/.test(path);
}

function safe(storage) {
  return {
    get(key) {
      try {
        return storage.getItem(key);
      } catch {
        return null;
      }
    },
    set(key, value) {
      try {
        storage.setItem(key, value);
      } catch {
        // Sin almacenamiento, no se recuerda.
      }
    },
    remove(key) {
      try {
        storage.removeItem(key);
      } catch {
        // Nada que borrar.
      }
    },
  };
}

export function createSession({ local, temporary }) {
  const store = safe(local);
  const tab = safe(temporary);

  function read() {
    try {
      return JSON.parse(store.get(TOKEN)) ?? {};
    } catch {
      return {};
    }
  }

  return {
    token: () => read().token ?? null,
    email: () => read().email ?? null,
    isLoggedIn: () => Boolean(read().token),
    save({ token, email }) {
      store.set(TOKEN, JSON.stringify({ token, email }));
    },
    clear() {
      store.remove(TOKEN);
      store.remove(SPACE);
    },
    spaceId() {
      const value = store.get(SPACE);
      return value === null ? null : Number(value);
    },
    setSpace(id) {
      store.set(SPACE, String(id));
    },
    /** El espacio recordado si todavía es miembro; si no, el primero. */
    chooseSpace(spaces) {
      const remembered = spaces.find((space) => space.id === this.spaceId());
      const chosen = remembered ?? spaces[0] ?? null;
      if (chosen) this.setSpace(chosen.id);
      return chosen;
    },
    setNext(path) {
      if (isSafePath(path)) tab.set(NEXT, path);
    },
    takeNext() {
      const path = tab.get(NEXT);
      tab.remove(NEXT);
      return isSafePath(path) ? path : null;
    },
  };
}
