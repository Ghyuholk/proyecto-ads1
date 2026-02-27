# Garrobito

Estructura separada en backend y frontend, ambos en Flask.

## Estructura

```text
backend/
  app/
  config.py
  run.py
  requirements.txt
frontend/
  app.py
  run.py
  requirements.txt
  templates/
  static/
```

## Backend (API Flask)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

API disponible en `http://127.0.0.1:5000`.

## Frontend (Flask)

```bash
cd frontend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

Frontend disponible en `http://127.0.0.1:5001`.

## Login y roles

- Login frontend: `GET/POST /login`
- Logout frontend: `GET /logout`
- Dashboards por rol:
  - `ADMIN -> /dashboard/admin`
  - `CAJERO -> /dashboard/caja`
  - `MESERO -> /dashboard/mesas`
  - `COCINA -> /dashboard/cocina`

El frontend guarda `access_token` JWT y `role` en sesión, y envía `Authorization: Bearer <token>` al backend.

Backend auth:

- `POST /auth/login` -> `{ access_token, user }`
- `GET /auth/me` -> usuario autenticado

## Datos iniciales para pruebas

Con backend activo, puedes cargar datos de prueba así:

```bash
cd backend
python seed.py
```

Alternativa con Flask CLI:

```bash
cd backend
flask --app run.py seed
```

Usuarios creados por seed:

- `admin / admin123` (ADMIN)
- `cajero / cajero123` (CAJERO)
- `mesero / mesero123` (MESERO)
- `cocina / cocina123` (COCINA)

También crea mesas (1-6), productos base con stock, y platillos con receta.

## Migraciones (Alembic)

Inicializar (ya incluido en el repo):

```bash
cd backend
flask --app run.py db init
```

Generar nueva migración:

```bash
cd backend
flask --app run.py db migrate -m "descripcion"
```

Aplicar migraciones:

```bash
cd backend
flask --app run.py db upgrade
```

Si tu base local existía antes de migraciones, una sola vez:

```bash
cd backend
flask --app run.py db stamp head
```

## Tests automáticos (unittest)

Ejecutar suite crítica:

```bash
cd backend
python -m unittest discover -s tests -p 'test_*_unittest.py' -v
```

## Configuración opcional

Puedes definir la URL del backend para el frontend con:

```bash
export BACKEND_API_URL="http://127.0.0.1:5000"
```

## Flujo funcional mínimo (desde el frontend)

1. Crear usuario (rol `CAJERO` o `MESERO`).
2. Crear mesa.
3. Crear producto (ingredientes de inventario).
4. Crear platillo y asignar ingrediente.
5. Abrir caja.
6. Crear pedido y agregar item.
7. Cobrar pedido.
8. Cerrar caja (usando el `apertura_id` mostrado en estado de caja).

## Producción (Docker + Gunicorn)

Se agregó runtime productivo para ambos servicios:

- Backend: `backend/Dockerfile` con `gunicorn` en puerto interno `5000`.
- Frontend: `frontend/Dockerfile` con `gunicorn` en puerto interno `80`.
- DB central: `docker-compose.yml` con MariaDB en red interna `garrobito_net` (sin exponer DB al host).

### Levantar DB central

```bash
cp .env.example .env
docker compose up -d garrobito_db
```

### Build local de imágenes

```bash
docker build -t garrobito-backend:local -f backend/Dockerfile backend
docker build -t garrobito-frontend:local -f frontend/Dockerfile frontend
```

## CI/CD base (Jenkins + Ansible)

Se agregaron:

- `Jenkinsfile`: build de imágenes, tests backend, selección de puerto libre y deploy.
- `ansible/app_deploy.yml`: despliegue multi-tenant por base de datos:
  - crea DB `db_<slug>` y usuario `usr_<slug truncado>`,
  - despliega backend + frontend por tenant,
  - ejecuta `flask --app run.py db upgrade`,
  - ejecuta `flask --app run.py seed-admin`.

### Credenciales Jenkins esperadas

- `mariadb-root-password`
- `tenant-admin-password`

### Dependencia Ansible esperada

```bash
ansible-galaxy collection install -r ansible/requirements.yml
```
