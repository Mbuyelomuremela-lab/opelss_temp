"""Tests for visitor ID / SACE / cellphone capture. Uses a throwaway local SQLite DB."""
import importlib
import os
import sqlite3
from datetime import date
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest
from openpyxl import load_workbook


def make_sa_id(yymmdd="900101", gender="5009", citizen="0", race="8"):
    """Build a 13-digit SA ID with a correct Luhn check digit."""
    body = yymmdd + gender + citizen + race
    for check in "0123456789":
        candidate = body + check
        total = 0
        for i, ch in enumerate(reversed(candidate)):
            n = int(ch)
            if i % 2 == 1:
                n = n * 2 - 9 if n * 2 > 9 else n * 2
            total += n
        if total % 10 == 0:
            return candidate
    raise AssertionError("unreachable")


VALID_ID = make_sa_id()
VALID_CELL = "0821234567"


# ---------------------------------------------------------------- validators

def test_sa_id_validator():
    from app.visitors.forms import sa_id_error

    assert sa_id_error(VALID_ID) is None
    assert sa_id_error(make_sa_id("000229")) is None  # 29 Feb 2000 is real
    assert "13 digits" in sa_id_error("12345")
    assert "13 digits" in sa_id_error("90010150090A8")
    assert "birth date" in sa_id_error(make_sa_id("901301"))  # month 13
    assert "birth date" in sa_id_error(make_sa_id("010229"))  # 29 Feb 2001/1901
    assert "citizenship" in sa_id_error(make_sa_id(citizen="2"))
    bad_check = VALID_ID[:-1] + str((int(VALID_ID[-1]) + 1) % 10)
    assert "check digit" in sa_id_error(bad_check)


@pytest.mark.parametrize("value,ok", [
    ("0821234567", True),
    ("+27821234567", True),
    ("082 123 4567", True),
    ("0721234567", True),
    ("0612345678", True),
    ("0121234567", False),   # landline prefix
    ("082123456", False),    # too short
    ("27821234567", False),  # missing +
    ("+2708212345678", False),
    ("abcdefghij", False),
])
def test_cellphone_validator(value, ok):
    from app.visitors.forms import is_valid_sa_mobile
    assert is_valid_sa_mobile(value) is ok


# ---------------------------------------------------------------- app fixture

@pytest.fixture
def app_env(tmp_path):
    db_path = tmp_path / "visitors_test.db"
    with patch.dict(os.environ, {
        "DATABASE_URL": f"sqlite:///{db_path}",
        "SECRET_KEY": "test-secret-key",
    }):
        os.environ.pop("VERCEL", None)
        import config
        importlib.reload(config)
        import app as app_package
        importlib.reload(app_package)
        app = app_package.create_app()
        app.config["WTF_CSRF_ENABLED"] = False

        with app.app_context():
            from app.extensions import db
            from app.models.lab import Lab
            from app.models.user import User
            lab = Lab.query.first()
            user = User.query.filter_by(email="admin@opelss.com").first()
            ids = {"lab_id": lab.id, "user_id": user.id}

        client = app.test_client()
        with client.session_transaction() as session:
            session["_user_id"] = str(ids["user_id"])
            session["_fresh"] = True

        yield app, client, ids, db_path

        with app.app_context():
            db.session.remove()
            db.engine.dispose()


def _payload(lab_id, **overrides):
    data = {
        "visitor_name": "Test Visitor",
        "category": "Other",
        "student_number": "",
        "sace_number": "",
        "id_number": VALID_ID,
        "cellphone_number": VALID_CELL,
        "purpose": "Testing",
        "visit_date": "2026-11-25",
        "lab_id": str(lab_id),
    }
    data.update(overrides)
    return data


def _post_json(client, data):
    return client.post("/visitors/create", json=data)


# ---------------------------------------------------------------- create

