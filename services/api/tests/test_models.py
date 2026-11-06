from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import Engine, delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    BudgetItem,
    Card,
    CardStatement,
    Category,
    Expense,
    Income,
    Invitation,
    Membership,
    Prepayment,
    Space,
    User,
    category_key,
)


def make_user(session: Session, email: str = "ana@example.com") -> User:
    user = User(email=email, password_hash="hash")
    session.add(user)
    session.flush()
    return user


def make_space(session: Session, name: str = "Casa") -> Space:
    space = Space(name=name)
    session.add(space)
    session.flush()
    return space


def test_foreign_keys_are_on_in_a_new_connection(engine: Engine) -> None:
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_membership_to_missing_space_is_rejected(session: Session) -> None:
    user = make_user(session)
    session.add(Membership(user_id=user.id, space_id=999))

    with pytest.raises(IntegrityError):
        session.flush()


def test_deleting_space_cascades_to_its_memberships(session: Session) -> None:
    user = make_user(session)
    doomed, kept = make_space(session, "Casa"), make_space(session, "Viajes")
    session.add_all(
        [
            Membership(user_id=user.id, space_id=doomed.id),
            Membership(user_id=user.id, space_id=kept.id),
        ]
    )
    session.flush()

    session.delete(doomed)
    session.flush()

    remaining = session.scalars(select(Membership.space_id)).all()
    assert remaining == [kept.id]
    assert session.get(User, user.id) is not None


def test_same_user_cannot_join_same_space_twice(session: Session) -> None:
    user = make_user(session)
    space = make_space(session)
    session.add(Membership(user_id=user.id, space_id=space.id))
    session.flush()

    session.add(Membership(user_id=user.id, space_id=space.id))
    with pytest.raises(IntegrityError):
        session.flush()


def test_email_is_unique(session: Session) -> None:
    make_user(session, "ana@example.com")

    with pytest.raises(IntegrityError):
        make_user(session, "ana@example.com")


def test_invitation_without_a_space_is_rejected(session: Session) -> None:
    # Desde el ADR 0005 toda invitación es de espacio (RF-15).
    user = make_user(session)
    session.add(
        Invitation(
            code_hash="abc",
            created_by=user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
    )

    with pytest.raises(IntegrityError):
        session.flush()


def test_dates_come_back_in_utc(session: Session) -> None:
    user = make_user(session)
    session.expire_all()

    created_at = session.get(User, user.id).created_at
    assert created_at.tzinfo is UTC


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (" Comida ", "comida"),
        ("Cómida", "comida"),
        ("Educacion", "Educación"),
        ("AÑO", "año"),
        ("Pingüino", "pinguino"),
    ],
)
def test_category_key_ignores_case_accents_and_surrounding_spaces(
    first: str, second: str
) -> None:
    # Spec 002, decisión 4.
    assert category_key(first) == category_key(second)


def test_category_key_keeps_the_enye_apart_from_the_n() -> None:
    # La ñ es una letra propia: "Año" y "Ano" son categorías distintas.
    assert category_key("Año") != category_key("Ano")


def test_category_fills_its_key_from_the_name(session: Session) -> None:
    category = Category(space_id=make_space(session).id, name="Educación")

    assert category.name_key == category_key("Educación")


