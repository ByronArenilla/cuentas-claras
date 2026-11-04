"""La conversación del bot, sin nada de Telegram (spec 005; principio 10).

`Conversations.handle` recibe un evento de un chat (un comando, un texto o
un botón) y devuelve las respuestas que el bot debe enviar. El adaptador de
`telegram_app.py` solo traduce entre Telegram y estos tipos.

El gasto se arma en un borrador, paso a paso: monto → espacio (si hay más de
uno) → categoría → tipo de pago → fecha → descripción → confirmación. Nada
llega a la API hasta que el usuario toca Confirmar (RF-19).
"""

import itertools
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from bot.api import ApiError, ApiRejected, ApiUnavailable, InvalidCode, NotLinked
from bot.parsing import (
    format_day,
    format_money,
    month_name,
    parse_amount,
    parse_day,
    shift_period,
)
from bot.views import remaining_text, summary_text

# Un borrador sin respuesta durante este tiempo se descarta (decisión 8).
DRAFT_TTL = timedelta(minutes=10)
# El mismo límite que la API (RF-7 de la 003).
MAX_DESCRIPTION_LENGTH = 200

PAYMENT_LABELS = {"debit": "Débito", "credit": "Crédito"}

# --- Eventos y respuestas ---


@dataclass(frozen=True)
class Command:
    """Un comando como `/vincular ABCD-EFGH`: `name="vincular"`, `args`."""

    name: str
    args: str = ""


@dataclass(frozen=True)
class Text:
    """Un mensaje de texto que no es un comando."""

    text: str


@dataclass(frozen=True)
class Press:
    """Un botón tocado; `data` es el que se le dio al crearlo."""

    data: str


Event = Command | Text | Press


@dataclass(frozen=True)
class Button:
    label: str
    data: str


@dataclass(frozen=True)
class Reply:
    """Un mensaje del bot, con filas de botones opcionales."""

    text: str
    buttons: tuple[tuple[Button, ...], ...] = ()


class Api(Protocol):
    """Lo que la conversación necesita de `bot.api.ApiClient`."""

    async def is_linked(self, chat_id: int) -> bool: ...
    async def link_chat(self, chat_id: int, code: str) -> str: ...
    async def unlink_chat(self, chat_id: int) -> None: ...
    async def spaces(self, chat_id: int) -> list[dict]: ...
    async def categories(self, chat_id: int, space_id: int) -> list[dict]: ...
    async def create_expense(self, chat_id: int, space_id: int, body: dict) -> dict: ...
    async def summary(self, chat_id: int, space_id: int, period: str) -> dict: ...


def utc_now() -> datetime:
    return datetime.now(UTC)


# --- Mensajes (RF-28: todos en español) ---

HELP = (
    "Hola, soy el bot de gastito: te ayudo a registrar tus gastos.\n\n"
    "/gasto: registrar un gasto. También puedes escribir solo el monto, "
    "por ejemplo 20.000.\n"
    "/cancelar: descartar el gasto que estás registrando.\n"
    "/resumen: cómo vas este mes frente al presupuesto.\n"
    "/ultimos: los últimos gastos registrados.\n"
    "/deshacer: borrar el último gasto que registraste.\n"
    "/vincular CÓDIGO: vincular este chat a tu cuenta de gastito.\n"
    "/desvincular: quitar la vinculación de este chat."
)
LINK_HELP = (
    "Este chat no está vinculado a ninguna cuenta de gastito. Pide un código "
    "de vinculación con tu sesión (POST /telegram/link-codes) y envíamelo "
    "así:\n/vincular ABCD-EFGH\nEl código caduca a los 10 minutos."
)
LINK_USAGE = "Envíame el código así: /vincular ABCD-EFGH"
LINK_INVALID = "Ese código no es válido, ya se usó o caducó. Pide uno nuevo."
UNLINKED = (
    "Listo: desvinculé este chat. Para volver a usarlo, vincúlalo con un código nuevo."
)
UNAVAILABLE = "No pude hablar con gastito. Intenta de nuevo en un rato."
NO_SPACES = (
    "No perteneces a ningún espacio de gastito: no hay dónde registrar el gasto."
)

