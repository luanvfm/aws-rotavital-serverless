# Atividade individual 1 — Serverless

Função serverless que emite a **guia de transporte** de uma requisição de bolsas de
sangue do projeto Rota Vital, executada localmente com **AWS SAM CLI**.

- **Disciplina:** Infraestrutura de Software — ADS · CESAR School · 2026.2
- **Caminho escolhido:** A (execução local com `sam local`, sem conta AWS)

---

## 1. O que é esta função

`POST /guias` recebe um pedido e devolve a guia emitida.

**Entrada:**

```json
{
  "requisicaoId": "R-001",
  "hospital": "H-Recife",
  "bolsas": ["O-NEG-0142"]
}
```

**Saída (201 Created):**

```json
{
  "guia": "G-R-001",
  "hospital": "H-Recife",
  "bolsas": ["O-NEG-0142"],
  "invocacaoNesteAmbiente": 1
}
```

Campos de controle:

| Campo | Para que serve |
|---|---|
| `requisicaoId` | obrigatório; sem ele a função devolve **400** |
| `demorar` | se `true`, a função dorme 5 s para estourar o `Timeout` de 3 s |
| `invocacaoNesteAmbiente` | quantas vezes **este** ambiente de execução já atendeu — revela reaproveitamento |

---

## 2. Como rodar

### Pré-requisitos

| Requisito | Verificação |
|---|---|
| Docker em execução | `docker info` |
| AWS SAM CLI | `sam --version` |
| Python 3.12 **com pip** | `python3.12 -m pip --version` |

### Preparar o ambiente (Fedora)

```bash
# SAM CLI, sem sudo, na pasta do usuário
curl -sSL -o sam.zip "https://github.com/aws/aws-sam-cli/releases/latest/download/aws-sam-cli-linux-x86_64.zip"
unzip -q sam.zip -d sam-installation
./sam-installation/install --install-dir "$HOME/.local/aws-sam-cli" --bin-dir "$HOME/.local/bin"

# Python 3.12 e o pip dele (o Fedora não empacota python3.12-pip)
sudo dnf install python3.12
python3.12 -m ensurepip --user --upgrade
```

### Construir e invocar por evento

```bash
sam build
chcon -Rt container_file_t .aws-sam/        # necessário no Fedora (SELinux) — ver 5.2
sam local invoke -e events/pedido.json
```

### Acionar por HTTP

```bash
# terminal 1 — sobe o API Gateway emulado
sam local start-api --port 3001

# terminal 2 — chama a função
curl -s -X POST http://localhost:3001/guias \
  -H 'Content-Type: application/json' \
  -d '{"requisicaoId":"R-002","hospital":"H-Recife","bolsas":["A-POS-0987"]}'
```

> A porta 3000 (padrão do SAM) estava ocupada por outro serviço nesta máquina;
> daí o `--port 3001`.

### Experimentos

```bash
# ambiente reaproveitado entre chamadas
sam local start-api --port 3001 --warm-containers LAZY

# estourar o limite de tempo (Timeout: 3 s contra time.sleep(5))
curl -s -X POST http://localhost:3001/guias \
  -H 'Content-Type: application/json' \
  -d '{"requisicaoId":"R-003","demorar":true}'
```

---

## 3. Medições obtidas

Todas as medições feitas nesta máquina (Fedora 45, Docker 29.9.3, SAM CLI 1.174.1),
em 26/11/2026.

### 3.1 Invocação por evento (`sam local invoke`)

Cada `invoke` **cria e destrói** um ambiente. O contador volta a `1` sempre.

| Execução | `real` (parede) | `Duration` | `Init Duration` | `invocacaoNesteAmbiente` |
|---|---|---|---|---|
| 1ª | — | 33,55 ms | 0,02 ms | 1 |
| 2ª | — | 37,04 ms | 0,02 ms | 1 |
| 3ª (medida com `time`) | **8,019 s** | 32,57 ms | 0,03 ms | 1 |

O contraste entre **8,019 s de tempo real** e **32,57 ms de execução** é o custo de
preparar o ambiente: 99,6% do tempo não foi o código da função.

### 3.2 Gatilho HTTP (`sam local start-api --port 3001`)

Quatro chamadas `curl` seguidas, sem reiniciar o servidor:

| Chamada | `Duration` | `Init Duration` | `invocacaoNesteAmbiente` |
|---|---|---|---|
| 1ª | 31,10 ms | 0,06 ms | 1 |
| 2ª | 1,19 ms | *campo ausente* | 2 |
| 3ª | 0,80 ms | *campo ausente* | 3 |
| 4ª | 0,79 ms | *campo ausente* | 4 |

Dois achados:

1. **O campo `Init Duration` desaparece** a partir da 2ª chamada. Não é omissão do
   relatório: sem ambiente novo, não há fase Init para medir. A ausência do campo é
   a evidência do reaproveitamento.
2. **O `start-api` reaproveita o ambiente sem a flag `--warm-containers`.** Ao subir,
   ele já imprime `Initializing the lambda functions containers` e pré-cria o
   contêiner. O contador cresceu de 1 a 4 sem nenhuma configuração extra — o
   comportamento do SAM CLI 1.174.1 difere do que o roteiro assumia.

Ganho do ambiente aquecido: **31,10 ms → 0,79 ms, cerca de 39× mais rápido**, apenas
por não repetir o Init.

### 3.3 Estouro do limite de tempo

