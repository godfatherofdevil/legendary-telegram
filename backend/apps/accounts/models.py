from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from ..common.enums import PresenceState
from ..common.models import CreatedAtModel, TimestampedModel


class UserManager(BaseUserManager):
    use_in_migrations = True

    def normalize_email(self, email):
        normalized = super().normalize_email(email)
        return normalized.lower() if normalized else normalized

    def _create_user(self, email, username, password, **extra_fields):
        if not email:
            raise ValueError("The given email must be set")
        if not username:
            raise ValueError("The given username must be set")

        email = self.normalize_email(email)
        now = timezone.now()
        user = self.model(
            email=email,
            username=username,
            presence_last_changed_at=extra_fields.pop("presence_last_changed_at", now),
            **extra_fields,
        )
        user.set_password(password)
        user.full_clean()
        user.save(using=self._db)
        return user

    def create_user(self, email, username, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, username, password, **extra_fields)

    def create_superuser(self, email, username, password, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, username, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin, TimestampedModel):
    email = models.EmailField(max_length=254, unique=True)
    username = models.CharField(max_length=150, unique=True)
    presence_state = models.CharField(
        max_length=16,
        choices=PresenceState.choices,
        default=PresenceState.OFFLINE,
    )
    presence_last_changed_at = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    objects = UserManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("email"), name="accounts_user_email_ci_unique"),
            models.CheckConstraint(
                condition=~models.Q(email=""),
                name="accounts_user_email_not_empty",
            ),
            models.CheckConstraint(
                condition=~models.Q(username=""),
                name="accounts_user_username_not_empty",
            ),
        ]

    def clean(self):
        super().clean()
        self.email = self.__class__.objects.normalize_email(self.email)

        if not self.username:
            raise ValidationError({"username": "Username must not be empty."})

        if not self.email:
            raise ValidationError({"email": "Email must not be empty."})

        if self.pk:
            current_username = (
                self.__class__.objects.filter(pk=self.pk).values_list("username", flat=True).first()
            )
            if current_username and current_username != self.username:
                raise ValidationError({"username": "Username is immutable."})

    def __str__(self):
        return self.username


class PasswordResetToken(CreatedAtModel):
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="password_reset_tokens",
    )
    token_hash = models.CharField(max_length=255, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)


class UserSession(CreatedAtModel):
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="session_records",
    )
    session_key_hash = models.CharField(max_length=255, unique=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    is_currently_valid = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["user", "is_currently_valid"]),
            models.Index(fields=["expires_at"]),
        ]
