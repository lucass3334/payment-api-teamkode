import os
from supabase import create_client, Client
from payment_kode_api.app.core.config import settings
from payment_kode_api.app.utilities.logging_config import logger
from datetime import datetime
from typing import Optional, Dict, Any
import uuid

# Lista de status válidos para pagamentos
VALID_PAYMENT_STATUSES = {"pending", "approved", "failed", "canceled"}

class SupabaseClient:
    """Gerencia a conexão única com o Supabase."""
    _client: Optional[Client] = None

    @classmethod
    def get_client(cls) -> Client:
        """Retorna um cliente reutilizável para o Supabase."""
        if cls._client is None:
            cls._client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        return cls._client

supabase = SupabaseClient.get_client()

# 🔹 Adicionando funções para tokenização de cartões
async def save_tokenized_card(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Salva um cartão tokenizado no banco de dados.
    """
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
                "expires_at": datetime.utcnow().isoformat()
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
    """
    Busca um cartão tokenizado pelo token único.
    """
    try:
        response = (
            supabase.table("cartoes_tokenizados")
            .select("*")
            .eq("card_token", card_token)
            .execute()
        )

        if response.data:
            return response.data[0]

        logger.warning(f"⚠️ Cartão tokenizado não encontrado para token: {card_token}")
        return None

    except Exception as e:
        logger.error(f"❌ Erro ao buscar cartão tokenizado: {e}")
        raise

async def delete_tokenized_card(card_token: str) -> bool:
    """
    Remove um cartão tokenizado do banco de dados.
    """
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

async def save_empresa(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Salva os dados de uma empresa no banco de dados.
    """
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
    """
    Busca uma empresa pelo CNPJ.
    """
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
    """
    Busca uma empresa pelo `access_token`.
    """
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

async def get_empresa_config(empresa_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtém as configurações de uma empresa para acessar as credenciais dos gateways de pagamento.
    """
    try:
        response = (
            supabase.table("empresas_config")
            .select("*")
            .eq("empresa_id", empresa_id)
            .execute()
        )

        if response.data:
            return response.data[0]

        logger.warning(f"⚠️ Configuração da empresa não encontrada: {empresa_id}")
        return None

    except Exception as e:
        logger.error(f"❌ Erro ao recuperar configuração da empresa {empresa_id}: {e}")
        raise

async def save_payment(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Salva um novo pagamento no banco de dados, garantindo idempotência.
    """
    try:
        empresa_id = data.get("empresa_id")
        transaction_id = data.get("transaction_id")

        existing_payment = await get_payment(transaction_id, empresa_id)
        if existing_payment:
            logger.info(f"ℹ️ Transação já processada para empresa {empresa_id}: {transaction_id}")
            return existing_payment

        new_payment = {
            **data,
            "status": "pending",
            "installments": data.get("installments", 1),
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        response = supabase.table("payments").insert(new_payment).execute()

        if not response.data:
            raise ValueError("Erro ao salvar pagamento.")

        logger.info(f"✅ Novo pagamento salvo para empresa {empresa_id}: {response.data[0]}")
        return response.data[0]

    except Exception as e:
        logger.error(f"❌ Erro ao salvar pagamento para empresa {empresa_id}: {e}")
        raise

async def get_payment(transaction_id: str, empresa_id: str, columns: str = "*") -> Optional[Dict[str, Any]]:
    """
    Recupera um pagamento pelo transaction_id e empresa_id.
    """
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
    """
    Atualiza o status de um pagamento.
    """
    try:
        if status not in VALID_PAYMENT_STATUSES:
            raise ValueError(f"Status inválido: {status}")

        update_data = {
            "status": status,
            "updated_at": datetime.utcnow().isoformat()
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
async def get_empresa_certificados(empresa_id: str) -> Optional[Dict[str, Any]]:
    """
    Recupera os certificados da empresa armazenados na tabela `empresas_certificados`.
    Retorna os certificados em formato Base64.
    """
    try:
        response = (
            supabase.table("empresas_certificados")
            .select("sicredi_cert_base64, sicredi_key_base64, sicredi_ca_base64")
            .eq("empresa_id", empresa_id)
            .execute()
        )

        if response.data:
            logger.info(f"✅ Certificados recuperados para empresa {empresa_id}")
            return response.data[0]

        logger.warning(f"⚠️ Nenhum certificado encontrado para a empresa {empresa_id}")
        return None

    except Exception as e:
        logger.error(f"❌ Erro ao recuperar certificados da empresa {empresa_id}: {e}")
        raise
async def save_empresa_certificados(empresa_id: str, sicredi_cert_base64: str, sicredi_key_base64: str, sicredi_ca_base64: str) -> Dict[str, Any]:
    """
    Salva ou atualiza os certificados de uma empresa na tabela `empresas_certificados`.
    """
    try:
        existing_cert = (
            supabase.table("empresas_certificados")
            .select("id")
            .eq("empresa_id", empresa_id)
            .execute()
        )

        data = {
            "empresa_id": empresa_id,
            "sicredi_cert_base64": sicredi_cert_base64,
            "sicredi_key_base64": sicredi_key_base64,
            "sicredi_ca_base64": sicredi_ca_base64,
            "updated_at": datetime.utcnow().isoformat()
        }

        if existing_cert.data:
            # Se já existe um registro, atualiza os certificados
            response = (
                supabase.table("empresas_certificados")
                .update(data)
                .eq("empresa_id", empresa_id)
                .execute()
            )
            logger.info(f"✅ Certificados da empresa {empresa_id} atualizados.")
        else:
            # Se não existe, cria um novo registro
            response = (
                supabase.table("empresas_certificados")
                .insert(data)
                .execute()
            )
            logger.info(f"✅ Certificados da empresa {empresa_id} salvos.")

        return response.data[0] if response.data else {}

    except Exception as e:
        logger.error(f"❌ Erro ao salvar certificados da empresa {empresa_id}: {e}")
        raise
