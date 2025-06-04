# payment_kode_api/app/services/gateways/asaas_client.py

import httpx
import asyncio
from fastapi import HTTPException
from typing import Any, Dict, Optional
from datetime import datetime, timezone

from ...utilities.logging_config import logger

# ✅ MANTÉM: Imports das interfaces (SEM imports circulares)
from ...interfaces import (
    ConfigRepositoryInterface,
    AsaasCustomerInterface,
)

# ❌ REMOVIDO: Imports que causavam circular import
# from ...dependencies import (
#     get_config_repository,
#     get_asaas_customer_repository,
# )

# ⏱️ Timeout padrão para conexões Asaas
TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)


async def get_asaas_headers(
    empresa_id: str,
    config_repo: Optional[ConfigRepositoryInterface] = None
) -> Dict[str, str]:
    """
    ✅ MIGRADO: Retorna os headers necessários para autenticação na API do Asaas da empresa específica.
    Agora usa interfaces para evitar imports circulares.
    """
    # ✅ LAZY LOADING: Dependency injection
    if config_repo is None:
        from ...dependencies import get_config_repository
        config_repo = get_config_repository()

    # ✅ USANDO INTERFACE
    config = await config_repo.get_empresa_config(empresa_id)
    if not config:
        logger.error(f"❌ Configuração da empresa {empresa_id} não encontrada")
        raise HTTPException(status_code=400, detail="Configuração da empresa não encontrada.")

    api_key = config.get("asaas_api_key")
    if not api_key:
        logger.error(f"❌ Asaas API key não configurada para empresa {empresa_id}")
        raise HTTPException(status_code=400, detail="Asaas API key não configurada.")

    return {
        "access_token": api_key,
        "Content-Type": "application/json"
    }


