# payment_kode_api/app/services/gateways/asaas_client.py

import httpx
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from decimal import Decimal

from payment_kode_api.app.core.config import settings
from payment_kode_api.app.utilities.logging_config import logger

# 🆕 NOVO: Import do serviço de criptografia por empresa
from ...services.company_encryption import CompanyEncryptionService


async def resolve_internal_token(empresa_id: str, card_token: str) -> Dict[str, Any]:
    """
    🆕 NOVA FUNÇÃO: Resolve token interno para dados reais do cartão.
    
    Args:
        empresa_id: ID da empresa
        card_token: Token interno do cartão (UUID)
        
    Returns:
        Dados reais do cartão para usar com o Asaas
        
    Raises:
        ValueError: Se token não encontrado ou inválido
        Exception: Se erro na descriptografia
    """
    try:
        # 1. Buscar token no banco
        from ...database.database import get_tokenized_card
        card = await get_tokenized_card(card_token)
        
        if not card or card["empresa_id"] != empresa_id:
            raise ValueError("Token não encontrado ou não pertence à empresa")
        
        # 2. Buscar chave da empresa e descriptografar
        encryption_service = CompanyEncryptionService()
        decryption_key = await encryption_service.get_empresa_decryption_key(empresa_id)
        
        # 3. Descriptografar dados
        encrypted_data = card.get("encrypted_card_data")
        if not encrypted_data:
            raise ValueError("Dados criptografados não encontrados para o token")
        
        card_data = encryption_service.decrypt_card_data_with_company_key(
            encrypted_data, 
            decryption_key
        )
        
        logger.info(f"✅ Token interno resolvido para dados reais: {card_token[:8]}...")
        return card_data
        
    except Exception as e:
        logger.error(f"❌ Erro ao resolver token interno {card_token}: {e}")
        raise


def is_internal_token(token: str) -> bool:
    """
    🆕 NOVA FUNÇÃO: Verifica se um token é interno (UUID) ou externo do Asaas.
    
    Args:
        token: Token a ser verificado
        
    Returns:
        True se for token interno (UUID format)
    """
    try:
        uuid.UUID(token)
        return True
    except (ValueError, TypeError):
        return False


async def create_asaas_payment(
    empresa_id: str,
    amount: float,
    payment_type: str,
    transaction_id: str,
    customer_data: Dict[str, Any],
    card_token: Optional[str] = None,
    card_data: Optional[Dict[str, Any]] = None,
    installments: int = 1,
    **kwargs
) -> Dict[str, Any]:
    """
    🔧 ATUALIZADO: Pagamento Asaas com resolução automática de token interno.
    
    Mudanças:
    - Detecta se card_token é token interno (UUID)
    - Resolve automaticamente para dados reais
    - Mantém compatibilidade com tokens externos do Asaas
    """
    try:
        logger.info(f"🚀 Processando pagamento Asaas para empresa {empresa_id}")
        
        # 🆕 NOVO: Resolver token interno se necessário
        resolved_card_data = card_data
        resolved_card_token = card_token
        
        if card_token:
            # Verificar se é token interno (UUID)
            if is_internal_token(card_token):
                logger.info(f"🔄 Detectado token interno, resolvendo: {card_token[:8]}...")
                
                # Resolver para dados reais
                real_card_data = await resolve_internal_token(empresa_id, card_token)
                
                # Usar dados reais em vez do token
                resolved_card_data = real_card_data
                resolved_card_token = None  # Não usar token, usar dados diretos
                
                logger.info("✅ Token interno resolvido - usando dados reais para Asaas")
            else:
                logger.info(f"🏷️ Token externo do Asaas detectado: {card_token[:8]}...")
        
        # Obter credenciais do Asaas
        from ...services.config_service import get_empresa_credentials
        credentials = await get_empresa_credentials(empresa_id)
        api_key = credentials.get("asaas_api_key")
        
        if not api_key:
            raise ValueError("API key do Asaas não configurada para esta empresa")
        
        # Configurar URL (sandbox vs produção)
        use_sandbox = credentials.get("use_sandbox", settings.USE_SANDBOX)
        base_url = "https://sandbox.asaas.com/api/v3" if use_sandbox else "https://api.asaas.com/v3"
        
        # Headers para API do Asaas
        headers = {
            "access_token": api_key,
            "Content-Type": "application/json",
        }
        
        # Criar ou obter cliente no Asaas
        asaas_customer_id = await _get_or_create_asaas_customer(
            empresa_id, customer_data, headers, base_url
        )
        
        # Preparar payload baseado no tipo de pagamento
        if payment_type.lower() == "pix":
            payment_payload = await _create_pix_payment_payload(
                asaas_customer_id, amount, customer_data, kwargs
            )
        elif payment_type.lower() == "credit_card":
            payment_payload = await _create_credit_card_payment_payload(
                asaas_customer_id, amount, resolved_card_data, resolved_card_token, installments, kwargs
            )
        else:
            raise ValueError(f"Tipo de pagamento não suportado: {payment_type}")
        
        # Adicionar referência externa
        payment_payload["externalReference"] = transaction_id
        
        logger.info(f"📡 Enviando requisição para Asaas: {base_url}/payments")
        logger.debug(f"🔍 Payload Asaas: {payment_payload}")
        
        # Enviar requisição
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{base_url}/payments", 
                json=payment_payload, 
                headers=headers
            )
            response.raise_for_status()
            
            response_data = response.json()
            logger.info(f"📥 Resposta do Asaas recebida")
            
            # Processar resposta do Asaas
            return await _process_asaas_response(empresa_id, response_data, transaction_id, payment_type)
            
    except httpx.HTTPStatusError as e:
        logger.error(f"❌ Erro HTTP no Asaas: {e.response.status_code} - {e.response.text}")
        return {
            "status": "failed",
            "message": f"Erro no Asaas: {e.response.status_code}",
            "error_code": str(e.response.status_code),
            "provider": "asaas"
        }
    except Exception as e:
        logger.error(f"❌ Erro inesperado no Asaas: {e}")
        return {
            "status": "failed",
            "message": f"Erro interno: {str(e)}",
            "provider": "asaas"
        }


