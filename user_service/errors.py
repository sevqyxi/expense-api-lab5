from typing import Dict, Optional


class ApiError(Exception):
    def __init__(self, status_code: int, error: str, message: str, headers: Optional[Dict[str, str]] = None):
        self.status_code = status_code
        self.error = error
        self.message = message
        self.headers = headers
