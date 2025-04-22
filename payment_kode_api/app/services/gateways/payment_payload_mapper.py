# payment_kode_api/app/services/gateways/payment_payload_mapper.py

from typing import Dict, Any


def map_to_sicredi_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mapeia os dados do pagamento para o formato do gateway Sicredi (Pix).
    - Recebe 'amount', 'chave_pix', 'txid', e opcionalmente 'cpf', 'cnpj' e 'solicitacaoPagador'.
    """
    if not data.get("chave_pix"):
        raise ValueError("A chave Pix (chave_pix) é obrigatória para pagamentos via Pix.")
    if not data.get("txid"):
        raise ValueError("O txid é obrigatório para pagamentos via Sicredi Pix.")

    payload: Dict[str, Any] = {
        "txid": data["txid"],
        "calendario": {"expiracao": 900},
        "valor": {"original": f"{round(data['amount'], 2):.2f}"},
        "chave": data["chave_pix"],
    }

    # devedor: CPF ou CNPJ, se fornecido
    devedor: Dict[str, Any] = {}
    if data.get("cpf"):
        devedor["cpf"] = data["cpf"]
    elif data.get("cnpj"):
        devedor["cnpj"] = data["cnpj"]
    if devedor:
        payload["devedor"] = devedor

    # solicitacaoPagador: descrição opcional
    if data.get("solicitacaoPagador"):
        payload["solicitacaoPagador"] = data["solicitacaoPagador"]

    return payload


def map_to_asaas_pix_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mapeia os dados do pagamento para o formato do gateway Asaas (PIX).
    - Recebe 'amount', 'chave_pix' e opcionalmente 'customer_id' e 'descricao'.
    """
    if not data.get("chave_pix"):
        raise ValueError("A chave Pix (chave_pix) é obrigatória para pagamentos via PIX.")
    return {
        "customer": data.get("customer_id", "cus_default"),
        "billingType": "PIX",
        "value": round(data["amount"], 2),
        "pixKey": data["chave_pix"],
        "description": data.get("descricao", "Pagamento via Pix (fallback Sicredi)")
    }


def map_to_rede_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mapeia os dados do pagamento para o formato do gateway Rede (Cartão).
    - Usa 'card_token' se presente, senão faz mapeamento completo dos dados de cartão.
    """
    if not data.get("card_token") and not all(k in data for k in (
        "card_number", "expiration_month", "expiration_year", "security_code", "cardholder_name"
    )):
        raise ValueError("É necessário fornecer `card_token` ou dados completos do cartão.")

    payload: Dict[str, Any] = {
        "amount": int(data["amount"] * 100),  # em centavos
        "installments": data["installments"],
        "capture": True,
        "softDescriptor": data.get("soft_descriptor", "Minha Empresa")
    }

    if data.get("card_token"):
        payload["cardToken"] = data["card_token"]
    else:
        payload.update({
            "cardNumber": data["card_number"],
            "cardExpirationDate": f"{int(data['expiration_month']):02d}{data['expiration_year'][-2:]}",
            "securityCode": data["security_code"],
            "cardHolderName": data["cardholder_name"],
        })

    return payload


def map_to_asaas_credit_payload(data: Dict[str, Any], support_tokenization: bool = True) -> Dict[str, Any]:
    """
    Mapeia os dados do pagamento para o formato do gateway Asaas (Cartão de Crédito).
    - Usa tokenização se disponível e suportada, senão envia dados completos do cartão.
    """
    if not data.get("card_token") and not all(k in data for k in (
        "card_number", "expiration_month", "expiration_year", "security_code", "cardholder_name"
    )):
        raise ValueError("É necessário fornecer `card_token` ou dados completos do cartão.")

    payload: Dict[str, Any] = {
        "customer": data.get("customer_id", "cus_default"),
        "billingType": "CREDIT_CARD",
        "value": round(data["amount"], 2),
        "installmentCount": data["installments"],
    }

    if support_tokenization and data.get("card_token"):
        payload["creditCardToken"] = data["card_token"]
    else:
        payload["creditCard"] = {
            "holderName": data["cardholder_name"],
            "number": data["card_number"],
            "expiryMonth": f"{int(data['expiration_month']):02d}",
            "expiryYear": data["expiration_year"],
            "ccv": data["security_code"]
        }
        payload["creditCardHolderInfo"] = {
            "name": data["cardholder_name"],
            "cpfCnpj": data.get("cpf_cnpj", ""),
            "postalCode": data.get("postal_code", ""),
            "addressNumber": data.get("address_number", ""),
            "phone": data.get("phone", "")
        }

    return payload