async def create_asaas_refund(empresa_id: str, transaction_id: str) -> Dict[str, Any]:
    """
    🔧 MANTIDO: Função de estorno do Asaas (sem alterações).
    
    Args:
        empresa_id: ID da empresa
        transaction_id: ID da transação a ser estornada
        
    Returns:
        Resultado do estorno
    """
    try:
        # Buscar dados da transação original
        from ...database.database import get_payment
        payment = await get_payment(transaction_id, empresa_id)
        
        if not payment:
            raise ValueError(f"Transação {transaction_id} não encontrada")
        
        asaas_payment_id = payment.get("asaas_payment_id")
        if not asaas_payment_id:
            raise ValueError("ID do pagamento Asaas não encontrado")
        
        # Obter credenciais
        from ...services.config_service import get_empresa_credentials
        credentials = await get_empresa_credentials(empresa_id)
        api_key = credentials.get("asaas_api_key")
        
        if not api_key:
            raise ValueError("API key do Asaas não configurada")
        
        use_sandbox = credentials.get("use_sandbox", settings.USE_SANDBOX)
        base_url = "https://sandbox.asaas.com/api/v3" if use_sandbox else "https://api.asaas.com/v3"
        
        headers = {
            "access_token": api_key,
            "Content-Type": "application/json",
        }
        
        logger.info(f"🔄 Solicitando estorno Asaas: {asaas_payment_id}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{base_url}/payments/{asaas_payment_id}/refund",
                headers=headers
            )
            response.raise_for_status()
            
            refund_data = response.json()
            
            # Processar resposta do estorno
            if refund_data.get("status") == "REFUNDED":
                logger.info(f"✅ Estorno Asaas aprovado: {transaction_id}")
                return {
                    "status": "refunded",
                    "message": "Estorno processado com sucesso",
                    "asaas_refund_id": refund_data.get("id"),
                    "asaas_payment_id": asaas_payment_id,
                    "amount": refund_data.get("value"),
                    "provider": "asaas"
                }
            else:
                logger.warning(f"⚠️ Estorno Asaas com status inesperado: {refund_data}")
                return {
                    "status": "failed",
                    "message": f"Estorno com status: {refund_data.get('status')}",
                    "provider": "asaas"
                }
                
    except Exception as e:
        logger.error(f"❌ Erro no estorno Asaas: {e}")
        return {
            "status": "failed",
            "message": f"Erro no estorno: {str(e)}",
            "provider": "asaas"
        }


