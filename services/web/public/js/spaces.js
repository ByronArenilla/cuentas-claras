// Espacios, sin DOM (spec 011, RF-23 a RF-26): crear, salir y compartir con
// un enlace (ADR 0005, decisión 18).

/** Crea el espacio y pasa a él (RF-24). */
export async function createSpace({ api, session }, name) {
  const space = await api.post("/spaces", { name });
  session.setSpace(space.id);
  return space;
}

/** Sale del espacio y pasa al primero que quede (RF-26). Si la API no deja
 * (único espacio o último miembro), el error trae su mensaje. */
export async function leaveSpace({ api, session }, space, spaces) {
  await api.del(`/spaces/${space.id}/members/me`);
  return session.chooseSpace(spaces.filter((candidate) => candidate.id !== space.id));
}

/** Lo que se comparte: el enlace y por qué hay que usarlo pronto. */
export function shareText(invitation, spaceName) {
  return {
    title: `Únete a «${spaceName}» en gastito`,
    text:
      `Te invito a «${spaceName}» en gastito, para llevar juntos el presupuesto. ` +
      "El enlace es de un solo uso y caduca en 24 horas.",
    url: invitation.url,
  };
}

/** Pide un enlace y lo comparte con el menú del sistema (Web Share API) o,
 * si no hay, lo copia. Devuelve `{ how, url }`: `how` es "shared",
 * "copied", "cancelled" o "manual" (no se pudo copiar: hay que mostrar el
 * enlace). */
export async function shareInvitation({ api }, space, { share, copy }) {
  const invitation = await api.post(`/spaces/${space.id}/invitations`);
  const data = shareText(invitation, space.name);
  if (share) {
    try {
      await share(data);
      return { how: "shared", url: invitation.url };
    } catch (error) {
      if (error.name === "AbortError") return { how: "cancelled", url: invitation.url };
    }
  }
  try {
    await copy(invitation.url);
    return { how: "copied", url: invitation.url };
  } catch {
    return { how: "manual", url: invitation.url };
  }
}
