from fastapi import HTTPException
from loguru import logger
from sqlalchemy.exc import IntegrityError, NoResultFound, SQLAlchemyError

from src.db_client import DBClient
from src.dto import (
    CreatePullRequestRequest,
    DeactivateUsersRequest,
    DeactivateUsersResponse,
    ErrorCode,
    MergePullRequestRequest,
    PullRequestResponse,
    ReassignPullRequestRequest,
    ReassignPullRequestResponse,
    SetIsActiveRequest,
    Team,
    TeamResponse,
    UserResponse,
    UserReviewsResponse,
    UsersPullRequestsResponse,
)


class ReviewService:
    def __init__(self, db_client: DBClient):
        self.db_client = db_client

    @staticmethod
    def raise_api_error(code: ErrorCode, message: str, status_code: int):
        raise HTTPException(
            status_code=status_code,
            detail={"error": {"code": code, "message": message}},
        )

    async def create_team(self, team: Team) -> TeamResponse | None:
        try:
            await self.db_client.create_team(
                team_name=team.team_name, members=team.members
            )
            return TeamResponse(team=team)
        except IntegrityError:
            self.raise_api_error(
                status_code=400,
                code=ErrorCode.TEAM_EXISTS,
                message="team already exists",
            )
        except SQLAlchemyError as e:
            logger.error(e)
            self.raise_api_error(
                status_code=500,
                code=ErrorCode.INTERNAL_ERROR,
                message="unexpected error",
            )

    async def get_team(self, team_name: str) -> Team | None:
        try:
            team_members = await self.db_client.get_team(team_name)
            if team_members is None:
                self.raise_api_error(
                    status_code=404, code=ErrorCode.NOT_FOUND, message="team not found"
                )
            return Team(team_name=team_name, members=team_members)
        except SQLAlchemyError as e:
            logger.error(e)
            self.raise_api_error(
                status_code=500,
                code=ErrorCode.INTERNAL_ERROR,
                message="unexpected error",
            )

    async def set_is_active(self, request: SetIsActiveRequest) -> UserResponse | None:
        try:
            user = await self.db_client.set_is_active(
                user_id=request.user_id, is_active=request.is_active
            )
            if user is None:
                self.raise_api_error(
                    status_code=404, code=ErrorCode.NOT_FOUND, message="user not found"
                )
            return UserResponse(user=user)

        except SQLAlchemyError as e:
            logger.error(e)
            self.raise_api_error(
                status_code=500,
                code=ErrorCode.INTERNAL_ERROR,
                message="unexpected error",
            )

    async def get_user_reviews(self, user_id: str) -> UserReviewsResponse | None:
        try:
            pull_requests = await self.db_client.get_user_reviews(user_id)
            return UserReviewsResponse(user_id=user_id, pull_requests=pull_requests)
        except SQLAlchemyError as e:
            logger.error(e)
            self.raise_api_error(
                status_code=500,
                code=ErrorCode.INTERNAL_ERROR,
                message="unexpected error",
            )

    async def create_pull_request(
        self, request: CreatePullRequestRequest
    ) -> PullRequestResponse | None:
        try:
            pull_request = await self.db_client.create_pull_request(
                **request.model_dump()
            )
            return PullRequestResponse(pr=pull_request)
        except NoResultFound:
            self.raise_api_error(
                status_code=404,
                code=ErrorCode.NOT_FOUND,
                message="author or team not found",
            )
        except IntegrityError:
            self.raise_api_error(
                status_code=409,
                code=ErrorCode.PR_EXISTS,
                message="pull request already exists",
            )
        except SQLAlchemyError as e:
            logger.error(e)
            self.raise_api_error(
                status_code=500,
                code=ErrorCode.INTERNAL_ERROR,
                message="unexpected error",
            )

    async def merge_pull_request(
        self, request: MergePullRequestRequest
    ) -> PullRequestResponse | None:
        try:
            pull_request = await self.db_client.merge_pull_request(
                request.pull_request_id
            )
            return PullRequestResponse(pr=pull_request)
        except NoResultFound:
            self.raise_api_error(
                status_code=404,
                code=ErrorCode.NOT_FOUND,
                message="pr or team not found",
            )
        except SQLAlchemyError as e:
            logger.error(e)
            self.raise_api_error(
                status_code=500,
                code=ErrorCode.INTERNAL_ERROR,
                message="unexpected error",
            )

    async def reassign_pull_request(
        self, request: ReassignPullRequestRequest
    ) -> ReassignPullRequestResponse | None:
        try:
            pull_request, new_reviewers_id = await self.db_client.reassign_pull_request(
                request.pull_request_id, request.old_user_id
            )
            return ReassignPullRequestResponse(
                pr=pull_request, replaced_by=new_reviewers_id
            )
        except SQLAlchemyError as e:
            logger.error(e)
            self.raise_api_error(
                status_code=500,
                code=ErrorCode.INTERNAL_ERROR,
                message="unexpected error",
            )

    async def deactivate_users(
        self, request: DeactivateUsersRequest
    ) -> DeactivateUsersResponse | None:
        try:
            await self.db_client.deactivate_users(**request.model_dump())
            team_members = await self.db_client.get_team(request.team_name)
            return DeactivateUsersResponse(
                team=Team(team_name=request.team_name, members=team_members)
            )
        except SQLAlchemyError as e:
            logger.error(e)
            self.raise_api_error(
                status_code=500,
                code=ErrorCode.INTERNAL_ERROR,
                message="unexpected error",
            )

    async def get_users_prs(self) -> UsersPullRequestsResponse | None:
        try:
            result = await self.db_client.get_users_prs()
            return UsersPullRequestsResponse(users_prs=result)
        except SQLAlchemyError as e:
            logger.error(e)
            self.raise_api_error(
                status_code=500,
                code=ErrorCode.INTERNAL_ERROR,
                message="unexpected error",
            )
