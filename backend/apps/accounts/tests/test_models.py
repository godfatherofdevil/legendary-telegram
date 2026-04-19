import pytest
from django.core.exceptions import ValidationError

from ..models import User


@pytest.mark.django_db
def test_user_email_is_normalized_to_lowercase() -> None:
    user = User.objects.create_user(
        email="User@Example.COM",
        username="alice",
        password="strong-pass-123",
    )

    assert user.email == "user@example.com"


@pytest.mark.django_db
def test_email_uniqueness_is_case_insensitive() -> None:
    User.objects.create_user(
        email="user@example.com",
        username="alice",
        password="strong-pass-123",
    )

    with pytest.raises(ValidationError):
        User.objects.create_user(
            email="USER@example.com",
            username="bob",
            password="strong-pass-123",
        )


@pytest.mark.django_db
def test_username_is_immutable_after_creation() -> None:
    user = User.objects.create_user(
        email="user@example.com",
        username="alice",
        password="strong-pass-123",
    )

    user.username = "bob"

    with pytest.raises(ValidationError):
        user.full_clean()
