AI_sandbox

once（in project directory）
$ docker network ls # sandbox_network がリストにあるか確認
$ docker network create sandbox_network # もし存在しなければ実行

$ docker build -t my-sandbox-python:3.10 -f Dockerfile.sandbox_base .