async def get_asaas_payment_status(empresa_id: str, transaction_id: str) -> Optional[Dict[str, Any]]:
    """
    🔧 MANTIDO: Consulta status de pagamento no Asaas (sem alterações).
    """
    try:
        # Buscar payment_id do Asaas
        from ...database.database import get_payment
        payment = await get_payment(transaction_id, empresa_id)
        
        if not payment:
            return None
        
        asaas_payment_id = payment.get("asaas_payment_id")
        if not asaas_payment_id:
            return None
        
        # Obter credenciais
        from ...services.config_service import get_empresa_credentials
        credentials = await get_empresa_credentials(empresa_id)
        api_key = credentials.get("asaas_api_key")
        
        if not api_key:
            return None
        
        use_sandbox = credentials.get("use_sandbox", settings.USE_SANDBOX)
        base_url = "https://sandbox.asaas.com/api/v3" if use_sandbox else "https://api.asaas.com/v3"
        
        headers = {
            "access_token": api_key,
            "Content-Type": "application/json",
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{base_url}/payments/{asaas_payment_id}",
                headers=headers
            )
            response.raise_for_status()
            
            payment_data = response.json()
            logger.info(f"✅ Status Asaas consultado: {asaas_payment_id}")
            return payment_data
            
    except Exception as e:
        logger.error(f"❌ Erro ao consultar status Asaas: {e}")
        return None


async def get_asaas_pix_qr_code(empresa_id: str, payment_id: str) -> Dict[str, Any]:
    """
    🔧 MANTIDO: Obtém QR Code PIX do Asaas (sem alterações).
    """
    try:
        # Obter credenciais
        from ...services.config_service import get_empresa_credentials
        credentials = await get_empresa_credentials(empresa_id)
        api_key = credentials.get("asaas_api_key")
        
        if not api_key:
            raise ValueError("API key do Asaas não configurada")
        
        use_sandbox = credentials.get("use_sandbox", settings.USE_SANDBOX)
        base_url = "https://sandbox.asaas.com/api/v3" if use_sandbox else "https://api.asaas.com/v3"
        
        headers = {
            "access_token": api_key,
            "Content-Type": "application/json",
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{base_url}/payments/{payment_id}/pixQrCode",
                headers=headers
            )
            response.raise_for_status()
            
            qr_data = response.json()
            
            return {
                "pix_link": qr_data.get("payload"),
                "qr_code_base64": qr_data.get("encodedImage"),
                "expiration": qr_data.get("expirationDate")
            }
            
    except Exception as e:
        logger.error(f"❌ Erro ao obter QR Code PIX: {e}")
        return {
            "pix_link": None,
            "qr_code_base64": None,
            "expiration": None
        }


async def list_asaas_pix_keys(empresa_id: str) -> List[Dict[str, Any]]:
    """
    🔧 MANTIDO: Lista chaves PIX do Asaas (sem alterações).
    """
    try:
        # Obter credenciais
        from ...services.config_service import get_empresa_credentials
        credentials = await get_empresa_credentials(empresa_id)
        api_key = credentials.get("asaas_api_key")
        
        if not api_key:
            raise ValueError("API key do Asaas não configurada")
        
        use_sandbox = credentials.get("use_sandbox", settings.USE_SANDBOX)
        base_url = "https://sandbox.asaas.com/api/v3" if use_sandbox else "https://api.asaas.com/v3"
        
        headers = {
            "access_token": api_key,
            "Content-Type": "application/json",
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{base_url}/pix/addressKeys",
                headers=headers
            )
            response.raise_for_status()
            
            keys_data = response.json()
            return keys_data.get("data", [])
            
    except Exception as e:
        logger.error(f"❌ Erro ao listar chaves PIX: {e}")
        return []


async def validate_asaas_pix_key(empresa_id: str, chave_pix: str) -> None:
    """
    🔧 MANTIDO: Valida chave PIX no Asaas (sem alterações).
    """
    try:
        pix_keys = await list_asaas_pix_keys(empresa_id)
        
        # Verificar se a chave está cadastrada
        key_found = False
        for key_data in pix_keys:
            if key_data.get("key") == chave_pix:
                key_found = True
                break
        
        if not key_found:
            raise ValueError(f"Chave PIX {chave_pix} não está cadastrada no Asaas")
        
        logger.info(f"✅ Chave PIX validada: {chave_pix}")
        
    except Exception as e:
        logger.error(f"❌ Erro ao validar chave PIX: {e}")
        raise


# ========== FUNÇÕES AUXILIARES PRIVADAS ==========

