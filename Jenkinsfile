pipeline {
  agent any

  parameters {
    string(name: 'CLIENT_NAME', defaultValue: 'Cliente Demo', description: 'Nombre comercial del cliente')
    string(name: 'SLUG', defaultValue: 'cliente-demo', description: 'Identificador único del cliente')
    string(name: 'ADMIN_USERNAME', defaultValue: 'admin', description: 'Usuario ADMIN inicial')
    password(name: 'ADMIN_PASSWORD', defaultValue: '', description: 'Contraseña ADMIN inicial (si se deja vacío usa credencial Jenkins)')
  }

  environment {
    APP_NAME = 'garrobito'
    BACKEND_IMAGE = "garrobito-backend:${env.BUILD_NUMBER}"
    FRONTEND_IMAGE = "garrobito-frontend:${env.BUILD_NUMBER}"
    PACKAGE_NAME = "codigo.tar.gz"
  }

  stages {
    stage('Ejecutar Pruebas') {
      steps {
        sh '''
          cd backend
          python3 -m venv .venv_ci
          . .venv_ci/bin/activate
          pip install -r requirements.txt
          python -m unittest discover -s tests -p 'test_*_unittest.py' -v
          deactivate
          rm -rf .venv_ci
        '''
      }
    }

    stage('Empaquetar Codigo') {
      steps {
        sh '''
          rm -f ${PACKAGE_NAME}
          tar -czf ${PACKAGE_NAME} \
            --exclude=.git \
            --exclude=.venv \
            --exclude=backend/.venv \
            --exclude=frontend/.venv \
            --exclude='*/__pycache__' \
            .
        '''
      }
    }

    stage('Desplegar Cliente') {
      steps {
        withCredentials([
          sshUserPrivateKey(credentialsId: 'ec2-ssh-key', keyFileVariable: 'EC2_SSH_KEY'),
          string(credentialsId: 'ec2-host', variable: 'EC2_HOST'),
          string(credentialsId: 'ec2-user', variable: 'EC2_USER'),
          string(credentialsId: 'ec2-sudo-pass', variable: 'EC2_SUDO_PASS'),
          string(credentialsId: 'mariadb-root-password', variable: 'MARIADB_ROOT_PASSWORD'),
          string(credentialsId: 'tenant-admin-password', variable: 'DEFAULT_ADMIN_PASSWORD')
        ]) {
          sh '''
            ADMIN_PASS="${ADMIN_PASSWORD}"
            if [ -z "${ADMIN_PASS}" ]; then
              ADMIN_PASS="${DEFAULT_ADMIN_PASSWORD}"
            fi

            ansible-playbook -i ansible/inventory.ini ansible/app_deploy.yml \
              --private-key "${EC2_SSH_KEY}" \
              -e app_name=${APP_NAME} \
              -e build_number=${BUILD_NUMBER} \
              -e package_path=${WORKSPACE}/${PACKAGE_NAME} \
              -e ansible_host=${EC2_HOST} \
              -e ansible_user=${EC2_USER} \
              -e ansible_become_password=${EC2_SUDO_PASS} \
              -e client_name="${CLIENT_NAME}" \
              -e slug=${SLUG} \
              -e backend_image=${BACKEND_IMAGE} \
              -e frontend_image=${FRONTEND_IMAGE} \
              -e admin_username=${ADMIN_USERNAME} \
              -e admin_password="${ADMIN_PASS}" \
              -e db_root_password=${MARIADB_ROOT_PASSWORD}
          '''
        }
      }
    }
  }

  post {
    always {
      sh 'rm -f ${PACKAGE_NAME} || true'
      sh 'docker image prune -f || true'
    }
  }
}
