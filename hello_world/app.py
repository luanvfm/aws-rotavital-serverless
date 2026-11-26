import base64
import json
import time

contador = 0  # roda uma vez, na criação do ambiente

def lambda_handler(event, context):
    global contador
    contador += 1

    # O corpo chega como STRING. Em algumas situações o API Gateway o envia
    # codificado em Base64 (conteúdo binário, e também o padrão do
    # 'sam local generate-event' nas versões recentes). O próprio evento diz
    # qual é o caso, no campo isBase64Encoded.
    corpo = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        corpo = base64.b64decode(corpo).decode()

    pedido = json.loads(corpo)

    if "requisicaoId" not in pedido:
        return {
            "statusCode": 400,
            "body": json.dumps({"erro": "requisicaoId obrigatório"}),
        }

    if pedido.get("demorar"):
        time.sleep(5)   # estoura o Timeout de 3s de propósito

    guia = {
        "guia": "G-" + pedido["requisicaoId"],
        "hospital": pedido.get("hospital"),
        "bolsas": pedido.get("bolsas", []),
        "invocacaoNesteAmbiente": contador,
    }

    return {"statusCode": 201, "body": json.dumps(guia)}