ASK_AMOUNT = "¿Cuánto gastaste? Escribe el monto en pesos, por ejemplo 20.000."
AMOUNT_INVALID = (
    "No entendí el monto. Escríbelo en pesos enteros, sin decimales ni comas, "
    "por ejemplo 20000 o 20.000. El máximo es un billón."
)
ASK_SPACE = "¿En qué espacio lo registro?"
ASK_CATEGORY = "¿En qué categoría?"
ASK_PAYMENT = "¿Cómo pagaste?"
ASK_DAY = "¿Cuándo fue el gasto?"
ASK_OTHER_DAY = "Escribe la fecha como DD/MM o DD/MM/AAAA, por ejemplo 30/10."
DAY_INVALID = (
    "No entendí la fecha. Escríbela como DD/MM o DD/MM/AAAA, por ejemplo 30/10."
)
ASK_DESCRIPTION = "¿Quieres añadir una descripción? Escríbela o toca Omitir."
DESCRIPTION_TOO_LONG = (
    f"La descripción puede tener como máximo {MAX_DESCRIPTION_LENGTH} "
    "caracteres. Escribe una más corta o toca Omitir."
)
BUTTON_HINT = "Elige una de las opciones de los botones, o escribe /cancelar."
CANCELLED = "Listo, descarté el gasto. No registré nada."
NOTHING_TO_CANCEL = "No hay ningún gasto en curso."
STALE = "Esa conversación ya terminó. Escribe /gasto para registrar otro gasto."
EXPIRED = (
    "El gasto que estabas registrando caducó tras 10 minutos sin respuesta. "
    "No registré nada."
)
ASK_SPACE_FOR_SUMMARY = "¿De qué espacio quieres el resumen?"
QUERY_COMMANDS = ("resumen", "ultimos", "deshacer")
# Botones de consulta: llevan todo lo que necesitan y no dependen del
# borrador (decisión 6 de la 006).
QUERY_PREFIXES = ("sum", "last", "undo")

SAVE_UNAVAILABLE = (
    "No pude registrar el gasto porque gastito no responde. Toca Confirmar "
    "para intentarlo de nuevo o Cancelar para descartarlo."
)


# --- Borrador ---


@dataclass
class Draft:
    """El gasto que se está armando en un chat. Vive solo en memoria."""

    # Identifica el borrador en los botones: uno de un borrador anterior no
    # coincide y no cambia nada (RF-24).
    number: int
    step: str
    spaces: list[dict]
    touched_at: datetime
    amount: int | None = None
    space: dict | None = None
    categories: list[dict] = field(default_factory=list)
    category: dict | None = None
    payment_type: str | None = None
    # Nulo para "Hoy": la API usa su propio hoy (plan 005).
    spent_on: date | None = None
    day: date | None = None
    description: str | None = None

    def button(self, label: str, value: str) -> Button:
        """Botón del paso actual: `número:paso:valor`."""
        return Button(label, f"{self.number}:{self.step}:{value}")


def pairs(buttons: list[Button]) -> tuple[tuple[Button, ...], ...]:
    """Botones de dos en dos, para que las categorías no ocupen una pantalla."""
    return tuple(tuple(buttons[i : i + 2]) for i in range(0, len(buttons), 2))


