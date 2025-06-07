# payment_kode_api/app/services/gateways/rede_client.py

import httpx
from base64 import b64encode
from typing import Any, Dict, Optional

from fastapi import HTTPException

from payment_kode_api.app.core.config import settings
from payment_kode_api.app.services.gateways.payment_payload_mapper import map_to_rede_payload
from payment_kode_api.app.utilities.logging_config import logger

# ✅ MANTÉM: Imports das interfaces (SEM imports circulares)
from ...interfaces import (
    ConfigRepositoryInterface,
    PaymentRepositoryInterface,
)

TIMEOUT = 15.0

# ─── URL BASE CORRIGIDAS ────────────────────────────────────────────────
# 🔧 CORRIGIDO: URLs corretas da e.Rede conforme documentação oficial
rede_env = getattr(settings, 'REDE_AMBIENT', 'production')
if rede_env.lower() == "sandbox":
    # ✅ URL CORRETA: Sandbox da e.Rede
    ECOMM_BASE_URL = "https://api.useredecloud.com.br/erede"
else:
    # ✅ URL CORRETA: Produção da e.Rede
    ECOMM_BASE_URL = "https://api.userede.com.br/erede"

CARD_URL         = f"{ECOMM_BASE_URL}/card"
TRANSACTIONS_URL = f"{ECOMM_BASE_URL}/transactions"

# 🔧 NOVO: Log das URLs para debugging
logger.info(f"🔧 Rede configurada - Ambiente: {rede_env}")
logger.info(f"📍 Base URL: {ECOMM_BASE_URL}")
logger.info(f"📍 Transações: {TRANSACTIONS_URL}")
logger.info(f"📍 Cartões: {CARD_URL}")


async def get_rede_headers(
    empresa_id: str,
    config_repo: Optional[ConfigRepositoryInterface] = None
) -> Dict[str, str]:
    """
    ✅ MIGRADO: Retorna headers com Basic Auth (PV + Integration Key).
    🔧 MELHORADO: Headers mais completos e logs de debugging.
    """
    # ✅ LAZY LOADING: Dependency injection
    if config_repo is None:
        from ...dependencies import get_config_repository
        config_repo = get_config_repository()

    # ✅ USANDO INTERFACE
    config = await config_repo.get_empresa_config(empresa_id)
    if not config:
        raise HTTPException(
            status_code=401,
            detail=f"Configuração da empresa {empresa_id} não encontrada"
        )

    pv = config.get("rede_pv")
    api_key = config.get("rede_api_key")
    if not pv or not api_key:
        raise HTTPException(
            status_code=401,
            detail=f"Credenciais da Rede não encontradas para empresa {empresa_id}"
        )

    auth = b64encode(f"{pv}:{api_key}".encode()).decode()
    
    # 🔧 MELHORADO: Headers mais completos conforme documentação da Rede
    headers = {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "PaymentKode-API/1.0"
    }
    
    logger.debug(f"🔐 Headers Rede preparados para empresa {empresa_id}")
    return headers


async def tokenize_rede_card(
    empresa_id: str, 
    card_data: Dict[str, Any],
    config_repo: Optional[ConfigRepositoryInterface] = None
) -> str:
    """
    ✅ MIGRADO: Tokeniza o cartão na Rede.
    🔧 CORRIGIDO: Usando URL correta e logs melhorados.
    """
    headers = await get_rede_headers(empresa_id, config_repo)
    payload = {
        "number":          card_data["card_number"],
        "expirationMonth": card_data["expiration_month"],
        "expirationYear":  card_data["expiration_year"],
        "securityCode":    card_data["security_code"],
        "holderName":      card_data["cardholder_name"],
    }
    
    logger.info(f"🔐 Tokenizando cartão na Rede: {CARD_URL}")
    logger.debug(f"📦 Payload tokenização: {payload}")
    
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(CARD_URL, json=payload, headers=headers)
            
            # 🔧 NOVO: Log da resposta para debugging
            logger.info(f"📥 Tokenização Rede Status: {resp.status_code}")
            
            resp.raise_for_status()
            result = resp.json()
            token = result.get("cardToken")
            
            if token:
                logger.info(f"✅ Cartão tokenizado com sucesso na Rede")
                return token
            else:
                logger.error(f"❌ Token não retornado pela Rede: {result}")
                raise HTTPException(status_code=502, detail="Token não retornado pela Rede")
                
    except httpx.HTTPStatusError as e:
        logger.error(f"❌ Rede tokenização HTTP {e.response.status_code}: {e.response.text}")
        
        # 🔧 NOVO: Tratamento específico para erro 405
        if e.response.status_code == 405:
            logger.error(f"❌ ERRO 405 na tokenização: Endpoint incorreto! URL: {CARD_URL}")
            raise HTTPException(
                status_code=502, 
                detail=f"Endpoint da Rede incorreto para tokenização (405). Ambiente: {rede_env}"
            )
        
        raise HTTPException(status_code=502, detail="Erro ao tokenizar cartão na Rede")
    except Exception as e:
        logger.error(f"❌ Rede tokenização erro: {e}")
        raise HTTPException(status_code=502, detail="Erro de conexão ao tokenizar cartão na Rede")


