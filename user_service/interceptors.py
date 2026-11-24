import grpc

from database import SessionLocal
from security import TokenError, user_from_token

BEARER_PREFIX = "Bearer "


def check_access(authorization, required_roles):
    # повертає (код, повідомлення) при відмові або None, якщо доступ дозволено
    if not authorization or not authorization.startswith(BEARER_PREFIX):
        return grpc.StatusCode.UNAUTHENTICATED, "Missing access token"
    token = authorization[len(BEARER_PREFIX):]
    with SessionLocal() as db:
        try:
            user = user_from_token(db, token)
        except TokenError as error:
            return grpc.StatusCode.UNAUTHENTICATED, error.message
        if user.role not in required_roles:
            return grpc.StatusCode.PERMISSION_DENIED, "Access denied: insufficient privileges"
    return None


class RBACServerInterceptor(grpc.ServerInterceptor):
    def __init__(self, method_roles_map):
        self.method_roles_map = method_roles_map

    def intercept_service(self, continuation, handler_call_details):
        required_roles = self.method_roles_map.get(handler_call_details.method, ())
        if not required_roles:
            return continuation(handler_call_details)

        # токен передається в metadata з ключем authorization
        metadata = dict(handler_call_details.invocation_metadata)
        denied = check_access(metadata.get("authorization"), required_roles)
        if denied is None:
            return continuation(handler_call_details)

        code, message = denied

        # у intercept_service немає контексту виклику, тому відмову повертаємо як обробник,
        # який сам завершує виклик із потрібним кодом статусу (всі методи AuthService унарні)
        def abort(request, context):
            context.abort(code, message)

        return grpc.unary_unary_rpc_method_handler(abort)
