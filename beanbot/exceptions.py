"""领域异常在 HTTP 边界统一转换成中文错误。"""
class DomainError(Exception):
    status_code = 400


class AccountNotFound(DomainError):
    pass


class LedgerWriteConflict(DomainError):
    status_code = 409


class ClarificationTimeout(DomainError):
    status_code = 410


class InvalidInviteCode(DomainError):
    pass


class NotFound(DomainError):
    status_code = 404


class Unauthorized(DomainError):
    status_code = 401
