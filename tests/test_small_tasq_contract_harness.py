import os
from pathlib import Path
import stat
import pytest
from worqer import contract_harness

def test_detect_harness_class():
    tasq = "User model must contain id, username, email, password. Fastapi."
    assert contract_harness.detect_harness_class(tasq) == "fastapi_users_memory_api.v1"
    
def test_build_harness():
    tasq = "User model must contain id. fastapi"
    h = contract_harness.build_harness(tasq)
    assert h["harness_id"] == "fastapi_users_memory_api.v1"
    assert "main.py" in h["required_files"]

def test_apply_autofixes(tmp_path):
    h = {"harness_id": "fastapi_users_memory_api.v1", "autofixes": ["requirements.txt", "run.sh"]}
    
    # Missing files
    applied = contract_harness.apply_autofixes(tmp_path, h).get("autofixes_applied", [])
    assert "requirements.txt" in applied
    assert "run.sh" in applied
    assert "fastapi" in (tmp_path / "requirements.txt").read_text()
    assert "uvicorn" in (tmp_path / "requirements.txt").read_text()
    run_sh = (tmp_path / "run.sh").read_text()
    assert "python -m uvicorn main:app --reload --port \"$PORT\"" in run_sh
    assert "PORT=8000" not in run_sh
    assert os.stat(tmp_path / "run.sh").st_mode & stat.S_IXUSR
    
    # Existing files but bad content
    (tmp_path / "requirements.txt").write_text("junk\n")
    applied = contract_harness.apply_autofixes(tmp_path, h).get("autofixes_applied", [])
    assert "requirements.txt" in applied
    assert "fastapi" in (tmp_path / "requirements.txt").read_text()

def test_run_harness_missing_files(tmp_path):
    h = {"harness_id": "test", "required_files": ["main.py"]}
    res = contract_harness.run_harness(tmp_path, h, apply_fixes=False)
    assert res["passed"] is False
    assert "main.py" in res["required_files"]["missing"]

def test_run_harness_success(tmp_path, monkeypatch):
    h = {"harness_id": "fastapi_users_memory_api.v1", "required_files": ["main.py", "requirements.txt", "run.sh"]}
    (tmp_path / "requirements.txt").write_text("fastapi\nuvicorn\n")
    (tmp_path / "run.sh").write_text("#!/bin/sh\nset -eu\npython -m uvicorn main:app --reload --port $PORT\n")
    (tmp_path / "run.sh").chmod(0o755)
    main_code = """
PORT = 8000
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

# Run with:
# uvicorn main:app --reload --port $PORT

class User(BaseModel):
    id: int
    username: str
    email: str
    password: str

users = []
next_id = 1

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.post("/users")
def create_user(payload: dict):
    global next_id
    user = User(id=next_id, username=payload["username"], email=payload["email"], password=payload["password"])
    users.append(user)
    next_id += 1
    return user

@app.get("/users")
def list_users():
    return users

@app.get("/users/{user_id}")
def get_user(user_id: int):
    for u in users:
        if u.id == user_id:
            return u
    raise HTTPException(status_code=404)
"""
    (tmp_path / "main.py").write_text(main_code)
    
    monkeypatch.setattr(
        contract_harness,
        "_launch_and_exercise_server",
        lambda *args, **kwargs: {
            "classification": "PASS",
            "code": "PASS",
            "message": "mocked launch success",
            "stdout": "",
            "stderr": "",
            "command": "/bin/sh run.sh",
        },
    )

    res = contract_harness.run_harness(tmp_path, h, apply_fixes=False)
    if not res["passed"]:
        print(res.get("violations"))
    assert res["passed"] is True
    assert res["status"] == "PASS"

def test_run_harness_bad_user_fields(tmp_path):
    h = {"harness_id": "fastapi_users_memory_api.v1", "required_files": ["main.py", "requirements.txt", "run.sh"]}
    (tmp_path / "requirements.txt").write_text("fastapi\nuvicorn\n")
    (tmp_path / "run.sh").write_text("#!/bin/sh\nset -eu\npython -m uvicorn main:app --reload --port $PORT\n")
    main_code = """
PORT = 8000
from fastapi import FastAPI
from pydantic import BaseModel
app = FastAPI()
# Run with:
# uvicorn main:app --reload --port $PORT
class User(BaseModel):
    id: int
    username: str
    is_active: bool # forbidden
"""
    (tmp_path / "main.py").write_text(main_code)
    res = contract_harness.run_harness(tmp_path, h, apply_fixes=False)
    assert res["passed"] is False
    msgs = [v["message"] for v in res["violations"]]
    assert any("Forbidden field 'is_active'" in m for m in msgs)
    assert any("missing field 'email'" in m for m in msgs)

def test_run_harness_inheritance(tmp_path, monkeypatch):
    h = {"harness_id": "fastapi_users_memory_api.v1", "required_files": ["main.py", "requirements.txt", "run.sh"]}
    (tmp_path / "requirements.txt").write_text("fastapi\nuvicorn\n")
    (tmp_path / "run.sh").write_text("#!/bin/sh\nset -eu\npython -m uvicorn main:app --reload --port $PORT\n")
    main_code = """
PORT = 8000
from fastapi import FastAPI
from pydantic import BaseModel
app = FastAPI()
# Run with:
# uvicorn main:app --reload --port $PORT
class UserBase(BaseModel):
    username: str
    email: str
    password: str
class User(UserBase):
    id: int

users = []
@app.get("/health")
def h(): return {"status": "healthy"}
@app.post("/users")
def c(u: UserBase):
    user = {"id": len(users) + 1, **u.dict()}
    users.append(user)
    return user
@app.get("/users")
def l(): return users
@app.get("/users/{id}")
def g(id: int):
    for u in users:
        if u["id"] == id: return u
    from fastapi import HTTPException
    raise HTTPException(status_code=404)
"""
    (tmp_path / "main.py").write_text(main_code)
    monkeypatch.setattr(
        contract_harness,
        "_launch_and_exercise_server",
        lambda *args, **kwargs: {
            "classification": "PASS",
            "code": "PASS",
            "message": "mocked launch success",
            "stdout": "",
            "stderr": "",
            "command": "/bin/sh run.sh",
        },
    )
    res = contract_harness.run_harness(tmp_path, h, apply_fixes=False)
    if not res["passed"]:
        print(res.get("violations"))
    assert res["passed"] is True
