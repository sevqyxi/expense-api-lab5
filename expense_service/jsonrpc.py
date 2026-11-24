"""JSON-RPC 2.0: одиночні й пакетні запити. Не залежить від FastAPI, тому його легко тестувати."""
import logging
from typing import Any, Callable, Optional

from errors import ApiError

logger = logging.getLogger(__name__)

# коди помилок зі специфікації JSON-RPC 2.0
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
# коди застосунку (діапазон -32000..-32099)
UNAUTHORIZED = -32001
SERVICE_UNAVAILABLE = -32002
FORBIDDEN = -32003
NOT_FOUND = -32004

# як коди HTTP-помилок із REST переходять у коди JSON-RPC
API_ERROR_CODES = {
    400: INVALID_PARAMS,
    401: UNAUTHORIZED,
    403: FORBIDDEN,
    404: NOT_FOUND,
    503: SERVICE_UNAVAILABLE,
}

Dispatcher = Callable[[str, Any], Any]


class RpcError(Exception):
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message


def error_response(request_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "error": {"code": code, "message": message}, "id": request_id}


def parse_error_response() -> dict:
    return error_response(None, PARSE_ERROR, "Parse error")


def _is_valid_id(value) -> bool:
    # id може бути рядком, цілим числом або null (bool не дозволяємо)
    return value is None or isinstance(value, str) or (isinstance(value, int) and not isinstance(value, bool))


def _run(method: str, params, dispatch: Dispatcher) -> tuple:
    # повертає (True, результат) або (False, (код, повідомлення))
    try:
        return True, dispatch(method, params)
    except RpcError as error:
        return False, (error.code, error.message)
    except ApiError as error:
        return False, (API_ERROR_CODES.get(error.status_code, INTERNAL_ERROR), error.message)
    except Exception:
        logger.exception("JSON-RPC method %s failed", method)
        return False, (INTERNAL_ERROR, "Internal error")


def _handle_one(item, dispatch: Dispatcher) -> Optional[dict]:
    if not isinstance(item, dict):
        return error_response(None, INVALID_REQUEST, "Invalid Request")

    has_id = "id" in item
    request_id = item.get("id")
    if (
        item.get("jsonrpc") != "2.0"
        or not isinstance(item.get("method"), str)
        or (has_id and not _is_valid_id(request_id))
        or ("params" in item and not isinstance(item["params"], (dict, list)))
    ):
        return error_response(request_id if _is_valid_id(request_id) else None, INVALID_REQUEST, "Invalid Request")

    ok, outcome = _run(item["method"], item.get("params", {}), dispatch)
    # notification (запит без id) виконується, але відповіді на нього немає
    if not has_id:
        return None
    if not ok:
        code, message = outcome
        return error_response(request_id, code, message)
    return {"jsonrpc": "2.0", "result": outcome, "id": request_id}


def handle_payload(payload, dispatch: Dispatcher) -> Optional[Any]:
    # payload — вже розпарсений JSON. None означає, що відповідати не потрібно
    if isinstance(payload, list):
        if not payload:
            return error_response(None, INVALID_REQUEST, "Invalid Request")
        responses = [r for r in (_handle_one(item, dispatch) for item in payload) if r is not None]
        return responses or None
    return _handle_one(payload, dispatch)
