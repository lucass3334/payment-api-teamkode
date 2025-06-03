# payment_kode_api/app/api/routes/webhooks.py

from fastapi import APIRouter, HTTPException, Request, Depends
import asyncio
from payment_kode_api.app.utilities.logging_config import logger

# ✅ NOVO: Imports das interfaces (SEM imports circulares)
from ...interfaces import (
    PaymentRepositoryInterface,
    WebhookServiceInterface,
    EmpresaRepositoryInterface,
)

# ✅ NOVO: Dependency injection
from ...dependencies import (
    get_payment_repository,
    get_webhook_service,
    get_empresa_repository,
)

router = APIRouter()


@router.post("/webhook/pix")
async def pix_webhook(
    request: Request,
    # ✅ NOVO: Dependency injection das interfaces
    payment_repo: PaymentRepositoryInterface = Depends(get_payment_repository),
    webhook_service: WebhookServiceInterface = Depends(get_webhook_service),
    empresa_repo: EmpresaRepositoryInterface = Depends(get_empresa_repository)
):
    """
    Webhook genérico para notificações de pagamentos via Pix.
    Suporta múltiplos provedores: Sicredi, Rede e Asaas.
    """
    try:
        payload = await request.json()
        logger.info(f"📩 Webhook Pix recebido: {payload}")

        provedor = identificar_provedor(payload)
        logger.info(f"📡 Provedor identificado: {provedor}")

        # Define lista de transações e empresa_id inicial
        empresa_id = None
        if provedor == "sicredi":
            transactions = payload.get("pix", [])
            if not transactions:
                raise HTTPException(status_code=400, detail="Payload Sicredi inválido.")
            chave_pix = transactions[0].get("chave")
            if not chave_pix:
                raise HTTPException(status_code=400, detail="Chave Pix ausente no payload.")
            
            # ✅ USANDO INTERFACE
            empresa_data = await empresa_repo.get_empresa_by_chave_pix(chave_pix)
            if not empresa_data or not empresa_data.get("empresa_id"):
                raise HTTPException(status_code=400, detail="Empresa não encontrada para a chave Pix.")
            empresa_id = empresa_data["empresa_id"]

        elif provedor == "asaas":
            payment = payload.get("payment")
            if not isinstance(payment, dict):
                raise HTTPException(status_code=400, detail="Payload Asaas inválido.")
            transactions = [payment]
            # empresa_id será buscado pelo txid ao processar

        elif provedor == "rede":
            # Rede envia o JSON diretamente
            transactions = [payload]
            # empresa_id será buscado pelo txid ao processar

        else:
            raise HTTPException(status_code=400, detail="Provedor de webhook não suportado.")

        # Processa em background
        asyncio.create_task(process_pix_webhook(
            transactions, 
            provedor, 
            empresa_id,
            payment_repo,
            webhook_service
        ))
        return {"status": "success", "message": f"Webhook {provedor} recebido com sucesso"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro inesperado ao processar webhook Pix: {e}")
        raise HTTPException(status_code=500, detail="Erro ao processar webhook Pix")


async def process_pix_webhook(
    transactions: list, 
    provedor: str, 
    empresa_id: str,
    payment_repo: PaymentRepositoryInterface,
    webhook_service: WebhookServiceInterface
):
    """
    Processa notificações Pix de diferentes provedores em background.
    Atualiza o status do pagamento e dispara o webhook externo configurado.
    ✅ ATUALIZADO: Agora usa interfaces para operações de banco
    """
    try:
        for trx in transactions:
            # Extrai txid e status conforme provedor
            if provedor == "sicredi":
                txid = trx.get("txid")
                status = trx.get("status")
            elif provedor == "asaas":
                txid = trx.get("id")
                status = trx.get("status")
                if not empresa_id:
                    # Recupera empresa_id pelo pagamento já salvo
                    # ✅ USANDO INTERFACE
                    payment = await payment_repo.get_payment_by_txid(txid)
                    empresa_id = payment.get("empresa_id") if payment else None
            elif provedor == "rede":
                txid = trx.get("externalReference") or trx.get("reference")
                status = trx.get("status")
                if not empresa_id:
                    # ✅ USANDO INTERFACE
                    payment = await payment_repo.get_payment_by_txid(txid)
                    empresa_id = payment.get("empresa_id") if payment else None
            else:
                continue  # Não deve ocorrer

            if not txid or not status or not empresa_id:
                logger.warning(f"⚠️ Dados insuficientes ({provedor}): {trx}")
                continue

            # Mapear status conforme provedor
            mapped_status = map_provider_status_to_internal(status, provedor)

            # Atualiza status no banco - ✅ USANDO INTERFACE
            await payment_repo.update_payment_status_by_txid(
                txid=txid,
                empresa_id=empresa_id,
                status=mapped_status
            )
            logger.info(f"✅ Pagamento {txid} atualizado para {mapped_status} (empresa {empresa_id}, provedor {provedor})")

            # Dispara webhook externo se configurado - ✅ USANDO INTERFACE
            payment = await payment_repo.get_payment_by_txid(txid)
            if payment and payment.get("webhook_url"):
                await webhook_service.notify_user_webhook(payment["webhook_url"], {
                    "transaction_id": payment.get("transaction_id", txid),
                    "status": mapped_status,
                    "provedor": provedor,
                    "txid": txid,
                    "payload": trx,
                    "data_marketing": payment.get("data_marketing")
                })

    except Exception as e:
        logger.error(f"❌ Erro no processamento do webhook ({provedor}): {e}")


def identificar_provedor(payload: dict) -> str:
    """
    Identifica o provedor de pagamento com base na estrutura do payload.
    """
    if "pix" in payload and isinstance(payload["pix"], list):
        return "sicredi"
    if "payment" in payload and isinstance(payload["payment"], dict):
        return "asaas"
    if "externalReference" in payload or "reference" in payload:
        return "rede"
    return "unknown"


def map_provider_status_to_internal(status: str, provider: str) -> str:
    """
    Mapeia status dos provedores para status interno padronizado.
    """
    status_upper = status.upper()
    
    if provider == "sicredi":
        mapping = {
            "CONCLUIDA": "approved",
            "ATIVA": "pending",
            "PENDENTE": "pending",
            "REMOVIDA_PELO_USUARIO_RECEBEDOR": "canceled",
            "REMOVIDA_POR_ERRO": "failed",
            "EXPIRADA": "failed"
        }
        return mapping.get(status_upper, status.lower())
    
    elif provider == "asaas":
        mapping = {
            "PENDING": "pending",
            "RECEIVED": "approved",
            "CONFIRMED": "approved",
            "OVERDUE": "failed",
            "REFUNDED": "canceled",
            "REFUNDED_PARTIAL": "canceled",
            "CHARGEBACK_REQUESTED": "failed",
            "CHARGEBACK_DISPUTE": "failed",
            "AWAITING_CHARGEBACK_REVERSAL": "failed"
        }
        return mapping.get(status_upper, status.lower())
    
    elif provider == "rede":
        mapping = {
            "APPROVED": "approved",
            "DENIED": "failed", 
            "PENDING": "pending",
            "CANCELLED": "canceled",
            "REFUNDED": "canceled",
            "CAPTURED": "approved",
            "AUTHORIZED": "pending"
        }
        return mapping.get(status_upper, status.lower())
    
    else:
        # Fallback para status desconhecidos
        return status.lower()


@router.post("/webhook/credit-card")
async def credit_card_webhook(
    request: Request,
    # ✅ NOVO: Dependency injection das interfaces
    payment_repo: PaymentRepositoryInterface = Depends(get_payment_repository),
    webhook_service: WebhookServiceInterface = Depends(get_webhook_service)
):
    """
    Webhook para notificações de pagamentos via cartão de crédito.
    Suporta múltiplos provedores: Rede e Asaas.
    """
    try:
        payload = await request.json()
        logger.info(f"📩 Webhook Cartão recebido: {payload}")

        # Identificar provedor
        provedor = identificar_provedor_cartao(payload)
        logger.info(f"📡 Provedor de cartão identificado: {provedor}")

        if provedor == "unknown":
            raise HTTPException(status_code=400, detail="Provedor de webhook de cartão não identificado.")

        # Extrair dados da transação
        if provedor == "rede":
            transaction_id = payload.get("reference")
            tid = payload.get("tid") 
            status = payload.get("returnCode", "")
            return_message = payload.get("returnMessage", "")
            
            # Mapear status da Rede (código numérico)
            if status == "00":
                mapped_status = "approved"
            elif status in ["05", "51", "54", "61", "62", "65"]:
                mapped_status = "failed"
            else:
                mapped_status = "failed"

        elif provedor == "asaas":
            payment_data = payload.get("payment", {})
            transaction_id = payment_data.get("externalReference")
            status = payment_data.get("status", "")
            mapped_status = map_provider_status_to_internal(status, "asaas")

        else:
            raise HTTPException(status_code=400, detail=f"Provedor {provedor} não suportado para cartão.")

        if not transaction_id:
            raise HTTPException(status_code=400, detail="Transaction ID não encontrado no payload.")

        # Buscar empresa_id pelo pagamento - ✅ USANDO INTERFACE
        payment = await payment_repo.get_payment(transaction_id, None)  # Busca em todas as empresas
        if not payment:
            logger.warning(f"⚠️ Pagamento não encontrado para transaction_id: {transaction_id}")
            raise HTTPException(status_code=404, detail="Pagamento não encontrado.")

        empresa_id = payment["empresa_id"]

        # Preparar dados extras para atualização
        extra_data = {}
        if provedor == "rede":
            extra_data.update({
                "rede_tid": tid,
                "return_code": status,
                "return_message": return_message
            })

        # Atualizar status no banco - ✅ USANDO INTERFACE
        await payment_repo.update_payment_status(
            transaction_id=transaction_id,
            empresa_id=empresa_id,
            status=mapped_status,
            extra_data=extra_data
        )

        logger.info(f"✅ Pagamento cartão {transaction_id} atualizado para {mapped_status} (provedor {provedor})")

        # Disparar webhook externo se configurado - ✅ USANDO INTERFACE
        if payment.get("webhook_url"):
            webhook_payload = {
                "transaction_id": transaction_id,
                "status": mapped_status,
                "provedor": provedor,
                "payload": payload,
                "data_marketing": payment.get("data_marketing")
            }
            
            # Adicionar dados específicos do provedor
            if provedor == "rede":
                webhook_payload.update({
                    "rede_tid": tid,
                    "return_code": status,
                    "return_message": return_message
                })

            await webhook_service.notify_user_webhook(payment["webhook_url"], webhook_payload)

        return {"status": "success", "message": f"Webhook cartão {provedor} processado com sucesso"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro inesperado ao processar webhook de cartão: {e}")
        raise HTTPException(status_code=500, detail="Erro ao processar webhook de cartão")


def identificar_provedor_cartao(payload: dict) -> str:
    """
    Identifica o provedor de cartão com base na estrutura do payload.
    """
    # Rede geralmente tem 'tid', 'reference', 'returnCode'
    if "tid" in payload and "reference" in payload and "returnCode" in payload:
        return "rede"
    
    # Asaas tem estrutura 'payment' com dados do pagamento
    if "payment" in payload and isinstance(payload["payment"], dict):
        payment_data = payload["payment"]
        if "billingType" in payment_data and payment_data.get("billingType") == "CREDIT_CARD":
            return "asaas"
    
    # Fallback para estruturas que podem indicar cartão
    if "externalReference" in payload and "status" in payload:
        return "asaas"  # Assumir Asaas como fallback
    
    return "unknown"


@router.post("/webhook/generic")
async def generic_webhook(
    request: Request,
    # ✅ NOVO: Dependency injection das interfaces
    payment_repo: PaymentRepositoryInterface = Depends(get_payment_repository),
    webhook_service: WebhookServiceInterface = Depends(get_webhook_service)
):
    """
    Webhook genérico que tenta identificar automaticamente o tipo e provedor.
    Útil quando não se sabe exatamente qual webhook será recebido.
    """
    try:
        payload = await request.json()
        logger.info(f"📩 Webhook genérico recebido: {payload}")

        # Tentar identificar se é PIX ou cartão
        if is_pix_webhook(payload):
            # Redirecionar para processamento PIX
            return await pix_webhook(request, payment_repo, webhook_service)
        elif is_credit_card_webhook(payload):
            # Redirecionar para processamento cartão
            return await credit_card_webhook(request, payment_repo, webhook_service)
        else:
            logger.warning(f"⚠️ Tipo de webhook não identificado: {payload}")
            return {"status": "warning", "message": "Tipo de webhook não identificado, mas recebido"}

    except Exception as e:
        logger.error(f"❌ Erro no webhook genérico: {e}")
        raise HTTPException(status_code=500, detail="Erro ao processar webhook genérico")


def is_pix_webhook(payload: dict) -> bool:
    """Verifica se o payload parece ser um webhook PIX"""
    # Indicadores de webhook PIX
    pix_indicators = [
        "pix" in payload,  # Sicredi
        "pixKey" in str(payload),  # Asaas PIX
        "billingType" in str(payload) and "PIX" in str(payload),  # Asaas PIX
        "txid" in payload,  # Identificador PIX
    ]
    return any(pix_indicators)


def is_credit_card_webhook(payload: dict) -> bool:
    """Verifica se o payload parece ser um webhook de cartão"""
    # Indicadores de webhook cartão
    card_indicators = [
        "tid" in payload,  # Rede
        "returnCode" in payload,  # Rede
        "billingType" in str(payload) and "CREDIT_CARD" in str(payload),  # Asaas
        "authorizationCode" in payload,  # Códigos de autorização
    ]
    return any(card_indicators)


@router.get("/webhook/health")
async def webhook_health():
    """
    Endpoint de health check para verificar se o serviço de webhooks está funcionando.
    """
    return {
        "status": "healthy",
        "message": "Serviço de webhooks operacional",
        "supported_providers": {
            "pix": ["sicredi", "asaas"],
            "credit_card": ["rede", "asaas"]
        },
        "endpoints": {
            "pix": "/webhook/pix",
            "credit_card": "/webhook/credit-card", 
            "generic": "/webhook/generic"
        }
    }


@router.post("/webhook/test")
async def webhook_test(
    request: Request,
    webhook_service: WebhookServiceInterface = Depends(get_webhook_service)
):
    """
    Endpoint de teste para validar o funcionamento dos webhooks.
    Útil para desenvolvimento e debugging.
    """
    try:
        payload = await request.json()
        
        # Log do payload recebido
        logger.info(f"🧪 Webhook de teste recebido: {payload}")
        
        # Identificar tipo e provedor
        provider_type = "unknown"
        provider_name = "unknown"
        
        if is_pix_webhook(payload):
            provider_type = "pix"
            provider_name = identificar_provedor(payload)
        elif is_credit_card_webhook(payload):
            provider_type = "credit_card"
            provider_name = identificar_provedor_cartao(payload)
        
        # Testar notificação webhook se URL fornecida
        test_webhook_url = payload.get("test_webhook_url")
        webhook_sent = False
        
        if test_webhook_url:
            try:
                await webhook_service.notify_user_webhook(test_webhook_url, {
                    "test": True,
                    "message": "Webhook de teste enviado com sucesso",
                    "original_payload": payload
                })
                webhook_sent = True
            except Exception as e:
                logger.warning(f"⚠️ Falha ao enviar webhook de teste: {e}")
        
        return {
            "status": "success",
            "message": "Webhook de teste processado",
            "analysis": {
                "provider_type": provider_type,
                "provider_name": provider_name,
                "is_pix": is_pix_webhook(payload),
                "is_credit_card": is_credit_card_webhook(payload),
                "webhook_sent": webhook_sent
            },
            "payload_received": payload
        }
        
    except Exception as e:
        logger.error(f"❌ Erro no webhook de teste: {e}")
        return {
            "status": "error",
            "message": f"Erro ao processar webhook de teste: {str(e)}"
        }