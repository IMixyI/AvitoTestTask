from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from src.dto import PullRequestStatus


class Base(DeclarativeBase):
    pass


class TeamModel(Base):
    __tablename__ = "teams"

    team_name: Mapped[str] = mapped_column(String, primary_key=True)
    members: Mapped[list["UserModel"]] = relationship(back_populates="team")


class UserModel(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    username: Mapped[str] = mapped_column(String, nullable=False)
    team_name: Mapped[str] = mapped_column(
        ForeignKey("teams.team_name"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)

    team: Mapped["TeamModel"] = relationship(back_populates="members")

    reviewed_prs: Mapped[list["PullRequestModel"]] = relationship(
        secondary="reviewers_for_pr", back_populates="assigned_reviewers"
    )


class PullRequestModel(Base):
    __tablename__ = "pull_requests"

    pull_request_id: Mapped[str] = mapped_column(String, primary_key=True)
    pull_request_name: Mapped[str] = mapped_column(String, nullable=False)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    status: Mapped[PullRequestStatus] = mapped_column(
        Enum(PullRequestStatus), nullable=False
    )
    createdAt: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    mergedAt: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    author: Mapped["UserModel"] = relationship()

    assigned_reviewers: Mapped[list["UserModel"]] = relationship(
        secondary="reviewers_for_pr", back_populates="reviewed_prs"
    )


class ReviewerForPRModel(Base):
    __tablename__ = "reviewers_for_pr"

    pull_request_id: Mapped[str] = mapped_column(
        ForeignKey("pull_requests.pull_request_id"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), primary_key=True)


async def create_table(engine: AsyncEngine):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
