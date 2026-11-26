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

Chamada com `{"requisicaoId": "R-003", "demorar": true}`, que faz a função dormir
5 s contra um `Timeout` de 3 s declarado no `template.yaml`.

**Resposta HTTP recebida:**

```json
{"message": "Internal server error"}
```

**Log do contêiner do runtime:**

```
[ERROR] (rapid) Invoke failed InvokeID=7f520c35-... error=errResetReceived
REPORT RequestId: 7f520c35-...  Duration: 3000.00 ms  Billed Duration: 3000 ms  Memory Size: 128 MB
```

| Observação | Valor |
|---|---|
| `Duration` | **3000,00 ms exatos** — o ambiente cortou no milissegundo do limite |
| `Billed Duration` | **3000 ms** — o tempo gasto até o corte **é cobrado** |
| Erro do runtime | `errResetReceived` (o processo foi reiniciado de fora) |
| Resposta ao cliente | `500 Internal server error` |

O `time.sleep(5)` **nunca terminou**. A execução não falhou por um erro do código:
foi interrompida pelo ambiente aplicando um limite declarado na infraestrutura.

---

## 4. Respostas

> As respostas abaixo foram redigidas com apoio de IA a partir das medições que eu
> executei nesta máquina (seção 3). Ver a seção 6, "Uso de IA".

### 4.1 Por que a primeira invocação demorou mais? O que acontece na fase de Init?

Porque na primeira chamada não existe ambiente de execução — ele precisa ser criado
antes de o código poder rodar. Isso é o **cold start**.

Na fase de Init acontecem, em ordem: a plataforma aloca um ambiente isolado, baixa e
descompacta o pacote da função, inicia o runtime Python, importa o `app.py` e executa
o **código de topo do arquivo** — no meu caso a linha `contador = 0`. Só depois disso
o `lambda_handler` é chamado. Nas chamadas seguintes, se o ambiente ainda estiver
vivo, todos esses passos são pulados e só o handler executa.

As duas medições que comprovam isso:

| Comparação | Valor |
|---|---|
| `invoke`: tempo total de parede vs. execução | **8,019 s** contra **32,57 ms** |
| `curl`: 1ª chamada vs. 4ª chamada | **31,10 ms** contra **0,79 ms** |

No primeiro caso, 99,6% do tempo não foi o meu código: foi preparar o ambiente. No
segundo, a mesma função ficou **39× mais rápida** apenas por não repetir o Init.

Há uma ressalva honesta: o campo `Init Duration` do emulador local marcou 0,02 ms
mesmo quando o ambiente foi recriado (ver 5.4), então ele não serve para medir cold
start localmente — precisei usar `time` para pegar o tempo de parede. Na AWS real o
cold start de uma função Python pequena fica tipicamente entre 200 e 800 ms.

Duas coisas aumentam o cold start: **tamanho do pacote** e **trabalho no código de
topo**. Meu pacote tem 4,4 MB por causa da biblioteca `requests`, que vem no template
`hello-world` e a minha função nem usa — é download e descompactação desperdiçados em
todo cold start.

### 4.2 O que o `invocacaoNesteAmbiente` mostrou com e sem `--warm-containers`? O que isso diz sobre guardar estado em variável global?

| Forma de execução | O que o contador devolveu |
|---|---|
| `sam local invoke` (3 execuções) | **1, 1, 1** |
| `sam local start-api` (4 chamadas) | **1, 2, 3, 4** |

Com `sam local invoke`, cada execução cria e destrói o ambiente, então a variável
global nasce zerada toda vez e o contador nunca passa de 1. Com `start-api`, o
contêiner é reaproveitado entre as chamadas e o contador cresce.

Um achado não previsto no roteiro: **o `start-api` já reaproveita o ambiente sem a
flag `--warm-containers`**. Ao subir, ele imprime `Initializing the lambda functions
containers` e pré-cria o contêiner. Confirmei pelo contador crescendo de 1 a 4 e pelo
**desaparecimento do campo `Init Duration`** a partir da segunda chamada — sem
ambiente novo, não há fase Init para relatar.

Sobre guardar estado em variável global: **não se pode confiar nele.** O
reaproveitamento é uma otimização da plataforma, não uma garantia contratual. Três
razões concretas:

