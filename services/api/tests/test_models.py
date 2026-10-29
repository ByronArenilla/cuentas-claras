from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Category, Invitation, Membership, Space, User, category_key


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
