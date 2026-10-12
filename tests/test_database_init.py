import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class DatabaseInitializationTest(unittest.TestCase):
    def test_create_app_does_not_create_or_modify_database_schema(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_app.db"
            with patch.dict(
                os.environ,
                {
                    "DATABASE_URL": f"sqlite:///{db_path}",
                    "SECRET_KEY": "test-secret-key",
                    "VERCEL": "1",
                },
            ):
                import config
                importlib.reload(config)

                import app as app_package
                importlib.reload(app_package)

                app = app_package.create_app()

                with app.app_context():
                    from app.extensions import db
                    inspector = db.inspect(db.engine)
                    tables = inspector.get_table_names()

                self.assertEqual(tables, [])

                with app.app_context():
                    from app.extensions import db as db_instance
                    db_instance.session.remove()
                    db_instance.engine.dispose()

            if db_path.exists():
                db_path.unlink(missing_ok=True)

    def test_vercel_requires_database_url_and_secret_key(self):
        import app as app_package

        with patch.dict(os.environ, {"VERCEL": "1"}):
            os.environ.pop("DATABASE_URL", None)
            os.environ.pop("SECRET_KEY", None)

            with self.assertRaisesRegex(
                RuntimeError,
                "DATABASE_URL, SECRET_KEY",
            ):
                app_package.create_app()


if __name__ == "__main__":
    unittest.main()
