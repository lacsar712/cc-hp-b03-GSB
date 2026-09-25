import json
import os
from datetime import datetime, timedelta, timezone

import psycopg
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from psycopg.rows import dict_row

from rules import judge

SECRET = os.environ.get("JWT_SECRET", "herb-process-dev-secret")
DSN = os.environ.get("DATABASE_URL", "postgresql://app:app@localhost:54393/herb")
REQUIRED_SIGNATURES = 2
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)
USERS = {
    "processor": {"role": "writer", "password_hash": pwd.hash("herb123456")},
    "checker": {"role": "reader", "password_hash": pwd.hash("check123456")},
    "checker2": {"role": "reader", "password_hash": pwd.hash("check2_123456")},
}


def connect():
    return psycopg.connect(DSN, row_factory=dict_row)


class LoginIn(BaseModel):
    username: str
    password: str


class StepIn(BaseModel):
    name: str
    temp_c: float
    minutes: float


class BatchIn(BaseModel):
    herb: str = Field(min_length=1, max_length=80)
    steps: list[StepIn]


class CountersignIn(BaseModel):
    comment: str = Field(default="", max_length=500)


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict:
    if credentials is None:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        payload = jwt.decode(credentials.credentials, SECRET, algorithms=["HS256"])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="无效令牌") from exc
    if payload.get("sub") not in USERS:
        raise HTTPException(401, "无效令牌")
    return {"username": payload["sub"], "role": payload.get("role")}


def require_writer(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "writer":
        raise HTTPException(status_code=403, detail="仅炮制员可写入记录")
    return user


def require_reader(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "reader":
        raise HTTPException(status_code=403, detail="仅质检员可会签")
    return user


def sign_status(count: int) -> str:
    return "会签完成" if count >= REQUIRED_SIGNATURES else "待会签"


def serialize_batch(conn, row: dict) -> dict:
    """挂载会签状态与履历。row 需来自 batches 全字段。"""
    signs = conn.execute(
        """SELECT checker, comment, signed_at
           FROM countersigns WHERE batch_id = %s ORDER BY signed_at, id""",
        (row["id"],),
    ).fetchall()
    out = dict(row)
    out["countersigns"] = [
        {"checker": s["checker"], "comment": s["comment"], "signed_at": s["signed_at"].isoformat()}
        for s in signs
    ]
    out["sign_count"] = len(signs)
    out["sign_status"] = sign_status(len(signs))
    out["release_effective"] = row["verdict"] == "放行" and len(signs) >= REQUIRED_SIGNATURES
    return out


app = FastAPI(title="饮片炮制记录台")


@app.on_event("startup")
def startup():
    with connect() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS batches (
                id serial PRIMARY KEY,
                herb text NOT NULL,
                doc jsonb NOT NULL,
                verdict text NOT NULL,
                reason text NOT NULL,
                created_by text NOT NULL,
                created_at timestamptz NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS countersigns (
                id serial PRIMARY KEY,
                batch_id integer NOT NULL REFERENCES batches(id),
                checker text NOT NULL,
                comment text NOT NULL DEFAULT '',
                signed_at timestamptz NOT NULL,
                UNIQUE (batch_id, checker)
            )"""
        )
        count = conn.execute("SELECT COUNT(*) AS n FROM batches").fetchone()["n"]
        if count == 0:
            now = datetime.now(timezone.utc)
            samples = [
                ("甘草", {"steps": [{"name": "清炒", "temp_c": 120, "minutes": 12}]}),
                ("黄芩", {"steps": [{"name": "清炒", "temp_c": 40, "minutes": 12}]}),
            ]
            for herb, doc in samples:
                verdict, reason = judge(doc)
                conn.execute(
                    """INSERT INTO batches (herb, doc, verdict, reason, created_by, created_at)
                       VALUES (%s, %s::jsonb, %s, %s, %s, %s)""",
                    (herb, json.dumps(doc, ensure_ascii=False), verdict, reason, "processor", now),
                )
        conn.commit()


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "herb-process-record"}


@app.post("/api/auth/login")
def login(body: LoginIn):
    username = body.username.strip()
    user = USERS.get(username)
    if not user or not pwd.verify(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    exp = datetime.now(timezone.utc) + timedelta(hours=8)
    token = jwt.encode({"sub": username, "role": user["role"], "exp": exp}, SECRET, algorithm="HS256")
    return {"access_token": token, "username": username, "role": user["role"]}


@app.get("/api/batches")
def list_batches(_user: dict = Depends(current_user)):
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, herb, doc, verdict, reason, created_by, created_at FROM batches ORDER BY id DESC"
        ).fetchall()
        return [serialize_batch(conn, row) for row in rows]


@app.get("/api/batches/{batch_id}")
def get_batch(batch_id: int, _user: dict = Depends(current_user)):
    with connect() as conn:
        row = conn.execute(
            "SELECT id, herb, doc, verdict, reason, created_by, created_at FROM batches WHERE id = %s",
            (batch_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="记录不存在")
        return serialize_batch(conn, row)


@app.post("/api/batches", status_code=201)
def create_batch(body: BatchIn, user: dict = Depends(require_writer)):
    doc = {"steps": [s.model_dump() for s in body.steps]}
    verdict, reason = judge(doc)
    with connect() as conn:
        row = conn.execute(
            """INSERT INTO batches (herb, doc, verdict, reason, created_by, created_at)
               VALUES (%s, %s::jsonb, %s, %s, %s, %s)
               RETURNING id, herb, doc, verdict, reason, created_by, created_at""",
            (body.herb.strip(), json.dumps(doc, ensure_ascii=False), verdict, reason,
             user["username"], datetime.now(timezone.utc)),
        ).fetchone()
        conn.commit()
        return serialize_batch(conn, row)


@app.post("/api/batches/{batch_id}/countersign", status_code=201)
def countersign_batch(batch_id: int, body: CountersignIn, user: dict = Depends(require_reader)):
    with connect() as conn:
        row = conn.execute(
            "SELECT id, herb, doc, verdict, reason, created_by, created_at FROM batches WHERE id = %s",
            (batch_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="记录不存在")
        if row["verdict"] != "放行":
            raise HTTPException(status_code=409, detail="仅放行记录需要会签")
        existed = conn.execute(
            "SELECT id FROM countersigns WHERE batch_id = %s AND checker = %s",
            (batch_id, user["username"]),
        ).fetchone()
        if existed is not None:
            raise HTTPException(status_code=409, detail="该质检员已会签，不能重复会签")
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM countersigns WHERE batch_id = %s",
            (batch_id,),
        ).fetchone()["n"]
        if count >= REQUIRED_SIGNATURES:
            raise HTTPException(status_code=409, detail="会签已满两人")
        conn.execute(
            """INSERT INTO countersigns (batch_id, checker, comment, signed_at)
               VALUES (%s, %s, %s, %s)""",
            (batch_id, user["username"], body.comment.strip(), datetime.now(timezone.utc)),
        )
        conn.commit()
        return serialize_batch(conn, row)
