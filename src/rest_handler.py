from typing import Annotated

from fastapi import Depends, Query, Request

from src.dto import (
    CreatePullRequestRequest,
    MergePullRequestRequest,
    PullRequestResponse,
    ReassignPullRequestRequest,
    ReassignPullRequestResponse,
    SetIsActiveRequest,
    Team,
    TeamResponse,
    UserResponse,
    UserReviewsResponse,
)
from src.lifespan import create_app
from src.review_service import ReviewService

app = create_app()


def get_review_service(request: Request) -> ReviewService:
    return request.app.state.review_service


ReviewServiceDEP = Annotated[ReviewService, Depends(get_review_service)]


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok"}


@app.post("/team/add", response_model=TeamResponse, status_code=201, tags=["Teams"])
async def create_team(team: Team, review_service: ReviewServiceDEP) -> TeamResponse:
    """Создать команду с участниками (создаёт/обновляет пользователей)"""
    return await review_service.create_team(team)


@app.get("/team/get", response_model=Team, tags=["Teams"])
async def get_team(
    review_service: ReviewServiceDEP,
    team_name: str = Query(..., description="Уникальное имя команды"),
) -> Team:
    """Получить команду с участниками"""
    return await review_service.get_team(team_name)


@app.post("/users/setIsActive", response_model=UserResponse, tags=["Users"])
async def set_is_active(
    request: SetIsActiveRequest, review_service: ReviewServiceDEP
) -> UserResponse:
    """Установить флаг активности пользователя"""
    return await review_service.set_is_active(request)


@app.get("/users/getReview", response_model=UserReviewsResponse, tags=["Users"])
async def get_user_reviews(
    review_service: ReviewServiceDEP,
    user_id: str = Query(..., description="Идентификатор пользователя"),
) -> UserReviewsResponse:
    """Получить PR'ы, где пользователь назначен ревьювером"""
    return await review_service.get_user_reviews(user_id)


@app.post(
    "/pullRequest/create",
    response_model=PullRequestResponse,
    status_code=201,
    tags=["PullRequests"],
)
async def create_pull_request(
    request: CreatePullRequestRequest, review_service: ReviewServiceDEP
) -> PullRequestResponse:
    """Создать PR и автоматически назначить до 2 ревьюверов из команды автора"""
    return await review_service.create_pull_request(request)


@app.post(
    "/pullRequest/merge", response_model=PullRequestResponse, tags=["PullRequests"]
)
async def merge_pull_request(
    request: MergePullRequestRequest, review_service: ReviewServiceDEP
) -> PullRequestResponse:
    """Пометить PR как MERGED (идемпотентная операция)"""
    return await review_service.merge_pull_request(request)


@app.post(
    "/pullRequest/reassign",
    response_model=ReassignPullRequestResponse,
    tags=["PullRequests"],
)
async def reassign_pull_request(
    request: ReassignPullRequestRequest, review_service: ReviewServiceDEP
) -> ReassignPullRequestResponse:
    """Переназначить конкретного ревьювера на другого из его команды"""
    return await review_service.reassign_pull_request(request)