class Conversations:
    """Las conversaciones de todos los chats, con sus borradores en memoria."""

    def __init__(
        self,
        api: Api,
        tz: str,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.api = api
        self.tz = ZoneInfo(tz)
        # Instante actual en UTC; los tests pasan uno fijo (principio 7).
        self.clock = clock
        self._drafts: dict[int, Draft] = {}
        self._numbers = itertools.count(1)

    def today(self) -> date:
        """Hoy en `TZ`, no en la zona del proceso (principio 7)."""
        return self.clock().astimezone(self.tz).date()

    async def handle(self, chat_id: int, event: Event) -> list[Reply]:
        """Respuestas del bot a un evento del chat."""
        replies: list[Reply] = []
        draft = self._drafts.get(chat_id)
        if draft is not None and self.clock() - draft.touched_at > DRAFT_TTL:
            # RF-23: un borrador caducado no se registra nunca.
            del self._drafts[chat_id]
            replies.append(Reply(EXPIRED))
            if isinstance(event, Press):
                return replies

        try:
            replies += await self._dispatch(chat_id, event)
        except NotLinked:
            self._drafts.pop(chat_id, None)
            replies.append(Reply(LINK_HELP))
        except ApiUnavailable:
            # En el registro, fuera de la confirmación (que lo maneja aparte,
            # RF-25), se descarta el borrador: no se registró nada. Una
            # consulta nunca toca el borrador (RF-18 de la 006).
            if not is_query(event):
                self._drafts.pop(chat_id, None)
            replies.append(Reply(UNAVAILABLE))
        except ApiRejected as error:
            # Por ejemplo, un espacio del que el usuario ya salió.
            replies.append(Reply(f"No pude completarlo: {error.detail}"))

        if chat_id in self._drafts:
            self._drafts[chat_id].touched_at = self.clock()
        return replies

    async def _dispatch(self, chat_id: int, event: Event) -> list[Reply]:
        if isinstance(event, Command):
            return await self._command(chat_id, event)
        if isinstance(event, Text):
            return await self._text(chat_id, event.text)
        return await self._press(chat_id, event.data)

    # --- Comandos ---

    async def _command(self, chat_id: int, command: Command) -> list[Reply]:
        if command.name in ("start", "ayuda"):
            return await self._help(chat_id)
        if command.name == "resumen":
            return await self._summary_start(chat_id)
        if command.name == "gasto":
            # RF-26: con un borrador en curso, `/gasto` empieza otro.
            self._drafts.pop(chat_id, None)
            return await self._start(chat_id, command.args)
        if command.name == "cancelar":
            if self._drafts.pop(chat_id, None) is None:
                return [Reply(NOTHING_TO_CANCEL)]
            return [Reply(CANCELLED)]
        if command.name == "vincular":
            self._drafts.pop(chat_id, None)
            return await self._link(chat_id, command.args)
        if command.name == "desvincular":
            self._drafts.pop(chat_id, None)
            await self.api.unlink_chat(chat_id)
            return [Reply(UNLINKED)]
        return [Reply(HELP)]

    async def _help(self, chat_id: int) -> list[Reply]:
        """Los comandos y, si el chat no está vinculado, cómo vincularlo
        (RF-27). Saber si lo está no toca ninguna ruta de datos (RF-7)."""
        if await self.api.is_linked(chat_id):
            return [Reply(HELP)]
        return [Reply(HELP), Reply(LINK_HELP)]

    async def _link(self, chat_id: int, code: str) -> list[Reply]:
        """`/vincular CÓDIGO` (RF-3, RF-4)."""
        if not code.strip():
            return [Reply(LINK_USAGE)]
        try:
            email = await self.api.link_chat(chat_id, code.strip())
        except InvalidCode:
            return [Reply(LINK_INVALID)]
        return [
            Reply(
                f"Listo: este chat quedó vinculado a {email}. Ya puedes "
                "registrar gastos con /gasto."
            )
        ]

    # --- Textos ---

    async def _text(self, chat_id: int, text: str) -> list[Reply]:
        draft = self._drafts.get(chat_id)
        if draft is None:
            # RF-12: un monto solo empieza un gasto; otra cosa, la ayuda.
            if parse_amount(text) is not None:
                return await self._start(chat_id, text)
            return [Reply(HELP)]
        if draft.step == "amount":
            return await self._take_amount(chat_id, draft, text)
        if draft.step == "other_day":
            return self._take_day(draft, text)
        if draft.step == "description":
            return self._take_description(draft, text)
        # RF-26: en un paso de botones, el texto no cambia el borrador.
        return [Reply(BUTTON_HINT)]

    # --- Botones ---

    async def _press(self, chat_id: int, data: str) -> list[Reply]:
        if is_query(Press(data)):
            # Antes de mirar el borrador: estos botones no lo tocan (RF-18).
            return await self._query_press(chat_id, data)
        draft = self._drafts.get(chat_id)
        number, _, rest = data.partition(":")
        step, _, value = rest.partition(":")
        if draft is None or str(draft.number) != number or draft.step != step:
            # RF-24 y RF-20: un botón de otro borrador o de otro paso, o un
            # segundo Confirmar, no cambia nada.
            return [Reply(STALE)]
        if step == "space":
            return await self._take_space(chat_id, draft, value)
        if step == "category":
            return self._take_category(draft, value)
        if step == "payment":
            return self._take_payment(draft, value)
        if step == "day":
            return self._take_day_button(draft, value)
        if step == "description":
            draft.description = None
            return self._ask_confirmation(draft)
        if step == "confirm":
            if value == "ok":
                return await self._save(chat_id, draft)
            del self._drafts[chat_id]
            return [Reply(CANCELLED)]
        return [Reply(STALE)]

    # --- Pasos ---

    async def _start(self, chat_id: int, amount_text: str) -> list[Reply]:
        """Empieza un borrador. Lo primero es pedir los espacios: si el chat
        no está vinculado, `NotLinked` corta aquí sin tocar nada (RF-7)."""
        spaces = await self.api.spaces(chat_id)
        if not spaces:
            return [Reply(NO_SPACES)]
        draft = Draft(
            number=next(self._numbers),
            step="amount",
            spaces=spaces,
            touched_at=self.clock(),
        )
        self._drafts[chat_id] = draft
        if not amount_text.strip():
            return [Reply(ASK_AMOUNT)]
        return await self._take_amount(chat_id, draft, amount_text)

    async def _take_amount(self, chat_id: int, draft: Draft, text: str) -> list[Reply]:
        amount = parse_amount(text)
        if amount is None:
            return [Reply(AMOUNT_INVALID)]  # RF-13: sin avanzar.
        draft.amount = amount
        if len(draft.spaces) == 1:
            # RF-14: con un solo espacio no se pregunta.
            draft.space = draft.spaces[0]
            return await self._ask_category(chat_id, draft)
        draft.step = "space"
        buttons = tuple(
            (draft.button(space["name"], str(space["id"])),) for space in draft.spaces
        )
        return [Reply(ASK_SPACE, buttons)]

    async def _take_space(self, chat_id: int, draft: Draft, value: str) -> list[Reply]:
        space = next((s for s in draft.spaces if str(s["id"]) == value), None)
        if space is None:
            return [Reply(STALE)]
        draft.space = space
        return await self._ask_category(chat_id, draft)

    async def _ask_category(self, chat_id: int, draft: Draft) -> list[Reply]:
        """Las categorías del espacio, en el orden de la API (RF-15)."""
        assert draft.space is not None
        draft.categories = await self.api.categories(chat_id, draft.space["id"])
        draft.step = "category"
        buttons = [draft.button(c["name"], str(c["id"])) for c in draft.categories]
        return [Reply(ASK_CATEGORY, pairs(buttons))]

    def _take_category(self, draft: Draft, value: str) -> list[Reply]:
        category = next((c for c in draft.categories if str(c["id"]) == value), None)
        if category is None:
            return [Reply(STALE)]
        draft.category = category
        draft.step = "payment"
        buttons = tuple(
            draft.button(label, key) for key, label in PAYMENT_LABELS.items()
        )
        return [Reply(ASK_PAYMENT, (buttons,))]

    def _take_payment(self, draft: Draft, value: str) -> list[Reply]:
        if value not in PAYMENT_LABELS:
            return [Reply(STALE)]
        draft.payment_type = value
        draft.step = "day"
        buttons = (
            draft.button("Hoy", "today"),
            draft.button("Ayer", "yesterday"),
            draft.button("Otra fecha", "other"),
        )
        return [Reply(ASK_DAY, (buttons,))]

    def _take_day_button(self, draft: Draft, value: str) -> list[Reply]:
        """Hoy y ayer en `TZ` (RF-17, decisión 5)."""
        today = self.today()
        if value == "today":
            draft.spent_on, draft.day = None, today
        elif value == "yesterday":
            draft.spent_on = draft.day = today - timedelta(days=1)
        elif value == "other":
            draft.step = "other_day"
            return [Reply(ASK_OTHER_DAY)]
        else:
            return [Reply(STALE)]
        return self._ask_description(draft)

    def _take_day(self, draft: Draft, text: str) -> list[Reply]:
        today = self.today()
        day = parse_day(text, today)
        if day is None:
            return [Reply(DAY_INVALID)]
        if day > today:
            # RF-17; RF-6 de la 003: un gasto es dinero que ya salió.
            return [
                Reply(
                    "La fecha no puede ser posterior a hoy "
                    f"({format_day(today, today).removeprefix('hoy, ')}). "
                    "Escribe otra."
                )
            ]
        draft.spent_on = draft.day = day
        return self._ask_description(draft)

    def _ask_description(self, draft: Draft) -> list[Reply]:
        draft.step = "description"
        return [Reply(ASK_DESCRIPTION, ((draft.button("Omitir", "skip"),),))]

    def _take_description(self, draft: Draft, text: str) -> list[Reply]:
        description = text.strip()
        if len(description) > MAX_DESCRIPTION_LENGTH:
            # RF-18: se pide de nuevo, con Omitir a mano.
            return [Reply(DESCRIPTION_TOO_LONG, ((draft.button("Omitir", "skip"),),))]
        draft.description = description or None
        return self._ask_confirmation(draft)

    def _ask_confirmation(self, draft: Draft) -> list[Reply]:
        """El borrador completo con Confirmar y Cancelar (RF-19). El espacio
        se muestra siempre, también si es el único (decisión 2)."""
        assert draft.amount is not None and draft.space is not None
        assert draft.category is not None and draft.payment_type is not None
        assert draft.day is not None
        draft.step = "confirm"
        lines = [
            "Revisa el gasto antes de registrarlo:",
            "",
            f"Monto: {format_money(draft.amount)}",
            f"Pago: {PAYMENT_LABELS[draft.payment_type]}",
            f"Categoría: {draft.category['name']}",
            f"Espacio: {draft.space['name']}",
            f"Fecha: {format_day(draft.day, self.today())}",
            f"Descripción: {draft.description or 'sin descripción'}",
        ]
        return [Reply("\n".join(lines), self._confirm_buttons(draft))]

    @staticmethod
    def _confirm_buttons(draft: Draft) -> tuple[tuple[Button, ...], ...]:
        return ((draft.button("Confirmar", "ok"), draft.button("Cancelar", "cancel")),)

    async def _save(self, chat_id: int, draft: Draft) -> list[Reply]:
        """Registra el gasto una sola vez (RF-20) y añade la línea del
        presupuesto (RF-21)."""
        assert draft.space is not None and draft.category is not None
        # Mientras se guarda, el paso no es "confirm": un segundo Confirmar
        # no coincide y no registra otra vez (RF-20).
        draft.step = "saving"
        body: dict = {
            "amount": draft.amount,
            "payment_type": draft.payment_type,
            "category_id": draft.category["id"],
        }
        if draft.spent_on is not None:
            body["spent_on"] = draft.spent_on.isoformat()
        if draft.description is not None:
            body["description"] = draft.description
        try:
            expense = await self.api.create_expense(chat_id, draft.space["id"], body)
        except ApiUnavailable:
            # RF-25: el borrador vuelve a la confirmación para reintentar.
            draft.step = "confirm"
            return [Reply(SAVE_UNAVAILABLE, self._confirm_buttons(draft))]
        except ApiRejected as error:
            del self._drafts[chat_id]
            return [Reply(f"No pude registrar el gasto: {error.detail}")]

        del self._drafts[chat_id]
        assert draft.amount is not None
        text = (
            f"Gasto registrado: {format_money(draft.amount)} en "
            f"{draft.category['name']}."
        )
        line = await self._budget_line(chat_id, draft, expense)
        return [Reply(text if line is None else f"{text}\n{line}")]

    async def _budget_line(
        self, chat_id: int, draft: Draft, expense: dict
    ) -> str | None:
        """Cómo va el presupuesto de la categoría en el mes del gasto
        (RF-21, decisión 4). Si el resumen falla, no hay línea."""
        assert draft.space is not None and draft.category is not None
        period = str(expense["spent_on"])[:7]
        try:
            summary = await self.api.summary(chat_id, draft.space["id"], period)
        except ApiError:
            return None
        row = next(
            (
                r
                for r in summary["categories"]
                if r["category_id"] == draft.category["id"]
            ),
            None,
        )
        if row is None:
            return None
        month = month_name(int(period[5:7]))
        name, spent = row["name"], format_money(row["spent"])
        if row["budget"] is None:
            return f"{name}: llevas {spent} en {month}. No tiene presupuesto."
        line = f"{name}: llevas {spent} de {format_money(row['budget'])} en {month}."
        return f"{line} {remaining_text(row['remaining'])}"

    # --- Consultas (spec 006) ---

    def current_period(self) -> str:
        """El mes actual en `TZ`, como `AAAA-MM` (principio 7)."""
        today = self.today()
        return f"{today.year:04d}-{today.month:02d}"

    async def _query_press(self, chat_id: int, data: str) -> list[Reply]:
        """Botones sin estado: `sum:<espacio>:<mes>`, `last:<espacio>`,
        `undo:<espacio>:<gasto>` y `undo:no`. Un dato mal formado no hace
        nada."""
        kind, _, rest = data.partition(":")
        parts = rest.split(":")
        try:
            if kind == "sum" and len(parts) == 2 and is_period(parts[1]):
                return await self._show_summary(chat_id, int(parts[0]), parts[1])
        except ValueError:
            pass
        return [Reply(STALE)]

    async def _space_name(self, chat_id: int, space_id: int) -> str:
        """El nombre del espacio, que el botón no lleva para no pasar de los
        64 bytes de `callback_data`."""
        spaces = await self.api.spaces(chat_id)
        return next((s["name"] for s in spaces if s["id"] == space_id), "Espacio")

    async def _summary_start(self, chat_id: int) -> list[Reply]:
        """`/resumen`: el mes actual del único espacio, o los botones para
        elegirlo (RF-5, decisión 5)."""
        spaces = await self.api.spaces(chat_id)
        if not spaces:
            return [Reply(NO_SPACES)]
        period = self.current_period()
        if len(spaces) == 1:
            return await self._show_summary(chat_id, spaces[0]["id"], period)
        buttons = tuple(
            (Button(space["name"], f"sum:{space['id']}:{period}"),) for space in spaces
        )
        return [Reply(ASK_SPACE_FOR_SUMMARY, buttons)]

    async def _show_summary(
        self, chat_id: int, space_id: int, period: str
    ) -> list[Reply]:
        """El resumen del mes con ‹ y › para moverse (RF-6 a RF-8)."""
        name = await self._space_name(chat_id, space_id)
        summary = await self.api.summary(chat_id, space_id, period)
        before, after = shift_period(period, -1), shift_period(period, 1)
        buttons = (
            (
                Button(f"‹ {month_name(int(before[5:7]))}", f"sum:{space_id}:{before}"),
                Button(f"{month_name(int(after[5:7]))} ›", f"sum:{space_id}:{after}"),
            ),
        )
        return [Reply(summary_text(name, summary), buttons)]


def is_period(text: str) -> bool:
    """Si el texto es un mes `AAAA-MM` válido."""
    return (
        len(text) == 7
        and text[4] == "-"
        and text[:4].isascii()
        and text[:4].isdigit()
        and text[5:].isascii()
        and text[5:].isdigit()
        and 1 <= int(text[5:]) <= 12
    )


def is_query(event: Event) -> bool:
    """Si el evento es una consulta de la 006, que no toca el borrador."""
    if isinstance(event, Command):
        return event.name in QUERY_COMMANDS
    if isinstance(event, Press):
        return event.data.partition(":")[0] in QUERY_PREFIXES
    return False
