from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import Engine, delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Category,
    Expense,
    Invitation,
    Membership,
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
