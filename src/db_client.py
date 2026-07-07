from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError, NoResultFound, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.dto import (
    ErrorCode,
    PullRequest,
    PullRequestShort,
    PullRequestStatus,
    TeamMember,
    User,
    UsersPRMapping,
)
from src.sql_models import PullRequestModel, ReviewerForPRModel, TeamModel, UserModel


class DBClient:
    def __init__(self, db_engine: AsyncEngine):
        self.db_engine = db_engine
        self.async_session_maker = async_sessionmaker(
            bind=db_engine, class_=AsyncSession, expire_on_commit=False
        )

    async def stop(self):
        await self.db_engine.dispose()

    @staticmethod
    def raise_api_error(code: ErrorCode, message: str, status_code: int):
        raise HTTPException(
            status_code=status_code,
            detail={"error": {"code": code, "message": message}},
        )

    async def reassignment_prs(
        self, session: AsyncSession, deactivated_user_ids: list[str], team_name
    ):
        query = (
            select(ReviewerForPRModel.pull_request_id)
            .where(ReviewerForPRModel.user_id.in_(deactivated_user_ids))
            .distinct()
        )
        result = await session.execute(query)
        pr_to_reassignment = list(result.scalars().all())

        delete_deactivated_reviewers_query = delete(ReviewerForPRModel).where(
            and_(
                ReviewerForPRModel.user_id.in_(deactivated_user_ids),
                ReviewerForPRModel.pull_request_id.in_(
                    select(PullRequestModel.pull_request_id).where(
                        PullRequestModel.status != PullRequestStatus.MERGED
                    )
                ),
            )
        )
        await session.execute(delete_deactivated_reviewers_query)

        for pr_id in pr_to_reassignment:
            query = select(PullRequestModel).where(
                PullRequestModel.pull_request_id == pr_id
            )
            result = await session.execute(query)
            pull_request = result.scalar_one_or_none()
            if pull_request.status == PullRequestStatus.MERGED:
                continue

            query = select(ReviewerForPRModel.user_id).where(
                and_(ReviewerForPRModel.pull_request_id == pr_id)
            )
            result = await session.execute(query)
            pr_reviewers_id = list(result.scalars().all())

            query = (
                select(UserModel.user_id)
                .where(
                    and_(
                        UserModel.is_active == True,
                        UserModel.user_id != pull_request.author_id,
                        UserModel.team_name == team_name,
                        UserModel.user_id.notin_(pr_reviewers_id),
                        UserModel.user_id.notin_(deactivated_user_ids),
                    )
                )
                .limit(max(0, 2 - len(pr_reviewers_id)))
            )
            result = await session.execute(query)
            available_reviewer_ids = list(result.scalars().all())
            if not pr_reviewers_id and not available_reviewer_ids:
                self.raise_api_error(
                    status_code=409,
                    code=ErrorCode.NO_CANDIDATE,
                    message="no active replacement candidate in team",
                )
            query = insert(ReviewerForPRModel).values(
                [
                    {"pull_request_id": pr_id, "user_id": available_reviewer_id}
                    for available_reviewer_id in available_reviewer_ids
                ]
            )
            await session.execute(query)

    async def create_team(self, team_name: str, members: list[TeamMember]) -> None:
        async with self.async_session_maker() as session:
            try:
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
        async with self.async_session_maker() as session:
            try:
                team = await session.get(TeamModel, team_name)
                if team is None:
                    return None
                query = select(UserModel).where(UserModel.team_name == team_name)
                result = await session.execute(query)
                team_members = list(result.scalars().all())
            except SQLAlchemyError as e:
                await session.rollback()
                raise e

        team_members = [TeamMember.model_validate(member) for member in team_members]
        return team_members

    async def deactivate_users(self, user_ids: list[str], team_name: str) -> None:
        async with self.async_session_maker() as session:
            try:
                query = (
                    update(UserModel)
                    .where(
                        and_(
                            UserModel.user_id.in_(user_ids),
                            UserModel.is_active == True,
                            UserModel.team_name == team_name,
                        )
                    )
                    .values(is_active=False)
                    .returning(UserModel.user_id)
                )
                result = await session.execute(query)
                deactivated_users = list(result.scalars().all())
                await self.reassignment_prs(
                    session=session,
                    deactivated_user_ids=deactivated_users,
                    team_name=team_name,
                )
                await session.commit()
            except SQLAlchemyError as e:
                await session.rollback()
                raise e
            except HTTPException as e:
                await session.rollback()
                raise e

    async def set_is_active(self, user_id: str, is_active: bool) -> User | None:
        async with self.async_session_maker() as session:
            try:
                query = (
                    update(UserModel)
                    .where(
                        and_(
                            UserModel.user_id == user_id,
                            UserModel.is_active != is_active,
                        )
                    )
                    .values(is_active=is_active)
                    .returning(UserModel)
                )
                result = await session.execute(query)
                user = result.scalar_one_or_none()
                if user is None:
                    user = await session.get(UserModel, user_id)
                    if user is None:
                        return None
                else:
                    if not is_active:
                        await self.reassignment_prs(session, [user_id], user.team_name)
                    await session.commit()
            except SQLAlchemyError as e:
                await session.rollback()
                raise e
            except HTTPException as e:
                await session.rollback()
                raise e

        return User.model_validate(user)

    async def get_user_reviews(self, user_id: str) -> list[PullRequestShort]:
        async with self.async_session_maker() as session:
            try:
                query = (
                    select(PullRequestModel)
                    .join(
                        ReviewerForPRModel,
                        PullRequestModel.pull_request_id
                        == ReviewerForPRModel.pull_request_id,
                    )
                    .where(ReviewerForPRModel.user_id == user_id)
                )
                result = await session.execute(query)
                pull_requests = list(result.scalars().all())
            except SQLAlchemyError as e:
                await session.rollback()
                raise e

        return [PullRequestShort.model_validate(pr) for pr in pull_requests]

    async def create_pull_request(
        self, pull_request_id: str, pull_request_name: str, author_id: str
    ) -> PullRequest:
        async with self.async_session_maker() as session:
            try:
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

    async def merge_pull_request(self, pull_request_id: str) -> PullRequest:
        async with self.async_session_maker() as session:
            try:
                query = (
                    update(PullRequestModel)
                    .where(PullRequestModel.pull_request_id == pull_request_id)
                    .values(
                        status=PullRequestStatus.MERGED,
                        mergedAt=func.coalesce(
                            PullRequestModel.mergedAt, datetime.now(timezone.utc)
                        ),
                    )
                    .returning(PullRequestModel)
                )
                result = await session.execute(query)
                pull_request = result.scalar_one_or_none()
                if pull_request is None:
                    raise NoResultFound

                query = select(ReviewerForPRModel.user_id).where(
                    ReviewerForPRModel.pull_request_id == pull_request_id
                )
                result = await session.execute(query)
                reviewers_id = list(result.scalars().all())
                await session.commit()
            except NoResultFound as e:
                await session.rollback()
                raise e
            except SQLAlchemyError as e:
                await session.rollback()
                raise e

        return PullRequest(
            pull_request_id=pull_request_id,
            pull_request_name=pull_request.pull_request_name,
            author_id=pull_request.author_id,
            status=pull_request.status,
            assigned_reviewers=reviewers_id,
            createdAt=pull_request.createdAt,
            mergedAt=pull_request.mergedAt,
        )

    async def reassign_pull_request(
        self, pull_request_id: str, old_user_id: str
    ) -> tuple[PullRequest, str]:
        async with self.async_session_maker() as session:
            try:
                query = select(PullRequestModel).where(
                    PullRequestModel.pull_request_id == pull_request_id
                )
                result = await session.execute(query)
                pull_request = result.scalar_one_or_none()

                query = select(UserModel).where(UserModel.user_id == old_user_id)
                result = await session.execute(query)
                old_user = result.scalar_one_or_none()

                if pull_request is None or old_user is None:
                    self.raise_api_error(
                        status_code=404,
                        code=ErrorCode.NOT_FOUND,
                        message="pr or user not found",
                    )
                if pull_request.status == PullRequestStatus.MERGED:
                    self.raise_api_error(
                        status_code=409,
                        code=ErrorCode.PR_MERGED,
                        message="cannot reassign on merged PR",
                    )

                query = select(ReviewerForPRModel.user_id).where(
                    and_(
                        ReviewerForPRModel.user_id == old_user_id,
                        ReviewerForPRModel.pull_request_id == pull_request_id,
                    )
                )
                result = await session.execute(query)
                pr_reviewers_id = list(result.scalars().all())

                if old_user_id not in pr_reviewers_id:
                    self.raise_api_error(
                        status_code=409,
                        code=ErrorCode.NOT_ASSIGNED,
                        message="reviewer is not assigned to this PR",
                    )

                query = (
                    select(UserModel.user_id)
                    .where(
                        and_(
                            UserModel.is_active == True,
                            UserModel.user_id != pull_request.author_id,
                            UserModel.team_name == old_user.team_name,
                            UserModel.user_id.notin_(pr_reviewers_id),
                        )
                    )
                    .limit(1)
                )
                result = await session.execute(query)
                available_reviewer_id = result.scalar_one_or_none()
                if available_reviewer_id is None:
                    self.raise_api_error(
                        status_code=409,
                        code=ErrorCode.NO_CANDIDATE,
                        message="no active replacement candidate in team",
                    )
                query = (
                    update(ReviewerForPRModel)
                    .where(
                        and_(
                            ReviewerForPRModel.pull_request_id == pull_request_id,
                            ReviewerForPRModel.user_id == old_user_id,
                        )
                    )
                    .values(user_id=available_reviewer_id)
                )
                await session.execute(query)
                await session.commit()

                pr_reviewers_id.remove(old_user_id)
                pr_reviewers_id.append(available_reviewer_id)
            except HTTPException as e:
                await session.rollback()
                raise e
            except SQLAlchemyError as e:
                await session.rollback()
                raise e

        return (
            PullRequest(
                pull_request_id=pull_request_id,
                pull_request_name=pull_request.pull_request_name,
                author_id=pull_request.author_id,
                status=pull_request.status,
                assigned_reviewers=pr_reviewers_id,
                createdAt=pull_request.createdAt,
                mergedAt=pull_request.mergedAt,
            ),
            available_reviewer_id,
        )

    async def get_users_prs(self) -> list[UsersPRMapping]:
        async with self.async_session_maker() as session:
            try:
                query = select(PullRequestModel.author_id, func.count()).group_by(
                    PullRequestModel.author_id
                )
                result = await session.execute(query)
                result = list(result.all())
            except SQLAlchemyError as e:
                await session.rollback()
                raise e

        return [
            UsersPRMapping(user_id=user_id, pull_requests_count=prs_count)
            for user_id, prs_count in result
        ]
