"""API falsa en memoria para probar la conversación sin red ni Telegram."""

from bot.api import ApiUnavailable, InvalidCode, NotLinked

VALID_CODE = "ABCD-EFGH"
EMAIL = "ana@example.com"

CATEGORIES = [
    {"id": 1, "name": "Hogar"},
    {"id": 2, "name": "Comida"},
    {"id": 3, "name": "Transporte"},
]


class FakeApi:
    """Lo mínimo de `ApiClient` que usa la conversación.

    `calls` guarda el nombre de cada llamada, para comprobar qué rutas se
    tocaron; `expenses` guarda los gastos registrados.
    """

    def __init__(self, linked: bool = True, spaces: list[dict] | None = None) -> None:
        self.linked = linked
        self.spaces_list = spaces or [{"id": 1, "name": "Personal"}]
        self.categories_list = CATEGORIES
        self.calls: list[str] = []
        self.expenses: list[tuple[int, dict]] = []
        self.summary_reply: dict | Exception | None = None
        self.create_error: Exception | None = None

    def _data(self, name: str) -> None:
        self.calls.append(name)
        if not self.linked:
            raise NotLinked("Este chat no está vinculado.")

    async def is_linked(self, chat_id: int) -> bool:
        self.calls.append("is_linked")
        return self.linked

    async def link_chat(self, chat_id: int, code: str) -> str:
        self.calls.append("link_chat")
        if code != VALID_CODE:
            raise InvalidCode("El código no es válido, ya se usó o caducó.")
        self.linked = True
        return EMAIL

    async def unlink_chat(self, chat_id: int) -> None:
        self.calls.append("unlink_chat")
        self.linked = False

    async def spaces(self, chat_id: int) -> list[dict]:
        self._data("spaces")
        return self.spaces_list

    async def categories(self, chat_id: int, space_id: int) -> list[dict]:
        self._data("categories")
        return self.categories_list

    async def create_expense(self, chat_id: int, space_id: int, body: dict) -> dict:
        self._data("create_expense")
        if self.create_error is not None:
            raise self.create_error
        self.expenses.append((space_id, body))
        spent_on = body.get("spent_on", "2026-10-31")
        return {"id": len(self.expenses), **body, "spent_on": spent_on}

    async def summary(self, chat_id: int, space_id: int, period: str) -> dict:
        self._data("summary")
        if isinstance(self.summary_reply, Exception):
            raise self.summary_reply
        if self.summary_reply is None:
            raise ApiUnavailable("sin resumen")
        return self.summary_reply
