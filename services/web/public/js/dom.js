// Ayudante para armar el DOM sin `innerHTML` (spec 011, plan): el texto
// siempre entra como texto, así que una descripción como `<img onerror=…>`
// se muestra tal cual y nunca se ejecuta. Complementa la CSP.
//
//   h("button", { class: "button", type: "button", onClick: guardar }, "Guardar")

export function h(tag, props = {}, ...children) {
  const element = document.createElement(tag);
  for (const [key, value] of Object.entries(props ?? {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key.startsWith("on") && typeof value === "function") {
      element.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (key === "class") {
      element.className = value;
    } else if (key === "dataset") {
      Object.assign(element.dataset, value);
    } else if (key === "value") {
      element.value = value;
    } else if (value === true) {
      element.setAttribute(key, "");
    } else {
      element.setAttribute(key, String(value));
    }
  }
  append(element, ...children);
  return element;
}

export function append(element, ...children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    element.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return element;
}