async def create_rede_payment(
    empresa_id: str,
    config_repo: Optional[ConfigRepositoryInterface] = None,
    payment_repo: Optional[PaymentRepositoryInterface] = None,
    **payment_data: Any
) -> Dict[str, Any]:
    """
    ✅ MIGRADO: Autoriza (e captura, se capture=True) uma transação.
    🔧 CORRIGIDO: URLs corretas, logs melhorados e tratamento de erros aprimorado.
    """
    # ✅ LAZY LOADING: Dependency injection
    if config_repo is None:
        from ...dependencies import get_config_repository
        config_repo = get_config_repository()
    if payment_repo is None:
        from ...dependencies import get_payment_repository
        payment_repo = get_payment_repository()

    # 🔧 CORRIGIDO: Usar payment_data diretamente
    payload = map_to_rede_payload(payment_data)
    tokenize = payment_data.get("tokenize", False)

    # ── Se for tokenização on-the-fly
    if "cardToken" not in payload:
        if tokenize:
            token = await tokenize_rede_card(empresa_id, payload, config_repo)
            for field in ("cardNumber","expirationMonth","expirationYear","securityCode","cardHolderName"):
                payload.pop(field, None)
            payload["cardToken"] = token
        else:
            # 🔧 CORRIGIDO: Verificar se campos existem antes de fazer pop
            if "cardNumber" in payload:
                payload["card"] = {
                    "number":          payload.pop("cardNumber"),
                    "expirationMonth": payload.pop("expirationMonth"),
                    "expirationYear":  payload.pop("expirationYear"),
                    "securityCode":    payload.pop("securityCode"),
                    "holderName":      payload.pop("cardHolderName"),
                }

    headers = await get_rede_headers(empresa_id, config_repo)
    
    # 🔧 NOVO: Logs detalhados para debugging
    logger.info(f"🚀 Enviando pagamento à Rede: empresa={empresa_id}")
    logger.info(f"📍 URL: {TRANSACTIONS_URL}")
    logger.info(f"🔧 Ambiente: {rede_env}")
    logger.debug(f"📦 Payload Rede: {payload}")
    logger.debug(f"🔐 Headers: {list(headers.keys())}")

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(TRANSACTIONS_URL, json=payload, headers=headers)
            
            # 🔧 NOVO: Log detalhado da resposta para debugging
            logger.info(f"📥 Rede Response Status: {resp.status_code}")
            logger.debug(f"📥 Rede Response Headers: {dict(resp.headers)}")
            
            # Tentar ler o conteúdo da resposta antes de raise_for_status
            try:
                response_text = resp.text
                logger.debug(f"📥 Rede Response Body (primeiros 500 chars): {response_text[:500]}")
            except:
                logger.warning("⚠️ Não foi possível ler o corpo da resposta")
            
            resp.raise_for_status()
            data = resp.json()
            
            # 🔧 NOVO: RESPONSE HANDLING MELHORADO
            return_code = data.get("returnCode", "")
            return_message = data.get("returnMessage", "")
            tid = data.get("tid")
            authorization_code = data.get("authorizationCode")
            
            logger.info(f"📥 Rede response: code={return_code}, message={return_message}, tid={tid}")
            
            # 🔧 NOVO: Atualizar pagamento no banco com dados da Rede - ✅ USANDO INTERFACE
            transaction_id = payment_data.get("transaction_id")
            if transaction_id and return_code == "00":
                # Salvar dados da Rede no banco
                await payment_repo.update_payment_status(
                    transaction_id=transaction_id,
                    empresa_id=empresa_id,
                    status="approved",
                    extra_data={
                        "rede_tid": tid,
                        "authorization_code": authorization_code,
                        "return_code": return_code,
                        "return_message": return_message
                    }
                )
                logger.info(f"✅ Status do pagamento atualizado no banco: {transaction_id}")
            
            # Retorno estruturado
            if return_code == "00":  # Sucesso
                return {
                    "status": "approved",
                    "transaction_id": transaction_id,
                    "rede_tid": tid,
                    "authorization_code": authorization_code,
                    "return_code": return_code,
                    "return_message": return_message,
                    "raw_response": data
                }
            else:
                # Pagamento recusado
                logger.warning(f"⚠️ Pagamento Rede recusado: {return_code} - {return_message}")
                return {
                    "status": "failed",
                    "transaction_id": transaction_id,
                    "return_code": return_code,
                    "return_message": return_message,
                    "raw_response": data
                }

    except httpx.HTTPStatusError as e:
        code, text = e.response.status_code, e.response.text
        logger.error(f"❌ Rede retornou HTTP {code}: {text}")
        
        # 🔧 NOVO: Tratamento específico para erro 405
        if code == 405:
            logger.error(f"❌ ERRO 405: Endpoint incorreto! URL usada: {TRANSACTIONS_URL}")
            logger.error(f"❌ Ambiente configurado: {rede_env}")
            logger.error(f"❌ Verifique se as credenciais e ambiente estão corretos")
            raise HTTPException(
                status_code=502, 
                detail=f"Endpoint da Rede incorreto (405). Ambiente: {rede_env} | URL: {TRANSACTIONS_URL}"
            )
        
        if code in (400, 402, 403):
            raise HTTPException(status_code=code, detail=f"Pagamento recusado pela Rede: {text}")
        raise HTTPException(status_code=502, detail="Erro no gateway Rede")
    except Exception as e:
        logger.error(f"❌ Erro de conexão com a Rede: {e}")
        raise HTTPException(status_code=502, detail="Erro de conexão ao processar pagamento na Rede")