1. O próximo ambiente começa zerado — e eu não controlo quando um é descartado.
2. Invocações simultâneas rodam em ambientes **diferentes**, que não compartilham
   memória. Dez chamadas paralelas podem ter dez contadores independentes.
3. O valor é imprevisível: a mesma função devolveu 1 por um caminho e 4 por outro.

O uso legítimo é **cache descartável**: uma conexão de banco, um cliente HTTP, uma
configuração lida uma vez. Coisas em que perder o valor significa apenas refazer o
trabalho, não perder informação. Estado de negócio — contagem, saldo, carrinho —
precisa de armazenamento externo (banco, Redis, DynamoDB).

Vindo de Java, o paralelo mais próximo é o `static`: ele vive enquanto a JVM estiver
carregada, como a variável de módulo vive enquanto o ambiente de execução existir. Em
ambos os casos se aposta na longevidade de um processo que não se controla — mas no
Lambda esse processo é descartado de propósito, com frequência.

### 4.3 O que aconteceu com `demorar=true`? Qual o tempo máximo de uma execução no Lambda? O que fazer quando o trabalho é mais longo?

A função foi **interrompida pelo ambiente**, não pelo próprio código. O
`time.sleep(5)` nunca terminou: o `template.yaml` declara `Timeout: 3`, e o log do
runtime registrou `Duration: 3000.00 ms` — exatamente o limite — com
`error=errResetReceived`. O cliente recebeu `500 Internal server error`.

O detalhe que mais chama atenção é o **`Billed Duration: 3000 ms`**: paga-se pelos 3
segundos consumidos até o corte, mesmo sem receber resultado algum. Timeout mal
dimensionado gera custo sem entregar valor.

O tempo máximo de uma execução no AWS Lambda é de **15 minutos** (900 segundos). O
padrão do SAM é 3 segundos, e é uma escolha deliberada: um limite baixo faz a falha
aparecer rápido em vez de a função ficar pendurada consumindo tempo cobrado.

Quando o trabalho é mais longo que o limite, aumentar o `Timeout` só adia o problema.
As saídas reais são:

- **Quebrar em etapas menores e coordená-las** — uma fila (SQS) ou uma máquina de
  estados (Step Functions) encadeia várias execuções curtas, cada uma dentro do
  limite, com reprocessamento de falhas.
- **Processar em lote em vez de por item** — uma função trata N registros por
  invocação e marca o progresso, de modo que a próxima continue de onde parou.
- **Usar um serviço de execução longa** — contêiner (ECS/Fargate), job em batch ou
  um servidor tradicional. Trabalho que leva horas simplesmente não pertence a uma
  função serverless.

### 4.4 Conta de custo

Premissas: 1.000.000 de execuções/mês, 128 MB de memória, 100 ms por execução,
US$ 0,20 por milhão de requisições e US$ 0,0000166667 por GB-segundo.

```
requisições : 1.000.000 ÷ 1.000.000 × US$ 0,20        = US$ 0,2000

computação  : 128 MB = 0,125 GB
              1.000.000 × 0,1 s × 0,125 GB            = 12.500 GB-s
              12.500 GB-s × US$ 0,0000166667          = US$ 0,2083
                                                        -----------
total mensal                                            US$ 0,4083
```

Menos de meio dólar por **um milhão** de execuções — algo como R$ 2,20. Para efeito
de comparação, a menor instância EC2 ligada o mês inteiro custa alguns dólares, e
ficaria ociosa na maior parte do tempo.

Três leituras que a conta permite:

1. **Para carga intermitente, serverless é dificílimo de superar em preço.** Não se
   paga por espera, só por execução.
2. **O custo cresce com `memória × tempo`.** Dobrar a memória dobra o preço por
   segundo — mas, como no Lambda a CPU é proporcional à memória, uma função mais
   "gorda" pode terminar antes e sair **mais barata**. Vale medir, não supor.
3. **O preço não é o único critério.** Esses US$ 0,41 não contabilizam cold start,
   limite de 15 minutos nem a dificuldade maior de depurar. Barato não é
   automaticamente adequado.

### 4.5 Onde no Rota Vital uma função assim faria sentido, e onde não faria?

