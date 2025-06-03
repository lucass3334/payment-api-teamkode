import os
from payment_kode_api.app.core.config import settings
from payment_kode_api.app.utilities.logging_config import logger
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
import uuid
from decimal import Decimal
from .supabase_client import supabase

VALID_PAYMENT_STATUSES = {"pending", "approved", "failed", "canceled"}


# 🔹 Cartões tokenizados
async def save_tokenized_card(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Atualizada para incluir referência ao cliente interno.
    """
    try:
        empresa_id = data.get("empresa_id")
        customer_id = data.get("customer_id")
        card_token = data.get("card_token")
        encrypted_card_data = data.get("encrypted_card_data")
        cliente_id = data.get("cliente_id")

        if not all([empresa_id, customer_id, card_token, encrypted_card_data]):
            raise ValueError("Campos obrigatórios ausentes para salvar o cartão.")

        card_record = {
            "empresa_id": empresa_id,
            "customer_id": customer_id,
            "card_token": card_token,
            "encrypted_card_data": encrypted_card_data,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=365)).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Adicionar referência ao cliente se disponível
        if cliente_id:
            card_record["cliente_id"] = cliente_id

        response = (
            supabase.table("cartoes_tokenizados")
            .insert(card_record)
            .execute()
        )

        if not response.data:
            raise ValueError("Erro ao salvar cartão tokenizado.")

        logger.info(f"✅ Cartão tokenizado salvo para empresa {empresa_id}, cliente {customer_id}, token {card_token}")
        return response.data[0]

    except Exception as e:
        logger.error(f"❌ Erro ao salvar cartão tokenizado: {e}")
        raise


async def get_tokenized_card(card_token: str) -> Optional[Dict[str, Any]]:
    try:
        response = (
            supabase.table("cartoes_tokenizados")
            .select("*")
            .eq("card_token", card_token)
            .execute()
        )
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"❌ Erro ao buscar cartão tokenizado: {e}")
        raise


async def delete_tokenized_card(card_token: str) -> bool:
    try:
        response = (
            supabase.table("cartoes_tokenizados")
            .delete()
            .eq("card_token", card_token)
            .execute()
        )
        if response.data:
            logger.info(f"✅ Cartão tokenizado {card_token} removido com sucesso.")
            return True
        logger.warning(f"⚠️ Nenhum cartão encontrado para exclusão: {card_token}")
        return False
    except Exception as e:
        logger.error(f"❌ Erro ao excluir cartão tokenizado: {e}")
        raise


# 🔹 Empresa
async def save_empresa(data: Dict[str, Any]) -> Dict[str, Any]:
    try:
        empresa_id = data.get("empresa_id", str(uuid.uuid4()))
        response = supabase.table("empresas").insert(data).execute()
        if not response.data:
            raise ValueError("Erro ao salvar empresa.")
        logger.info(f"✅ Empresa {empresa_id} salva com sucesso.")
        return response.data[0]
    except Exception as e:
        logger.error(f"❌ Erro ao salvar empresa {empresa_id}: {e}")
        raise


async def get_empresa(cnpj: str) -> Optional[Dict[str, Any]]:
    try:
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
    try:
        response = (
            supabase.table("empresas")
            .select("*")
            .eq("access_token", access_token)
            .execute()
        )
        if response.data:
            logger.info(f"✅ Empresa encontrada pelo token")
            return response.data[0]
        logger.warning(f"⚠️ Nenhuma empresa encontrada para Access Token fornecido")
        return None
    except Exception as e:
        logger.error(f"❌ Erro ao buscar empresa pelo Access Token: {e}")
        raise


# 🔹 Busca o token da Sicredi para uma empresa, atualizando se expirado
async def get_sicredi_token_or_refresh(empresa_id: str) -> str:
    """
    Busca no Supabase o token Sicredi salvo; se expirou, solicita um novo
    e atualiza a tabela `empresas_config`.
    """
    try:
        # 1) Busca diretamente no Supabase
        resp = (
            supabase
            .table("empresas_config")
            .select("sicredi_token, sicredi_token_expires_at")
            .eq("empresa_id", empresa_id)
            .limit(1)
            .execute()
        )
        row = resp.data[0] if resp.data else {}
        token = row.get("sicredi_token")
        expires_at = row.get("sicredi_token_expires_at")

        # 2) Verifica validade
        if token and expires_at:
            now = datetime.now(timezone.utc)
            try:
                if isinstance(expires_at, str):
                    if expires_at.endswith('Z'):
                        expires_at = expires_at[:-1] + '+00:00'
                    exp_dt = datetime.fromisoformat(expires_at)
                else:
                    exp_dt = expires_at
            except ValueError:
                try:
                    exp_dt = datetime.strptime(expires_at, "%Y-%m-%dT%H:%M:%S.%f")
                except ValueError:
                    exp_dt = datetime.strptime(expires_at, "%Y-%m-%dT%H:%M:%S")
            
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)

            # Buffer de 5 minutos para renovação
            if exp_dt > now + timedelta(minutes=5):
                logger.info(f"🟢 Reutilizando token Sicredi para {empresa_id}")
                return token

            logger.info(f"🔄 Token Sicredi expirado/expirando para {empresa_id}, renovando...")

        # 3) Importa e renova token
        from payment_kode_api.app.services.gateways.sicredi_client import get_access_token

        new_token = await get_access_token(empresa_id)
        new_expires = datetime.now(timezone.utc) + timedelta(seconds=3300)  # 55 min

        # 4) Atualiza no Supabase
        upd = (
            supabase
            .table("empresas_config")
            .update({
                "sicredi_token": new_token,
                "sicredi_token_expires_at": new_expires.isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            })
            .eq("empresa_id", empresa_id)
            .execute()
        )

        if upd.data:
            logger.info(f"✅ Token Sicredi atualizado no Supabase para {empresa_id}")
        else:
            logger.warning(f"⚠️ Não foi possível salvar token Sicredi para {empresa_id}")

        return new_token

    except Exception as e:
        logger.error(f"❌ Erro em get_sicredi_token_or_refresh({empresa_id}): {e}")
        raise


# 🔹 Atualiza os gateways padrão (Pix e Crédito) da empresa
async def atualizar_config_gateway(payload: Dict[str, Any]) -> bool:
    try:
        empresa_id = payload.get("empresa_id")
        pix_provider = payload.get("pix_provider", "sicredi")
        credit_provider = payload.get("credit_provider", "rede")

        if not empresa_id:
            raise ValueError("O campo 'empresa_id' é obrigatório.")

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
            logger.info(f"✅ Gateways atualizados para empresa {empresa_id}")
            return True
        else:
            logger.warning(f"⚠️ Nenhuma empresa encontrada com ID {empresa_id}")
            return False

    except Exception as e:
        logger.error(f"❌ Erro ao atualizar os gateways da empresa: {e}")
        raise


# 🔹 Retorna os providers atuais da empresa
async def get_empresa_gateways(empresa_id: str) -> Optional[Dict[str, str]]:
    try:
        response = (
            supabase.table("empresas_config")
            .select("pix_provider, credit_provider")
            .eq("empresa_id", empresa_id)
            .limit(1)
            .execute()
        )

        if response.data:
            logger.info(f"📦 Providers da empresa {empresa_id} retornados com sucesso.")
            return response.data[0]

        logger.warning(f"⚠️ Nenhum provider encontrado para empresa {empresa_id}.")
        return None

    except Exception as e:
        logger.error(f"❌ Erro ao buscar providers da empresa {empresa_id}: {e}")
        return None


# 🔹 Pagamentos
async def save_payment(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Atualizada para incluir referência ao cliente.
    """
    try:
        empresa_id = data.get("empresa_id")
        transaction_id = data.get("transaction_id")

        existing_payment = await get_payment(transaction_id, empresa_id)
        if existing_payment:
            logger.info(f"ℹ️ Transação já processada para empresa {empresa_id}: {transaction_id}")
            return existing_payment

        sanitized_data = {
            k: float(v) if isinstance(v, Decimal) else v
            for k, v in data.items()
        }

        new_payment = {
            **sanitized_data,
            "status": "pending",
            "installments": sanitized_data.get("installments", 1),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "data_marketing": data.get("data_marketing", {}),
            
            # Campos para Rede
            "rede_tid": data.get("rede_tid"),
            "authorization_code": data.get("authorization_code"),
            "return_code": data.get("return_code"),
            "return_message": data.get("return_message"),
            
            # Referência ao cliente
            "cliente_id": data.get("cliente_id")
        }

        if "txid" in data:
            new_payment["txid"] = data["txid"]

        response = supabase.table("payments").insert(new_payment).execute()

        if not response.data:
            raise ValueError("Erro ao salvar pagamento.")

        logger.info(f"✅ Novo pagamento salvo para empresa {empresa_id}")
        return response.data[0]

    except Exception as e:
        logger.error(f"❌ Erro ao salvar pagamento para empresa {empresa_id}: {e}")
        raise


async def get_payment(transaction_id: str, empresa_id: str, columns: str = "*") -> Optional[Dict[str, Any]]:
    try:
        response = (
            supabase.table("payments")
            .select(columns)
            .eq("transaction_id", transaction_id)
            .eq("empresa_id", empresa_id)
            .execute()
        )
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"❌ Erro ao recuperar pagamento: {e}")
        raise