async def _get_or_create_asaas_customer(
    empresa_id: str, 
    customer_data: Dict[str, Any], 
    headers: Dict[str, str], 
    base_url: str
) -> str:
    """
    🔧 FUNÇÃO AUXILIAR: Busca ou cria cliente no Asaas.
    """

    raw_name = customer_data.get("name")
    name = raw_name.strip() if raw_name and raw_name.strip() else "Cliente"
    customer_data["name"] = name
    try:
        # Tentar buscar cliente existente pelo externalReference
        external_ref = customer_data.get("externalReference") or customer_data.get("local_id")
        
        if external_ref:
            async with httpx.AsyncClient(timeout=30.0) as client:
                search_response = await client.get(
                    f"{base_url}/customers",
                    params={"externalReference": external_ref},
                    headers=headers
                )
                
                if search_response.status_code == 200:
                    search_data = search_response.json()
                    customers = search_data.get("data", [])
                    
                    if customers:
                        customer_id = customers[0]["id"]
                        logger.info(f"✅ Cliente Asaas existente encontrado: {customer_id}")
                        return customer_id
        
        # Criar novo cliente
        customer_payload = {
            "name": customer_data.get("name", ""),
            "email": customer_data.get("email"),
            "cpfCnpj": customer_data.get("cpfCnpj"),
            "phone": customer_data.get("phone"),
            "mobilePhone": customer_data.get("mobilePhone"),
            "externalReference": external_ref
        }
        
        # Remover campos vazios
        customer_payload = {k: v for k, v in customer_payload.items() if v}
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            create_response = await client.post(
                f"{base_url}/customers",
                json=customer_payload,
                headers=headers
            )
            create_response.raise_for_status()
            
            new_customer = create_response.json()
            customer_id = new_customer["id"]
            
            logger.info(f"✅ Novo cliente Asaas criado: {customer_id}")
            return customer_id
            
    except Exception as e:
        logger.error(f"❌ Erro ao gerenciar cliente Asaas: {e}")
        raise


async def _create_pix_payment_payload(
    customer_id: str, 
    amount: float, 
    customer_data: Dict[str, Any], 
    extra_kwargs: Dict[str, Any]
) -> Dict[str, Any]:
    """
    🔧 FUNÇÃO AUXILIAR: Cria payload para pagamento PIX.
    """
    payload = {
        "customer": customer_id,
        "billingType": "PIX",
        "value": amount,
        "dueDate": extra_kwargs.get("due_date", datetime.now().strftime("%Y-%m-%d"))
    }
    
    # Adicionar chave PIX se fornecida
    if customer_data.get("pixKey"):
        payload["pixKey"] = customer_data["pixKey"]
    
    # Adicionar descrição se fornecida
    if extra_kwargs.get("description"):
        payload["description"] = extra_kwargs["description"]
    
    return payload


async def _create_credit_card_payment_payload(
    customer_id: str, 
    amount: float, 
    card_data: Optional[Dict[str, Any]], 
    card_token: Optional[str], 
    installments: int, 
    extra_kwargs: Dict[str, Any]
) -> Dict[str, Any]:
    """
    🔧 FUNÇÃO AUXILIAR: Cria payload para pagamento com cartão.
    """
    payload = {
        "customer": customer_id,
        "billingType": "CREDIT_CARD",
        "value": amount,
        "dueDate": datetime.now().strftime("%Y-%m-%d"),
        "installmentCount": installments
    }
    
    # Usar token ou dados do cartão
    if card_token and not card_data:
        # Token externo do Asaas
        payload["creditCardToken"] = card_token
    elif card_data:
        # Dados diretos do cartão (de token interno resolvido)
        payload["creditCard"] = {
            "holderName": card_data["cardholder_name"],
            "number": card_data["card_number"],
            "expiryMonth": card_data["expiration_month"],
            "expiryYear": card_data["expiration_year"],
            "ccv": card_data["security_code"]
        }
    else:
        raise ValueError("É necessário fornecer card_token ou card_data")
    
    # Adicionar dados extras
    if extra_kwargs.get("description"):
        payload["description"] = extra_kwargs["description"]
    
    return payload


