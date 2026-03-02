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

## Inicio de sesion y roles

- Inicio de sesion frontend: `GET/POST /login`
- Cierre de sesion frontend: `GET /logout`
- Paneles por rol:
  - `ADMIN -> /dashboard/admin`
  - `CAJERO -> /dashboard/caja`
  - `MESERO -> /dashboard/mesas`
  - `COCINA -> /dashboard/cocina`

El frontend guarda `access_token` JWT y `role` en sesión, y envía `Authorization: Bearer <token>` al backend.

Autenticacion del backend:

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

Usuarios creados por semilla:

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

## Pruebas automaticas (unittest)

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

Entorno productivo actual:

- Backend: `backend/Dockerfile` con `gunicorn` en puerto interno `5000`.
- Frontend: `frontend/Dockerfile` con `gunicorn` en puerto interno `80`.
- DB central: MariaDB en red Docker interna.

### Levantar todo con un comando

```bash
cp .env.example .env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
docker compose up -d --build
```

Verificación:

```bash
docker compose ps
curl -s http://127.0.0.1:5000/health && echo
curl -s http://127.0.0.1:5001/health && echo
```

## CI/CD base (Jenkins + Ansible)

Se agregaron:

- `Jenkinsfile`: construccion de imagenes, pruebas de backend, seleccion de puerto libre y despliegue.
- `ansible/app_deploy.yml`: despliegue multiinquilino por base de datos:
  - crea DB `db_<slug>` y usuario `usr_<slug truncado>`,
  - despliega backend + frontend por cliente,
  - ejecuta `flask --app run.py db upgrade`,
  - ejecuta `flask --app run.py seed-admin`.

### Credenciales Jenkins esperadas

- `mariadb-root-password`
- `tenant-admin-password`

### Dependencia Ansible esperada

```bash
ansible-galaxy collection install -r ansible/requirements.yml
```

## Solicitud de despliegue desde la web

Pantalla de registro de cliente:

- Frontend: `GET/POST /onboarding`
- API de backend: `POST /deployments/tenant`

Campos mínimos del formulario:

- `client_name`
- `slug`
- `admin_password`

`admin_username` se fija automáticamente en `admin`.

Flujo:

1. Cliente completa formulario.
2. Frontend llama a backend.
3. Backend valida y dispara Jenkins (`buildWithParameters`).
4. Jenkins ejecuta Ansible y crea el cliente (`db_<slug>`, contenedor API y Web por cliente).

Variables backend:

- `DEPLOY_API_KEY`
- `JENKINS_URL`
- `JENKINS_USER`
- `JENKINS_API_TOKEN`
- `JENKINS_JOB_NAME`
- `JENKINS_VERIFY_SSL`

Variables frontend:

- `BACKEND_API_URL`
- `BACKEND_DEPLOY_KEY` (debe coincidir con `DEPLOY_API_KEY` del backend)

## Despliegue en AWS EC2 (resumen)

1. Clonar repo en EC2 y configurar `.env`, `backend/.env` y `frontend/.env`.
2. Levantar stack base: `docker compose up -d --build`.
3. Configurar Jenkins job `garrobito-deploy` con `Pipeline script from SCM`.
4. Crear credenciales Jenkins:
   - `mariadb-root-password`
   - `tenant-admin-password`
5. Verificar que Jenkins tenga permisos para Docker/Ansible en el host.
6. Probar `http://<IP_EC2>:5001/onboarding` y confirmar construccion y despliegue del cliente.
