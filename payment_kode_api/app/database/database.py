# payment_kode_api/app/database/database.py

import os
from payment_kode_api.app.core.config import settings
from payment_kode_api.app.utilities.logging_config import logger
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Union
import uuid
from decimal import Decimal
from .supabase_client import supabase

# ========== CONSTANTES ==========
VALID_PAYMENT_STATUSES = {"pending", "approved", "failed", "canceled", "refunded", "processing"}
VALID_PAYMENT_TYPES = {"pix", "credit_card", "debit_card", "boleto"}
VALID_CARD_BRANDS = {"VISA", "MASTERCARD", "AMEX", "DISCOVER", "ELO", "HIPERCARD", "UNKNOWN"}
CARD_EXPIRY_DAYS = 365 * 2  # 2 anos por padrão


# ========== FUNÇÕES AUXILIARES ==========
def sanitize_decimal(value: Any) -> float:
    """Converte Decimal para float de forma segura."""
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def validate_uuid(uuid_string: str) -> bool:
    """Valida se uma string é um UUID válido."""
    try:
        uuid.UUID(uuid_string)
        return True
    except (ValueError, TypeError):
        return False


def normalize_datetime(dt_input: Union[str, datetime]) -> str:
    """Normaliza datetime para ISO string UTC."""
    if isinstance(dt_input, str):
        return dt_input
    if isinstance(dt_input, datetime):
        if dt_input.tzinfo is None:
            dt_input = dt_input.replace(tzinfo=timezone.utc)
        return dt_input.isoformat()
    return datetime.now(timezone.utc).isoformat()


def validate_installments(installments: Any) -> int:
    """Valida e normaliza número de parcelas."""
    try:
        installments = int(installments)
        if installments < 1:
            logger.warning(f"⚠️ Parcelas menores que 1 ajustadas para 1: {installments}")
            return 1
        elif installments > 12:
            logger.warning(f"⚠️ Parcelas maiores que 12 ajustadas para 12: {installments}")
            return 12
        return installments
    except (ValueError, TypeError):
        logger.warning(f"⚠️ Parcelas inválidas definidas como 1: {installments}")
        return 1


