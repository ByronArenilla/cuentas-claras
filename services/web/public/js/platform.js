// Guía para fijar la app en la pantalla de inicio (spec 011, RF-29, decisión
// 20): detecta el navegador y devuelve solo sus pasos. Sin DOM.

/** "ios", "android-chrome", "desktop-chrome", "desktop-edge", "mac-safari" u
 * "other". En iPhone todos los navegadores fijan igual, desde Compartir. */
export function detectPlatform(userAgent) {
  if (/iPhone|iPad|iPod/.test(userAgent)) return "ios";
  if (/Android/.test(userAgent)) {
    return /Chrome\//.test(userAgent) && !/SamsungBrowser|EdgA|OPR/.test(userAgent)
      ? "android-chrome"
      : "other";
  }
  if (/Edg\//.test(userAgent)) return "desktop-edge";
  if (/Chrome\//.test(userAgent) && !/OPR/.test(userAgent)) return "desktop-chrome";
  if (/Macintosh/.test(userAgent) && /Version\/\d+.*Safari/.test(userAgent)) return "mac-safari";
  return "other";
}

const GUIDES = {
  ios: {
    title: "En el iPhone",
    steps: [
      "Toca Compartir (el cuadrado con la flecha hacia arriba).",
      "Elige «Añadir a pantalla de inicio» y toca Añadir.",
    ],
    note: "Abierta desde el ícono, no te vuelve a pedir que entres.",
  },
  "android-chrome": {
    title: "En Chrome para Android",
    steps: [
      "Toca el menú ⋮ arriba a la derecha.",
      "Elige «Añadir a pantalla de inicio» (o «Instalar app») y confirma.",
    ],
    note: "",
  },
  "desktop-chrome": {
    title: "En Chrome",
    steps: [
      "Haz clic en el ícono de instalar al final de la barra de direcciones,",
      "o en el menú ⋮ › Transmitir, guardar y compartir › Instalar página como app.",
    ],
    note: "",
  },
  "desktop-edge": {
    title: "En Edge",
    steps: ["Abre el menú … › Aplicaciones › Instalar este sitio como una aplicación."],
    note: "",
  },
  "mac-safari": {
    title: "En Safari para Mac",
    steps: ["Abre el menú Archivo › Agregar al Dock."],
    note: "",
  },
  other: {
    title: "En este navegador",
    steps: [],
    note:
      "Este navegador no permite fijarla. Ábrela en Safari (iPhone), Chrome (Android) o Chrome o Edge (computador).",
  },
};

/** Los pasos del navegador, o `null` si la app ya se abrió fijada. */
export function pinGuide(userAgent, { standalone = false } = {}) {
  if (standalone) return null;
  return GUIDES[detectPlatform(userAgent)];
}
