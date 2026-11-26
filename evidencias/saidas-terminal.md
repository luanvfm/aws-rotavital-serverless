# Evidências — saídas de terminal

Todas as saídas foram capturadas nesta máquina em **26/11/2026**, conforme o `date`
registrado na seção 1.

---

## 1. Ambiente

```
$ date
Thu Nov 26 05:24:29 PM -03 2026

$ sam --version && docker --version && python3.12 --version
SAM CLI, version 1.174.1
Docker version 29.9.3, build 1.fc45
Python 3.12.16
```

Sistema: Fedora 45 (kernel 7.3.3-300.fc45.x86_64), SELinux em modo `Enforcing`.

---

## 2. Projeto construído

```
$ sam validate
/home/linho/dev/aws/aws-rotavital-serverless/template.yaml is a valid SAM Template

$ sam build
Building codeuri: .../hello_world runtime: python3.12 architecture: x86_64 functions: HelloWorldFunction
 Running PythonPipBuilder:CleanUp
 Running PythonPipBuilder:ResolveDependencies
 Running PythonPipBuilder:CopySource

Build Succeeded
```

Rótulo SELinux do código montado, **após** a correção com `chcon`:

```
$ ls -lZ .aws-sam/build/HelloWorldFunction/app.py
-rw-r--r--. 1 linho linho unconfined_u:object_r:container_file_t:s0 1120 Nov 26 16:50 app.py
```

---

## 3. Invocação por evento (`sam local invoke`)

### 3.1 Execução bem-sucedida

```
$ sam local invoke -e events/pedido.json
Invoking app.lambda_handler (python3.12)
Local image is up-to-date
Using local image: public.ecr.aws/lambda/python:3.12-rapid-x86_64.

Mounting .../.aws-sam/build/HelloWorldFunction as /var/task:ro,delegated, inside runtime container
START RequestId: a33d1fdb-a5f9-4fbd-b3a7-8e29408415de Version: $LATEST
END RequestId: a33d1fdb-a5f9-4fbd-b3a7-8e29408415de
REPORT RequestId: a33d1fdb-...  Init Duration: 0.03 ms  Duration: 35.06 ms  Billed Duration: 36 ms  Memory Size: 128 MB  Max Memory Used: 128 MB
{"statusCode": 201, "body": "{\"guia\": \"G-R-001\", \"hospital\": \"H-Recife\", \"bolsas\": [\"O-NEG-0142\"], \"invocacaoNesteAmbiente\": 1}"}
```

### 3.2 Cold start medido com `time`

Três execuções independentes, cada uma criando e destruindo o ambiente:

```
$ time sam local invoke -e events/pedido.json
REPORT ... Init Duration: 0.02 ms  Duration: 32.57 ms  Billed Duration: 33 ms
real    0m8.019s

$ time sam local invoke -e events/pedido.json
REPORT ... Init Duration: 0.03 ms  Duration: 35.06 ms  Billed Duration: 36 ms
real    0m8.775s

$ time sam local invoke -e events/pedido.json
REPORT ... Init Duration: 0.03 ms  Duration: 34.56 ms  Billed Duration: 35 ms
real    0m7.802s
```

| Execução | `real` (parede) | `Duration` | Proporção de overhead |
|---|---|---|---|
| 1ª | 8,019 s | 32,57 ms | 99,59% |
| 2ª | 8,775 s | 35,06 ms | 99,60% |
| 3ª | 7,802 s | 34,56 ms | 99,56% |
| **média** | **8,20 s** | **34,06 ms** | **99,58%** |

O `invocacaoNesteAmbiente` devolveu **1 em todas as execuções** — prova de que cada
`invoke` recria o ambiente.

---

## 4. Gatilho HTTP (`sam local start-api --port 3001`)

### 4.1 Servidor no ar

```
$ sam local start-api --port 3001
Initializing the lambda functions containers.
Local image is up-to-date
Using local image: public.ecr.aws/lambda/python:3.12-rapid-x86_64.

Mounting .../.aws-sam/build/HelloWorldFunction as /var/task:ro,delegated, inside runtime container
Containers created. Waiting for readiness...
Waiting for 1 containers to be running...
All 1 containers running after 0.0 seconds
All containers are ready.
Mounting HelloWorldFunction at http://127.0.0.1:3001/guias [POST]
 * Running on http://127.0.0.1:3001
```

> Note o `Initializing the lambda functions containers` **antes de qualquer
> requisição**: o SAM pré-cria o contêiner.

### 4.2 Quatro chamadas consecutivas

```
$ curl -s -X POST http://localhost:3001/guias \
    -H 'Content-Type: application/json' \
    -d '{"requisicaoId":"R-002","hospital":"H-Recife","bolsas":["A-POS-0987"]}'

{"guia": "G-R-002", "hospital": "H-Recife", "bolsas": ["A-POS-0987"], "invocacaoNesteAmbiente": 1}
{"guia": "G-R-002", "hospital": "H-Recife", "bolsas": ["A-POS-0987"], "invocacaoNesteAmbiente": 2}
{"guia": "G-R-002", "hospital": "H-Recife", "bolsas": ["A-POS-0987"], "invocacaoNesteAmbiente": 3}
{"guia": "G-R-002", "hospital": "H-Recife", "bolsas": ["A-POS-0987"], "invocacaoNesteAmbiente": 4}
```

Relatórios correspondentes, no terminal do servidor:

