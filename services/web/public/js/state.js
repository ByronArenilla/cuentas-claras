// Estado en memoria que sobrevive a cambiar de pantalla, pero no a recargar
// la página (spec 011, decisión 16): lo escrito en un formulario si hay que
// entrar de nuevo. Nunca se guardan datos de gastos en el dispositivo.

export function createDrafts() {
  const drafts = new Map();
  return {
    get: (key) => drafts.get(key) ?? null,
    set: (key, value) => drafts.set(key, value),
    clear: (key) => drafts.delete(key),
  };
}
