import json
import os
from datetime import datetime, timedelta, timezone

import psycopg
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from rules import judge

SECRET = os.environ.get("JWT_SECRET", "herb-process-dev-secret")
DSN = os.environ.get("DATABASE_URL", "postgresql://app:app@localhost:54393/herb")
REQUIRED_COSIGNS = 2
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)
USERS = {
    "processor": {"role": "writer", "password_hash": pwd.hash("herb123456")},
    "checker": {"role": "reader", "password_hash": pwd.hash("check123456")},
    "checker2": {"role": "reader", "password_hash": pwd.hash("check123456")},
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


class CosignIn(BaseModel):
    opinion: str = Field(min_length=1, max_length=500)


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict:
    if credentials is None:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        payload = jwt.decode(credentials.credentials, SECRET, algorithms=["HS256"])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="无效令牌") from exc
    if payload.get("sub") not in USERS:
        raise HTTPException(status_code=401, detail="无效令牌")
    return {"username": payload["sub"], "role": payload.get("role")}


def require_writer(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "writer":
        raise HTTPException(status_code=403, detail="仅炮制员可写入记录")
    return user


def require_reader(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "reader":
        raise HTTPException(status_code=403, detail="仅质检员可会签")
    return user


def cosign_status(verdict: str, count: int) -> str | None:
    if verdict != "放行":
        return None
    return "会签完成" if count >= REQUIRED_COSIGNS else "待会签"


def batch_summary(row: dict, cosign_count: int) -> dict:
    return {
        "id": row["id"],
        "herb": row["herb"],
        "verdict": row["verdict"],
        "reason": row["reason"],
        "created_by": row["created_by"],
        "created_at": row["created_at"],
        "cosign_required": row["verdict"] == "放行",
        "cosign_count": cosign_count,
        "cosign_status": cosign_status(row["verdict"], cosign_count),
    }


def fetch_cosigns(conn, batch_id: int) -> list[dict]:
    return conn.execute(
        "SELECT signed_by, opinion, created_at FROM cosigns WHERE batch_id = %s ORDER BY id",
        (batch_id,),
    ).fetchall()


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
            """CREATE TABLE IF NOT EXISTS cosigns (
                id serial PRIMARY KEY,
                batch_id integer NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
                signed_by text NOT NULL,
                opinion text NOT NULL,
                created_at timestamptz NOT NULL,
                UNIQUE (batch_id, signed_by)
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
    user = USERS.get(body.username.strip())
    if not user or not pwd.verify(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    exp = datetime.now(timezone.utc) + timedelta(hours=8)
    token = jwt.encode({"sub": body.username.strip(), "role": user["role"], "exp": exp}, SECRET, algorithm="HS256")
    return {"access_token": token, "username": body.username.strip(), "role": user["role"]}


@app.get("/api/batches")
def list_batches(_user: dict = Depends(current_user)):
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, herb, verdict, reason, created_by, created_at FROM batches ORDER BY id DESC"
        ).fetchall()
        counts = {
            r["batch_id"]: r["n"]
            for r in conn.execute("SELECT batch_id, COUNT(*) AS n FROM cosigns GROUP BY batch_id").fetchall()
        }
    return [batch_summary(row, counts.get(row["id"], 0)) for row in rows]


@app.post("/api/batches", status_code=201)
def create_batch(body: BatchIn, user: dict = Depends(require_writer)):
    doc = {"steps": [s.model_dump() for s in body.steps]}
    verdict, reason = judge(doc)
    with connect() as conn:
        row = conn.execute(
            """INSERT INTO batches (herb, doc, verdict, reason, created_by, created_at)
               VALUES (%s, %s::jsonb, %s, %s, %s, %s)
               RETURNING id, herb, doc, verdict, reason, created_by, created_at""",
            (body.herb.strip(), json.dumps(doc, ensure_ascii=False), verdict, reason, user["username"], datetime.now(timezone.utc)),
        ).fetchone()
        conn.commit()
    return batch_summary(row, 0)


@app.get("/api/batches/{batch_id}")
def get_batch(batch_id: int, _user: dict = Depends(current_user)):
    with connect() as conn:
        row = conn.execute(
            "SELECT id, herb, doc, verdict, reason, created_by, created_at FROM batches WHERE id = %s",
            (batch_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="记录不存在")
        cosigns = fetch_cosigns(conn, batch_id)
    data = batch_summary(row, len(cosigns))
    data["doc"] = row["doc"]
    data["cosigns"] = cosigns
    return data


@app.post("/api/batches/{batch_id}/cosign", status_code=201)
def cosign_batch(batch_id: int, body: CosignIn, user: dict = Depends(require_reader)):
    opinion = body.opinion.strip()
    if not opinion:
        raise HTTPException(status_code=422, detail="请填写会签意见")
    with connect() as conn:
        row = conn.execute("SELECT id, verdict FROM batches WHERE id = %s", (batch_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="记录不存在")
        if row["verdict"] != "放行":
            raise HTTPException(status_code=409, detail="未放行记录无需会签")
        signers = [
            r["signed_by"]
            for r in conn.execute("SELECT signed_by FROM cosigns WHERE batch_id = %s", (batch_id,)).fetchall()
        ]
        if user["username"] in signers:
            raise HTTPException(status_code=409, detail="该质检员已会签过此记录")
        if len(signers) >= REQUIRED_COSIGNS:
            raise HTTPException(status_code=409, detail="会签已完成，无需再签")
        try:
            conn.execute(
                "INSERT INTO cosigns (batch_id, signed_by, opinion, created_at) VALUES (%s, %s, %s, %s)",
                (batch_id, user["username"], opinion, datetime.now(timezone.utc)),
            )
        except UniqueViolation as exc:
            raise HTTPException(status_code=409, detail="该质检员已会签过此记录") from exc
        conn.commit()
        cosigns = fetch_cosigns(conn, batch_id)
    return {
        "batch_id": batch_id,
        "cosign_count": len(cosigns),
        "cosign_status": cosign_status(row["verdict"], len(cosigns)),
        "cosigns": cosigns,
    }