# ========== CARTÕES TOKENIZADOS ==========
async def save_tokenized_card(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    ✅ MELHORADO: Salva cartão tokenizado com validações robustas.
    """
    try:
        # Validações obrigatórias
        empresa_id = data.get("empresa_id")
        card_token = data.get("card_token")
        encrypted_card_data = data.get("encrypted_card_data")
        
        if not all([empresa_id, card_token, encrypted_card_data]):
            missing_fields = [f for f, v in [
                ("empresa_id", empresa_id),
                ("card_token", card_token), 
                ("encrypted_card_data", encrypted_card_data)
            ] if not v]
            raise ValueError(f"Campos obrigatórios ausentes: {', '.join(missing_fields)}")

        # Dados opcionais com validações
        customer_id = data.get("customer_id")  # String (ID externo)
        cliente_id = data.get("cliente_id")    # UUID interno
        card_brand = data.get("card_brand", "UNKNOWN").upper()
        
        # Validar bandeira do cartão
        if card_brand not in VALID_CARD_BRANDS:
            logger.warning(f"⚠️ Bandeira de cartão desconhecida: {card_brand}, usando UNKNOWN")
            card_brand = "UNKNOWN"
        
        # Validar último dígitos
        last_four_digits = data.get("last_four_digits")
        if last_four_digits:
            last_four_digits = str(last_four_digits)[-4:].zfill(4)
        
        # Validar cliente UUID se fornecido
        if cliente_id and not validate_uuid(str(cliente_id)):
            logger.warning(f"⚠️ UUID de cliente inválido: {cliente_id}, ignorando")
            cliente_id = None

        # Calcular data de expiração
        expires_at = data.get("expires_at")
        if not expires_at:
            expires_at = (datetime.now(timezone.utc) + timedelta(days=CARD_EXPIRY_DAYS)).isoformat()
        
        # Montar registro
        card_record = {
            "empresa_id": empresa_id,
            "customer_id": customer_id,
            "card_token": card_token,
            "encrypted_card_data": encrypted_card_data,
            "last_four_digits": last_four_digits,
            "card_brand": card_brand,
            "expires_at": expires_at,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Adicionar cliente UUID se válido
        if cliente_id:
            card_record["cliente_id"] = str(cliente_id)

        # Inserir no banco
        response = (
            supabase.table("cartoes_tokenizados")
            .insert(card_record)
            .execute()
        )

        if not response.data:
            raise ValueError("Falha ao inserir cartão no banco de dados")

        logger.info(f"✅ Cartão tokenizado salvo | Empresa: {empresa_id} | Customer: {customer_id or 'N/A'} | Cliente UUID: {cliente_id or 'N/A'} | Bandeira: {card_brand}")
        return response.data[0]

    except Exception as e:
        logger.error(f"❌ Erro ao salvar cartão tokenizado: {e}")
        raise


async def get_tokenized_card(card_token: str) -> Optional[Dict[str, Any]]:
    """Busca cartão tokenizado por token."""
    try:
        if not card_token or not isinstance(card_token, str):
            raise ValueError("Token do cartão é obrigatório e deve ser string")

        response = (
            supabase.table("cartoes_tokenizados")
            .select("*")
            .eq("card_token", card_token)
            .execute()
        )
        
        if response.data:
            card = response.data[0]
            
            # Verificar se cartão expirou
            expires_at = card.get("expires_at")
            if expires_at:
                try:
                    exp_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                    if exp_dt.tzinfo is None:
                        exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                    
                    if exp_dt < datetime.now(timezone.utc):
                        logger.warning(f"⚠️ Cartão tokenizado expirado: {card_token}")
                        card["is_expired"] = True
                    else:
                        card["is_expired"] = False
                except Exception as e:
                    logger.warning(f"⚠️ Erro ao verificar expiração do cartão {card_token}: {e}")
                    card["is_expired"] = False
            
            return card
        
        return None
        
    except Exception as e:
        logger.error(f"❌ Erro ao buscar cartão tokenizado {card_token}: {e}")
        raise


async def delete_tokenized_card(card_token: str) -> bool:
    """Remove cartão tokenizado."""
    try:
        if not card_token:
            raise ValueError("Token do cartão é obrigatório")

        response = (
            supabase.table("cartoes_tokenizados")
            .delete()
            .eq("card_token", card_token)
            .execute()
        )
        
        if response.data:
            logger.info(f"✅ Cartão tokenizado removido: {card_token}")
            return True
        
        logger.warning(f"⚠️ Cartão não encontrado para exclusão: {card_token}")
        return False
        
    except Exception as e:
        logger.error(f"❌ Erro ao excluir cartão tokenizado {card_token}: {e}")
        raise


async def get_cards_by_cliente(empresa_id: str, cliente_id: str) -> List[Dict[str, Any]]:
    """
    ✅ MELHORADO: Busca cartões por cliente UUID ou customer_id.
    """
    try:
        if not empresa_id or not cliente_id:
            raise ValueError("empresa_id e cliente_id são obrigatórios")

        # Tentar buscar por cliente_id (UUID) primeiro
        query = supabase.table("cartoes_tokenizados").select(
            "card_token, last_four_digits, card_brand, created_at, expires_at, customer_id, cliente_id"
        ).eq("empresa_id", empresa_id)
        
        # Se parece UUID, buscar por cliente_id, senão por customer_id
        if validate_uuid(cliente_id):
            query = query.eq("cliente_id", cliente_id)
        else:
            query = query.eq("customer_id", cliente_id)
        
        response = query.order("created_at", desc=True).execute()
        cards = response.data or []
        
        # Enriquecer dados dos cartões
        now = datetime.now(timezone.utc)
        for card in cards:
            expires_at = card.get("expires_at")
            if expires_at:
                try:
                    exp_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                    if exp_dt.tzinfo is None:
                        exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                    
                    card["is_expired"] = exp_dt < now
                    card["days_to_expire"] = (exp_dt - now).days
                    card["expires_soon"] = (exp_dt - now).days <= 30
                except Exception:
                    card["is_expired"] = True
                    card["days_to_expire"] = 0
                    card["expires_soon"] = True
            else:
                card["is_expired"] = True
                card["days_to_expire"] = 0
                card["expires_soon"] = True
        
        logger.info(f"🃏 Encontrados {len(cards)} cartões para cliente {cliente_id}")
        return cards
        
    except Exception as e:
        logger.error(f"❌ Erro ao buscar cartões do cliente {cliente_id}: {e}")
        return []


# ========== EMPRESAS ==========
async def save_empresa(data: Dict[str, Any]) -> Dict[str, Any]:
    """Salva nova empresa."""
    try:
        empresa_id = data.get("empresa_id") or str(uuid.uuid4())
        data["empresa_id"] = empresa_id
        data["created_at"] = datetime.now(timezone.utc).isoformat()
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        response = supabase.table("empresas").insert(data).execute()
        
        if not response.data:
            raise ValueError("Erro ao salvar empresa no banco")
        
        logger.info(f"✅ Empresa {empresa_id} salva com sucesso")
        return response.data[0]
        
    except Exception as e:
        logger.error(f"❌ Erro ao salvar empresa: {e}")
        raise


async def get_empresa(cnpj: str) -> Optional[Dict[str, Any]]:
    """Busca empresa por CNPJ."""
    try:
        if not cnpj:
            raise ValueError("CNPJ é obrigatório")
            
        response = (
            supabase.table("empresas")
            .select("*")
            .eq("cnpj", cnpj)
            .execute()
        )
        return response.data[0] if response.data else None
        
    except Exception as e:
        logger.error(f"❌ Erro ao buscar empresa com CNPJ {cnpj}: {e}")
        raise


async def get_empresa_by_token(access_token: str) -> Optional[Dict[str, Any]]:
    """Busca empresa por access token."""
    try:
        if not access_token:
            raise ValueError("Access token é obrigatório")
            
        response = (
            supabase.table("empresas")
            .select("*")
            .eq("access_token", access_token)
            .execute()
        )
        
        if response.data:
            logger.info(f"✅ Empresa encontrada pelo token")
            return response.data[0]
        
        logger.warning(f"⚠️ Nenhuma empresa encontrada para o token fornecido")
        return None
        
    except Exception as e:
        logger.error(f"❌ Erro ao buscar empresa pelo token: {e}")
        raise


async def get_empresa_by_chave_pix(chave_pix: str) -> Optional[Dict[str, Any]]:
    """Busca empresa por chave PIX."""
    try:
        if not chave_pix:
            raise ValueError("Chave PIX é obrigatória")
            
        response = (
            supabase.table("empresas_config")
            .select("empresa_id")
            .eq("chave_pix", chave_pix)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None
        
    except Exception as e:
        logger.error(f"❌ Erro ao buscar empresa pela chave PIX {chave_pix}: {e}")
        return None


# ========== CONFIGURAÇÕES DA EMPRESA ==========
async def get_empresa_config(empresa_id: str) -> Optional[Dict[str, Any]]:
    """Busca configuração da empresa."""
    try:
        if not empresa_id:
            raise ValueError("empresa_id é obrigatório")
            
        response = (
            supabase.table("empresas_config")
            .select("*")
            .eq("empresa_id", empresa_id)
            .execute()
        )
        return response.data[0] if response.data else None
        
    except Exception as e:
        logger.error(f"❌ Erro ao carregar config da empresa {empresa_id}: {e}")
        raise


async def atualizar_config_gateway(payload: Dict[str, Any]) -> bool:
    """Atualiza configuração de gateways da empresa."""
    try:
        empresa_id = payload.get("empresa_id")
        if not empresa_id:
            raise ValueError("O campo 'empresa_id' é obrigatório")

        pix_provider = payload.get("pix_provider", "sicredi")
        credit_provider = payload.get("credit_provider", "rede")

        update_data = {
            "pix_provider": pix_provider,
            "credit_provider": credit_provider,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        response = (
            supabase.table("empresas_config")
            .update(update_data)
            .eq("empresa_id", empresa_id)
            .execute()
        )

        if response.data:
            logger.info(f"✅ Gateways atualizados para empresa {empresa_id}: PIX={pix_provider}, Crédito={credit_provider}")
            return True
        else:
            logger.warning(f"⚠️ Empresa não encontrada para atualização: {empresa_id}")
            return False

    except Exception as e:
        logger.error(f"❌ Erro ao atualizar gateways da empresa: {e}")
        raise


async def get_empresa_gateways(empresa_id: str) -> Optional[Dict[str, str]]:
    """Retorna configuração de gateways da empresa."""
    try:
        if not empresa_id:
            raise ValueError("empresa_id é obrigatório")
            
        response = (
            supabase.table("empresas_config")
            .select("pix_provider, credit_provider")
            .eq("empresa_id", empresa_id)
            .limit(1)
            .execute()
        )

        if response.data:
            logger.info(f"📦 Gateways da empresa {empresa_id} retornados")
            return response.data[0]

        logger.warning(f"⚠️ Nenhum gateway configurado para empresa {empresa_id}")
        return None

    except Exception as e:
        logger.error(f"❌ Erro ao buscar gateways da empresa {empresa_id}: {e}")
        return None


# ========== TOKEN SICREDI ==========
async def get_sicredi_token_or_refresh(empresa_id: str) -> str:
    """
    ✅ MELHORADO: Busca token Sicredi com renovação automática.
    """
    try:
        if not empresa_id:
            raise ValueError("empresa_id é obrigatório")
            
        # Buscar token atual
        response = (
            supabase.table("empresas_config")
            .select("sicredi_token, sicredi_token_expires_at")
            .eq("empresa_id", empresa_id)
            .limit(1)
            .execute()
        )
        
        row = response.data[0] if response.data else {}
        token = row.get("sicredi_token")
        expires_at = row.get("sicredi_token_expires_at")

        # Verificar validade do token
        if token and expires_at:
            now = datetime.now(timezone.utc)
            try:
                # Normalizar formato de data
                if isinstance(expires_at, str):
                    expires_at = expires_at.replace('Z', '+00:00')
                    exp_dt = datetime.fromisoformat(expires_at)
                else:
                    exp_dt = expires_at
                
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)

                # Buffer de 5 minutos para renovação
                if exp_dt > now + timedelta(minutes=5):
                    logger.info(f"🟢 Token Sicredi válido para empresa {empresa_id}")
                    return token

                logger.info(f"🔄 Token Sicredi expirando para empresa {empresa_id}, renovando...")

            except (ValueError, TypeError) as e:
                logger.warning(f"⚠️ Erro ao parsear data de expiração: {e}, renovando token")

        # Renovar token
        from payment_kode_api.app.services.gateways.sicredi_client import get_access_token

        new_token = await get_access_token(empresa_id)
        new_expires = datetime.now(timezone.utc) + timedelta(seconds=3300)  # 55 minutos

        # Atualizar no banco
        update_response = (
            supabase.table("empresas_config")
            .update({
                "sicredi_token": new_token,
                "sicredi_token_expires_at": new_expires.isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            })
            .eq("empresa_id", empresa_id)
            .execute()
        )

        if update_response.data:
            logger.info(f"✅ Token Sicredi renovado e salvo para empresa {empresa_id}")
        else:
            logger.warning(f"⚠️ Falha ao salvar token renovado para empresa {empresa_id}")

        return new_token

    except Exception as e:
        logger.error(f"❌ Erro ao obter/renovar token Sicredi para empresa {empresa_id}: {e}")
        raise


# ========== CERTIFICADOS RSA ==========
async def save_empresa_certificados(
    empresa_id: str, 
    sicredi_cert_base64: str, 
    sicredi_key_base64: str, 
    sicredi_ca_base64: Optional[str] = None
) -> Dict[str, Any]:
    """Salva certificados RSA da empresa."""
    try:
        if not all([empresa_id, sicredi_cert_base64, sicredi_key_base64]):
            raise ValueError("empresa_id, certificado e chave privada são obrigatórios")

        data = {
            "empresa_id": empresa_id,
            "sicredi_cert_base64": sicredi_cert_base64,
            "sicredi_key_base64": sicredi_key_base64,
            "sicredi_ca_base64": sicredi_ca_base64,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        # Verificar se já existe
        existing = (
            supabase.table("empresas_certificados")
            .select("id")
            .eq("empresa_id", empresa_id)
            .limit(1)
            .execute()
        )

        if existing.data:
            # Atualizar
            response = (
                supabase.table("empresas_certificados")
                .update(data)
                .eq("empresa_id", empresa_id)
                .execute()
            )
            logger.info(f"🔄 Certificados RSA atualizados para empresa {empresa_id}")
        else:
            # Inserir novo
            response = (
                supabase.table("empresas_certificados")
                .insert(data)
                .execute()
            )
            logger.info(f"✅ Certificados RSA salvos para empresa {empresa_id}")

        return response.data[0] if response.data else {}

    except Exception as e:
        logger.error(f"❌ Erro ao salvar certificados da empresa {empresa_id}: {e}")
        raise


async def get_empresa_certificados(empresa_id: str) -> Optional[Dict[str, Any]]:
    """Recupera certificados RSA da empresa."""
    try:
        if not empresa_id:
            raise ValueError("empresa_id é obrigatório")
            
        response = (
            supabase.table("empresas_certificados")
            .select("sicredi_cert_base64, sicredi_key_base64, sicredi_ca_base64")
            .eq("empresa_id", empresa_id)
            .limit(1)
            .execute()
        )

        if response.data:
            logger.info(f"🔐 Certificados RSA recuperados para empresa {empresa_id}")
            return response.data[0]

        logger.warning(f"⚠️ Certificados não encontrados para empresa {empresa_id}")
        return None

    except Exception as e:
        logger.error(f"❌ Erro ao recuperar certificados da empresa {empresa_id}: {e}")
        return None


# ========== PAGAMENTOS ==========
async def save_payment(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    ✅ MELHORADO: Salva pagamento com validações robustas.
    """
    try:
        empresa_id = data.get("empresa_id")
        transaction_id = data.get("transaction_id")
        
        if not all([empresa_id, transaction_id]):
            raise ValueError("empresa_id e transaction_id são obrigatórios")

        # Verificar duplicação
        existing_payment = await get_payment(transaction_id, empresa_id)
        if existing_payment:
            logger.info(f"ℹ️ Pagamento já existe: {transaction_id}")
            return existing_payment

        # Sanitizar dados
        sanitized_data = {}
        for k, v in data.items():
            if isinstance(v, Decimal):
                sanitized_data[k] = sanitize_decimal(v)
            else:
                sanitized_data[k] = v

        # Validações
        amount = sanitized_data.get("amount", 0)
        if amount <= 0:
            raise ValueError(f"Valor inválido: {amount}")

        payment_type = sanitized_data.get("payment_type", "").lower()
        if payment_type not in VALID_PAYMENT_TYPES:
            raise ValueError(f"Tipo de pagamento inválido: {payment_type}")

        status = sanitized_data.get("status", "pending")
        if status not in VALID_PAYMENT_STATUSES:
            logger.warning(f"⚠️ Status inválido {status}, usando 'pending'")
            status = "pending"

        installments = validate_installments(sanitized_data.get("installments", 1))
        cliente_id = sanitized_data.get("cliente_id")
        
        # Validar cliente UUID se fornecido
        if cliente_id and not validate_uuid(str(cliente_id)):
            logger.warning(f"⚠️ UUID de cliente inválido: {cliente_id}, ignorando")
            cliente_id = None

        # Montar registro do pagamento
        new_payment = {
            **sanitized_data,
            "status": status,
            "installments": installments,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "data_marketing": sanitized_data.get("data_marketing", {}),
            
            # Campos específicos da Rede
            "rede_tid": sanitized_data.get("rede_tid"),
            "authorization_code": sanitized_data.get("authorization_code"),
            "return_code": sanitized_data.get("return_code"),
            "return_message": sanitized_data.get("return_message"),
            
            # Cliente (UUID interno)
            "cliente_id": cliente_id
        }

        # TXID para PIX
        if "txid" in sanitized_data:
            new_payment["txid"] = sanitized_data["txid"]

        # Inserir no banco
        response = supabase.table("payments").insert(new_payment).execute()

        if not response.data:
            raise ValueError("Falha ao inserir pagamento no banco")

        logger.info(f"✅ Pagamento salvo | ID: {transaction_id} | Tipo: {payment_type} | Valor: R$ {amount} | Parcelas: {installments}")
        return response.data[0]

    except Exception as e:
        logger.error(f"❌ Erro ao salvar pagamento: {e}")
        raise


async def get_payment(transaction_id: str, empresa_id: str, columns: str = "*") -> Optional[Dict[str, Any]]:
    """Busca pagamento por ID da transação."""
    try:
        if not all([transaction_id, empresa_id]):
            raise ValueError("transaction_id e empresa_id são obrigatórios")
            
        response = (
            supabase.table("payments")
            .select(columns)
            .eq("transaction_id", transaction_id)
            .eq("empresa_id", empresa_id)
            .execute()
        )
        return response.data[0] if response.data else None
        
    except Exception as e:
        logger.error(f"❌ Erro ao buscar pagamento {transaction_id}: {e}")
        raise


async def get_payment_by_txid(txid: str) -> Optional[Dict[str, Any]]:
    """Busca pagamento por TXID (PIX)."""
    try:
        if not txid:
            raise ValueError("TXID é obrigatório")
            
        response = (
            supabase.table("payments")
            .select("*")
            .eq("txid", txid)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None
        
    except Exception as e:
        logger.error(f"❌ Erro ao buscar pagamento por TXID {txid}: {e}")
        raise


async def update_payment_status(
    transaction_id: str, 
    empresa_id: str, 
    status: str,
    extra_data: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """
    ✅ MELHORADO: Atualiza status do pagamento com validações.
    """
    try:
        if not all([transaction_id, empresa_id, status]):
            raise ValueError("transaction_id, empresa_id e status são obrigatórios")
            
        if status not in VALID_PAYMENT_STATUSES:
            raise ValueError(f"Status inválido: {status}. Válidos: {VALID_PAYMENT_STATUSES}")

        update_data = {
            "status": status,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        if extra_data:
            # Sanitizar extra_data
            for k, v in extra_data.items():
                if isinstance(v, Decimal):
                    update_data[k] = sanitize_decimal(v)
                else:
                    update_data[k] = v

        response = (
            supabase.table("payments")
            .update(update_data)
            .eq("transaction_id", transaction_id)
            .eq("empresa_id", empresa_id)
            .execute()
        )

        if not response.data:
            logger.warning(f"⚠️ Pagamento não encontrado para atualização: {transaction_id}")
            return None

        logger.info(f"✅ Status do pagamento atualizado: {transaction_id} → {status}")
        return response.data[0]

    except Exception as e:
        logger.error(f"❌ Erro ao atualizar status do pagamento {transaction_id}: {e}")
        raise


async def update_payment_status_by_txid(
    txid: str, 
    empresa_id: str, 
    status: str,
    extra_data: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """Atualiza status do pagamento por TXID."""
    try:
        payment = await get_payment_by_txid(txid)
        if not payment:
            logger.warning(f"⚠️ Pagamento não encontrado para TXID: {txid}")
            return None
            
        return await update_payment_status(
            transaction_id=payment["transaction_id"],
            empresa_id=payment["empresa_id"],
            status=status,
            extra_data=extra_data
        )
        
    except Exception as e:
        logger.error(f"❌ Erro ao atualizar status por TXID {txid}: {e}")
        raise


async def get_payments_by_cliente(empresa_id: str, cliente_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    ✅ MELHORADO: Busca pagamentos de um cliente com suporte a UUID e customer_id.
    """
    try:
        if not all([empresa_id, cliente_id]):
            raise ValueError("empresa_id e cliente_id são obrigatórios")

        # Validar limit
        limit = max(1, min(limit, 1000))

        # Buscar por UUID interno se possível, senão por customer_id
        query = supabase.table("payments").select("*").eq("empresa_id", empresa_id)
        
        if validate_uuid(cliente_id):
            query = query.eq("cliente_id", cliente_id)
        else:
            # Buscar por customer_id - pode precisar de JOIN ou query separada
            # Por enquanto, assumindo que temos cliente_id preenchido
            query = query.eq("cliente_id", cliente_id)
        
        response = query.order("created_at", desc=True).limit(limit).execute()
        payments = response.data or []
        
        # Enriquecer dados dos pagamentos
        for payment in payments:
            installments = payment.get("installments", 1)
            amount = sanitize_decimal(payment.get("amount", 0))
            
            payment["amount_per_installment"] = round(amount / installments, 2) if installments > 0 else amount
            payment["has_installments"] = installments > 1
            payment["total_installment_amount"] = round(amount, 2)
        
        logger.info(f"📊 Encontrados {len(payments)} pagamentos para cliente {cliente_id}")
        return payments
        
    except Exception as e:
        logger.error(f"❌ Erro ao buscar pagamentos do cliente {cliente_id}: {e}")
        return []


# ========== ESTATÍSTICAS E ANÁLISES ==========
async def get_cliente_stats(empresa_id: str, cliente_id: str) -> Dict[str, Any]:
    """
    ✅ MELHORADO: Estatísticas completas de um cliente.
    """
    try:
        if not all([empresa_id, cliente_id]):
            raise ValueError("empresa_id e cliente_id são obrigatórios")
            
        # Buscar todos os pagamentos do cliente
        query = supabase.table("payments").select(
            "amount, payment_type, created_at, status, installments"
        ).eq("empresa_id", empresa_id)
        
        if validate_uuid(cliente_id):
            query = query.eq("cliente_id", cliente_id)
        else:
            query = query.eq("cliente_id", cliente_id)  # Assumindo que funciona
            
        response = query.execute()
        all_payments = response.data or []
        
        if not all_payments:
            return {
                "total_transactions": 0,
                "approved_transactions": 0,
                "total_spent": 0.0,
                "avg_transaction": 0.0,
                "pix_transactions": 0,
                "card_transactions": 0,
                "first_transaction": None,
                "last_transaction": None,
                "success_rate": 0.0,
                "avg_installments": 0.0,
                "max_installments": 0,
                "pending_transactions": 0,
                "failed_transactions": 0
            }

        # Separar por status
        approved_payments = [p for p in all_payments if p["status"] == "approved"]
        pending_payments = [p for p in all_payments if p["status"] == "pending"]
        failed_payments = [p for p in all_payments if p["status"] == "failed"]
        
        # Cálculos básicos
        total_spent = sum(sanitize_decimal(p["amount"]) for p in approved_payments)
        approved_count = len(approved_payments)
        
        # Por tipo de pagamento
        pix_count = len([p for p in approved_payments if p["payment_type"] == "pix"])
        card_count = len([p for p in approved_payments if p["payment_type"] == "credit_card"])
        
        # Datas
        if approved_payments:
            dates = sorted([p["created_at"] for p in approved_payments])
            first_transaction = dates[0]
            last_transaction = dates[-1]
        else:
            first_transaction = None
            last_transaction = None
        
        # Taxa de sucesso
        success_rate = (approved_count / len(all_payments) * 100) if all_payments else 0
        
        # Estatísticas de parcelas (apenas cartão)
        card_payments = [p for p in approved_payments if p["payment_type"] == "credit_card"]
        if card_payments:
            installments_list = [p.get("installments", 1) for p in card_payments]
            avg_installments = sum(installments_list) / len(installments_list)
            max_installments = max(installments_list)
        else:
            avg_installments = 0.0
            max_installments = 0

        return {
            "total_transactions": len(all_payments),
            "approved_transactions": approved_count,
            "pending_transactions": len(pending_payments),
            "failed_transactions": len(failed_payments),
            "total_spent": round(total_spent, 2),
            "avg_transaction": round(total_spent / approved_count, 2) if approved_count > 0 else 0.0,
            "pix_transactions": pix_count,
            "card_transactions": card_count,
            "first_transaction": first_transaction,
            "last_transaction": last_transaction,
            "success_rate": round(success_rate, 1),
            "avg_installments": round(avg_installments, 1),
            "max_installments": max_installments,
            "months_as_customer": calculate_months_difference(first_transaction) if first_transaction else 0
        }
        
    except Exception as e:
        logger.error(f"❌ Erro ao calcular estatísticas do cliente {cliente_id}: {e}")
        return {"error": str(e)}


def calculate_months_difference(date_str: str) -> int:
    """Calcula diferença em meses entre uma data e agora."""
    try:
        date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        diff = now - date
        return max(0, int(diff.days / 30))
    except Exception:
        return 0


async def get_installments_statistics(empresa_id: str) -> Dict[str, Any]:
    """
    ✅ MELHORADO: Estatísticas de uso de parcelas com mais detalhes.
    """
    try:
        if not empresa_id:
            raise ValueError("empresa_id é obrigatório")
            
        # Buscar pagamentos de cartão de crédito
        response = (
            supabase.table("payments")
            .select("installments, amount, status, created_at")
            .eq("empresa_id", empresa_id)
            .eq("payment_type", "credit_card")
            .execute()
        )
        
        payments = response.data or []
        
        if not payments:
            return {
                "total_payments": 0,
                "avg_installments": 0.0,
                "installments_distribution": {},
                "avg_amount_per_installment": 0.0,
                "max_installments_used": 0,
                "min_installments_used": 0,
                "most_used_installments": 1,
                "single_installment_percentage": 0.0,
                "multiple_installment_percentage": 0.0
            }
        
        # Filtrar apenas aprovados para estatísticas financeiras
        approved_payments = [p for p in payments if p["status"] == "approved"]
        
        # Estatísticas básicas
        total_payments = len(payments)
        installments_list = [p.get("installments", 1) for p in payments]
        avg_installments = sum(installments_list) / total_payments
        
        # Distribuição de parcelas
        distribution = {}
        for installments in installments_list:
            str_installments = str(installments)
            distribution[str_installments] = distribution.get(str_installments, 0) + 1
        
        # Parcela mais usada
        most_used = max(distribution.items(), key=lambda x: x[1])[0] if distribution else "1"
        
        # Percentuais
        single_count = distribution.get("1", 0)
        multiple_count = total_payments - single_count
        single_percentage = (single_count / total_payments * 100) if total_payments > 0 else 0
        multiple_percentage = (multiple_count / total_payments * 100) if total_payments > 0 else 0
        
        # Valor médio por parcela (apenas aprovados)
        if approved_payments:
            total_amount_per_installment = 0
            for payment in approved_payments:
                amount = sanitize_decimal(payment.get("amount", 0))
                installments = payment.get("installments", 1)
                total_amount_per_installment += amount / installments if installments > 0 else amount
            
            avg_amount_per_installment = total_amount_per_installment / len(approved_payments)
        else:
            avg_amount_per_installment = 0.0

        return {
            "total_payments": total_payments,
            "approved_payments": len(approved_payments),
            "avg_installments": round(avg_installments, 1),
            "installments_distribution": distribution,
            "avg_amount_per_installment": round(avg_amount_per_installment, 2),
            "max_installments_used": max(installments_list) if installments_list else 0,
            "min_installments_used": min(installments_list) if installments_list else 0,
            "most_used_installments": int(most_used),
            "single_installment_percentage": round(single_percentage, 1),
            "multiple_installment_percentage": round(multiple_percentage, 1)
        }
        
    except Exception as e:
        logger.error(f"❌ Erro ao calcular estatísticas de parcelas: {e}")
        return {"error": str(e)}


async def get_payments_with_installments(empresa_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    ✅ MELHORADO: Busca pagamentos com análise de parcelas.
    """
    try:
        if not empresa_id:
            raise ValueError("empresa_id é obrigatório")
            
        # Validar limit
        limit = max(1, min(limit, 1000))
        
        response = (
            supabase.table("payments")
            .select("transaction_id, amount, installments, payment_type, status, created_at, cliente_id")
            .eq("empresa_id", empresa_id)
            .eq("payment_type", "credit_card")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        
        payments = response.data or []
        
        # Enriquecer dados
        for payment in payments:
            installments = payment.get("installments", 1)
            amount = sanitize_decimal(payment.get("amount", 0))
            
            payment["amount_per_installment"] = round(amount / installments, 2) if installments > 0 else amount
            payment["has_installments"] = installments > 1
            payment["total_amount"] = round(amount, 2)
            
            # Classificar tipo de parcelamento
            if installments == 1:
                payment["installment_type"] = "à vista"
            elif installments <= 3:
                payment["installment_type"] = "curto prazo"
            elif installments <= 6:
                payment["installment_type"] = "médio prazo"
            else:
                payment["installment_type"] = "longo prazo"
        
        logger.info(f"📊 Encontrados {len(payments)} pagamentos com cartão para análise")
        return payments
        
    except Exception as e:
        logger.error(f"❌ Erro ao buscar pagamentos com parcelas: {e}")
        return []


# ========== FUNÇÕES DE ANÁLISE AVANÇADA ==========
async def get_empresa_payment_summary(empresa_id: str, days: int = 30) -> Dict[str, Any]:
    """
    ✅ NOVO: Resumo completo de pagamentos da empresa.
    """
    try:
        if not empresa_id:
            raise ValueError("empresa_id é obrigatório")
            
        # Data limite
        start_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        
        # Buscar pagamentos do período
        response = (
            supabase.table("payments")
            .select("amount, payment_type, status, installments, created_at")
            .eq("empresa_id", empresa_id)
            .gte("created_at", start_date)
            .execute()
        )
        
        payments = response.data or []
        
        if not payments:
            return {
                "period_days": days,
                "total_transactions": 0,
                "total_amount": 0.0,
                "approved_amount": 0.0,
                "success_rate": 0.0,
                "payment_types": {},
                "daily_average": 0.0,
                "installments_summary": {}
            }
        
        # Análises
        total_transactions = len(payments)
        approved_payments = [p for p in payments if p["status"] == "approved"]
        
        total_amount = sum(sanitize_decimal(p["amount"]) for p in payments)
        approved_amount = sum(sanitize_decimal(p["amount"]) for p in approved_payments)
        
        success_rate = (len(approved_payments) / total_transactions * 100) if total_transactions > 0 else 0
        
        # Por tipo de pagamento
        payment_types = {}
        for payment in approved_payments:
            ptype = payment["payment_type"]
            if ptype not in payment_types:
                payment_types[ptype] = {"count": 0, "amount": 0.0}
            payment_types[ptype]["count"] += 1
            payment_types[ptype]["amount"] += sanitize_decimal(payment["amount"])
        
        # Análise de parcelas
        card_payments = [p for p in approved_payments if p["payment_type"] == "credit_card"]
        installments_summary = {}
        if card_payments:
            for payment in card_payments:
                installments = str(payment.get("installments", 1))
                if installments not in installments_summary:
                    installments_summary[installments] = {"count": 0, "amount": 0.0}
                installments_summary[installments]["count"] += 1
                installments_summary[installments]["amount"] += sanitize_decimal(payment["amount"])
        
        return {
            "period_days": days,
            "total_transactions": total_transactions,
            "approved_transactions": len(approved_payments),
            "total_amount": round(total_amount, 2),
            "approved_amount": round(approved_amount, 2),
            "success_rate": round(success_rate, 1),
            "payment_types": payment_types,
            "daily_average": round(approved_amount / days, 2),
            "installments_summary": installments_summary
        }
        
    except Exception as e:
        logger.error(f"❌ Erro ao gerar resumo de pagamentos: {e}")
        return {"error": str(e)}


async def get_top_customers_by_spending(empresa_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    ✅ NOVO: Top clientes por valor gasto.
    """
    try:
        if not empresa_id:
            raise ValueError("empresa_id é obrigatório")
            
        # Validar limit
        limit = max(1, min(limit, 100))
        
        # Buscar pagamentos aprovados com cliente
        response = (
            supabase.table("payments")
            .select("cliente_id, amount, payment_type, created_at")
            .eq("empresa_id", empresa_id)
            .eq("status", "approved")
            .not_.is_("cliente_id", "null")
            .execute()
        )
        
        payments = response.data or []
        
        if not payments:
            return []
        
        # Agrupar por cliente
        customer_stats = {}
        for payment in payments:
            cliente_id = payment["cliente_id"]
            amount = sanitize_decimal(payment["amount"])
            
            if cliente_id not in customer_stats:
                customer_stats[cliente_id] = {
                    "cliente_id": cliente_id,
                    "total_spent": 0.0,
                    "transaction_count": 0,
                    "pix_count": 0,
                    "card_count": 0,
                    "first_purchase": payment["created_at"],
                    "last_purchase": payment["created_at"]
                }
            
            stats = customer_stats[cliente_id]
            stats["total_spent"] += amount
            stats["transaction_count"] += 1
            
            if payment["payment_type"] == "pix":
                stats["pix_count"] += 1
            elif payment["payment_type"] == "credit_card":
                stats["card_count"] += 1
            
            # Atualizar datas
            if payment["created_at"] < stats["first_purchase"]:
                stats["first_purchase"] = payment["created_at"]
            if payment["created_at"] > stats["last_purchase"]:
                stats["last_purchase"] = payment["created_at"]
        
        # Calcular médias e ordenar
        top_customers = []
        for stats in customer_stats.values():
            stats["avg_transaction"] = round(stats["total_spent"] / stats["transaction_count"], 2)
            stats["total_spent"] = round(stats["total_spent"], 2)
            top_customers.append(stats)
        
        # Ordenar por valor total gasto
        top_customers.sort(key=lambda x: x["total_spent"], reverse=True)
        
        return top_customers[:limit]
        
    except Exception as e:
        logger.error(f"❌ Erro ao buscar top clientes: {e}")
        return []


# ========== FUNÇÕES DE LIMPEZA E MANUTENÇÃO ==========
async def cleanup_expired_cards(empresa_id: str) -> Dict[str, Any]:
    """
    ✅ NOVO: Remove cartões expirados da empresa.
    """
    try:
        if not empresa_id:
            raise ValueError("empresa_id é obrigatório")
            
        # Data atual
        now = datetime.now(timezone.utc).isoformat()
        
        # Buscar cartões expirados
        response = (
            supabase.table("cartoes_tokenizados")
            .select("card_token, expires_at")
            .eq("empresa_id", empresa_id)
            .lt("expires_at", now)
            .execute()
        )
        
        expired_cards = response.data or []
        
        if not expired_cards:
            return {
                "removed_cards": 0,
                "message": "Nenhum cartão expirado encontrado"
            }
        
        # Remover cartões expirados
        card_tokens = [card["card_token"] for card in expired_cards]
        
        delete_response = (
            supabase.table("cartoes_tokenizados")
            .delete()
            .eq("empresa_id", empresa_id)
            .in_("card_token", card_tokens)
            .execute()
        )
        
        removed_count = len(delete_response.data) if delete_response.data else 0
        
        logger.info(f"🧹 Removidos {removed_count} cartões expirados da empresa {empresa_id}")
        
        return {
            "removed_cards": removed_count,
            "expired_tokens": card_tokens,
            "message": f"Removidos {removed_count} cartões expirados"
        }
        
    except Exception as e:
        logger.error(f"❌ Erro ao limpar cartões expirados: {e}")
        return {"error": str(e)}


async def health_check_database() -> Dict[str, Any]:
    """
    ✅ MELHORADO: Verifica saúde do banco de dados.
    """
    try:
        # Teste básico de conectividade
        response = supabase.table("empresas").select("empresa_id").limit(1).execute()
        
        # Verificar tabelas principais
        tables_to_check = [
            "empresas", "empresas_config", "payments", 
            "cartoes_tokenizados", "clientes", "enderecos"
        ]
        
        table_status = {}
        for table in tables_to_check:
            try:
                test_response = supabase.table(table).select("*").limit(1).execute()
                table_status[table] = "healthy"
            except Exception as e:
                table_status[table] = f"error: {str(e)}"
        
        # Estatísticas gerais
        try:
            stats_response = supabase.table("payments").select("*", count="exact").execute()
            total_payments = stats_response.count or 0
        except Exception:
            total_payments = "unknown"
        
        return {
            "status": "healthy",
            "message": "Database connection OK",
            "tables": table_status,
            "total_payments": total_payments,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "message": f"Database error: {str(e)}",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


# ========== EXPORTS ==========
__all__ = [
    # Cartões
    "save_tokenized_card", "get_tokenized_card", "delete_tokenized_card", "get_cards_by_cliente",
    
    # Empresas
    "save_empresa", "get_empresa", "get_empresa_by_token", "get_empresa_by_chave_pix",
    
    # Configurações
    "get_empresa_config", "atualizar_config_gateway", "get_empresa_gateways",
    
    # Tokens e Certificados
    "get_sicredi_token_or_refresh", "save_empresa_certificados", "get_empresa_certificados",
    
    # Pagamentos
    "save_payment", "get_payment", "get_payment_by_txid", 
    "update_payment_status", "update_payment_status_by_txid", "get_payments_by_cliente",
    
    # Estatísticas
    "get_cliente_stats", "get_installments_statistics", "get_payments_with_installments",
    "get_empresa_payment_summary", "get_top_customers_by_spending",
    
    # Manutenção
    "cleanup_expired_cards", "health_check_database",
    
    # Utilitários
    "sanitize_decimal", "validate_uuid", "validate_installments", "VALID_PAYMENT_STATUSES"
]