async def get_payments_by_cliente(empresa_id: str, cliente_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Busca pagamentos de um cliente específico.
    """
    try:
        response = (
            supabase.table("payments")
            .select("*")
            .eq("empresa_id", empresa_id)
            .eq("cliente_id", cliente_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        
        payments = response.data or []
        logger.info(f"📊 Encontrados {len(payments)} pagamentos para cliente {cliente_id}")
        return payments
        
    except Exception as e:
        logger.error(f"❌ Erro ao buscar pagamentos do cliente {cliente_id}: {e}")
        return []


async def update_payment_status(
    transaction_id: str, 
    empresa_id: str, 
    status: str,
    extra_data: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    try:
        if status not in VALID_PAYMENT_STATUSES:
            raise ValueError(f"Status inválido: {status}")

        update_data = {
            "status": status,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        if extra_data:
            update_data.update(extra_data)

        response = (
            supabase.table("payments")
            .update(update_data)
            .eq("transaction_id", transaction_id)
            .eq("empresa_id", empresa_id)
            .execute()
        )

        if not response.data:
            logger.warning(f"⚠️ Pagamento não encontrado: {transaction_id}")
            return None

        logger.info(f"✅ Status atualizado: {transaction_id} → {status}")
        return response.data[0]

    except Exception as e:
        logger.error(f"❌ Erro ao atualizar status do pagamento: {e}")
        raise


# 🔹 Pagamento por TXID
async def get_payment_by_txid(txid: str) -> Optional[Dict[str, Any]]:
    try:
        resp = (
            supabase.table("payments")
            .select("*")
            .eq("txid", txid)
            .limit(1)
            .execute()
        )
        return resp.data[0] if resp.data else None
    except Exception as e:
        logger.error(f"❌ Erro ao recuperar pagamento pelo TXID {txid}: {e}")
        raise


async def update_payment_status_by_txid(
    txid: str, 
    empresa_id: str, 
    status: str,
    extra_data: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    try:
        payment = await get_payment_by_txid(txid)
        if not payment:
            logger.warning(f"⚠️ Nenhum pagamento encontrado para TXID: {txid}")
            return None
        return await update_payment_status(
            transaction_id=payment["transaction_id"],
            empresa_id=payment["empresa_id"],
            status=status,
            extra_data=extra_data
        )
    except Exception as e:
        logger.error(f"❌ Erro ao atualizar status pelo TXID {txid}: {e}")
        raise


# 🔹 Consulta por chave Pix
async def get_empresa_by_chave_pix(chave_pix: str) -> Optional[Dict[str, Any]]:
    try:
        response = supabase.table("empresas_config").select("empresa_id").eq("chave_pix", chave_pix).limit(1).execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        logger.error(f"❌ Erro ao buscar empresa pela chave Pix: {e}")
        return None


# 🔹 Certificados RSA
async def save_empresa_certificados(
    empresa_id: str, 
    sicredi_cert_base64: str, 
    sicredi_key_base64: str, 
    sicredi_ca_base64: Optional[str] = None
) -> Dict[str, Any]:
    try:
        data = {
            "empresa_id": empresa_id,
            "sicredi_cert_base64": sicredi_cert_base64,
            "sicredi_key_base64": sicredi_key_base64,
            "sicredi_ca_base64": sicredi_ca_base64,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        existing = (
            supabase.table("empresas_certificados")
            .select("id")
            .eq("empresa_id", empresa_id)
            .limit(1)
            .execute()
        )

        if existing.data:
            response = (
                supabase.table("empresas_certificados")
                .update(data)
                .eq("empresa_id", empresa_id)
                .execute()
            )
            logger.info(f"🔄 Certificados RSA atualizados para empresa {empresa_id}")
        else:
            response = (
                supabase.table("empresas_certificados")
                .insert(data)
                .execute()
            )
            logger.info(f"✅ Certificados RSA salvos para empresa {empresa_id}")

        return response.data[0] if response.data else {}

    except Exception as e:
        logger.error(f"❌ Erro ao salvar certificados RSA da empresa {empresa_id}: {e}")
        raise


async def get_empresa_certificados(empresa_id: str) -> Optional[Dict[str, Any]]:
    try:
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

        logger.warning(f"⚠️ Nenhum certificado RSA encontrado para a empresa {empresa_id}")
        return None

    except Exception as e:
        logger.error(f"❌ Erro ao recuperar certificados RSA da empresa {empresa_id}: {e}")
        return None


# 🔹 Config da empresa
async def get_empresa_config(empresa_id: str) -> Optional[Dict[str, Any]]:
    try:
        resp = (
            supabase
            .table("empresas_config")
            .select("*")
            .eq("empresa_id", empresa_id)
            .execute()
        )
        return resp.data[0] if resp.data else None
    except Exception as e:
        logger.error(f"❌ Erro ao carregar config da empresa {empresa_id}: {e}")
        raise


async def get_cards_by_cliente(empresa_id: str, customer_id: str) -> List[Dict[str, Any]]:
    """
    Busca cartões tokenizados de um cliente.
    """
    try:
        response = (
            supabase.table("cartoes_tokenizados")
            .select("card_token, created_at, expires_at, customer_id, cliente_id")
            .eq("empresa_id", empresa_id)
            .eq("customer_id", customer_id)
            .order("created_at", desc=True)
            .execute()
        )
        
        cards = response.data or []
        
        # Adicionar status de validade
        now = datetime.now(timezone.utc)
        for card in cards:
            if card.get("expires_at"):
                try:
                    expires = datetime.fromisoformat(card["expires_at"])
                    if expires.tzinfo is None:
                        expires = expires.replace(tzinfo=timezone.utc)
                    card["is_expired"] = expires < now
                    card["days_to_expire"] = (expires - now).days
                except:
                    card["is_expired"] = True
                    card["days_to_expire"] = 0
            else:
                card["is_expired"] = True
                card["days_to_expire"] = 0
        
        logger.info(f"🃏 Encontrados {len(cards)} cartões para cliente {customer_id}")
        return cards
        
    except Exception as e:
        logger.error(f"❌ Erro ao buscar cartões do cliente {customer_id}: {e}")
        return []


async def get_cliente_stats(empresa_id: str, cliente_id: str) -> Dict[str, Any]:
    """
    Retorna estatísticas de um cliente.
    """
    try:
        response = (
            supabase.table("payments")
            .select("amount, payment_type, created_at, status")
            .eq("empresa_id", empresa_id)
            .eq("cliente_id", cliente_id)
            .execute()
        )
        
        all_payments = response.data or []
        approved_payments = [p for p in all_payments if p["status"] == "approved"]
        
        if not approved_payments:
            return {
                "total_transactions": len(all_payments),
                "approved_transactions": 0,
                "total_spent": 0.0,
                "avg_transaction": 0.0,
                "pix_transactions": 0,
                "card_transactions": 0,
                "first_transaction": None,
                "last_transaction": None,
                "success_rate": 0.0
            }
        
        total_spent = sum(float(p["amount"]) for p in approved_payments)
        approved_count = len(approved_payments)
        pix_count = len([p for p in approved_payments if p["payment_type"] == "pix"])
        card_count = len([p for p in approved_payments if p["payment_type"] == "credit_card"])
        
        dates = [p["created_at"] for p in approved_payments]
        dates.sort()
        
        success_rate = (approved_count / len(all_payments) * 100) if all_payments else 0
        
        return {
            "total_transactions": len(all_payments),
            "approved_transactions": approved_count,
            "total_spent": round(total_spent, 2),
            "avg_transaction": round(total_spent / approved_count, 2) if approved_count > 0 else 0.0,
            "pix_transactions": pix_count,
            "card_transactions": card_count,
            "first_transaction": dates[0] if dates else None,
            "last_transaction": dates[-1] if dates else None,
            "success_rate": round(success_rate, 1)
        }
        
    except Exception as e:
        logger.error(f"❌ Erro ao calcular estatísticas do cliente {cliente_id}: {e}")
        return {
            "total_transactions": 0,
            "approved_transactions": 0,
            "total_spent": 0.0,
            "avg_transaction": 0.0,
            "pix_transactions": 0,
            "card_transactions": 0,
            "first_transaction": None,
            "last_transaction": None,
            "success_rate": 0.0
        }