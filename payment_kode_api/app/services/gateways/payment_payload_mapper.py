from typing import Dict, Any

def map_to_sicredi_payload(data: Dict[str, Any]) -> Dict[str, Any]:
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

def map_to_asaas_pix_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """Mapeia os dados do pagamento para o formato do gateway Asaas (Pix)."""
    return {
        "customer": data.get("customer_id", "cus_default"),
        "billingType": "PIX",
        "value": round(data["amount"], 2),  # Valor em reais (já esperado pelo Asaas)
        "pixKey": data["chave_pix"],  # 🔹 Chave Pix
        "description": data.get("descricao", "Pagamento via Pix (fallback Sicredi)")
    }

def map_to_rede_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mapeia os dados do pagamento para o formato do gateway Rede.
    Prioriza o uso de `card_token` se presente e suportado.
    """
    if not data.get("card_token") and not all(
        key in data for key in ["card_number", "expiration_month", "expiration_year", "security_code", "cardholder_name"]
    ):
        raise ValueError("É necessário fornecer `card_token` ou dados completos do cartão.")

    payload = {
        "amount": int(data["amount"] * 100),  # Converte reais para centavos
        "installments": data["installments"],
        "capture": True,
        "softDescriptor": data.get("soft_descriptor", "Minha Empresa")
    }

    if data.get("card_token"):
        payload["cardToken"] = data["card_token"]  # 🔹 Usa token quando suportado pela Rede
    else:
        # Se `card_token` não estiver presente, verifica e mapeia os dados do cartão
        payload.update({
            "cardNumber": data["card_number"],
            "cardExpirationDate": f"{data['expiration_month']:02}{data['expiration_year'][-2:]}",
            "securityCode": data["security_code"],
            "cardHolderName": data["cardholder_name"],
        })
    
    return payload

def map_to_asaas_credit_payload(data: Dict[str, Any], support_tokenization: bool = True) -> Dict[str, Any]:
    """
    Mapeia os dados do pagamento para o formato do gateway Asaas (Cartão de Crédito).
    Verifica suporte a tokenização.
    """
    if not data.get("card_token") and not all(
        key in data for key in ["card_number", "expiration_month", "expiration_year", "security_code", "cardholder_name"]
    ):
        raise ValueError("É necessário fornecer `card_token` ou dados completos do cartão.")

    payload = {
        "customer": data.get("customer_id", "cus_default"),
        "billingType": "CREDIT_CARD",
        "value": round(data["amount"], 2),  # Já está em reais
        "installmentCount": data["installments"],
    }

    if support_tokenization and "card_token" in data:
        # 🔹 Se a empresa e o Asaas suportarem tokenização, usa `card_token`
        payload["creditCardToken"] = data["card_token"]
    else:
        # Caso contrário, faz mapeamento completo dos dados sensíveis
        payload["creditCard"] = {
            "holderName": data["cardholder_name"],
            "number": data["card_number"],
            "expiryMonth": f"{int(data['expiration_month']):02}",
            "expiryYear": data["expiration_year"],
            "cvv": data["security_code"]  # Alguns gateways usam "cvv" em vez de "ccv"
        }
        payload["creditCardHolderInfo"] = {
            "name": data["cardholder_name"],
            "cpfCnpj": data.get("cpf_cnpj", "00000000000"),
            "postalCode": data.get("postal_code", "00000000"),
            "addressNumber": data.get("address_number", "0"),
            "phone": data.get("phone", "11999999999")
        }

    return payload
