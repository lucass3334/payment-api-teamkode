import os
from supabase import create_client, Client
from payment_kode_api.app.config import settings
from payment_kode_api.app.utilities.logging_config import logger
from datetime import datetime
from typing import Optional, Dict, Any
import asyncio

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

async def save_payment(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Salva um novo pagamento no banco de dados, garantindo idempotência para cada empresa.
    """
    try:
        empresa_id = data.get("empresa_id")
        transaction_id = data.get("transaction_id")

        if not empresa_id or not transaction_id:
            raise ValueError("empresa_id e transaction_id são obrigatórios para salvar um pagamento.")

        # Verifica se o pagamento já existe sem fazer uma query separada
        response = (
            supabase.table("payments")
            .select("*")
            .eq("transaction_id", transaction_id)
            .eq("empresa_id", empresa_id)
            .execute()
        )

        if response.data:
            logger.info(f"Transação já processada para empresa {empresa_id}: {transaction_id}. Retornando dados salvos.")
            return response.data[0]

        new_payment = {
            **data,
            "status": "pending",
            "installments": data.get("installments", 1),  
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        response = supabase.table("payments").insert(new_payment).execute()

        if response.data:
            logger.info(f"Novo pagamento salvo para empresa {empresa_id}: {response.data[0]}")
            return response.data[0]

        raise ValueError("Erro ao salvar pagamento: resposta vazia do Supabase.")

    except Exception as e:
        logger.error(f"Erro ao salvar pagamento para empresa {empresa_id}: {e}")
        raise

async def get_payment(transaction_id: str, empresa_id: str, columns: str = "*") -> Optional[Dict[str, Any]]:
    """
    Recupera um pagamento pelo transaction_id e empresa_id, permitindo selecionar colunas específicas.
    """
    try:
        response = (
            supabase.table("payments")
            .select(columns)
            .eq("transaction_id", transaction_id)
            .eq("empresa_id", empresa_id)
            .execute()
        )

        if response.data:
            return response.data[0]

        logger.warning(f"Pagamento não encontrado para empresa {empresa_id}, transaction_id: {transaction_id}")
        return None

    except Exception as e:
        logger.error(f"Erro ao recuperar pagamento para empresa {empresa_id}, transaction_id {transaction_id}: {e}")
        raise

async def update_payment_status(transaction_id: str, empresa_id: str, status: str) -> Optional[Dict[str, Any]]:
    """
    Atualiza o status de um pagamento no banco de dados.
    """
    try:
        if status not in VALID_PAYMENT_STATUSES:
            logger.warning(f"Status inválido recebido: {status} para empresa {empresa_id}, transaction_id: {transaction_id}")
            return None

        response = (
            supabase.table("payments")
            .update({"status": status, "updated_at": datetime.utcnow().isoformat()})
            .eq("transaction_id", transaction_id)
            .eq("empresa_id", empresa_id)
            .execute()
        )

        if response.data:
            logger.info(f"Status atualizado para empresa {empresa_id}, transaction_id {transaction_id}: {status}")
            return response.data[0]

        logger.warning(f"Falha ao atualizar status, pagamento não encontrado: Empresa {empresa_id}, transaction_id {transaction_id}")
        return None

    except Exception as e:
        logger.error(f"Erro ao atualizar status do pagamento para empresa {empresa_id}, transaction_id {transaction_id}: {e}")
        raise

async def save_empresa(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Salva uma nova empresa no banco de dados, verificando se já existe.
    """
    try:
        empresa_id = data.get("empresa_id")
        cnpj = data.get("cnpj")

        if not empresa_id or not cnpj:
            raise ValueError("empresa_id e cnpj são obrigatórios para salvar uma empresa.")

        # Verifica se a empresa já existe sem fazer uma query separada
        response = (
            supabase.table("empresas")
            .select("empresa_id")
            .eq("cnpj", cnpj)
            .execute()
        )

        if response.data:
            logger.info(f"Empresa já cadastrada no sistema: {empresa_id}")
            return response.data[0]

        response = supabase.table("empresas").insert(data).execute()

        if response.data:
            logger.info(f"Nova empresa salva no banco: {response.data[0]}")
            return response.data[0]

        raise ValueError("Erro ao salvar empresa: resposta vazia do Supabase.")

    except Exception as e:
        logger.error(f"Erro ao salvar empresa: {e}")
        raise

async def get_empresa_config(empresa_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtém as configurações de pagamento da empresa.
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

        logger.warning(f"Configuração não encontrada para empresa {empresa_id}")
        return None

    except Exception as e:
        logger.error(f"Erro ao recuperar configuração da empresa {empresa_id}: {e}")
        raise
