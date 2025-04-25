import os
from payment_kode_api.app.core.config import settings
from payment_kode_api.app.utilities.logging_config import logger
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from .supabase_client import supabase




datetime.now(timezone.utc)

VALID_PAYMENT_STATUSES = {"pending", "approved", "failed", "canceled"}


# 🔹 Cartões tokenizados
async def save_tokenized_card(data: Dict[str, Any]) -> Dict[str, Any]:
    try:
        empresa_id = data.get("empresa_id")
        customer_id = data.get("customer_id")
        card_token = data.get("card_token")
        encrypted_card_data = data.get("encrypted_card_data")

        if not all([empresa_id, customer_id, card_token, encrypted_card_data]):
            raise ValueError("Campos obrigatórios ausentes para salvar o cartão.")

        response = (
            supabase.table("cartoes_tokenizados")
            .insert({
                "empresa_id": empresa_id,
                "customer_id": customer_id,
                "card_token": card_token,
                "encrypted_card_data": encrypted_card_data,
                "expires_at": datetime.now(timezone.utc).isoformat()
            })
            .execute()
        )

        if not response.data:
            raise ValueError("Erro ao salvar cartão tokenizado.")

        logger.info(f"✅ Cartão tokenizado salvo para empresa {empresa_id} e cliente {customer_id}.")
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
            logger.info(f"✅ Empresa encontrada pelo token: {response.data[0]}")
            return response.data[0]
        logger.warning(f"⚠️ Nenhuma empresa encontrada para Access Token: {access_token}")
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
        # 1) Busca diretamente no Supabase (sem passar pelo config_service)
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
                exp_dt = datetime.fromisoformat(expires_at)
            except ValueError:
                exp_dt = datetime.strptime(expires_at, "%Y-%m-%dT%H:%M:%S.%f")
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            # --- Fim do patch ---

            if exp_dt > now:
                logger.info(f"🟢 Reutilizando token Sicredi para {empresa_id}")
                return token

            logger.info(f"🔄 Token Sicredi expirado para {empresa_id}, renovando...")

        # 3) Só agora importamos a função que vai chamar o Sicredi
        from payment_kode_api.app.services.gateways.sicredi_client import get_access_token

        new_token = await get_access_token(empresa_id)
        # subtrai 60s pra dar folga
        new_expires = datetime.now(timezone.utc) + timedelta(seconds=3600 - 60)

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
            logger.warning(f"⚠️ Não salvou token Sicredi para {empresa_id}")

        return new_token

    except Exception as e:
        logger.error(f"❌ Erro em get_sicredi_token_or_refresh({empresa_id}): {e}")
        raise

# 🔹 Atualiza os gateways padrão (Pix e Crédito) da empresa
async def atualizar_config_gateway(payload: Dict[str, Any]) -> bool:
    """
    Atualiza os providers de Pix e Crédito para a empresa no Supabase.
    """
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
            logger.info(f"✅ Gateways atualizados para empresa {empresa_id}: Pix = {pix_provider}, Crédito = {credit_provider}")
            return True
        else:
            logger.warning(f"⚠️ Nenhuma empresa encontrada com ID {empresa_id} para atualizar gateways.")
            return False

    except Exception as e:
        logger.error(f"❌ Erro ao atualizar os gateways da empresa {payload.get('empresa_id')}: {e}")
        raise

# 🔹 Retorna os providers atuais da empresa (Pix e Crédito)
async def get_empresa_gateways(empresa_id: str) -> Optional[Dict[str, str]]:
    """
    Retorna os providers configurados para Pix e Crédito de uma empresa.
    """
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
        }

        if "txid" in data:
            new_payment["txid"] = data["txid"]

        response = supabase.table("payments").insert(new_payment).execute()

        if not response.data:
            raise ValueError("Erro ao salvar pagamento.")

        logger.info(f"✅ Novo pagamento salvo para empresa {empresa_id}: {response.data[0]}")
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
        logger.error(f"❌ Erro ao recuperar pagamento para empresa {empresa_id}, transaction_id {transaction_id}: {e}")
        raise

async def update_payment_status(transaction_id: str, empresa_id: str, status: str) -> Optional[Dict[str, Any]]:
    try:
        if status not in VALID_PAYMENT_STATUSES:
            raise ValueError(f"Status inválido: {status}")

        update_data = {
            "status": status,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        response = (
            supabase.table("payments")
            .update(update_data)
            .eq("transaction_id", transaction_id)
            .eq("empresa_id", empresa_id)
            .execute()
        )

        if not response.data:
            logger.warning(f"⚠️ Pagamento não encontrado: Empresa {empresa_id}, transaction_id {transaction_id}")
            return None

        logger.info(f"✅ Status atualizado para empresa {empresa_id}, transaction_id {transaction_id}: {status}")
        return response.data[0]

    except Exception as e:
        logger.error(f"❌ Erro ao atualizar status do pagamento para empresa {empresa_id}, transaction_id {transaction_id}: {e}")
        raise

# 🔹 Pagamento por TXID
async def get_payment_by_txid(txid: str) -> Optional[Dict[str, Any]]:
    """
    Busca no Supabase o pagamento que tenha o txid informado.
    """
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

async def update_payment_status_by_txid(txid: str, status: str) -> Optional[Dict[str, Any]]:
    """
    Atualiza status do pagamento usando apenas o txid.
    Retorna o pagamento atualizado ou None se não encontrado.
    """
    try:
        payment = await get_payment_by_txid(txid)
        if not payment:
            logger.warning(f"⚠️ Nenhum pagamento encontrado para TXID: {txid}")
            return None
        return await update_payment_status(
            transaction_id=payment["transaction_id"],
            empresa_id=payment["empresa_id"],
            status=status
        )
    except Exception as e:
        logger.error(f"❌ Erro ao atualizar status pelo TXID {txid}: {e}")
        raise


# 🔹 Consulta por chave Pix
async def get_empresa_by_chave_pix(chave_pix: str) -> dict:
    try:
        response = supabase.table("empresas_config").select("empresa_id").eq("chave_pix", chave_pix).limit(1).execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        print(f"Erro ao buscar empresa pela chave Pix: {e}")
        return None


# 🔹 Salva as chaves públicas/privadas RSA da empresa
async def save_empresa_certificados(empresa_id: str, public_key_base64: str, private_key_base64: str) -> Dict[str, Any]:
    """
    Insere ou atualiza os certificados RSA (public/private key) da empresa na tabela `empresas_certificados`.
    """
    try:
        data = {
            "empresa_id": empresa_id,
            "public_key_base64": public_key_base64,
            "private_key_base64": private_key_base64,
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


# 🔹 Recupera os certificados RSA da empresa
async def get_empresa_certificados(empresa_id: str) -> Optional[Dict[str, Any]]:
    """
    Recupera os certificados públicos/privados da empresa armazenados na tabela `empresas_certificados`.
    """
    try:
        response = (
            supabase.table("empresas_certificados")
            .select("public_key_base64, private_key_base64")
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
    


# 🔹 Recupera config direto do supabase (quebra import circular)
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