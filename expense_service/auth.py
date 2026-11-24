import os
from dataclasses import dataclass, field

import grpc
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from errors import ApiError
from proto import auth_pb2, auth_pb2_grpc

USER_SERVICE_ADDRESS = os.getenv("USER_SERVICE_GRPC_ADDR", "localhost:50051")
# скільки секунд чекати відповіді від User Service
USER_SERVICE_TIMEOUT = float(os.getenv("USER_SERVICE_TIMEOUT", "3"))

bearer_scheme = HTTPBearer(auto_error=False)

ROLE_USER = "user"
ROLE_AUDITOR = "auditor"
ROLE_ADMIN = "admin"


def bearer_token(header):
    # "Bearer <token>" -> <token>, інакше None
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


@dataclass
class CurrentUser:
    id: int
    role: str
    # токен потрібен для наступних gRPC-викликів від імені цього користувача
    token: str = field(repr=False)


_channel = grpc.insecure_channel(USER_SERVICE_ADDRESS)
_stub = auth_pb2_grpc.AuthServiceStub(_channel)


def unauthorized(message: str) -> ApiError:
    return ApiError(401, "unauthorized", message, headers={"WWW-Authenticate": "Bearer"})


def _call(rpc):
    # помилки gRPC переводимо в HTTP-помилки, щоб клієнт бачив зрозумілу відповідь
    try:
        return rpc()
    except grpc.RpcError as error:
        code = error.code()
        if code == grpc.StatusCode.UNAUTHENTICATED:
            raise unauthorized(error.details() or "Invalid access token")
        if code == grpc.StatusCode.PERMISSION_DENIED:
            raise ApiError(403, "forbidden", "Access denied: insufficient privileges")
        # UNAVAILABLE, DEADLINE_EXCEEDED та інші: User Service недоступний або не відповідає
        raise ApiError(503, "service_unavailable", "User Service is unavailable, try again later")


def _metadata(token: str):
    # токен передається в gRPC metadata, як у методичці
    return (("authorization", f"Bearer {token}"),)


def resolve_current_user(token: str) -> CurrentUser:
    response = _call(
        lambda: _stub.ValidateToken(
            auth_pb2.ValidateTokenRequest(token=token),
            metadata=_metadata(token),
            timeout=USER_SERVICE_TIMEOUT,
        )
    )
    if not response.is_valid or not response.roles:
        raise unauthorized("Invalid access token")
    return CurrentUser(id=int(response.user_id), role=response.roles[0], token=token)


def user_exists(current: CurrentUser, user_id: int) -> bool:
    response = _call(
        lambda: _stub.UserExists(
            auth_pb2.UserExistsRequest(user_id=user_id),
            metadata=_metadata(current.token),
            timeout=USER_SERVICE_TIMEOUT,
        )
    )
    return response.exists


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> CurrentUser:
    if credentials is None:
        raise unauthorized("Missing access token")
    return resolve_current_user(credentials.credentials)


def require_roles(*roles: str):
    # RBAC: роль береться з User Service при кожному запиті
    def checker(current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current.role not in roles:
            raise ApiError(403, "forbidden", "Access denied: insufficient privileges")
        return current

    return checker
