pipeline {
  agent any

  parameters {
    string(name: 'CLIENT_NAME', defaultValue: 'Cliente Demo', description: 'Nombre comercial del cliente')
    string(name: 'SLUG', defaultValue: 'cliente-demo', description: 'Slug único del tenant')
    string(name: 'ADMIN_USERNAME', defaultValue: 'admin', description: 'Usuario ADMIN inicial')
  }

  environment {
    APP_NAME = 'garrobito'
    BACKEND_IMAGE = "garrobito-backend:${env.BUILD_NUMBER}"
    FRONTEND_IMAGE = "garrobito-frontend:${env.BUILD_NUMBER}"
  }

  stages {
    stage('Build Images') {
      steps {
        sh 'docker build -t ${BACKEND_IMAGE} -f backend/Dockerfile backend'
        sh 'docker build -t ${FRONTEND_IMAGE} -f frontend/Dockerfile frontend'
      }
    }

    stage('Run Tests') {
      steps {
        sh '''
          docker run --rm ${BACKEND_IMAGE} \
            sh -lc "python -m unittest discover -s tests -p 'test_*_unittest.py' -v"
        '''
      }
    }

    stage('Pick Free Port') {
      steps {
        script {
          env.APP_PORT = sh(
            script: '''
              for p in $(seq 8002 8999); do
                if ! ss -ltn | awk '{print $4}' | grep -q ":$p$"; then
                  echo "$p"
                  exit 0
                fi
              done
              exit 1
            ''',
            returnStdout: true
          ).trim()
        }
      }
    }

    stage('Deploy Tenant') {
      steps {
        withCredentials([
          string(credentialsId: 'mariadb-root-password', variable: 'MARIADB_ROOT_PASSWORD'),
          string(credentialsId: 'tenant-admin-password', variable: 'ADMIN_PASSWORD')
        ]) {
          sh '''
            ansible-playbook -i ansible/inventory.ini ansible/app_deploy.yml \
              -e app_name=${APP_NAME} \
              -e client_name="${CLIENT_NAME}" \
              -e slug=${SLUG} \
              -e app_port=${APP_PORT} \
              -e backend_image=${BACKEND_IMAGE} \
              -e frontend_image=${FRONTEND_IMAGE} \
              -e admin_username=${ADMIN_USERNAME} \
              -e admin_password=${ADMIN_PASSWORD} \
              -e db_root_password=${MARIADB_ROOT_PASSWORD}
          '''
        }
      }
    }
  }

  post {
    always {
      sh 'docker image prune -f || true'
    }
  }
}
