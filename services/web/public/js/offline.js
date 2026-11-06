// Estado de la conexión (spec 011, RF-30, decisión 15). Sin service worker:
// combina `navigator.onLine`, sus eventos y lo que informa el cliente de la
// API cuando una petición falla por red o responde.

export function createConnection(win) {
  let online = win.navigator.onLine !== false;
  const listeners = new Set();

  function report(value) {
    if (value === online) return;
    online = value;
    for (const listener of listeners) listener(online);
  }

  win.addEventListener("online", () => report(true));
  win.addEventListener("offline", () => report(false));

  return {
    online: () => online,
    report,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}
