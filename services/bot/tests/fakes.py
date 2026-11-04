"""API falsa en memoria para probar la conversación sin red ni Telegram."""

from bot.api import ApiUnavailable, InvalidCode, NotFound, NotLinked

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
        # Spec 006: resúmenes por (espacio, mes), últimos gastos por espacio
        # (del más reciente al más antiguo) y gastos borrados.
        self.summaries: dict[tuple[int, str], dict] = {}
        self.summary_requests: list[tuple[int, str]] = []
        self.recent: dict[int, list[dict]] = {}
        self.deleted: list[tuple[int, int]] = []
        self.me_id = 1
        self.down = False

    def _data(self, name: str) -> None:
        self.calls.append(name)
        if not self.linked:
            raise NotLinked("Este chat no está vinculado.")
        if self.down:
            raise ApiUnavailable("caída")

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
        self.summary_requests.append((space_id, period))
        if isinstance(self.summary_reply, Exception):
            raise self.summary_reply
        if self.summary_reply is not None:
            return self.summary_reply
        if (space_id, period) in self.summaries:
            return self.summaries[(space_id, period)]
        raise ApiUnavailable("sin resumen")

    async def me(self, chat_id: int) -> dict:
        self._data("me")
        return {"id": self.me_id, "email": EMAIL}

    async def recent_expenses(
        self, chat_id: int, space_id: int, limit: int = 5, mine: bool = False
    ) -> list[dict]:
        self._data("recent_expenses")
        expenses = [
            e
            for e in self.recent.get(space_id, [])
            if (space_id, e["id"]) not in self.deleted
            and (not mine or e["created_by"] == self.me_id)
        ]
        return expenses[:limit]

    async def delete_expense(
        self, chat_id: int, space_id: int, expense_id: int
    ) -> None:
        self._data("delete_expense")
        exists = any(e["id"] == expense_id for e in self.recent.get(space_id, []))
        if not exists or (space_id, expense_id) in self.deleted:
            raise NotFound("Gasto no encontrado.")
        self.deleted.append((space_id, expense_id))
