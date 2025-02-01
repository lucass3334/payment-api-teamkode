from pydantic import BaseModel
from pydantic.types import StringConstraints, DecimalConstraints
from typing import Annotated, Optional
import uuid

# Tipos de dados validados
TransactionIDType = Annotated[str, StringConstraints(min_length=6, max_length=35)]
AmountType = Annotated[float, DecimalConstraints(gt=0, decimal_places=2)]
StatusType = Annotated[str, StringConstraints(min_length=3, max_length=20)]  # Ex: "pending", "approved", "failed"
UUIDType = Annotated[str, StringConstraints(min_length=36, max_length=36)]  # Validação para UUID

class CustomerInfo(BaseModel):
    """
    Informações do cliente associadas a um pagamento.
    """
    name: Annotated[str, StringConstraints(min_length=3, max_length=100)]
    email: Annotated[str, StringConstraints(min_length=5, max_length=100)]
    cpf_cnpj: Annotated[str, StringConstraints(min_length=11, max_length=14)]  # CPF (11) ou CNPJ (14)
    phone: Annotated[str, StringConstraints(min_length=10, max_length=15)]  # Formato DDD + Número
    endereco: Optional[dict] = None  # Permite armazenar endereço como JSON

class EmpresaSchema(BaseModel):
    """
    Estrutura para criar e consultar empresas no sistema.
    """
    id: uuid.UUID
    nome: Annotated[str, StringConstraints(min_length=3, max_length=100)]
    cnpj: Annotated[str, StringConstraints(min_length=14, max_length=14)]  # CNPJ sem formatação

class PaymentSchema(BaseModel):
    """
    Estrutura para criação e consulta de pagamentos.
    """
    empresa_id: UUIDType  # Relaciona o pagamento a uma empresa específica
    transaction_id: TransactionIDType
    amount: AmountType
    description: Annotated[str, StringConstraints(min_length=3, max_length=255)]
    payment_type: Annotated[str, StringConstraints(min_length=3, max_length=15)]  # "pix" ou "credit_card"
    status: Optional[StatusType] = "pending"
    customer: CustomerInfo
    webhook_url: Optional[str] = None  # Webhook opcional para notificações externas
