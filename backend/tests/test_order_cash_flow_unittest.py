import os
import tempfile
import unittest

from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import RoleEnum, User


class OrderCashFlowTestCase(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(prefix="garrobito_test_flow_", suffix=".db")

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
            return user.id

    def _login_headers(self, username, password):
        resp = self.client.post("/auth/login", json={"username": username, "password": password})
        self.assertEqual(resp.status_code, 200)
        token = resp.get_json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_pedido_cobro_descuenta_stock_y_genera_kardex(self):
        self._create_user("admin", "admin123", RoleEnum.ADMIN)
        mesero_id = self._create_user("mesero", "mesero123", RoleEnum.MESERO)
        self._create_user("cocina", "cocina123", RoleEnum.COCINA)
        cajero_id = self._create_user("cajero", "cajero123", RoleEnum.CAJERO)

        admin_h = self._login_headers("admin", "admin123")
        mesero_h = self._login_headers("mesero", "mesero123")
        cocina_h = self._login_headers("cocina", "cocina123")
        cajero_h = self._login_headers("cajero", "cajero123")

        mesa = self.client.post("/mesas", json={"numero": 1, "estado": "LIBRE"}, headers=mesero_h)
        self.assertEqual(mesa.status_code, 201)
        mesa_id = mesa.get_json()["id"]

        producto = self.client.post(
            "/productos",
            json={"nombre": "Tomate", "unidad": "kg", "stock_actual": 10, "costo_promedio": 2},
            headers=admin_h,
        )
        self.assertEqual(producto.status_code, 201)
        producto_id = producto.get_json()["id"]

        platillo = self.client.post("/platillos", json={"nombre": "Ensalada", "precio": 12}, headers=admin_h)
        self.assertEqual(platillo.status_code, 201)
        platillo_id = platillo.get_json()["id"]

        receta = self.client.post(
            f"/platillos/{platillo_id}/ingredientes",
            json={"ingredientes": [{"producto_id": producto_id, "cantidad_por_unidad": 1}]},
            headers=admin_h,
        )
        self.assertEqual(receta.status_code, 201)

        apertura = self.client.post(
            "/caja/apertura",
            json={"user_id": cajero_id, "monto_inicial": 100},
            headers=cajero_h,
        )
        self.assertEqual(apertura.status_code, 201)

        pedido = self.client.post(
            "/pedidos",
            json={"mesa_id": mesa_id, "user_id": mesero_id},
            headers=mesero_h,
        )
        self.assertEqual(pedido.status_code, 201)
        pedido_id = pedido.get_json()["id"]

        item = self.client.post(
            f"/pedidos/{pedido_id}/items",
            json={"platillo_id": platillo_id, "cantidad": 2},
            headers=mesero_h,
        )
        self.assertEqual(item.status_code, 201)

        enviar = self.client.patch(
            f"/pedidos/{pedido_id}/estado",
            json={"estado": "PREPARACION"},
            headers=mesero_h,
        )
        self.assertEqual(enviar.status_code, 200)

        listo = self.client.patch(
            f"/pedidos/{pedido_id}/estado",
            json={"estado": "SERVIDO"},
            headers=cocina_h,
        )
        self.assertEqual(listo.status_code, 200)

        cobro = self.client.post(
            "/caja/cobro",
            json={"pedido_id": pedido_id, "metodo": "EFECTIVO"},
            headers=cajero_h,
        )
        self.assertEqual(cobro.status_code, 201)

        productos = self.client.get("/productos", headers=admin_h).get_json()
        tomate = next(p for p in productos if p["id"] == producto_id)
        self.assertEqual(tomate["stock_actual"], 8.0)

        kardex = self.client.get(f"/kardex/{producto_id}", headers=admin_h).get_json()
        tipos = [mov["tipo"] for mov in kardex["movimientos"]]
        self.assertIn("COMPRA", tipos)
        self.assertIn("VENTA", tipos)

    def test_mesero_edita_items_y_no_libera_mesa_con_pedido_activo(self):
        self._create_user("admin", "admin123", RoleEnum.ADMIN)
        mesero_id = self._create_user("mesero", "mesero123", RoleEnum.MESERO)

        admin_h = self._login_headers("admin", "admin123")
        mesero_h = self._login_headers("mesero", "mesero123")

        mesa = self.client.post("/mesas", json={"numero": 5, "estado": "LIBRE"}, headers=mesero_h)
        self.assertEqual(mesa.status_code, 201)
        mesa_id = mesa.get_json()["id"]

        platillo = self.client.post("/platillos", json={"nombre": "Sanduche", "precio": 9}, headers=admin_h)
        self.assertEqual(platillo.status_code, 201)
        platillo_id = platillo.get_json()["id"]

        pedido = self.client.post(
            "/pedidos",
            json={"mesa_id": mesa_id, "user_id": mesero_id},
            headers=mesero_h,
        )
        self.assertEqual(pedido.status_code, 201)
        pedido_id = pedido.get_json()["id"]

        item = self.client.post(
            f"/pedidos/{pedido_id}/items",
            json={"platillo_id": platillo_id, "cantidad": 2},
            headers=mesero_h,
        )
        self.assertEqual(item.status_code, 201)
        detalle_id = item.get_json()["detalle"]["id"]
        self.assertEqual(item.get_json()["pedido_total"], 18.0)

        edit_item = self.client.patch(
            f"/pedidos/{pedido_id}/items/{detalle_id}",
            json={"cantidad": 3},
            headers=mesero_h,
        )
        self.assertEqual(edit_item.status_code, 200)
        self.assertEqual(edit_item.get_json()["pedido_total"], 27.0)

        remove_item = self.client.delete(
            f"/pedidos/{pedido_id}/items/{detalle_id}",
            headers=mesero_h,
        )
        self.assertEqual(remove_item.status_code, 200)
        self.assertEqual(remove_item.get_json()["pedido_total"], 0.0)

        liberar = self.client.patch(f"/mesas/{mesa_id}", json={"estado": "LIBRE"}, headers=mesero_h)
        self.assertEqual(liberar.status_code, 400)


if __name__ == "__main__":
    unittest.main()
