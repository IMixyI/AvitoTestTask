from datetime import datetime, timezone

from sqlalchemy import and_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError, NoResultFound, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.dto import PullRequest, PullRequestStatus, TeamMember, User
from src.sql_models import PullRequestModel, ReviewerForPRModel, TeamModel, UserModel


class DBClient:
    def __init__(self, db_engine: AsyncEngine):
        self.db_engine = db_engine
        self.async_session_maker = async_sessionmaker(
            bind=db_engine, class_=AsyncSession, expire_on_commit=False
        )

    async def stop(self):
        await self.db_engine.dispose()

    async def create_team(self, team_name: str, members: list[TeamMember]) -> None:
        try:
            async with self.async_session_maker() as session:
                session.add(TeamModel(team_name=team_name))

                members = [
                    {**member.model_dump(), "team_name": team_name}
                    for member in members
                ]

                query = insert(UserModel).values(members)

                query = query.on_conflict_do_update(
                    index_elements=["user_id"],
                    set_={
                        "username": query.excluded.username,
                        "team_name": query.excluded.team_name,
                        "is_active": query.excluded.is_active,
                    },
                )
                await session.execute(query)
                await session.commit()
        except IntegrityError as e:
            await session.rollback()
            raise e
        except SQLAlchemyError as e:
            await session.rollback()
            raise e

    async def get_team(self, team_name: str) -> list[TeamMember] | None:
        try:
            async with self.async_session_maker() as session:
                team = await session.get(TeamModel, team_name)
                if team is None:
                    return None
                query = select(UserModel).where(UserModel.team_name == team_name)
                result = await session.execute(query)
            team_members = list(result.scalars().all())
            team_members = [
                TeamMember.model_validate(member) for member in team_members
            ]
            return team_members

        except SQLAlchemyError as e:
            await session.rollback()
            raise e

    async def set_is_active(self, user_id: str, is_active: bool) -> User | None:
        try:
            async with self.async_session_maker() as session:
                query = (
                    update(UserModel)
                    .where(UserModel.user_id == user_id)
                    .values(is_active=is_active)
                    .returning(UserModel)
                )
                result = await session.execute(query)
                await session.commit()
            return User.model_validate(result.scalar_one_or_none())
        except SQLAlchemyError as e:
            await session.rollback()
            raise e

    async def get_user_reviews(self, user_id: str) -> list[PullRequestModel]:
        pass

    async def create_pull_request(
        self, pull_request_id: str, pull_request_name: str, author_id: str
    ) -> PullRequest:
        try:
            async with self.async_session_maker() as session:
                author = await session.get(UserModel, author_id)
                if author is None:
                    raise NoResultFound

                team = await session.get(TeamModel, author.team_name)
                if team is None:
                    raise NoResultFound
                team_name = team.team_name

                pull_request = PullRequestModel(
                    pull_request_id=pull_request_id,
                    pull_request_name=pull_request_name,
                    author_id=author_id,
                    status=PullRequestStatus.OPEN,
                    createdAt=datetime.now(timezone.utc),
                )
                session.add(pull_request)

                free_reviewers_query = (
                    select(UserModel.user_id)
                    .where(
                        and_(
                            UserModel.user_id != author_id,
                            UserModel.team_name == team_name,
                            UserModel.is_active == True,
                        )
                    )
                    .limit(2)
                )
                free_reviewers = await session.execute(free_reviewers_query)
                free_reviewers = list(free_reviewers.scalars().all())

                if free_reviewers:
                    add_reviewers_query = insert(ReviewerForPRModel).values(
                        [
                            {"pull_request_id": pull_request_id, "user_id": user_id}
                            for user_id in free_reviewers
                        ]
                    )
                    await session.execute(add_reviewers_query)

                await session.commit()
                return PullRequest(
                    pull_request_id=pull_request_id,
                    pull_request_name=pull_request_name,
                    author_id=author_id,
                    status=pull_request.status,
                    createdAt=pull_request.createdAt,
                    mergedAt=None,
                    assigned_reviewers=free_reviewers,
                )
        except NoResultFound as e:
            await session.rollback()
            raise e

        except IntegrityError as e:
            await session.rollback()
            raise e

        except SQLAlchemyError as e:
            await session.rollback()
            raise e

    async def get_pr_reviewers(self, pull_request_id: str) -> list[str]:
        pass

    async def merge_pull_request(self, pull_request_id: str) -> PullRequestModel:
        pass

    async def reassign_pull_request(
        self, pull_request_id: str, old_user_id: str
    ) -> PullRequestModel:
        pass
