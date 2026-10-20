"""Isolated ZTE HTTP protocol and AI fixtures. Never part of a production image."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

app = FastAPI(title="Synthetic smoke services")
DATABASE = Path("/var/lib/gsm-agent/fixtures.sqlite3")


@contextmanager
def connect():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    try:
        with db:
            db.execute("CREATE TABLE IF NOT EXISTS incoming (id INTEGER PRIMARY KEY, body TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS outgoing (body TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS calls (history TEXT NOT NULL)")
            yield db
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok", "synthetic": True}


@app.get("/js/config/config.js", response_class=PlainTextResponse)
def config():
    return "define(function() { return { DEVICE: 'datacard/mf833T' }; });"


@app.get("/goform/goform_get_cmd_process")
def read(cmd: str, page: int = 0):
    if cmd == "sms_page_data":
        with connect() as db:
            rows = db.execute(
                "SELECT id, body FROM incoming ORDER BY id DESC LIMIT 50 OFFSET ?", (page * 50,)
            )
            return {
                "messages": [
                    {
                        "id": str(row["id"]),
                        "number": "+212600000000",
                        "date": "26;01;01;12;00;00;+00",
                        "content": row["body"].encode("utf-16-be").hex(),
                        "tag": "1",
                        "received_all_concat_sms": "1",
                    }
                    for row in rows
                ]
            }
    if cmd == "sms_cmd_status_info":
        return {"sms_cmd_status_result": "3"}
    return {
        "wa_inner_version": "BD_WANAMARMF833TV1.0.0B04",
        "hardware_version": "djtA",
        "network_provider": "Synthetic carrier",
        "network_type": "LTE",
        "signalbar": "4",
    }


@app.post("/goform/goform_set_cmd_process")
async def submit(request: Request):
    data = parse_qs((await request.body()).decode())
    if data.get("goformId") != ["SEND_SMS"] or data.get("Number") != ["+212600000000"]:
        raise HTTPException(400, "Unexpected synthetic submission")
    body = bytes.fromhex(data["MessageBody"][0]).decode("utf-16-be")
    with connect() as db:
        db.execute("INSERT INTO outgoing VALUES (?)", (body,))
    return {"result": "success"}


class Incoming(BaseModel):
    body: str = Field(min_length=1, max_length=1000)


@app.post("/incoming")
def incoming(body: Incoming):
    with connect() as db:
        cursor = db.execute("INSERT INTO incoming (body) VALUES (?)", (body.body,))
        return {"id": str(cursor.lastrowid)}


@app.post("/agent")
async def agent(request: Request):
    data = await request.json()
    with connect() as db:
        db.execute("INSERT INTO calls VALUES (?)", (json.dumps(data["messages"]),))
    return {"action": "reply", "text": "**Hello!** This is a synthetic SMS reply."}


@app.get("/effects")
def effects():
    with connect() as db:
        return {
            "outgoing": [row["body"] for row in db.execute("SELECT body FROM outgoing")],
            "histories": [json.loads(row["history"]) for row in db.execute("SELECT history FROM calls")],
        }
