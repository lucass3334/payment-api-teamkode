from pydantic import BaseModel, StringConstraints, condecimal, field_validator
from typing import Annotated, Optional, Dict
from decimal import Decimal, ROUND_HALF_UP
import uuid

# Tipos de dados validados
TransactionIDType = Annotated[str, StringConstraints(min_length=6, max_length=35)]
StatusType = Annotated[str, StringConstraints(min_length=3, max_length=20)]  # Ex: "pending", "approved", "failed"

class CustomerInfo(BaseModel):
    """
    Informações do cliente associadas a um pagamento.
    """
    name: Annotated[str, StringConstraints(min_length=3, max_length=100)]
    email: Annotated[str, StringConstraints(min_length=5, max_length=100)]
    cpf_cnpj: Annotated[str, StringConstraints(min_length=11, max_length=14)]  # CPF (11) ou CNPJ (14)
    phone: Annotated[str, StringConstraints(min_length=10, max_length=15)]  # Formato DDD + Número
    endereco: Optional[Dict[str, str]] = None  # ✅ Usa Dict validado para JSON do endereço

class EmpresaSchema(BaseModel):
    """
    Estrutura para criar e consultar empresas no sistema.
    """
    id: uuid.UUID
    nome: Annotated[str, StringConstraints(min_length=3, max_length=100)]
    cnpj: Annotated[str, StringConstraints(min_length=14, max_length=14)]  # CNPJ sem formatação

class EmpresaConfigSchema(BaseModel):
    """
    Estrutura para credenciais da empresa nos serviços de pagamento.
    """
    id: uuid.UUID
    empresa_id: uuid.UUID
    asaas_api_key: Optional[str] = None
    sicredi_client_id: Optional[str] = None
    sicredi_client_secret: Optional[str] = None
    sicredi_api_key: Optional[str] = None
    rede_pv: Optional[str] = None
    rede_api_key: Optional[str] = None

class EmpresaCertificadosSchema(BaseModel):
    """
    Estrutura para armazenar certificados mTLS do Sicredi.
    """
    id: uuid.UUID
    empresa_id: uuid.UUID
    sicredi_cert_base64: Optional[str] = None
    sicredi_key_base64: Optional[str] = None
    sicredi_ca_base64: Optional[str] = None

class PaymentSchema(BaseModel):
    """
    Estrutura para criação e consulta de pagamentos.
    """
    empresa_id: uuid.UUID
    transaction_id: TransactionIDType
    txid: Optional[Annotated[str, StringConstraints(min_length=4, max_length=35)]] = None
    # txid é opcional, mas se fornecido deve ter entre 4 e 35 caracteres
    amount: Decimal  # 🔧 Corrigido para usar Decimal direto
    description: Annotated[str, StringConstraints(min_length=3, max_length=255)]
    payment_type: Annotated[str, StringConstraints(min_length=3, max_length=15)]  # "pix" ou "credit_card"
    status: Optional[StatusType] = "pending"
    customer: CustomerInfo
    webhook_url: Optional[str] = None  # Webhook opcional para notificações externas

    @field_validator('amount', mode='before')
    @classmethod
    def normalize_amount(cls, v):
        """
        Converte o valor recebido para Decimal com 2 casas decimais,
        aceitando int, float ou string.
        """
        try:
            decimal_value = Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except Exception as e:
            raise ValueError(f"Valor inválido para amount: {v}. Erro: {e}")

        if decimal_value <= 0:
            raise ValueError("O valor de 'amount' deve ser maior que 0.")
        return decimal_value
