"""Тести gRPC AuthService: ValidateToken, UserExists і перехоплювач авторизації."""
import os

import grpc
import pytest

from proto import auth_pb2, auth_pb2_grpc

GRPC_ADDRESS = f"localhost:{os.environ['USER_SERVICE_GRPC_PORT']}"


@pytest.fixture
def stub(app_client):
    # app_client запускає lifespan, тобто й gRPC-сервер
    channel = grpc.insecure_channel(GRPC_ADDRESS)
    yield auth_pb2_grpc.AuthServiceStub(channel)
    channel.close()


def bearer(token):
    return (("authorization", f"Bearer {token}"),)


def token_of(user):
    return user["headers"]["Authorization"].split()[1]


def test_validate_token_returns_user_id_and_roles(stub, user):
    token = token_of(user)
    response = stub.ValidateToken(auth_pb2.ValidateTokenRequest(token=token), metadata=bearer(token))
    assert response.is_valid is True
    assert response.user_id == str(user["id"])
    assert list(response.roles) == ["user"]


def test_validate_token_without_metadata_is_rejected(stub, user):
    request = auth_pb2.ValidateTokenRequest(token=token_of(user))
    with pytest.raises(grpc.RpcError) as error:
        stub.ValidateToken(request)
    assert error.value.code() == grpc.StatusCode.UNAUTHENTICATED


def test_validate_token_with_invalid_token_is_rejected(stub):
    request = auth_pb2.ValidateTokenRequest(token="not.a.token")
    with pytest.raises(grpc.RpcError) as error:
        stub.ValidateToken(request, metadata=bearer("not.a.token"))
    assert error.value.code() == grpc.StatusCode.UNAUTHENTICATED


def test_validate_token_rejects_mismatched_tokens(stub, user, other_user):
    # токен у metadata і в тілі запиту мають збігатися
    response = stub.ValidateToken(
        auth_pb2.ValidateTokenRequest(token=token_of(other_user)),
        metadata=bearer(token_of(user)),
    )
    assert response.is_valid is False


def test_token_of_deleted_user_is_rejected_by_grpc(stub, client, user, admin):
    token = token_of(user)
    assert client.delete(f"/user/{user['id']}", headers=admin["headers"]).status_code == 204
    request = auth_pb2.ValidateTokenRequest(token=token)
    with pytest.raises(grpc.RpcError) as error:
        stub.ValidateToken(request, metadata=bearer(token))
    assert error.value.code() == grpc.StatusCode.UNAUTHENTICATED


def test_user_exists(stub, user, admin):
    token = token_of(admin)
    existing = stub.UserExists(auth_pb2.UserExistsRequest(user_id=user["id"]), metadata=bearer(token))
    missing = stub.UserExists(auth_pb2.UserExistsRequest(user_id=999999), metadata=bearer(token))
    assert existing.exists is True
    assert missing.exists is False


def test_user_exists_requires_token(stub, user):
    with pytest.raises(grpc.RpcError) as error:
        stub.UserExists(auth_pb2.UserExistsRequest(user_id=user["id"]))
    assert error.value.code() == grpc.StatusCode.UNAUTHENTICATED


def test_user_role_cannot_call_user_exists(stub, user):
    # RBAC на рівні gRPC: роль user не має права перевіряти інших користувачів
    token = token_of(user)
    with pytest.raises(grpc.RpcError) as error:
        stub.UserExists(auth_pb2.UserExistsRequest(user_id=user["id"]), metadata=bearer(token))
    assert error.value.code() == grpc.StatusCode.PERMISSION_DENIED
