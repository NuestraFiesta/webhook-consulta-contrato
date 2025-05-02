import base64
import json
import requests
from datetime import datetime, timedelta
import os
import time
from flask import Flask, request, jsonify

# ========== CONFIGURAÇÕES ==========
CLIENT_ID = "0fe3fe2603fdf7138f87fd510b61744a79642ff6"
CLIENT_SECRET = "2dd575585fc45aa95c9d09eed08ca14fcad4046dae299fad7751a69b3305"
TOKEN_FILE = "token_cache.json"
MAX_RETRIES = 10
# ===================================

app = Flask(__name__)

def carregar_token():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            return json.load(f)
    return None

def salvar_token(token_data):
    token_data["expires_at"] = (datetime.utcnow() + timedelta(seconds=token_data["expires_in"]))\
        .isoformat()
    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f)

def token_expirado(token_data):
    if not token_data or "expires_at" not in token_data:
        return True
    return datetime.utcnow() >= datetime.fromisoformat(token_data["expires_at"])

def renovar_token(refresh_token):
    auth_str = f"{CLIENT_ID}:{CLIENT_SECRET}"
    auth_b64 = base64.b64encode(auth_str.encode()).decode()

    headers = {
        "Authorization": f"Basic {auth_b64}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }

    response = requests.post("https://www.bling.com.br/Api/v3/oauth/token", headers=headers, data=data)
    if response.status_code == 200:
        novo_token = response.json()
        salvar_token(novo_token)
        return novo_token
    return None

def obter_token_valido():
    token_data = carregar_token()
    if token_expirado(token_data):
        token_data = renovar_token(token_data.get("refresh_token") if token_data else "")
    return token_data

def requisicao_com_espera(url, headers):
    tentativas = 0
    while tentativas < MAX_RETRIES:
        response = requests.get(url, headers=headers)
        if response.status_code == 429:
            time.sleep(1)
            tentativas += 1
            continue
        return response
    return response

def formatar_data(data_str):
    try:
        return datetime.strptime(data_str, "%Y-%m-%d").strftime("%d/%m/%Y")
    except:
        return data_str

def consultar_pedido(headers, numero_pedido):
    url = f"https://www.bling.com.br/Api/v3/pedidos/vendas?numero={numero_pedido}&expand=*"
    response = requisicao_com_espera(url, headers)

    if response.status_code == 200:
        data = response.json()

        if not data.get("data"):
            return f"❌ Nenhum pedido encontrado com o número {numero_pedido}."

        pedido = data["data"][0]
        numero = pedido.get("numero")
        data_venda = formatar_data(pedido.get("data", ""))
        data_saida = formatar_data(pedido.get("dataSaida", ""))
        data_prevista = pedido.get("dataPrevista")
        retirada = "Não foi agendada" if data_prevista == "0000-00-00" else formatar_data(data_prevista)
        cliente = pedido.get("contato", {}).get("nome", "Desconhecido")
        total = pedido.get("total", 0.0)

        mensagem = (
            f"📄 Pedido Nº: {numero}\n"
            f"📅 Data da venda: {data_venda}\n"
            f"📦 Data de entrega: {data_saida}\n"
            f"📤 Data de retirada: {retirada}\n"
            f"👤 Cliente: {cliente}\n"
            f"💰 Valor total da venda: R$ {total:.2f}"
        )
        return mensagem
    return f"❌ Erro ao consultar a API. Status: {response.status_code}"

def limpar_cnpj_cpf(valor):
    return "".join(filter(str.isdigit, valor or ""))

def eh_cpf_ou_cnpj(valor):
    valor_numerico = limpar_cnpj_cpf(valor)
    if len(valor_numerico) == 11:
        return "cpf", valor_numerico
    if len(valor_numerico) == 14:
        return "cnpj", valor_numerico
    return None, None

def buscar_pedido_por_identificacao(headers, identificacao):
    tipo, valor = eh_cpf_ou_cnpj(identificacao)
    if not valor:
        return f"❌ Identificação inválida."

    url = f"https://www.bling.com.br/Api/v3/pedidos/vendas?expand=*&limit=100"
    response = requisicao_com_espera(url, headers)

    if response.status_code == 200:
        pedidos = response.json().get("data", [])
        for pedido in pedidos:
            doc = limpar_cnpj_cpf(pedido.get("contato", {}).get("numeroDocumento", ""))
            if doc == valor:
                numero = pedido.get("numero")
                return consultar_pedido(headers, numero)
        return "❌ Cliente não encontrado."
    return f"❌ Erro ao consultar pedidos. Status: {response.status_code}"

@app.route("/consultar", methods=["POST"])
def webhook():
    token_data = obter_token_valido()
    if not token_data:
        return jsonify({"error": "Token inválido."}), 401

    headers = {
        "Authorization": f"Bearer {token_data['access_token']}"
    }

    dados = request.json or {}
    cep = dados.get("cep_destino")
    identificador = dados.get("identificacao_cliente")

    if identificador:
        resposta = buscar_pedido_por_identificacao(headers, identificador)
        return jsonify({"mensagem": resposta})

    if cep:
        return jsonify({"mensagem": f"🚛 Frete calculado para o CEP {cep} (exemplo)."})

    return jsonify({"mensagem": "❌ Nenhuma informação válida fornecida."})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
