// Runs on the Jenkins container on the app box itself. That container mounts
// the host docker socket, so every `docker` call here targets the host daemon
// and the containers it starts are siblings of Jenkins, not children.
//
// Jenkins home is bind-mounted at the SAME path inside and outside the
// container (/var/jenkins_home). That is deliberate: build contexts and bind
// mount sources in this workspace are resolved by the host daemon, so the path
// has to mean the same thing on both sides.
pipeline {
  agent any

  options {
    buildDiscarder(logRotator(numToKeepStr: '20'))
    disableConcurrentBuilds()
    timestamps()
    timeout(time: 20, unit: 'MINUTES')
  }

  triggers {
    // A localhost-only Jenkins cannot receive GitHub webhooks, so poll instead.
    pollSCM('H/2 * * * *')
  }

  environment {
    COMPOSE_PROJECT_NAME = 'my-expenses'
    IMAGE_TAG            = "b${env.BUILD_NUMBER}"
  }

  stages {
    stage('Build') {
      steps {
        script {
          env.SHORT_SHA   = sh(script: 'git rev-parse --short HEAD', returnStdout: true).trim()
          env.APP_VERSION = "b${env.BUILD_NUMBER} (${env.SHORT_SHA})"
        }
        echo "Building ${env.APP_VERSION}"
        sh 'docker compose build'
      }
    }

    stage('Test') {
      // pytest runs inside the image that is about to be deployed, so it
      // exercises the real artifact rather than the source tree next to it.
      // requirements.txt already carries pytest, so nothing extra is installed.
      steps {
        sh '''
          docker run --rm \
            -v "$WORKSPACE/tests":/app/tests:ro \
            -w /app \
            my-expenses-app:$IMAGE_TAG \
            python -m pytest tests/ -q -p no:cacheprovider
        '''
      }
    }

    stage('Deploy') {
      steps {
        // Set before `up`, not after: a half-finished `up` can leave some
        // containers already replaced, and that still needs rolling back.
        script { env.DEPLOYED = 'true' }
        sh 'docker compose up -d'
      }
    }

    stage('Health gate') {
      // /healthz actually reads SQLite. / and /login both render without
      // touching the DB, so they would report healthy even with the data
      // volume unmounted -- which is the failure this gate exists to catch.
      steps {
        sh '''
          for i in $(seq 1 20); do
            body=$(curl -fsS http://host.docker.internal/healthz 2>/dev/null || true)
            if echo "$body" | grep -qE '"status": ?"ok"'; then
              echo "healthy: $body"
              exit 0
            fi
            sleep 3
          done
          echo "FAILED: /healthz did not report ok within 60s"
          docker compose logs --tail=50 app
          exit 1
        '''
      }
    }

    stage('Promote') {
      // Only a build that passed the health gate becomes :latest, so a plain
      // `docker compose up -d` with no IMAGE_TAG always lands on a known-good
      // image.
      steps {
        sh '''
          docker tag my-expenses-app:$IMAGE_TAG   my-expenses-app:latest
          docker tag my-expenses-nginx:$IMAGE_TAG my-expenses-nginx:latest
        '''
      }
    }
  }

  post {
    // `unsuccessful`, not `failure`: the 20-minute timeout and a manual abort
    // both end as ABORTED, and either can strike after Deploy has swapped the
    // containers.
    unsuccessful {
      script {
        if (env.DEPLOYED == 'true') {
          // :latest is only ever a build that passed the health gate (see
          // Promote). It is missing only before the first green build, in
          // which case there is nothing known-good to go back to.
          sh '''
            if docker image inspect my-expenses-app:latest my-expenses-nginx:latest >/dev/null 2>&1; then
              echo "Rolling back to :latest"
              IMAGE_TAG=latest docker compose up -d --no-build
            else
              echo "No :latest images yet -- nothing to roll back to. Leaving $IMAGE_TAG running."
            fi
          '''
        } else {
          echo 'Failed before Deploy; the running containers were not touched.'
        }
      }
    }
    cleanup {
      // Image layers accumulate on the 30 GB root volume otherwise. In
      // `cleanup` so it runs after the rollback above.
      sh 'docker image prune -f || true'
    }
  }
}
