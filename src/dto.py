from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class ErrorCode(str, Enum):
    TEAM_EXISTS = "TEAM_EXISTS"
    PR_EXISTS = "PR_EXISTS"
    PR_MERGED = "PR_MERGED"
    NOT_ASSIGNED = "NOT_ASSIGNED"
    NO_CANDIDATE = "NO_CANDIDATE"
    NOT_FOUND = "NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class PullRequestStatus(str, Enum):
    OPEN = "OPEN"
    MERGED = "MERGED"


class ErrorDetail(BaseModel):
    code: ErrorCode
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class TeamMember(BaseModel):
    user_id: str
    username: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class Team(BaseModel):
    team_name: str
    members: list[TeamMember]


class User(BaseModel):
    user_id: str
    username: str
    team_name: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class PullRequest(BaseModel):
    pull_request_id: str
    pull_request_name: str
    author_id: str
    status: PullRequestStatus
    assigned_reviewers: list[str]
    createdAt: datetime | None
    mergedAt: datetime | None


class PullRequestShort(BaseModel):
    pull_request_id: str
    pull_request_name: str
    author_id: str
    status: PullRequestStatus


class SetIsActiveRequest(BaseModel):
    user_id: str
    is_active: bool


class CreatePullRequestRequest(BaseModel):
    pull_request_id: str
    pull_request_name: str
    author_id: str


class MergePullRequestRequest(BaseModel):
    pull_request_id: str


class ReassignPullRequestRequest(BaseModel):
    pull_request_id: str
    old_user_id: str


class TeamResponse(BaseModel):
    team: Team


class UserResponse(BaseModel):
    user: User


class PullRequestResponse(BaseModel):
    pr: PullRequest


class ReassignPullRequestResponse(BaseModel):
    pr: PullRequest
    replaced_by: str


class UserReviewsResponse(BaseModel):
    user_id: str
    pull_requests: list[PullRequestShort]