<!-- PREENCHER com o resultado do curl com "demorar": true -->

---

## 4. Respostas

<!-- ESCREVER COM AS PRÓPRIAS PALAVRAS, apoiando-se nos números da seção 3 -->

### 4.1 Por que a primeira invocação demorou mais? O que acontece na fase de Init?

### 4.2 O que o `invocacaoNesteAmbiente` mostrou com e sem `--warm-containers`? O que isso diz sobre guardar estado em variável global?

### 4.3 O que aconteceu com `demorar=true`? Qual o tempo máximo de uma execução no Lambda? O que fazer quando o trabalho é mais longo?

### 4.4 Conta de custo

Premissas: 1.000.000 de execuções/mês, 128 MB de memória, 100 ms por execução,
US$ 0,20 por milhão de requisições e US$ 0,0000166667 por GB-segundo.

```
requisições : 1.000.000 ÷ 1.000.000 × US$ 0,20       = US$ 0,2000
computação  : 1.000.000 × 0,1 s × 0,125 GB           = 12.500 GB-s
              12.500 GB-s × US$ 0,0000166667         = US$ 0,2083
                                                       -----------
total                                                  US$ 0,4083
```

<!-- conferir a conta e comentar: o resultado é alto ou baixo? o que isso sugere? -->

### 4.5 Onde no Rota Vital uma função assim faria sentido, e onde não faria?

---

## 5. Dificuldades encontradas

### 5.1 `sam build` não encontrava o Python 3.12

O `sam build` instala as dependências usando o Python **do host**, e exige a mesma
versão declarada em `Runtime:`. A máquina tinha apenas Python 3.14.

Agravante: **o Fedora não empacota `python3.12-pip`** — existem `devel`, `debug`,
`idle`, `libs` e `test`, mas não o pip. A solução foi instalar o interpretador pelo
`dnf` e o pip pela própria biblioteca padrão do Python:

```bash
sudo dnf install python3.12
python3.12 -m ensurepip --user --upgrade
```

O `--user` instala em `~/.local`, sem precisar de root.

### 5.2 SELinux bloqueava a leitura do código montado no contêiner

Sintoma: `Runtime.ImportModuleError: Unable to import module 'app': No module named 'app'`
— apesar de o arquivo existir, com permissão `rw-r--r--`.

A causa não era permissão POSIX, e sim o **rótulo SELinux**. Arquivos da pasta do
usuário nascem como `user_home_t`, que contêineres não têm permissão para ler:

```
$ ls -lZ .aws-sam/build/HelloWorldFunction/app.py
-rw-r--r--. 1 linho linho unconfined_u:object_r:user_home_t:s0 725 app.py

$ docker run --rm -v "$PWD/.aws-sam/build/HelloWorldFunction:/var/task:ro" \
    alpine:3 head -2 /var/task/app.py
head: /var/task/app.py: Permission denied
```

O teste com o `alpine` isolou a camada: se um contêiner qualquer não lê o arquivo,
o problema não está no SAM. Correção:

```bash
chcon -Rt container_file_t .aws-sam/
```

O rótulo **se perde a cada `sam build`** que recria a pasta, então o comando faz
parte do ciclo de desenvolvimento, não é correção definitiva. Ubuntu e Debian usam
AppArmor, mais permissivo por padrão — por isso a maioria dos tutoriais não
menciona esse obstáculo.

### 5.3 O corpo do evento vinha em Base64

`sam local generate-event ... --body '<json>'` gerou o corpo **codificado em
Base64**, com `isBase64Encoded: true`. Código que faz `json.loads(event["body"])`
direto quebra com:

```
JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```

Optei por tratar no **código**, não por editar o arquivo de evento — o API Gateway
real envia Base64 para conteúdo binário e texto puro para `application/json`, e o
próprio evento informa qual é o caso:

```python
corpo = event.get("body") or "{}"
if event.get("isBase64Encoded"):
    corpo = base64.b64decode(corpo).decode()
pedido = json.loads(corpo)
```

Corrigir o evento adaptaria o teste ao código; corrigir o código aceita os dois
formatos e continua funcionando com `curl`, com `start-api` e na nuvem.

### 5.4 O `Init Duration` do emulador local não mede cold start

O `REPORT` local reportou `Init Duration: 0,02 ms` mesmo em invocações que
**recriaram** o ambiente — comprovado por `invocacaoNesteAmbiente` voltar a `1`. O
emulador começa a contar depois que o runtime já está de pé, então o tempo de criar
o contêiner e importar o módulo não entra nesse campo.

Para medir o custo real usei o tempo de parede do comando inteiro:

```bash
time sam local invoke -e events/pedido.json
```

### 5.5 "Missing Authentication Token" ao abrir a URL no navegador

Mensagem enganosa do API Gateway: não tem relação com autenticação. O navegador faz
`GET` e a rota aceita apenas `POST`; quando o método (ou o caminho) não casa, a
resposta é `403` com esse texto.

### 5.6 Porta 3000 ocupada

O padrão do `sam local start-api` é a porta 3000, já em uso por outro serviço nesta
máquina. Resolvido com `--port 3001`.

---

## 6. Uso de IA

<!-- declarar honestamente: o que foi perguntado, o que foi aceito, e o que foi
     verificado ou rejeitado -->

---

## 7. Evidências

As capturas estão em [`evidencias/`](evidencias/).

| # | Arquivo | Mostra |
|---|---|---|
| | | |
