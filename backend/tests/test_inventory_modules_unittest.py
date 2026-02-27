import os
import tempfile
import unittest

from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import RoleEnum, User


class InventoryModulesTestCase(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(prefix="garrobito_test_inventory_", suffix=".db")

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

    def test_compra_y_aplicacion_inventario_fisico(self):
        self._create_user("admin", "admin123", RoleEnum.ADMIN)
        admin_h = self._login_headers("admin", "admin123")

        producto = self.client.post(
            "/productos",
            json={"nombre": "Harina", "unidad": "kg", "stock_actual": 0, "costo_promedio": 0},
            headers=admin_h,
        )
        self.assertEqual(producto.status_code, 201)
        producto_id = producto.get_json()["id"]

        compra = self.client.post(
            "/compras",
            json={
                "proveedor": "Proveedor Demo",
                "detalles": [{"producto_id": producto_id, "cantidad": 10, "costo_unitario": 4}],
            },
            headers=admin_h,
        )
        self.assertEqual(compra.status_code, 201)

        inventario_fisico = self.client.post(
            "/inventarios-fisicos",
            json={
                "tipo": "MENSUAL",
                "detalles": [{"producto_id": producto_id, "conteo": 8}],
            },
            headers=admin_h,
        )
        self.assertEqual(inventario_fisico.status_code, 201)
        inv_id = inventario_fisico.get_json()["id"]

        aplicar = self.client.post(f"/inventarios-fisicos/{inv_id}/aplicar", headers=admin_h)
        self.assertEqual(aplicar.status_code, 200)

        productos = self.client.get("/productos", headers=admin_h).get_json()
        harina = next(p for p in productos if p["id"] == producto_id)
        self.assertEqual(harina["stock_actual"], 8.0)

    def test_filtros_y_toggle_activo(self):
        self._create_user("admin", "admin123", RoleEnum.ADMIN)
        mesero_id = self._create_user("mesero", "mesero123", RoleEnum.MESERO)
        admin_h = self._login_headers("admin", "admin123")
        mesero_h = self._login_headers("mesero", "mesero123")

        producto = self.client.post(
            "/productos",
            json={"nombre": "Queso", "unidad": "kg", "stock_actual": 5, "costo_promedio": 7},
            headers=admin_h,
        )
        self.assertEqual(producto.status_code, 201)
        producto_id = producto.get_json()["id"]

        platillo = self.client.post("/platillos", json={"nombre": "Pizza", "precio": 15}, headers=admin_h)
        self.assertEqual(platillo.status_code, 201)
        platillo_id = platillo.get_json()["id"]

        compra = self.client.post(
            "/compras",
            json={
                "proveedor": "ACME Foods",
                "fecha": "2026-01-10T10:00:00",
                "detalles": [{"producto_id": producto_id, "cantidad": 3, "costo_unitario": 8}],
            },
            headers=admin_h,
        )
        self.assertEqual(compra.status_code, 201)

        compra_filter = self.client.get("/compras?proveedor=ACME&date_from=2026-01-01&date_to=2026-12-31", headers=admin_h)
        self.assertEqual(compra_filter.status_code, 200)
        self.assertGreaterEqual(len(compra_filter.get_json()), 1)

        inv = self.client.post(
            "/inventarios-fisicos",
            json={"tipo": "MENSUAL", "fecha": "2026-01-15T08:00:00", "detalles": [{"producto_id": producto_id, "conteo": 6}]},
            headers=admin_h,
        )
        self.assertEqual(inv.status_code, 201)

        inv_filter = self.client.get("/inventarios-fisicos?estado=BORRADOR&tipo=MENSUAL&date_from=2026-01-01&date_to=2026-12-31", headers=admin_h)
        self.assertEqual(inv_filter.status_code, 200)
        self.assertGreaterEqual(len(inv_filter.get_json()), 1)

        pedido = self.client.post("/pedidos", json={"mesa_id": 1, "user_id": mesero_id}, headers=mesero_h)
        # mesa 1 puede no existir en este test aislado; crear mesa si hace falta.
        if pedido.status_code == 404:
            mesa = self.client.post("/mesas", json={"numero": 1, "estado": "LIBRE"}, headers=mesero_h)
            self.assertEqual(mesa.status_code, 201)
            pedido = self.client.post("/pedidos", json={"mesa_id": mesa.get_json()["id"], "user_id": mesero_id}, headers=mesero_h)
        self.assertEqual(pedido.status_code, 201)

        pedidos_filter = self.client.get("/pedidos?estado=ABIERTO", headers=admin_h)
        self.assertEqual(pedidos_filter.status_code, 200)
        self.assertGreaterEqual(len(pedidos_filter.get_json()), 1)

        prod_toggle = self.client.patch(f"/productos/{producto_id}", json={"activo": False}, headers=admin_h)
        self.assertEqual(prod_toggle.status_code, 200)
        self.assertFalse(prod_toggle.get_json()["activo"])

        plat_toggle = self.client.patch(f"/platillos/{platillo_id}", json={"activo": False}, headers=admin_h)
        self.assertEqual(plat_toggle.status_code, 200)
        self.assertFalse(plat_toggle.get_json()["activo"])

    def test_unidades_estandar_y_receta_en_creacion_y_edicion(self):
        self._create_user("admin", "admin123", RoleEnum.ADMIN)
        admin_h = self._login_headers("admin", "admin123")

        producto = self.client.post(
            "/productos",
            json={"nombre": "Pollo Crudo", "unidad": "kilo", "stock_actual": 2, "costo_promedio": 6},
            headers=admin_h,
        )
        self.assertEqual(producto.status_code, 201)
        producto_id = producto.get_json()["id"]

        producto_bad = self.client.post(
            "/productos",
            json={"nombre": "Item Malo", "unidad": "balde", "stock_actual": 0, "costo_promedio": 0},
            headers=admin_h,
        )
        self.assertEqual(producto_bad.status_code, 400)

        platillo = self.client.post(
            "/platillos",
            json={
                "nombre": "Pollo Grill",
                "precio": 18,
                "ingredientes": [{"producto_id": producto_id, "cantidad_por_unidad": 0.5}],
            },
            headers=admin_h,
        )
        self.assertEqual(platillo.status_code, 201)
        platillo_id = platillo.get_json()["id"]

        edit = self.client.patch(
            f"/platillos/{platillo_id}",
            json={
                "nombre": "Pollo Grill XL",
                "precio": 22,
                "ingredientes": [{"producto_id": producto_id, "cantidad_por_unidad": 0.75}],
            },
            headers=admin_h,
        )
        self.assertEqual(edit.status_code, 200)

        listado = self.client.get("/platillos", headers=admin_h)
        self.assertEqual(listado.status_code, 200)
        platillo_data = next(p for p in listado.get_json() if p["id"] == platillo_id)
        self.assertEqual(platillo_data["nombre"], "Pollo Grill XL")
        self.assertEqual(len(platillo_data["ingredientes"]), 1)
        self.assertEqual(platillo_data["ingredientes"][0]["cantidad_por_unidad"], 0.75)


if __name__ == "__main__":
    unittest.main()
