@Library('corevision-library')

docker_yocto_img='docker-registry.core-vision.nl/videology/scailx_yocto:v0.0.2'

pipeline {
    agent {label 'robot-agent'}
    stages {
      stage('Checkout sources'){
        steps {
          deleteDir()
          dir('kernel-module-crosslink_cv'){
            checkout scm
          }
        }
      }

    stage('Environment variables') {
      steps {
        dir('kernel-module-crosslink_cv'){
          script {
          extractEnvironmentVariablesFromRepository()
          sh (script: 'env', label: 'Print environment variables')
          buildName env.BUILD_NAME
          buildDescription "By ${env.COMMIT_AUTHOR_NAME}"
          isTagBuild = env.TAG_NAME != null
          }
        }
      }
    }
    stage('Fetch Scailx-Yocto SDK') {
      steps {
          copyArtifacts(
              projectName: "/Videology/lvds_to_mipi/scailx_yocto_cv/${env.BRANCH_NAME.replaceAll('/', '%2F')}",
              selector: lastSuccessful(),
              fingerprintArtifacts: true
          )
        }
      }
      stage('Driver - Crosslink'){
        steps {
          script {
            docker.withRegistry('https://docker-registry.core-vision.nl', 'DOCKER_REGISTERY_CREDENTIAL') {
              def dockerImage=docker.image(docker_yocto_img)
              dockerImage.pull()
              dockerImage.inside("--privileged --network host"){
                  COMMAND="mkdir sdk; \
                           ${env.WORKSPACE}/build/deploy/sdk/scailx-glibc-x86_64-scailx-ml-armv8a-scailx-imx8mp-toolchain-*.sh -y -d ${env.WORKSPACE}/sdk; \
                           . sdk/environment-setup-armv8a-poky-linux; \
                           make -C ${env.WORKSPACE}/sdk/sysroots/armv8a-poky-linux/usr/src/kernel prepare; \
                           make -C kernel-module-crosslink_cv KERNEL_SRC=${env.WORKSPACE}/sdk/sysroots/armv8a-poky-linux/usr/src/kernel"
                  sh "$COMMAND"
              }
              archiveArtifacts artifacts: 'kernel-module-crosslink_cv/lvds2mipi.ko', fingerprint: true
            }
          }
        }
      }
    }
  // Post is always executed independent of the build status
    post {
    cleanup {
        sh (script: 'chown -R 1000:1000 .')
    }
  }
}