def test_same_key_is_rejected_within_a_space(session: Session) -> None:
    # RF-8: la base de datos frena el duplicado aunque el código no lo vea.
    space = make_space(session)
    session.add(Category(space_id=space.id, name="Comida"))
    session.flush()

    session.add(Category(space_id=space.id, name="cómida"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_same_key_is_allowed_in_different_spaces(session: Session) -> None:
    # RF-9: cada espacio tiene sus propias categorías.
    casa, viajes = make_space(session, "Casa"), make_space(session, "Viajes")
    session.add_all(
        [
            Category(space_id=casa.id, name="Comida"),
            Category(space_id=viajes.id, name="Comida"),
        ]
    )
    session.flush()

    assert len(session.scalars(select(Category)).all()) == 2


def test_category_to_missing_space_is_rejected(session: Session) -> None:
    # RF-2: toda categoría pertenece a un espacio que existe.
    session.add(Category(space_id=999, name="Comida"))

    with pytest.raises(IntegrityError):
        session.flush()


def test_deleting_space_cascades_to_its_categories(session: Session) -> None:
    # RF-11.
    doomed, kept = make_space(session, "Casa"), make_space(session, "Viajes")
    session.add_all(
        [
            Category(space_id=doomed.id, name="Comida"),
            Category(space_id=kept.id, name="Comida"),
        ]
    )
    session.flush()

    session.delete(doomed)
    session.flush()

    remaining = session.scalars(select(Category.space_id)).all()
    assert remaining == [kept.id]


def make_expense(
    session: Session, space: Space, user: User, **fields: object
) -> Expense:
    """Gasto válido en `space`, con una categoría nueva de ese espacio."""
    category = Category(space_id=space.id, name=f"Comida {space.id}")
    session.add(category)
    session.flush()
    values: dict[str, object] = {
        "space_id": space.id,
        "category_id": category.id,
        "created_by": user.id,
        "amount": 20_000,
        "payment_type": "debit",
        "spent_on": date(2026, 10, 31),
        **fields,
    }
    expense = Expense(**values)
    session.add(expense)
    session.flush()
    return expense


def test_expense_is_saved_and_read_back(session: Session) -> None:
    user, space = make_user(session), make_space(session)
    expense = make_expense(session, space, user, description="Mercado")
    session.expire_all()

    saved = session.get(Expense, expense.id)
    assert saved.amount == 20_000
    assert saved.payment_type == "debit"
    assert saved.spent_on == date(2026, 10, 31)
    assert type(saved.spent_on) is date
    assert saved.description == "Mercado"
    assert saved.created_by == user.id
    assert saved.created_at.tzinfo is UTC


def test_expense_description_is_optional(session: Session) -> None:
    expense = make_expense(session, make_space(session), make_user(session))

    assert expense.description is None


@pytest.mark.parametrize("amount", [0, -1])
def test_database_rejects_amount_not_greater_than_zero(
    session: Session, amount: int
) -> None:
    # RF-3: última defensa si algo salta la validación de la API.
    with pytest.raises(IntegrityError):
        make_expense(session, make_space(session), make_user(session), amount=amount)


@pytest.mark.parametrize("payment_type", ["cash", "CREDIT", ""])
def test_database_rejects_unknown_payment_type(
    session: Session, payment_type: str
) -> None:
    # RF-4: solo `credit` o `debit`.
    with pytest.raises(IntegrityError):
        make_expense(
            session,
            make_space(session),
            make_user(session),
            payment_type=payment_type,
        )


def test_amount_of_one_trillion_fits(session: Session) -> None:
    # El tope de la decisión 7 no cabe en un entero de 32 bits.
    expense = make_expense(
        session, make_space(session), make_user(session), amount=1_000_000_000_000
    )
    session.expire_all()

    assert session.get(Expense, expense.id).amount == 1_000_000_000_000


def test_deleting_space_cascades_to_its_expenses_and_categories(
    session: Session,
) -> None:
    # RF-21. Se borra con una sentencia, como la ruta de la spec 001: la
    # cascada quita categorías y gastos a la vez y `category_id` no choca.
    user = make_user(session)
    doomed, kept = make_space(session, "Casa"), make_space(session, "Viajes")
    make_expense(session, doomed, user)
    kept_expense = make_expense(session, kept, user)

    session.execute(delete(Space).where(Space.id == doomed.id))
    session.flush()

    assert session.scalars(select(Expense.id)).all() == [kept_expense.id]
    assert session.scalars(select(Category.space_id)).all() == [kept.id]


# --- Categorías (helper compartido) ---


def make_category(session: Session, space: Space, name: str = "Comida") -> Category:
    category = Category(space_id=space.id, name=name)
    session.add(category)
    session.flush()
    return category


# --- Rubros, ingresos y categorías eliminadas (spec 008) ---


def make_item(session: Session, category: Category, **fields: object) -> BudgetItem:
    """Rubro "Mercado" de `category` en noviembre de 2026, salvo otro indicado."""
    values: dict[str, object] = {
        "space_id": category.space_id,
        "category_id": category.id,
        "period_start": date(2026, 11, 1),
        "name": "Mercado",
        "amount": 800_000,
        **fields,
    }
    item = BudgetItem(**values)
    session.add(item)
    session.flush()
    return item


def make_income(session: Session, space: Space, **fields: object) -> Income:
    """Ingreso "Salario" del espacio en noviembre de 2026, salvo otro indicado."""
    values: dict[str, object] = {
        "space_id": space.id,
        "period_start": date(2026, 11, 1),
        "name": "Salario",
        "amount": 5_000_000,
        **fields,
    }
    income = Income(**values)
    session.add(income)
    session.flush()
    return income


def test_budget_item_is_saved_and_read_back(session: Session) -> None:
    category = make_category(session, make_space(session))
    item = make_item(session, category, name="Acción de gracias")
    session.expire_all()

    saved = session.get(BudgetItem, item.id)
    assert saved.period_start == date(2026, 11, 1)
    assert type(saved.period_start) is date
    assert saved.name == "Acción de gracias"
    assert saved.name_key == category_key("Acción de gracias")
    assert saved.category_id == category.id
    assert saved.amount == 800_000
    assert saved.created_at.tzinfo is UTC


def test_income_is_saved_and_read_back(session: Session) -> None:
    income = make_income(session, make_space(session), name="Bonificación")
    session.expire_all()

    saved = session.get(Income, income.id)
    assert saved.period_start == date(2026, 11, 1)
    assert saved.name == "Bonificación"
    assert saved.name_key == "bonificacion"
    assert saved.amount == 5_000_000
    assert saved.created_at.tzinfo is UTC


@pytest.mark.parametrize("amount", [0, -1])
def test_database_rejects_item_or_income_not_greater_than_zero(
    session: Session, amount: int
) -> None:
    # RF-4: última defensa tras la validación de la API.
    space = make_space(session)
    with pytest.raises(IntegrityError):
        make_item(session, make_category(session, space), amount=amount)
    session.rollback()

    with pytest.raises(IntegrityError):
        make_income(session, make_space(session), amount=amount)


def test_equivalent_item_names_clash_in_the_same_space_and_month(
    session: Session,
) -> None:
    # RF-3, decisión 22: "accion" choca con "Acción" en el mismo mes.
    category = make_category(session, make_space(session))
    make_item(session, category, name="Acción")

    with pytest.raises(IntegrityError):
        make_item(session, category, name="accion")


def test_equivalent_income_names_clash_in_the_same_space_and_month(
    session: Session,
) -> None:
    space = make_space(session)
    make_income(session, space, name="Salario")

    with pytest.raises(IntegrityError):
        make_income(session, space, name="SALARIO")


def test_same_names_are_allowed_in_another_month_or_space(session: Session) -> None:
    casa, viajes = make_space(session, "Casa"), make_space(session, "Viajes")
    comida_casa = make_category(session, casa)
    make_item(session, comida_casa)
    make_item(session, comida_casa, period_start=date(2026, 12, 1))
    make_item(session, make_category(session, viajes))
    make_income(session, casa)
    make_income(session, casa, period_start=date(2026, 12, 1))
    make_income(session, viajes)

    assert len(session.scalars(select(BudgetItem)).all()) == 3
    assert len(session.scalars(select(Income)).all()) == 3


def test_expense_can_have_a_budget_item_or_none(session: Session) -> None:
    user, space = make_user(session), make_space(session)
    unplanned = make_expense(session, space, user)
    item = make_item(session, session.get(Category, unplanned.category_id))
    # Directo y no con `make_expense`, que crearía otra categoría "Comida N"
    # con el mismo nombre en el mismo espacio.
    planned = Expense(
        space_id=space.id,
        category_id=item.category_id,
        budget_item_id=item.id,
        created_by=user.id,
        amount=412_000,
        payment_type="debit",
        spent_on=date(2026, 11, 3),
    )
    session.add(planned)
    session.flush()
    session.expire_all()

    assert session.get(Expense, unplanned.id).budget_item_id is None
    assert session.get(Expense, planned.id).budget_item_id == item.id


def test_expense_with_a_missing_budget_item_is_rejected(session: Session) -> None:
    with pytest.raises(IntegrityError):
        make_expense(
            session, make_space(session), make_user(session), budget_item_id=999
        )


def test_categories_start_not_deleted(session: Session) -> None:
    category = make_category(session, make_space(session))
    session.expire_all()

    assert session.get(Category, category.id).deleted_at is None


def test_deleting_space_cascades_to_items_incomes_and_linked_expenses(
    session: Session,
) -> None:
    # RF-30. Con gastos ligados a rubros: la cascada quita gastos, rubros,
    # ingresos y categorías en la misma sentencia y ninguna clave foránea
    # sin `ON DELETE` choca (plan 008).
    user = make_user(session)
    doomed, kept = make_space(session, "Casa"), make_space(session, "Viajes")
    for space in (doomed, kept):
        item = make_item(session, make_category(session, space))
        make_expense(
            session, space, user, category_id=item.category_id, budget_item_id=item.id
        )
        make_income(session, space)

    session.execute(delete(Space).where(Space.id == doomed.id))
    session.flush()

    assert session.scalars(select(BudgetItem.space_id)).all() == [kept.id]
    assert session.scalars(select(Income.space_id)).all() == [kept.id]
    assert set(session.scalars(select(Expense.space_id)).all()) == {kept.id}


# --- Tarjetas, compras con tarjeta, abonos y extractos (spec 009) ---


def make_card(session: Session, space: Space, **fields: object) -> Card:
    """Tarjeta "Visa" con corte 25, pago 10 y tasa 1,90 %, salvo otro dato."""
    values: dict[str, object] = {
        "space_id": space.id,
        "name": "Visa",
        "cutoff_day": 25,
        "due_day": 10,
        "monthly_rate_bp": 190,
        **fields,
    }
    card = Card(**values)
    session.add(card)
    session.flush()
    return card


def make_purchase(
    session: Session, space: Space, user: User, card: Card, **fields: object
) -> Expense:
    """Compra con tarjeta "Compra TV" a 6 cuotas, con primera cuota en 2026-12."""
    values: dict[str, object] = {
        "payment_type": "credit",
        "card_id": card.id,
        "installments": 6,
        "first_due_start": date(2026, 12, 1),
        "amount": 1_200_000,
        "spent_on": date(2026, 11, 12),
        "description": "Compra TV",
        # Deuda, como trataba la 009 toda compra con tarjeta (spec 010).
        "is_debt": True,
        **fields,
    }
    return make_expense(session, space, user, **values)


def test_card_is_saved_with_its_name_key(session: Session) -> None:
    card = make_card(session, make_space(session), name="Visa Éxito")
    session.expire_all()

    saved = session.get(Card, card.id)
    assert saved.name_key == "visa exito"
    assert saved.monthly_rate_bp == 190
    assert saved.deleted_at is None


def test_card_rate_is_optional(session: Session) -> None:
    card = make_card(session, make_space(session), monthly_rate_bp=None)
    session.expire_all()

    assert session.get(Card, card.id).monthly_rate_bp is None


@pytest.mark.parametrize(
    "fields",
    [
        {"cutoff_day": 0},
        {"cutoff_day": 32},
        {"due_day": 0},
        {"due_day": 32},
        {"monthly_rate_bp": 0},
        {"monthly_rate_bp": 1001},
    ],
)
def test_database_rejects_invalid_card_days_and_rate(
    session: Session, fields: dict[str, object]
) -> None:
    with pytest.raises(IntegrityError):
        make_card(session, make_space(session), **fields)


def test_equivalent_card_names_clash_in_the_same_space(session: Session) -> None:
    space = make_space(session)
    make_card(session, space, name="Visa")

    with pytest.raises(IntegrityError):
        make_card(session, space, name=" VISA ")


def test_same_card_name_is_allowed_in_another_space(session: Session) -> None:
    make_card(session, make_space(session, "Casa"))
    make_card(session, make_space(session, "Viajes"))

    assert len(session.scalars(select(Card)).all()) == 2


def test_card_purchase_is_saved_and_read_back(session: Session) -> None:
    user, space = make_user(session), make_space(session)
    purchase = make_purchase(session, space, user, make_card(session, space))
    session.expire_all()

    saved = session.get(Expense, purchase.id)
    assert saved.installments == 6
    assert saved.first_due_start == date(2026, 12, 1)


def test_expense_without_card_has_no_card_fields(session: Session) -> None:
    expense = make_expense(session, make_space(session), make_user(session))
    session.expire_all()

    saved = session.get(Expense, expense.id)
    assert (saved.card_id, saved.installments, saved.first_due_start) == (
        None,
        None,
        None,
    )


@pytest.mark.parametrize(
    "fields",
    [
        {"payment_type": "debit"},
        {"installments": None},
        {"installments": 0},
        {"installments": 49},
        {"first_due_start": None},
        # Spec 010: con tarjeta siempre se sabe si es deuda, y a varias cuotas
        # lo es.
        {"is_debt": None},
        {"is_debt": False},
    ],
)
def test_database_rejects_a_malformed_card_purchase(
    session: Session, fields: dict[str, object]
) -> None:
    user, space = make_user(session), make_space(session)
    card = make_card(session, space)

    with pytest.raises(IntegrityError):
        make_purchase(session, space, user, card, **fields)


def test_database_rejects_a_card_purchase_with_a_budget_item(session: Session) -> None:
    user, space = make_user(session), make_space(session)
    card = make_card(session, space)
    item = make_item(session, make_category(session, space, "Hogar"))

    with pytest.raises(IntegrityError):
        make_purchase(session, space, user, card, budget_item_id=item.id)


@pytest.mark.parametrize(
    "fields",
    [
        {"installments": 1},
        {"first_due_start": date(2026, 12, 1)},
        {"is_debt": False},
    ],
)
def test_database_rejects_card_fields_without_a_card(
    session: Session, fields: dict[str, object]
) -> None:
    with pytest.raises(IntegrityError):
        make_expense(session, make_space(session), make_user(session), **fields)


def test_prepayment_and_statement_are_saved(session: Session) -> None:
    user, space = make_user(session), make_space(session)
    card = make_card(session, space)
    purchase = make_purchase(session, space, user, card)
    session.add_all(
        [
            Prepayment(
                space_id=space.id,
                expense_id=purchase.id,
                period_start=date(2026, 12, 1),
                amount=400_000,
                reduces="term",
                created_by=user.id,
            ),
            CardStatement(
                space_id=space.id,
                card_id=card.id,
                period_start=date(2026, 12, 1),
                amount=0,
            ),
        ]
    )
    session.flush()
    session.expire_all()

    assert session.scalars(select(Prepayment.amount)).all() == [400_000]
    assert session.scalars(select(CardStatement.amount)).all() == [0]


@pytest.mark.parametrize(
    ("amount", "reduces"), [(0, "term"), (-1, "term"), (1, "plazo"), (1, "")]
)
def test_database_rejects_invalid_prepayments(
    session: Session, amount: int, reduces: str
) -> None:
    user, space = make_user(session), make_space(session)
    purchase = make_purchase(session, space, user, make_card(session, space))
    session.add(
        Prepayment(
            space_id=space.id,
            expense_id=purchase.id,
            period_start=date(2026, 12, 1),
            amount=amount,
            reduces=reduces,
            created_by=user.id,
        )
    )

    with pytest.raises(IntegrityError):
        session.flush()


def test_database_rejects_a_negative_statement(session: Session) -> None:
    space = make_space(session)
    card = make_card(session, space)
    session.add(
        CardStatement(
            space_id=space.id,
            card_id=card.id,
            period_start=date(2026, 12, 1),
            amount=-1,
        )
    )

    with pytest.raises(IntegrityError):
        session.flush()


def test_one_prepayment_per_purchase_and_month(session: Session) -> None:
    user, space = make_user(session), make_space(session)
    purchase = make_purchase(session, space, user, make_card(session, space))
    for _ in range(2):
        session.add(
            Prepayment(
                space_id=space.id,
                expense_id=purchase.id,
                period_start=date(2026, 12, 1),
                amount=1,
                reduces="term",
                created_by=user.id,
            )
        )

    with pytest.raises(IntegrityError):
        session.flush()


def test_one_statement_per_card_and_month(session: Session) -> None:
    space = make_space(session)
    card = make_card(session, space)
    for amount in (1, 2):
        session.add(
            CardStatement(
                space_id=space.id,
                card_id=card.id,
                period_start=date(2026, 12, 1),
                amount=amount,
            )
        )

    with pytest.raises(IntegrityError):
        session.flush()


def test_deleting_space_cascades_to_cards_purchases_prepayments_and_statements(
    session: Session,
) -> None:
    # RF-44. Las claves foráneas sin `ON DELETE` (compra → tarjeta, abono →
    # compra, extracto → tarjeta) se comprueban al final de la sentencia, así
    # que la cascada no choca (plan 009).
    user = make_user(session)
    doomed, kept = make_space(session, "Casa"), make_space(session, "Viajes")
    for space in (doomed, kept):
        card = make_card(session, space)
        purchase = make_purchase(session, space, user, card)
        session.add_all(
            [
                Prepayment(
                    space_id=space.id,
                    expense_id=purchase.id,
                    period_start=date(2026, 12, 1),
                    amount=1,
                    reduces="term",
                    created_by=user.id,
                ),
                CardStatement(
                    space_id=space.id,
                    card_id=card.id,
                    period_start=date(2026, 12, 1),
                    amount=1,
                ),
            ]
        )
    session.flush()

    session.execute(delete(Space).where(Space.id == doomed.id))
    session.flush()

    assert session.scalars(select(Card.space_id)).all() == [kept.id]
    assert session.scalars(select(Prepayment.space_id)).all() == [kept.id]
    assert session.scalars(select(CardStatement.space_id)).all() == [kept.id]
    assert set(session.scalars(select(Expense.space_id)).all()) == {kept.id}


# --- Gasto del mes con tarjeta (spec 010) ---


def test_a_month_expense_on_a_card_is_saved_with_or_without_item(
    session: Session,
) -> None:
    user, space = make_user(session), make_space(session)
    card = make_card(session, space)
    item = make_item(session, make_category(session, space, "Comida"))

    planned = make_purchase(
        session,
        space,
        user,
        card,
        installments=1,
        is_debt=False,
        budget_item_id=item.id,
        category_id=item.category_id,
        description=None,
    )
    # En otro espacio: `make_expense` crea una categoría "Comida N" por
    # espacio, y dos en el mismo chocarían por nombre.
    other = make_space(session, "Viajes")
    unplanned = make_purchase(
        session, other, user, make_card(session, other), installments=1, is_debt=False
    )
    session.expire_all()

    assert session.get(Expense, planned.id).is_debt is False
    assert session.get(Expense, planned.id).budget_item_id == item.id
    assert session.get(Expense, unplanned.id).is_debt is False