@pytest.mark.parametrize("category,extra", [
    ("UNISA Student", {"student_number": "12345678"}),
    ("Learner", {}),
    ("Other", {}),
])
def test_id_categories_create_and_encrypt(app_env, category, extra):
    app, client, ids, db_path = app_env
    resp = _post_json(client, _payload(ids["lab_id"], category=category, **extra))
    assert resp.status_code == 200, resp.get_json()
    assert VALID_ID.encode() in resp.get_json()["row_html"].encode()

    with app.app_context():
        from app.models.visitor import Visitor
        v = Visitor.query.one()
        assert v.id_number == VALID_ID
        assert v.id_number_encrypted and VALID_ID not in v.id_number_encrypted
        assert v.sace_number is None
        assert v.cellphone_number == VALID_CELL
        assert v.student_number == (extra.get("student_number"))

    raw = sqlite3.connect(db_path).execute("SELECT id_number_encrypted FROM visitors").fetchone()[0]
    assert VALID_ID not in raw


def test_educator_requires_sace_not_id(app_env):
    app, client, ids, _ = app_env
    resp = _post_json(client, _payload(ids["lab_id"], category="Educator", id_number="", sace_number=""))
    assert resp.status_code == 400
    assert "SACE number is required" in resp.get_json()["message"]

    resp = _post_json(client, _payload(ids["lab_id"], category="Educator", id_number="", sace_number="1234567"))
    assert resp.status_code == 400
    assert "exactly 8 digits" in resp.get_json()["message"]

    resp = _post_json(client, _payload(ids["lab_id"], category="Educator", id_number=VALID_ID, sace_number="12345678"))
    assert resp.status_code == 200
    with app.app_context():
        from app.models.visitor import Visitor
        v = Visitor.query.one()
        assert v.sace_number == "12345678"
        assert v.id_number is None  # ID ignored for educators


@pytest.mark.parametrize("category", ["UNISA Student", "Learner", "Other"])
def test_id_required_and_validated(app_env, category):
    _, client, ids, _ = app_env
    extra = {"student_number": "12345678"} if category == "UNISA Student" else {}
    resp = _post_json(client, _payload(ids["lab_id"], category=category, id_number="", **extra))
    assert resp.status_code == 400
    assert "ID number is required" in resp.get_json()["message"]

    bad = VALID_ID[:-1] + str((int(VALID_ID[-1]) + 1) % 10)
    resp = _post_json(client, _payload(ids["lab_id"], category=category, id_number=bad, **extra))
    assert resp.status_code == 400
    assert "check digit" in resp.get_json()["message"]


def test_unisa_still_requires_student_number(app_env):
    _, client, ids, _ = app_env
    resp = _post_json(client, _payload(ids["lab_id"], category="UNISA Student", student_number=""))
    assert resp.status_code == 400
    assert "Student number is required" in resp.get_json()["message"]


@pytest.mark.parametrize("category,extra", [
    ("UNISA Student", {"student_number": "12345678"}),
    ("Educator", {"sace_number": "12345678", "id_number": ""}),
    ("Other", {}),
])
def test_cellphone_required_except_learner(app_env, category, extra):
    _, client, ids, _ = app_env
    resp = _post_json(client, _payload(ids["lab_id"], category=category, cellphone_number="", **extra))
    assert resp.status_code == 400
    assert "Cellphone number is required" in resp.get_json()["message"]

    resp = _post_json(client, _payload(ids["lab_id"], category=category, cellphone_number="12345", **extra))
    assert resp.status_code == 400
    assert "valid SA cellphone" in resp.get_json()["message"]


def test_learner_cellphone_optional_but_validated(app_env):
    _, client, ids, _ = app_env
    resp = _post_json(client, _payload(ids["lab_id"], category="Learner", cellphone_number=""))
    assert resp.status_code == 200
    resp = _post_json(client, _payload(ids["lab_id"], category="Learner", cellphone_number="0123"))
    assert resp.status_code == 400


def test_cellphone_spaces_are_stripped(app_env):
    app, client, ids, _ = app_env
    resp = _post_json(client, _payload(ids["lab_id"], cellphone_number="+27 82 123 4567"))
    assert resp.status_code == 200
    with app.app_context():
        from app.models.visitor import Visitor
        assert Visitor.query.one().cellphone_number == "+27821234567"


# ---------------------------------------------------------------- old records