async def tokenize_asaas_card(
    empresa_id: str, 
    card_data: Dict[str, Any],
    config_repo: Optional[ConfigRepositoryInterface] = None
) -> str:
    """
    ✅ MIGRADO: Tokeniza os dados do cartão na API do Asaas.
    Agora usa interfaces para evitar imports circulares.
    """
    headers = await get_asaas_headers(empresa_id, config_repo)
    
    # ✅ LAZY LOADING: Buscar configurações
    if config_repo is None:
        from ...dependencies import get_config_repository
        config_repo = get_config_repository()
    
    config = await config_repo.get_empresa_config(empresa_id)
    use_sandbox = config.get("use_sandbox", True)
    
    url = (
        "https://sandbox.asaas.com/api/v3/creditCard/tokenize"
        if use_sandbox else
        "https://api.asaas.com/v3/creditCard/tokenize"
    )

    payload = {
        "holderName":  card_data["cardholder_name"],
        "number":      card_data["card_number"],
        "expiryMonth": card_data["expiration_month"],
        "expiryYear":  card_data["expiration_year"],
        "ccv":         card_data["security_code"]
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json().get("creditCardToken")
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ HTTP {e.response.status_code} ao tokenizar Asaas: {e.response.text}")
            raise HTTPException(status_code=e.response.status_code, detail="Erro ao tokenizar cartão no Asaas")
        except Exception as e:
            logger.error(f"❌ Erro na tokenização Asaas: {e}")
            raise HTTPException(status_code=500, detail="Erro inesperado na tokenização Asaas")


async def list_asaas_pix_keys(
    empresa_id: str,
    config_repo: Optional[ConfigRepositoryInterface] = None
) -> list[Dict[str, Any]]:
    """
    ✅ MIGRADO: Retorna todas as chaves Pix cadastradas para esta empresa no Asaas.
    Endpoint: GET /v3/pix/addressKeys
    Agora usa interfaces para evitar imports circulares.
    """
    headers = await get_asaas_headers(empresa_id, config_repo)
    
    # ✅ LAZY LOADING: Buscar configurações
    if config_repo is None:
        from ...dependencies import get_config_repository
        config_repo = get_config_repository()
    
    config = await config_repo.get_empresa_config(empresa_id)
    use_sandbox = config.get("use_sandbox", False)
    
    base_url = (
        "https://sandbox.asaas.com/api/v3"
        if use_sandbox else
        "https://api.asaas.com/v3"
    )
    url = f"{base_url}/pix/addressKeys"

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json().get("data", [])


async def create_asaas_payment(
    empresa_id: str,
    amount: float,
    payment_type: str,
    transaction_id: str,
    customer_data: Dict[str, Any],
    card_data: Optional[Dict[str, Any]] = None,
    card_token: Optional[str] = None,
    installments: int = 1,
    retries: int = 2,
    config_repo: Optional[ConfigRepositoryInterface] = None,
    asaas_customer_repo: Optional[AsaasCustomerInterface] = None
) -> Dict[str, Any]:
    """
    ✅ MIGRADO: Cria um pagamento no Asaas para a empresa específica.
    Suporta PIX e Cartão de Crédito.
    Garante que o cliente exista via get_or_create_asaas_customer.
    Agora usa interfaces para evitar imports circulares.
    """
    # ✅ LAZY LOADING: Dependency injection
    if config_repo is None:
        from ...dependencies import get_config_repository
        config_repo = get_config_repository()
    if asaas_customer_repo is None:
        from ...dependencies import get_asaas_customer_repository
        asaas_customer_repo = get_asaas_customer_repository()

    # 1) Ajuste para evitar problemas de serialização
    amount = float(amount)

    # 2) Obtém ou cria cliente na Asaas - ✅ USANDO INTERFACE
    asaas_customer_id = await asaas_customer_repo.get_or_create_asaas_customer(
        empresa_id=empresa_id,
        local_customer_id=customer_data.get("local_id", transaction_id),
        customer_data={
            "name":              customer_data.get("name"),
            "email":             customer_data.get("email"),
            "cpfCnpj":           customer_data.get("cpfCnpj") or customer_data.get("cpf"),
            "phone":             customer_data.get("phone"),
            "mobilePhone":       customer_data.get("mobilePhone"),
            "postalCode":        customer_data.get("postalCode"),
            "address":           customer_data.get("address"),
            "addressNumber":     customer_data.get("addressNumber"),
            "externalReference": customer_data.get("externalReference", transaction_id)
        }
    )

    headers = await get_asaas_headers(empresa_id, config_repo)
    
    # ✅ USANDO INTERFACE: Buscar configurações
    config = await config_repo.get_empresa_config(empresa_id)
    use_sandbox = config.get("use_sandbox", False)
    
    base_url = (
        "https://sandbox.asaas.com/api/v3/payments"
        if use_sandbox else
        "https://api.asaas.com/v3/payments"
    )
    callback = config.get("webhook_pix")

    # 3) Monta payload conforme tipo
    if payment_type == "pix":
        pix_key = customer_data.get("pixKey")
        if not pix_key:
            raise HTTPException(400, "Para PIX, é obrigatório informar 'pixKey' em customer_data.")
        payload = {
            "customer":          asaas_customer_id,
            "value":             amount,
            "billingType":       "PIX",
            "pixKey":            pix_key,                          # ← inclusão da chave Pix
            "dueDate":           customer_data.get("due_date"),
            "description":       f"PIX {transaction_id}",
            "externalReference": transaction_id,
            "postalService":     False,
            "callbackUrl":       callback
        }

    elif payment_type == "credit_card":
        installments = max(1, min(installments, 12))
        common = {
            "customer":          asaas_customer_id,
            "value":             amount,
            "billingType":       "CREDIT_CARD",
            "dueDate":           customer_data.get("due_date"),
            "description":       f"Cartão {transaction_id}",
            "externalReference": transaction_id,
            "callbackUrl":       callback,
            "installmentCount":  installments
        }
        if card_token:
            payload = {**common, "creditCardToken": card_token}
        else:
            if not card_data:
                raise HTTPException(status_code=400, detail="Dados do cartão obrigatórios.")
            payload = {
                **common,
                "creditCard": card_data,
                "creditCardHolderInfo": {
                    "name":           customer_data.get("name"),
                    "email":          customer_data.get("email"),
                    "cpfCnpj":        customer_data.get("cpfCnpj") or customer_data.get("cpf"),
                    "postalCode":     customer_data.get("postalCode"),
                    "addressNumber":  customer_data.get("addressNumber"),
                    "phone":          customer_data.get("phone")
                }
            }

    else:
        raise HTTPException(status_code=400, detail="Tipo de pagamento inválido.")

    # 4) Tenta criar pagamento com retries
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for attempt in range(1, retries + 1):
            try:
                resp = await client.post(base_url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                # para PIX, Asaas retorna 'PENDING' inicial → tratamos como sucesso
                if payment_type == "pix" and data.get("status", "").upper() == "PENDING":
                    data["status"] = "approved"
                return data

            except httpx.HTTPStatusError as e:
                logger.error(f"❌ HTTP {e.response.status_code} Asaas payment attempt {attempt}: {e.response.text}")
                if e.response.status_code in {400, 402, 403}:
                    raise HTTPException(status_code=e.response.status_code, detail="Erro no pagamento Asaas")

            except Exception as e:
                logger.warning(f"⚠️ Erro conexão Asaas attempt {attempt}: {e}")

            await asyncio.sleep(2)

    raise HTTPException(status_code=500, detail="Falha no pagamento Asaas após múltiplas tentativas")


async def get_asaas_payment_status(
    empresa_id: str, 
    transaction_id: str,
    config_repo: Optional[ConfigRepositoryInterface] = None
) -> Optional[Dict[str, Any]]:
    """
    ✅ MIGRADO: Verifica o status de um pagamento no Asaas usando externalReference.
    Agora usa interfaces para evitar imports circulares.
    """
    headers = await get_asaas_headers(empresa_id, config_repo)
    
    # ✅ LAZY LOADING: Buscar configurações
    if config_repo is None:
        from ...dependencies import get_config_repository
        config_repo = get_config_repository()
    
    config = await config_repo.get_empresa_config(empresa_id)
    use_sandbox = config.get("use_sandbox", True)
    
    base_url = (
        "https://sandbox.asaas.com/api/v3/payments"
        if use_sandbox else
        "https://api.asaas.com/v3/payments"
    )
    url = f"{base_url}?externalReference={transaction_id}"

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json().get("data", [])
            return data[0] if data else None
        except Exception as e:
            logger.error(f"❌ Erro ao buscar status Asaas: {e}")
            raise HTTPException(status_code=500, detail="Erro ao buscar status Asaas")


async def create_asaas_refund(
    empresa_id: str, 
    transaction_id: str,
    config_repo: Optional[ConfigRepositoryInterface] = None
) -> Dict[str, Any]:
    """
    ✅ MIGRADO: Solicita estorno (refund) de um pagamento aprovado na Asaas.
    POST /payments/{transaction_id}/refund
    Agora usa interfaces para evitar imports circulares.
    """
    # ✅ LAZY LOADING: Dependency injection
    if config_repo is None:
        from ...dependencies import get_config_repository
        config_repo = get_config_repository()

    # ✅ USANDO INTERFACE
    config = await config_repo.get_empresa_config(empresa_id)
    if not config:
        logger.error(f"❌ Configuração da empresa {empresa_id} não encontrada")
        raise HTTPException(status_code=400, detail="Configuração da empresa não encontrada.")

    api_key = config.get("asaas_api_key")
    if not api_key:
        logger.error(f"❌ Asaas API key não encontrada para refund empresa {empresa_id}")
        raise HTTPException(status_code=400, detail="Asaas API key não configurada para refund.")

    use_sandbox = config.get("use_sandbox", True)
    base_url = (
        "https://sandbox.asaas.com/api/v3" if use_sandbox else "https://api.asaas.com/v3"
    )
    url = f"{base_url}/payments/{transaction_id}/refund"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json"
    }

    logger.info(f"🔄 [create_asaas_refund] solicitando estorno Asaas: POST {url}")
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            resp = await client.post(url, headers=headers)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ HTTP {e.response.status_code} refund Asaas: {e.response.text}")
            raise HTTPException(status_code=e.response.status_code, detail="Erro no estorno Asaas")
        except Exception as e:
            logger.error(f"❌ Erro inesperado refund Asaas: {e!r}")
            raise HTTPException(status_code=500, detail="Erro inesperado no estorno Asaas")

    data = resp.json()
    status = data.get("status", "").lower()
    logger.info(f"✅ [create_asaas_refund] status Asaas para {transaction_id}: {status}")
    return {"status": status, **data}


async def validate_asaas_pix_key(
    empresa_id: str, 
    chave_pix: str,
    config_repo: Optional[ConfigRepositoryInterface] = None
) -> None:
    """
    ✅ MIGRADO: Lança HTTPException(400) se a chave_pix não estiver cadastrada no Asaas.
    Agora usa interfaces para evitar imports circulares.
    """
    keys = await list_asaas_pix_keys(empresa_id, config_repo)
    if not any(k.get("key") == chave_pix for k in keys):
        raise HTTPException(
            status_code=400,
            detail=f"Chave Pix '{chave_pix}' não cadastrada no Asaas. Cadastre-a no painel."
        )


async def get_asaas_pix_qr_code(
    empresa_id: str,
    payment_id: str,
    config_repo: Optional[ConfigRepositoryInterface] = None
) -> Dict[str, Any]:
    """
    ✅ MIGRADO: Busca o QR-Code (base64 + copia e cola) de uma cobrança Pix no Asaas.
    Endpoint: GET /v3/payments/{paymentId}/pixQrCode
    Agora usa interfaces para evitar imports circulares.
    """
    headers = await get_asaas_headers(empresa_id, config_repo)
    
    # ✅ LAZY LOADING: Buscar configurações
    if config_repo is None:
        from ...dependencies import get_config_repository
        config_repo = get_config_repository()
    
    config = await config_repo.get_empresa_config(empresa_id)
    use_sandbox = config.get("use_sandbox", True)
    
    base = "https://sandbox.asaas.com/api/v3" if use_sandbox else "https://api.asaas.com/v3"
    url = f"{base}/payments/{payment_id}/pixQrCode"

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Pix QRCode Asaas HTTP {e.response.status_code}: {e.response.text}")
            raise HTTPException(
                status_code=502,
                detail="Erro ao buscar QR-Code Pix no Asaas."
            )

    data = resp.json()
    # O Asaas agora retorna os campos no root, não dentro de "qrCode"
    success = data.get("success", False)
    encoded = data.get("encodedImage")
    payload = data.get("payload")
    expiration = data.get("expirationDate") or data.get("expirationDateTime")

    if success and encoded:
        # Opcional: converta expiration para ISO 8601, se quiser
        expiration_iso = expiration.replace(" ", "T") if expiration else None

        return {
            "qr_code_base64": encoded,
            "pix_link":       payload,
            "expiration":     expiration_iso
        }

    # Ainda não gerado
    return {
        "qr_code_base64": None,
        "pix_link":       None,
        "expiration":     None
    }


# ========== CLASSE WRAPPER PARA INTERFACE ==========

class AsaasGateway:
    """
    ✅ NOVO: Classe wrapper que implementa AsaasGatewayInterface
    Permite uso direto das funções via dependency injection
    """
    
    def __init__(
        self,
        config_repo: Optional[ConfigRepositoryInterface] = None,
        asaas_customer_repo: Optional[AsaasCustomerInterface] = None
    ):
        # ✅ LAZY LOADING nos constructors também
        if config_repo is None:
            from ...dependencies import get_config_repository
            config_repo = get_config_repository()
        if asaas_customer_repo is None:
            from ...dependencies import get_asaas_customer_repository
            asaas_customer_repo = get_asaas_customer_repository()
            
        self.config_repo = config_repo
        self.asaas_customer_repo = asaas_customer_repo
    
    async def create_payment(
        self, 
        empresa_id: str, 
        amount: float, 
        payment_type: str, 
        transaction_id: str,
        customer_data: Dict[str, Any],
        **kwargs
    ) -> Dict[str, Any]:
        """Implementa AsaasGatewayInterface.create_payment"""
        return await create_asaas_payment(
            empresa_id,
            amount,
            payment_type,
            transaction_id,
            customer_data,
            config_repo=self.config_repo,
            asaas_customer_repo=self.asaas_customer_repo,
            **kwargs
        )
    
    async def create_refund(self, empresa_id: str, transaction_id: str) -> Dict[str, Any]:
        """Implementa AsaasGatewayInterface.create_refund"""
        return await create_asaas_refund(
            empresa_id,
            transaction_id,
            config_repo=self.config_repo
        )
    
    async def tokenize_card(self, empresa_id: str, card_data: Dict[str, Any]) -> str:
        """Implementa AsaasGatewayInterface.tokenize_card"""
        return await tokenize_asaas_card(
            empresa_id,
            card_data,
            config_repo=self.config_repo
        )
    
    async def get_payment_status(self, empresa_id: str, transaction_id: str) -> Optional[Dict[str, Any]]:
        """Implementa AsaasGatewayInterface.get_payment_status"""
        return await get_asaas_payment_status(
            empresa_id,
            transaction_id,
            config_repo=self.config_repo
        )
    
    async def get_pix_qr_code(self, empresa_id: str, payment_id: str) -> Dict[str, Any]:
        """Implementa AsaasGatewayInterface.get_pix_qr_code"""
        return await get_asaas_pix_qr_code(
            empresa_id,
            payment_id,
            config_repo=self.config_repo
        )
    
    async def list_pix_keys(self, empresa_id: str) -> list[Dict[str, Any]]:
        """Implementa AsaasGatewayInterface.list_pix_keys"""
        return await list_asaas_pix_keys(
            empresa_id,
            config_repo=self.config_repo
        )
    
    async def validate_pix_key(self, empresa_id: str, chave_pix: str) -> None:
        """Implementa AsaasGatewayInterface.validate_pix_key"""
        return await validate_asaas_pix_key(
            empresa_id,
            chave_pix,
            config_repo=self.config_repo
        )


# ========== FUNÇÃO PARA DEPENDENCY INJECTION ==========

def get_asaas_gateway_instance() -> AsaasGateway:
    """
    ✅ NOVO: Função para criar instância do AsaasGateway
    Pode ser usada nos dependencies.py
    """
    return AsaasGateway()


# ========== BACKWARD COMPATIBILITY ==========
# Mantém as funções originais para compatibilidade, mas agora elas usam interfaces

async def create_asaas_payment_legacy(
    empresa_id: str,
    amount: float,
    payment_type: str,
    transaction_id: str,
    customer_data: Dict[str, Any],
    **kwargs
) -> Dict[str, Any]:
    """
    ⚠️ DEPRECATED: Use create_asaas_payment com dependency injection
    Mantido apenas para compatibilidade
    """
    logger.warning("⚠️ Usando função legacy create_asaas_payment_legacy. Migre para a nova versão com interfaces.")
    return await create_asaas_payment(empresa_id, amount, payment_type, transaction_id, customer_data, **kwargs)


# ========== EXPORTS ==========

__all__ = [
    # Funções principais (migradas)
    "tokenize_asaas_card",
    "list_asaas_pix_keys",
    "create_asaas_payment",
    "get_asaas_payment_status",
    "create_asaas_refund",
    "get_asaas_pix_qr_code",
    "validate_asaas_pix_key",
    "get_asaas_headers",
    
    # Classe wrapper
    "AsaasGateway",
    "get_asaas_gateway_instance",
    
    # Legacy (deprecated)
    "create_asaas_payment_legacy",
]