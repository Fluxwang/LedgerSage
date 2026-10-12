"""交易 id 编解码。

交易 id = base64url("<相对路径>:<行号>:<摘要>")。摘要是规范渲染文本的 SHA-256 前八位，
用来在删除前确认「这一行还是我当初看到的那一笔」。详见 ADR 0013。
"""

from __future__ import annotations

import base64
import binascii

from beanbot.exceptions import NotFound

ID_SEPARATOR = ":"


def encode_transaction_id(relative: str, lineno: int, digest: str) -> str:
    raw = f"{relative}{ID_SEPARATOR}{lineno}{ID_SEPARATOR}{digest}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_transaction_id(transaction_id: str) -> tuple[str, int, str]:
    padded = transaction_id + "=" * (-len(transaction_id) % 4)
    try:
        relative, lineno, digest = (
            base64.urlsafe_b64decode(padded).decode().rsplit(ID_SEPARATOR, 2)
        )
        return relative, int(lineno), digest
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise NotFound("交易 id 不合法") from exc
