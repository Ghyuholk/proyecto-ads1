import os
import tempfile
import unittest

from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import RoleEnum, User


class AuthRolesTestCase(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(prefix="garrobito_test_auth_", suffix=".db")

        class TestConfig:
            TESTING = True
            SECRET_KEY = "test-secret"
            JWT_SECRET_KEY = "test-jwt-secret"
            SQLALCHEMY_TRACK_MODIFICATIONS = False
            SQLALCHEMY_DATABASE_URI = f"sqlite:///{self.db_path}"

        self.app = create_app(TestConfig)
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

        os.close(self.db_fd)
        os.unlink(self.db_path)

    def _create_user(self, username, password, role):
        with self.app.app_context():
            user = User(
                username=username,
                password_hash=generate_password_hash(password),
                role=role,
                is_active=True,
            )
            db.session.add(user)
            db.session.commit()

    def _login_headers(self, username, password):
        resp = self.client.post("/auth/login", json={"username": username, "password": password})
        self.assertEqual(resp.status_code, 200)
        token = resp.get_json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_login_returns_token_and_user(self):
        self._create_user("admin", "admin123", RoleEnum.ADMIN)
        resp = self.client.post("/auth/login", json={"username": "admin", "password": "admin123"})

        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertIn("access_token", body)
        self.assertEqual(body["user"]["username"], "admin")
        self.assertEqual(body["user"]["role"], RoleEnum.ADMIN.value)

    def test_auth_me(self):
        self._create_user("mesero", "mesero123", RoleEnum.MESERO)
        headers = self._login_headers("mesero", "mesero123")
        resp = self.client.get("/auth/me", headers=headers)

        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["user"]["username"], "mesero")
        self.assertEqual(body["user"]["role"], RoleEnum.MESERO.value)

    def test_roles_guard(self):
        self._create_user("admin", "admin123", RoleEnum.ADMIN)
        self._create_user("cajero", "cajero123", RoleEnum.CAJERO)
        self._create_user("mesero", "mesero123", RoleEnum.MESERO)

        admin_h = self._login_headers("admin", "admin123")
        cajero_h = self._login_headers("cajero", "cajero123")
        mesero_h = self._login_headers("mesero", "mesero123")

        self.assertEqual(self.client.get("/api/admin/ping", headers=admin_h).status_code, 200)
        self.assertEqual(self.client.get("/api/admin/ping", headers=mesero_h).status_code, 403)

        self.assertEqual(self.client.get("/api/caja/ping", headers=cajero_h).status_code, 200)
        self.assertEqual(self.client.get("/api/caja/ping", headers=mesero_h).status_code, 403)

        self.assertEqual(self.client.get("/api/pedidos/ping", headers=mesero_h).status_code, 200)
        self.assertEqual(self.client.get("/api/pedidos/ping", headers=cajero_h).status_code, 403)


if __name__ == "__main__":
    unittest.main()
