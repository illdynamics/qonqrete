import sys
import tempfile
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "worqer"))

from qualifier.adapters.python import PythonAdapter  # noqa: E402
from qualifier.base import QualifyContext  # noqa: E402


def test_python_import_check_treats_fastapi_as_pydantic_provider():
    with tempfile.TemporaryDirectory() as td:
        qodeyard = Path(td)
        main_py = qodeyard / "main.py"
        main_py.write_text(
            "\n".join(
                [
                    "from fastapi import FastAPI",
                    "from pydantic import BaseModel",
                    "",
                    "app = FastAPI()",
                    "",
                    "class User(BaseModel):",
                    "    id: int",
                ]
            ),
            encoding="utf-8",
        )
        (qodeyard / "requirements.txt").write_text("fastapi\nuvicorn\n", encoding="utf-8")

        ctx = QualifyContext(
            qodeyard_path=qodeyard,
            qontext_path=None,
            config={},
            python_checks={"syntax": False, "imports": True, "skeleton_match": False},
            tier="low",
        )

        adapter = PythonAdapter()
        with mock.patch("qualifier.adapters.python.find_binary", return_value=None):
            results = adapter.qualify(main_py, ctx)

        undeclared_rows = [
            row
            for row in results
            if row.check_type == "import:undeclared" and "pydantic" in row.message.lower()
        ]
        assert undeclared_rows == []