async def _process_asaas_response(
    empresa_id: str, 
    response_data: Dict[str, Any], 
    transaction_id: str, 
    payment_type: str
) -> Dict[str, Any]:
    """
    🔧 FUNÇÃO AUXILIAR: Processa resposta do Asaas e atualiza banco.
    """
    try:
        asaas_payment_id = response_data.get("id")
        status = response_data.get("status", "").upper()
        
        # Mapear status do Asaas para nosso padrão
        if status in ["PENDING", "AWAITING_PAYMENT"]:
            mapped_status = "pending"
            message = "Aguardando pagamento"
        elif status in ["RECEIVED", "CONFIRMED"]:
            mapped_status = "approved"
            message = "Pagamento confirmado"
        elif status in ["OVERDUE", "REFUNDED", "REFUNDED_PARTIAL"]:
            mapped_status = "failed"
            message = f"Pagamento {status.lower()}"
        else:
            mapped_status = "pending"
            message = f"Status: {status}"
        
        # Atualizar pagamento no banco
        if transaction_id:
            from ...database.database import update_payment_status
            await update_payment_status(
                transaction_id=transaction_id,
                empresa_id=empresa_id,
                status=mapped_status,
                extra_data={
                    "asaas_payment_id": asaas_payment_id,
                    "asaas_status": status,
                    "asaas_response": response_data
                }
            )
        
        logger.info(f"✅ Pagamento Asaas processado: {mapped_status} | ID: {asaas_payment_id}")
        
        # Retorno base
        result = {
            "status": mapped_status,
            "message": message,
            "transaction_id": transaction_id,
            "id": asaas_payment_id,
            "provider": "asaas",
            "payment_type": payment_type
        }
        
        # Adicionar dados específicos do tipo de pagamento
        if payment_type.lower() == "pix":
            result.update({
                "pix_qr_code": response_data.get("pixQrCode"),
                "due_date": response_data.get("dueDate")
            })
        elif payment_type.lower() == "credit_card":
            result.update({
                "installments": response_data.get("installmentCount", 1)
            })
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Erro ao processar resposta do Asaas: {e}")
        return {
            "status": "failed",
            "message": f"Erro ao processar resposta: {str(e)}",
            "provider": "asaas"
        }


# ========== FUNÇÕES AUXILIARES PARA TOKENIZAÇÃO (OPCIONAIS) ==========

async def tokenize_asaas_card(empresa_id: str, card_data: Dict[str, Any]) -> str:
    """
    🔧 OPCIONAL: Tokenização nativa do Asaas (se suportada).
    
    Args:
        empresa_id: ID da empresa
        card_data: Dados do cartão
        
    Returns:
        Token do Asaas
        
    Note:
        Esta função é opcional pois agora preferimos tokens internos.
    """
    try:
        # Obter credenciais
        from ...services.config_service import get_empresa_credentials
        credentials = await get_empresa_credentials(empresa_id)
        api_key = credentials.get("asaas_api_key")
        
        if not api_key:
            raise ValueError("API key do Asaas não configurada")
        
        use_sandbox = credentials.get("use_sandbox", settings.USE_SANDBOX)
        base_url = "https://sandbox.asaas.com/api/v3" if use_sandbox else "https://api.asaas.com/v3"
        
        headers = {
            "access_token": api_key,
            "Content-Type": "application/json",
        }
        
        # Payload para tokenização
        tokenization_payload = {
            "holderName": card_data["cardholder_name"],
            "number": card_data["card_number"],
            "expiryMonth": card_data["expiration_month"],
            "expiryYear": card_data["expiration_year"],
            "ccv": card_data["security_code"]
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{base_url}/creditCard/tokenize",
                json=tokenization_payload,
                headers=headers
            )
            response.raise_for_status()
            
            token_data = response.json()
            asaas_token = token_data.get("creditCardToken")
            
            if not asaas_token:
                raise ValueError("Token não retornado pelo Asaas")
            
            logger.info(f"✅ Cartão tokenizado no Asaas: {asaas_token[:8]}...")
            return asaas_token
            
    except Exception as e:
        logger.error(f"❌ Erro na tokenização Asaas: {e}")
        raise


# ========== EXPORTS ==========

__all__ = [
    # Funções principais
    "create_asaas_payment",
    "create_asaas_refund",
    "get_asaas_payment_status",
    "get_asaas_pix_qr_code",
    "list_asaas_pix_keys", 
    "validate_asaas_pix_key",
    
    # 🆕 NOVAS: Funções de resolução de token
    "resolve_internal_token",
    "is_internal_token",
    
    # Funções auxiliares (opcionais)
    "tokenize_asaas_card",
]