```
Lambda function 'HelloWorldFunction' is already running
REPORT RequestId: 9f95c961-...  Init Duration: 0.06 ms  Duration: 31.10 ms  Billed Duration: 32 ms
REPORT RequestId: 806dff48-...                          Duration:  1.19 ms  Billed Duration:  2 ms
REPORT RequestId: e05f27f7-...                          Duration:  0.80 ms  Billed Duration:  1 ms
REPORT RequestId: 6fee17f9-...                          Duration:  0.79 ms  Billed Duration:  1 ms
```

| Chamada | `Duration` | `Init Duration` | `invocacaoNesteAmbiente` |
|---|---|---|---|
| 1ª | 31,10 ms | 0,06 ms | 1 |
| 2ª | 1,19 ms | **ausente** | 2 |
| 3ª | 0,80 ms | **ausente** | 3 |
| 4ª | 0,79 ms | **ausente** | 4 |

Dois fatos visíveis: o contador **cresce** (ambiente reaproveitado) e o campo
`Init Duration` **desaparece** (não houve fase Init). Ganho: **31,10 ms → 0,79 ms,
≈ 39×**.

---

## 5. Estouro do limite de tempo

Requisição com `"demorar": true`, que dispara `time.sleep(5)` contra `Timeout: 3`:

```
$ curl -s -X POST http://localhost:3001/guias \
    -H 'Content-Type: application/json' \
    -d '{"requisicaoId":"R-003","demorar":true}'

{"message":"Internal server error"}
```

Log do contêiner do runtime:

```
26 Nov 2026 20:16:58,065 [ERROR] (rapid) Invoke failed InvokeID=7f520c35-157d-47e5-bbc3-47cbdb47aa4f error=errResetReceived
REPORT RequestId: 7f520c35-...  Duration: 3000.00 ms  Billed Duration: 3000 ms  Memory Size: 128 MB  Max Memory Used: 128 MB
```

| Observação | Valor |
|---|---|
| `Duration` | **3000,00 ms exatos** — cortado no milissegundo do limite declarado |
| `Billed Duration` | **3000 ms** — o tempo até o corte **é cobrado** |
| Erro do runtime | `errResetReceived` |
| Resposta ao cliente | `500 Internal server error` |

---

## 6. Erros de ambiente encontrados no caminho

### 6.1 Python 3.12 ausente

```
Error: PythonPipBuilder:Validation - Binary validation failed for python, searched for
python in following locations : ['/usr/bin/python', '/bin/python', '/usr/bin/python3',
'/bin/python3'] which did not satisfy constraints for runtime: python3.12.
Do you have python for runtime: python3.12 on your PATH?
```

### 6.2 Python 3.12 presente, mas sem pip

```
Error: PythonPipBuilder:ResolveDependencies - Failed to find a Python runtime containing pip on the PATH
```

O Fedora não fornece `python3.12-pip`:

```
$ dnf search python3.12
 python3.12.x86_64        Version 3.12 of the Python interpreter
 python3.12-debug.x86_64  Debug version of the Python runtime
 python3.12-devel.x86_64  Libraries and header files needed for Python development
 python3.12-idle.x86_64   A basic graphical development environment for Python
 python3.12-libs.x86_64   Python runtime libraries
```

Resolvido com `python3.12 -m ensurepip --user --upgrade`.

### 6.3 SELinux impedindo a leitura do código

```
$ ls -lZ .aws-sam/build/HelloWorldFunction/app.py
-rw-r--r--. 1 linho linho unconfined_u:object_r:user_home_t:s0 725 app.py

$ docker run --rm -v "$PWD/.aws-sam/build/HelloWorldFunction:/var/task:ro" alpine:3 head -2 /var/task/app.py
head: /var/task/app.py: Permission denied

$ getenforce
Enforcing
```

Sintoma no SAM:

```
[ERROR] Runtime.ImportModuleError: Unable to import module 'app': No module named 'app'
26 Nov 2026 19:34:15,526 [ERROR] (rapid) Init failed error=Runtime exited with error: exit status 1
```

Resolvido com `chcon -Rt container_file_t .aws-sam/`.

### 6.4 Corpo do evento em Base64

```
[ERROR] JSONDecodeError: Expecting value: line 1 column 1 (char 0)
Traceback (most recent call last):
  File "/var/task/app.py", line 10, in lambda_handler
    pedido = json.loads(event.get("body") or "{}")
```

Conteúdo do evento gerado:

```
isBase64Encoded: True
body: 'eyJyZXF1aXNpY2FvSWQiOiJSLTAwMSIsImhvc3BpdGFsIjoiSC1SZWNpZmUiLCJib2xzYXMiOlsiTy1ORUctMDE0MiJdfQ=='
body decodificado: {"requisicaoId":"R-001","hospital":"H-Recife","bolsas":["O-NEG-0142"]}
```

Resolvido tratando `isBase64Encoded` no código.

### 6.5 Método HTTP incorreto (navegador)

```
"GET /guias HTTP/1.1" 403
"GET /favicon.ico HTTP/1.1" 403
{"message":"Missing Authentication Token"}
```

A rota aceita apenas `POST`; a mensagem sobre autenticação é enganosa.

### 6.6 Porta ocupada

```
Address already in use
Port 3000 is in use by another program. Either identify and stop that program,
or start the server with a different port.
```

Resolvido com `--port 3001`.

---

## 7. Capturas de tela

As capturas do `curl` recebendo POST e do estouro de timeout estão registradas em
notas separadas (Obsidian), e as saídas de terminal acima são a evidência textual
completa de cada etapa.
