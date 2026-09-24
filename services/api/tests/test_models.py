from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Invitation, Membership, Space, User


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


def test_instance_invitation_cannot_point_to_a_space(session: Session) -> None:
    user = make_user(session)
    space = make_space(session)
    session.add(
        Invitation(
            code_hash="abc",
            kind="instance",
            space_id=space.id,
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
