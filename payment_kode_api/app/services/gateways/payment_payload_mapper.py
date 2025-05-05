# payment_kode_api/app/services/gateways/payment_payload_mapper.py

from typing import Dict, Any


def map_to_sicredi_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mapeia os dados do pagamento para o formato do gateway Sicredi (Pix).
    - Recebe 'amount', 'chave_pix', 'txid', e opcionalmente 'cpf', 'cnpj', 'nome_devedor', 'solicitacaoPagador' e 'due_date'.
    - Se 'due_date' for fornecido, será criada uma cobrança com vencimento (cobv), caso contrário, uma cobrança imediata (cob).
    """
    if not data.get("chave_pix"):
        raise ValueError("A chave Pix (chave_pix) é obrigatória para pagamentos via Pix.")
    if not data.get("txid"):
        raise ValueError("O txid é obrigatório para pagamentos via Sicredi Pix.")

    # Define o campo 'calendario' com base na presença de 'due_date'
    if data.get("due_date"):
        calendario = {
            "dataDeVencimento": data["due_date"],
            "validadeAposVencimento": 7
        }
    else:
        calendario = {
            "expiracao": 900
        }

    payload: Dict[str, Any] = {
        "txid": data["txid"],
        "calendario": calendario,
        "valor": {"original": f"{round(data['amount'], 2):.2f}"},
        "chave": data["chave_pix"],
    }

    # devedor: obrigatório em cobranças com vencimento
    if data.get("due_date"):
        if not data.get("nome_devedor"):
            raise ValueError("Para cobranças com vencimento, 'nome_devedor' é obrigatório.")
        if not data.get("cpf") and not data.get("cnpj"):
            raise ValueError("Para cobranças com vencimento, 'cpf' ou 'cnpj' é obrigatório.")

        devedor: Dict[str, Any] = {"nome": data["nome_devedor"]}
        if data.get("cpf"):
            devedor["cpf"] = data["cpf"]
        else:
            devedor["cnpj"] = data["cnpj"]

        payload["devedor"] = devedor

    # solicitacaoPagador: descrição opcional
    if data.get("solicitacaoPagador"):
        payload["solicitacaoPagador"] = data["solicitacaoPagador"]

    return payload


def map_to_asaas_pix_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mapeia os dados do pagamento para o formato do gateway Asaas (PIX).
    - Recebe 'amount', 'chave_pix', e opcionalmente 'customer_id', 'descricao' e 'txid'.
    - Inclui 'externalReference' para rastrear a transação.
    """
    if not data.get("chave_pix"):
        raise ValueError("A chave Pix (chave_pix) é obrigatória para pagamentos via PIX.")

    payload: Dict[str, Any] = {
        "customer":          data.get("customer_id", ""),
        "billingType":       "PIX",
        "value":             round(data["amount"], 2),
        "pixKey":            data["chave_pix"],
        "externalReference": data.get("transaction_id", ""),
        "description":       data.get("descricao") or f"PIX (txid {data.get('transaction_id')})"
    }
    return payload


def map_to_rede_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mapeia os dados do pagamento para o formato do gateway Rede (Cartão).
    - Usa 'card_token' se presente, senão faz mapeamento completo dos dados de cartão.
    - Inclui 'reference' para rastrear a transação.
    """
    if not data.get("card_token") and not all(k in data for k in (
        "card_number", "expiration_month", "expiration_year", "security_code", "cardholder_name"
    )):
        raise ValueError("É necessário fornecer `card_token` ou dados completos do cartão.")

    payload: Dict[str, Any] = {
        "capture":      True,
        "kind":         "credit",
        "reference":    data.get("transaction_id", ""),
        "amount":       str(int(data["amount"] * 100)),
        "installments": data.get("installments", 1),
        "softDescriptor": data.get("soft_descriptor", "Minha Empresa")
    }

    if data.get("card_token"):
        payload["cardToken"] = data["card_token"]
    else:
        payload.update({
            "cardNumber":      data["card_number"],
            "expirationMonth": f"{int(data['expiration_month']):02d}",
            "expirationYear":  data["expiration_year"],
            "securityCode":    data["security_code"],
            "cardHolderName":  data["cardholder_name"],
        })

    return payload


def map_to_asaas_credit_payload(data: Dict[str, Any], support_tokenization: bool = True) -> Dict[str, Any]:
    """
    Mapeia os dados do pagamento para o formato do gateway Asaas (Cartão de Crédito).
    - Usa tokenização se disponível e suportada, senão envia dados completos do cartão.
    - Inclui 'externalReference' para rastrear a transação.
    """
    if not data.get("card_token") and not all(k in data for k in (
        "card_number", "expiration_month", "expiration_year", "security_code", "cardholder_name"
    )):
        raise ValueError("É necessário fornecer `card_token` ou dados completos do cartão.")

    payload: Dict[str, Any] = {
        "customer":          data.get("customer_id", ""),
        "billingType":       "CREDIT_CARD",
        "value":             round(data["amount"], 2),
        "installmentCount":  data.get("installments", 1),
        "externalReference": data.get("transaction_id", "")
    }

    if support_tokenization and data.get("card_token"):
        payload["creditCardToken"] = data["card_token"]
    else:
        payload["creditCard"] = {
            "holderName": data["cardholder_name"],
            "number":     data["card_number"],
            "expiryMonth": f"{int(data['expiration_month']):02d}",
            "expiryYear":  data["expiration_year"],
            "ccv":         data["security_code"]
        }
        payload["creditCardHolderInfo"] = {
            "name":          data.get("cardholder_name", ""),
            "cpfCnpj":       data.get("cpf_cnpj", ""),
            "postalCode":    data.get("postal_code", ""),
            "addressNumber": data.get("address_number", ""),
            "phone":         data.get("phone", "")
        }

    return payload
