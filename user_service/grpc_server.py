from concurrent import futures

import grpc

from database import SessionLocal
from interceptors import RBACServerInterceptor
from models import ROLE_ADMIN, ROLE_AUDITOR, ROLE_USER, UserModel
from proto import auth_pb2, auth_pb2_grpc
from security import TokenError, user_from_token

BEARER_PREFIX = "Bearer "
ALL_ROLES = (ROLE_USER, ROLE_AUDITOR, ROLE_ADMIN)

# для яких методів потрібен валідний токен і яку роль він має мати.
# UserExists викликається лише для auditor/admin: звичайний user чужих id не перевіряє
METHOD_ROLES = {
    "/auth.AuthService/ValidateToken": ALL_ROLES,
    "/auth.AuthService/UserExists": (ROLE_AUDITOR, ROLE_ADMIN),
}


class AuthServicer(auth_pb2_grpc.AuthServiceServicer):
    def ValidateToken(self, request, context):
        # токен має бути в metadata і в тілі запиту, і вони мають збігатися
        authorization = dict(context.invocation_metadata()).get("authorization", "")
        if not authorization.startswith(BEARER_PREFIX):
            return auth_pb2.ValidateTokenResponse(is_valid=False)
        if authorization[len(BEARER_PREFIX):] != request.token:
            return auth_pb2.ValidateTokenResponse(is_valid=False)

        with SessionLocal() as db:
            try:
                user = user_from_token(db, request.token)
            except TokenError:
                return auth_pb2.ValidateTokenResponse(is_valid=False)
            return auth_pb2.ValidateTokenResponse(is_valid=True, user_id=str(user.id), roles=[user.role])

    def UserExists(self, request, context):
        with SessionLocal() as db:
            exists = db.get(UserModel, request.user_id) is not None
        return auth_pb2.UserExistsResponse(exists=exists)


def start_grpc_server(port: int) -> grpc.Server:
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
        interceptors=[RBACServerInterceptor(METHOD_ROLES)],
    )
    auth_pb2_grpc.add_AuthServiceServicer_to_server(AuthServicer(), server)
    server.add_insecure_port(f"0.0.0.0:{port}")
    server.start()
    return server
