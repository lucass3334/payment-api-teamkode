from typing import Dict

def map_to_sicredi_payload(data: Dict) -> Dict:
    """Mapeia os dados do pagamento para o formato do gateway Sicredi (Pix)."""
    
    devedor = {}
    if "cpf" in data:
        devedor["cpf"] = data["cpf"]
    elif "cnpj" in data:
        devedor["cnpj"] = data["cnpj"]
    
    return {
        "calendario": {
            "expiracao": 900  # Tempo de expiração do QR Code em segundos (15 minutos)
        },
        "devedor": devedor,  # Apenas um dos dois (CPF ou CNPJ)
        "valor": {
            "original": f"{round(data['amount'], 2):.2f}"  # Valor no formato correto (string com duas casas decimais)
        },
        "chave": data["chave_pix"],  # 🔹 Chave Pix da empresa
        "solicitacaoPagador": data.get("descricao", "Pagamento via Pix")
    }

def map_to_asaas_pix_payload(data: Dict) -> Dict:
    """Mapeia os dados do pagamento para o formato do gateway Asaas (Pix)."""
    return {
        "customer": data.get("customer_id", "cus_default"),
        "billingType": "PIX",
        "value": round(data["amount"], 2),  # Valor em reais (já esperado pelo Asaas)
        "pixKey": data["chave_pix"],  # 🔹 Chave Pix
        "description": data.get("descricao", "Pagamento via Pix (fallback Sicredi)")
    }

def map_to_rede_payload(data: Dict) -> Dict:
    """Mapeia os dados do pagamento para o formato do gateway Rede (Cartão de Crédito)."""
    return {
        "amount": int(data["amount"] * 100),  # Converte reais para centavos
        "cardNumber": data["card_number"],
        "cardExpirationDate": f"{data['expiration_month']:02}{data['expiration_year'][-2:]}",  # MMYY
        "securityCode": data["security_code"],
        "cardHolderName": data["cardholder_name"],
        "installments": data["installments"],
        "capture": True,
        "softDescriptor": data.get("soft_descriptor", "Minha Empresa")
    }

def map_to_asaas_credit_payload(data: Dict) -> Dict:
    """Mapeia os dados do pagamento para o formato do gateway Asaas (Cartão de Crédito)."""
    return {
        "customer": data.get("customer_id", "cus_default"),
        "billingType": "CREDIT_CARD",
        "value": round(data["amount"], 2),  # Já está em reais
        "installmentCount": data["installments"],
        "creditCard": {
            "holderName": data["cardholder_name"],
            "number": data["card_number"],
            "expiryMonth": f"{int(data['expiration_month']):02}",
            "expiryYear": data["expiration_year"],
            "cvv": data["security_code"]  # Alguns gateways usam "cvv" em vez de "ccv"
        },
        "creditCardHolderInfo": {
            "name": data["cardholder_name"],
            "cpfCnpj": data.get("cpf_cnpj", "00000000000"),
            "postalCode": data.get("postal_code", "00000000"),
            "addressNumber": data.get("address_number", "0"),
            "phone": data.get("phone", "11999999999")
        }
    }
