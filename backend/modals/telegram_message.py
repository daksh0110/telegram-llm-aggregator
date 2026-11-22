from datetime import datetime, timezone

from database import Base
from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column


class TelegramMessage(Base):
    __tablename__ = "telegram_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    channel_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("telegram_channels.channel_id"),
        nullable=False,
        index=True,
    )

    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    message_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    message_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    processing_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "channel_id",
            "message_id",
            name="uq_channel_message",
        ),
    )