def _insert_old_record(app, lab_id):
    with app.app_context():
        from app.extensions import db
        from app.models.visitor import Visitor
        v = Visitor(visitor_name="Old Visitor", category="Other", cellphone_number=VALID_CELL,
                    purpose="Legacy", visit_date=date(2025, 1, 1), lab_id=lab_id)
        db.session.add(v)
        db.session.commit()
        return v.id


def test_old_record_lists_and_must_be_completed_on_edit(app_env):
    app, client, ids, _ = app_env
    vid = _insert_old_record(app, ids["lab_id"])

    page = client.get("/visitors/")
    assert page.status_code == 200
    assert b"Old Visitor" in page.data

    form = _payload(ids["lab_id"], visitor_name="Old Visitor", id_number="")
    resp = client.post(f"/visitors/{vid}/update", data=form, follow_redirects=True)
    assert b"ID number is required" in resp.data
    with app.app_context():
        from app.models.visitor import Visitor
        assert Visitor.query.get(vid).id_number is None

    form["id_number"] = VALID_ID
    resp = client.post(f"/visitors/{vid}/update", data=form, follow_redirects=True)
    assert b"Visitor updated successfully" in resp.data
    with app.app_context():
        from app.models.visitor import Visitor
        assert Visitor.query.get(vid).id_number == VALID_ID


def test_index_and_export_show_full_id(app_env):
    _, client, ids, _ = app_env
    _post_json(client, _payload(ids["lab_id"]))
    _post_json(client, _payload(ids["lab_id"], visitor_name="Teacher", category="Educator",
                                id_number="", sace_number="87654321"))

    page = client.get("/visitors/")
    assert VALID_ID.encode() in page.data
    assert b"87654321" in page.data

    resp = client.get("/visitors/export")
    assert resp.status_code == 200
    ws = load_workbook(BytesIO(resp.data))["Visitors"]
    header = [c.value for c in ws[1]]
    assert "ID Number" in header and "SACE Number" in header
    rows = [[c.value for c in r] for r in ws.iter_rows(min_row=2)]
    id_col, sace_col = header.index("ID Number"), header.index("SACE Number")
    assert VALID_ID in [r[id_col] for r in rows]
    assert "87654321" in [r[sace_col] for r in rows]


def test_html_in_name_is_escaped_in_new_row(app_env):
    _, client, ids, _ = app_env
    resp = _post_json(client, _payload(ids["lab_id"], visitor_name="<script>x</script>"))
    assert resp.status_code == 200
    assert "<script>" not in resp.get_json()["row_html"]


# ---------------------------------------------------------------- schema

def test_runtime_schema_adds_new_columns_to_old_table(tmp_path):
    db_path = tmp_path / "old.db"
    con = sqlite3.connect(db_path)
    con.execute(
        "CREATE TABLE visitors (id INTEGER PRIMARY KEY, visitor_name VARCHAR(120) NOT NULL, "
        "category VARCHAR(100) NOT NULL, purpose TEXT NOT NULL, visit_date DATE NOT NULL, lab_id INTEGER NOT NULL)"
    )
    con.commit()
    con.close()

    with patch.dict(os.environ, {"DATABASE_URL": f"sqlite:///{db_path}", "SECRET_KEY": "k"}):
        os.environ.pop("VERCEL", None)
        import config
        importlib.reload(config)
        import app as app_package
        importlib.reload(app_package)
        app = app_package.create_app()
        with app.app_context():
            from app.extensions import db
            db.engine.dispose()

    cols = {r[1] for r in sqlite3.connect(db_path).execute("PRAGMA table_info(visitors)")}
    assert {"student_number", "cellphone_number", "sace_number", "id_number_encrypted"} <= cols


def test_migration_chain_has_single_head():
    versions = Path(__file__).resolve().parent.parent / "migrations" / "versions"
    revs, downs = set(), set()
    for f in versions.glob("*.py"):
        text = f.read_text()
        ns = {}
        for line in text.splitlines():
            if line.startswith(("revision", "down_revision")):
                key, _, value = line.partition("=")
                ns[key.split(":")[0].strip()] = eval(value.strip())  # simple string literals
        revs.add(ns["revision"])
        if ns.get("down_revision"):
            downs.add(ns["down_revision"])
    heads = revs - downs
    assert heads == {"c8d4e2f6a1b7"}
