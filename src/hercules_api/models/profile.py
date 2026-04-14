from datetime import date, datetime

from sqlalchemy import Boolean, Date, Float, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from hercules_api.db import Base


class UserProfile(Base):
    """Single-user profile. At most one row exists (id=1 by convention)."""

    __tablename__ = "user_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    height_cm: Mapped[float | None] = mapped_column(Float)
    age: Mapped[int | None] = mapped_column(Integer)
    sex: Mapped[str | None] = mapped_column(String(8))  # 'male' | 'female'
    activity_level: Mapped[str | None] = mapped_column(String(16))
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    calorie_target: Mapped[float] = mapped_column(Float)
    protein_g_target: Mapped[float] = mapped_column(Float)
    carbs_g_target: Mapped[float] = mapped_column(Float)
    fat_g_target: Mapped[float] = mapped_column(Float)

    # Optional TDEE/BMR snapshots at the time the goal was set.
    tdee: Mapped[float | None] = mapped_column(Float)
    bmr: Mapped[float | None] = mapped_column(Float)

    notes: Mapped[str | None] = mapped_column(Text)

    start_date: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    end_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        # At most one active goal at a time.
        Index(
            "ix_goals_single_active",
            "is_active",
            unique=True,
            postgresql_where="is_active",
        ),
    )