**Onde faria sentido** — trabalho pontual, curto, disparado por evento e tolerante a
algumas centenas de milissegundos de latência:

- **Emitir a guia de transporte**, que é exatamente esta função: recebe um pedido,
  gera um documento, devolve. Sem estado, sem processo longo.
- **Notificar hospitais** quando uma bolsa é alocada (e-mail, push, WhatsApp).
  Acontece esporadicamente e não faz sentido manter servidor ligado para isso.
- **Gerar relatórios assíncronos** de estoque, acionados por agendamento noturno.
- **Processar arquivos enviados** — uma planilha de doações que chega e precisa ser
  validada e importada.

**Onde não faria sentido:**

- **A API principal do Rota Vital.** É um sistema de emergência médica: o cold start
  de centenas de milissegundos na primeira requisição depois de um período de
  silêncio é um risco que não se justifica, e a aplicação recebe tráfego constante —
  o cenário em que servidor ligado sai mais barato e mais previsível.
- **O banco de dados.** Serverless é sem estado por definição; dados persistentes
  precisam de um serviço feito para isso.
- **A stack de observabilidade** (Prometheus, Grafana, Loki, Tempo). São processos
  que precisam rodar continuamente, raspando métricas e mantendo séries temporais —
  o oposto de execução efêmera.
- **Qualquer operação que ultrapasse 15 minutos**, como uma migração grande ou
  reprocessamento histórico de rotas.
- **Caso concreto da entrega anterior:** a listagem de estoque do Rota Vital tem um
  problema N+1 que dispara cerca de 526 consultas por requisição. Numa função
  serverless isso seria pior que num servidor, porque não há pool de conexões
  reaproveitado entre execuções e cada ambiente novo precisaria reconectar ao banco.
  O defeito precisa ser corrigido antes de qualquer discussão sobre onde hospedar.

A regra que extraí: serverless combina com **trabalho que acontece de vez em quando,
termina rápido e não guarda nada**. Quanto mais o trabalho for contínuo, demorado ou
dependente de estado, mais o modelo atrapalha.

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

Usei um assistente de IA (Claude, via Hermes) como par de programação durante toda a
atividade. Declaro abaixo o que foi feito por cada parte.

**O que a IA fez:**

- Explicou os conceitos (cold start, fase de Init, estado efêmero, limite de tempo,
  `Transform` do SAM, diferença entre `&&` e `|`, rótulos do SELinux).
- Sugeriu os comandos e explicou cada opção antes de eu executar.
- Diagnosticou os erros de ambiente a partir das mensagens que eu colei.
- Redigiu as respostas da seção 4 e o texto deste README, a partir das medições que
  **eu** executei.

**O que eu fiz:**

- Executei todos os comandos nesta máquina e coletei as saídas e os tempos.
- Decidi o caminho (A, local), o provedor (AWS) e o fluxo do sistema (guia de
  transporte).
- Escrevi o `template.yaml` e o `app.py`, com orientação.
- Revisei as respostas antes de entregar.

**O que a IA errou e foi corrigido com evidência:**

Registro isto porque faz parte de usar IA com responsabilidade — as respostas dela
não foram aceitas sem verificação:

| Afirmação da IA | O que a execução mostrou |
|---|---|
| "você não precisa do Python 3.12 no host" | `sam build` falhou exigindo exatamente a versão do runtime |
| "aponte a modeline para o schema do SAM e terá autocomplete" | o schema tem ~18 MB; a extensão falha em silêncio e nenhuma sugestão aparece |
| "o `requirements.txt` está vazio, nada será baixado" | o template `hello-world` traz `requests`; o pacote ficou com 4,4 MB |
| sequência de comandos `mv` / `rm -rf` em linhas separadas | o `mv` falhou e o `rm -rf` apagou o projeto; faltava proteger com `&&` |

O último caso custou o projeto inteiro e exigiu refazer o `sam init`. A lição ficou:
**comando destrutivo nunca deve ser encadeado sem `&&` protegendo o passo anterior.**

---

## 7. Evidências

As capturas estão em [`evidencias/`](evidencias/).

| # | Arquivo | Mostra |
|---|---|---|
| | | |
