"""邀请码注册及 Bearer 身份认证。"""

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.hash import bcrypt
from pydantic import BaseModel, Field, field_validator

from beanbot.exceptions import DomainError, InvalidInviteCode, Unauthorized
from beanbot.storage.database import now

router = APIRouter(prefix="/auth")
# 从请求头里解析 Authorization: Bearer<token>
# 解析成功后，把token封装成 HTTPAuthorizationCredentials对象
bearer = HTTPBearer(auto_error=False)


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=64, pattern=r"^[\w.-]+$")
    password: str = Field(min_length=8, max_length=72)

    @field_validator("password")
    @classmethod
    def password_bytes(cls, value):
        if len(value.encode()) > 72:
            raise ValueError("密码不得超过 72 字节")
        return value


class Register(Login):
    invite_code: str = ""


def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> dict:
    if not credentials:
        raise Unauthorized("请先登录")
    try:
        claims = jwt.decode(
            credentials.credentials,
            request.app.state.settings.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            options={"require_exp": True, "require_sub": True},
        )
        users = request.app.state.db.rows(
            "SELECT id,username,ledger_path FROM users WHERE id=?", (claims["sub"],)
        )
    except (JWTError, KeyError):
        raise Unauthorized("登录已过期，请重新登录") from None
    if not users:
        raise Unauthorized("用户不存在")
    return users[0]


def token(request: Request, user_id: str):
    return {
        "access_token": jwt.encode(
            {"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(days=7)},
            request.app.state.settings.jwt_secret.get_secret_value(),
            algorithm="HS256",
        ),
        "token_type": "bearer",
    }


@router.post("/register")
async def register(body: Register, request: Request):
    store = request.app.state.db
    user_id = uuid4().hex
    password_hash = bcrypt.using(rounds=12).hash(body.password)
    try:
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            invite = db.execute(
                "SELECT * FROM invite_codes WHERE code=? AND used_by IS NULL",
                (body.invite_code,),
            ).fetchone()
            if not invite:
                raise InvalidInviteCode("邀请码无效或已使用")
            db.execute(
                "INSERT INTO users VALUES(?,?,?,?,?)",
                (user_id, body.username, password_hash, None, now()),
            )
            db.execute(
                "INSERT INTO user_settings(user_id,confidence_threshold) VALUES(?,?)",
                (user_id, request.app.state.settings.confidence_threshold),
            )
            request.app.state.ledgers.get({"id": user_id, "ledger_path": None})
            db.execute(
                "UPDATE invite_codes SET used_by=?,used_at=? WHERE code=?",
                (user_id, now(), body.invite_code),
            )
    except sqlite3.IntegrityError:
        raise DomainError("用户名已存在") from None
    return token(request, user_id)


@router.post("/login")
async def login(body: Login, request: Request):
    users = request.app.state.db.rows(
        "SELECT * FROM users WHERE username=?", (body.username,)
    )
    # 未知用户也执行一次密码校验，避免明显的时间差。
    stored = (
        users[0]["password_hash"] if users else request.app.state.dummy_password_hash
    )
    valid = bcrypt.verify(body.password, stored)
    if not users or not valid:
        raise Unauthorized("用户名或密码错误")
    return token(request, users[0]["id"])


CurrentUser = Annotated[dict, Depends(get_current_user)]


@router.get("/me")
async def me(user: CurrentUser):
    return {"id": user["id"], "username": user["username"]}