async def capture_rede_transaction(
    empresa_id: str,
    transaction_id: str,
    amount: Optional[int] = None,
    config_repo: Optional[ConfigRepositoryInterface] = None
) -> Dict[str, Any]:
    """
    ✅ MIGRADO: Confirma (captura) uma autorização prévia.
    Endpoint: PUT /erede/transactions/{transaction_id}
    """
    headers = await get_rede_headers(empresa_id, config_repo)
    url = f"{TRANSACTIONS_URL}/{transaction_id}"
    payload: Dict[str, Any] = {}
    if amount is not None:
        payload["amount"] = amount

    logger.info(f"🔄 Capturando transação Rede: {url}")

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.put(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()

    except httpx.HTTPStatusError as e:
        status, text = e.response.status_code, e.response.text
        logger.error(f"❌ Rede capture HTTP {status}: {text}")
        if status in (400, 403, 404):
            raise HTTPException(
                status_code=status,
                detail=f"Erro ao capturar transação Rede: {text}"
            )
        raise HTTPException(status_code=502, detail="Erro no gateway Rede ao capturar transação")
    except Exception as e:
        logger.error(f"❌ Erro de conexão ao capturar Rede: {e}")
        raise HTTPException(status_code=502, detail="Erro de conexão ao capturar transação na Rede")


async def get_rede_transaction(
    empresa_id: str,
    transaction_id: str,
    config_repo: Optional[ConfigRepositoryInterface] = None
) -> Dict[str, Any]:
    """
    ✅ MIGRADO: Consulta o status de uma transação.
    Endpoint: GET /erede/transactions/{transaction_id}
    """
    headers = await get_rede_headers(empresa_id, config_repo)
    url = f"{TRANSACTIONS_URL}/{transaction_id}"

    logger.info(f"🔍 Consultando transação Rede: {url}")

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.json()

    except httpx.HTTPStatusError as e:
        status, text = e.response.status_code, e.response.text
        logger.error(f"❌ Rede consulta HTTP {status}: {text}")
        raise HTTPException(status_code=status, detail="Erro ao buscar transação na Rede")
    except Exception as e:
        logger.error(f"❌ Erro de conexão ao consultar Rede: {e}")
        raise HTTPException(status_code=502, detail="Erro de conexão ao consultar transação na Rede")


async def create_rede_refund(
    empresa_id: str,
    transaction_id: str,
    amount: Optional[int] = None,
    config_repo: Optional[ConfigRepositoryInterface] = None,
    payment_repo: Optional[PaymentRepositoryInterface] = None
) -> Dict[str, Any]:
    """
    ✅ MIGRADO: Solicita estorno usando TID da Rede (não nosso transaction_id).
    Endpoint: POST /erede/transactions/{rede_tid}/refunds
    """
    # ✅ LAZY LOADING: Dependency injection
    if payment_repo is None:
        from ...dependencies import get_payment_repository
        payment_repo = get_payment_repository()
    if config_repo is None:
        from ...dependencies import get_config_repository
        config_repo = get_config_repository()

    # 🔧 NOVO: Buscar TID da Rede no banco - ✅ USANDO INTERFACE
    payment = await payment_repo.get_payment(transaction_id, empresa_id)
    if not payment:
        raise HTTPException(404, "Pagamento não encontrado")
    
    rede_tid = payment.get("rede_tid")
    if not rede_tid:
        raise HTTPException(400, "TID da Rede não encontrado para este pagamento")
    
    headers = await get_rede_headers(empresa_id, config_repo)
    # 🔧 CORRIGIDO: Usar rede_tid ao invés de transaction_id
    url = f"{TRANSACTIONS_URL}/{rede_tid}/refunds"
    payload: Dict[str, Any] = {}
    if amount is not None:
        payload["amount"] = amount

    try:
        logger.info(f"🔄 Solicitando estorno Rede: POST {url} – payload={payload}")
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            
            # 🔧 NOVO: Verificar código de retorno do estorno
            return_code = data.get("returnCode", "")
            if return_code == "00":
                # Atualizar status no banco - ✅ USANDO INTERFACE
                await payment_repo.update_payment_status(transaction_id, empresa_id, "canceled")
                logger.info(f"✅ Estorno Rede processado com sucesso: {transaction_id}")
                return {"status": "refunded", **data}
            else:
                logger.warning(f"⚠️ Estorno Rede falhou: {return_code} - {data.get('returnMessage')}")
                raise HTTPException(400, f"Estorno Rede falhou: {data.get('returnMessage')}")

    except httpx.HTTPStatusError as e:
        status, text = e.response.status_code, e.response.text
        logger.error(f"❌ Rede estorno HTTP {status}: {text}")
        if status in (400, 402, 403, 404):
            raise HTTPException(status_code=status, detail=f"Erro no estorno Rede: {text}")
        raise HTTPException(status_code=502, detail="Erro no gateway Rede ao processar estorno")
    except Exception as e:
        logger.error(f"❌ Erro de conexão ao estornar na Rede: {e}")
        raise HTTPException(status_code=502, detail="Erro de conexão ao processar estorno na Rede")


# 🆕 NOVA: Função para testar conectividade com a Rede
async def test_rede_connectivity(empresa_id: str) -> Dict[str, Any]:
    """
    🧪 NOVO: Testa a conectividade com a API da Rede.
    Útil para debugging de problemas de endpoint.
    """
    try:
        headers = await get_rede_headers(empresa_id)
        
        # Teste simples fazendo uma requisição GET ou POST mínima
        test_endpoints = [
            {"url": ECOMM_BASE_URL, "method": "GET", "description": "Base URL"},
            {"url": TRANSACTIONS_URL, "method": "GET", "description": "Transactions endpoint"},
        ]
        
        results = []
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            for endpoint in test_endpoints:
                try:
                    if endpoint["method"] == "GET":
                        resp = await client.get(endpoint["url"], headers=headers)
                    else:
                        resp = await client.post(endpoint["url"], headers=headers, json={})
                    
                    results.append({
                        "endpoint": endpoint["description"],
                        "url": endpoint["url"],
                        "status_code": resp.status_code,
                        "status": "success" if resp.status_code < 500 else "warning",
                        "response_size": len(resp.content) if resp.content else 0
                    })
                    
                except Exception as e:
                    results.append({
                        "endpoint": endpoint["description"],
                        "url": endpoint["url"],
                        "status": "error",
                        "error": str(e)
                    })
        
        return {
            "status": "completed",
            "environment": rede_env,
            "base_url": ECOMM_BASE_URL,
            "empresa_id": empresa_id,
            "tests": results,
            "message": f"Teste de conectividade concluído para ambiente {rede_env}"
        }
            
    except Exception as e:
        return {
            "status": "error",
            "environment": rede_env,
            "base_url": ECOMM_BASE_URL,
            "empresa_id": empresa_id,
            "error": str(e),
            "message": "Falha crítica no teste de conectividade"
        }


# ========== CLASSE WRAPPER PARA INTERFACE ==========

class RedeGateway:
    """
    ✅ NOVO: Classe wrapper que implementa RedeGatewayInterface
    Permite uso direto das funções via dependency injection
    """
    
    def __init__(
        self,
        config_repo: Optional[ConfigRepositoryInterface] = None,
        payment_repo: Optional[PaymentRepositoryInterface] = None
    ):
        # ✅ LAZY LOADING nos constructors também
        if config_repo is None:
            from ...dependencies import get_config_repository
            config_repo = get_config_repository()
        if payment_repo is None:
            from ...dependencies import get_payment_repository
            payment_repo = get_payment_repository()
            
        self.config_repo = config_repo
        self.payment_repo = payment_repo
    
    async def create_payment(self, empresa_id: str, **kwargs) -> Dict[str, Any]:
        """Implementa RedeGatewayInterface.create_payment"""
        return await create_rede_payment(
            empresa_id,
            config_repo=self.config_repo,
            payment_repo=self.payment_repo,
            **kwargs
        )
    
    async def create_refund(self, empresa_id: str, transaction_id: str, amount: Optional[int] = None) -> Dict[str, Any]:
        """Implementa RedeGatewayInterface.create_refund"""
        return await create_rede_refund(
            empresa_id,
            transaction_id,
            amount,
            config_repo=self.config_repo,
            payment_repo=self.payment_repo
        )
    
    async def tokenize_card(self, empresa_id: str, card_data: Dict[str, Any]) -> str:
        """Implementa RedeGatewayInterface.tokenize_card"""
        return await tokenize_rede_card(
            empresa_id,
            card_data,
            config_repo=self.config_repo
        )
    
    async def capture_transaction(self, empresa_id: str, transaction_id: str, amount: Optional[int] = None) -> Dict[str, Any]:
        """Implementa RedeGatewayInterface.capture_transaction"""
        return await capture_rede_transaction(
            empresa_id,
            transaction_id,
            amount,
            config_repo=self.config_repo
        )
    
    async def get_transaction(self, empresa_id: str, transaction_id: str) -> Dict[str, Any]:
        """Implementa RedeGatewayInterface.get_transaction"""
        return await get_rede_transaction(
            empresa_id,
            transaction_id,
            config_repo=self.config_repo
        )
    
    async def test_connectivity(self, empresa_id: str) -> Dict[str, Any]:
        """🆕 NOVO: Testa conectividade"""
        return await test_rede_connectivity(empresa_id)


# ========== FUNÇÃO PARA DEPENDENCY INJECTION ==========

def get_rede_gateway_instance() -> RedeGateway:
    """
    ✅ NOVO: Função para criar instância do RedeGateway
    Pode ser usada nos dependencies.py
    """
    return RedeGateway()


# ========== BACKWARD COMPATIBILITY ==========
# Mantém as funções originais para compatibilidade, mas agora elas usam interfaces

async def create_rede_payment_legacy(empresa_id: str, **payment_data: Any) -> Dict[str, Any]:
    """
    ⚠️ DEPRECATED: Use create_rede_payment com dependency injection
    Mantido apenas para compatibilidade
    """
    logger.warning("⚠️ Usando função legacy create_rede_payment_legacy. Migre para a nova versão com interfaces.")
    return await create_rede_payment(empresa_id, **payment_data)


# ========== EXPORTS ==========

__all__ = [
    # Funções principais (migradas)
    "create_rede_payment",
    "tokenize_rede_card",
    "capture_rede_transaction",
    "get_rede_transaction", 
    "create_rede_refund",
    "get_rede_headers",
    "test_rede_connectivity",  # 🆕 NOVA
    
    # Classe wrapper
    "RedeGateway",
    "get_rede_gateway_instance",
    
    # Legacy (deprecated)
    "create_rede_payment_legacy",
]