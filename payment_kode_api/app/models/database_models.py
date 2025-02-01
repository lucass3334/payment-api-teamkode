from pydantic import BaseModel
from datetime import datetime
from pydantic.types import StringConstraints, DecimalConstraints
from typing import Annotated, Optional
import uuid

# Tipos de dados validados
TransactionIDType = Annotated[str, StringConstraints(min_length=6, max_length=35)]
AmountType = Annotated[float, DecimalConstraints(gt=0, decimal_places=2)]
StatusType = Annotated[str, StringConstraints(min_length=3, max_length=20)]  # Ex: "pending", "approved", "failed"
UUIDType = Annotated[str, StringConstraints(min_length=36, max_length=36)]  # Validação para UUID

class PaymentModel(BaseModel):
    """
    Modelo para representar pagamentos no banco de dados.
    """
    id: uuid.UUID
    empresa_id: UUIDType  # Relaciona o pagamento a uma empresa específica
    transaction_id: TransactionIDType
    amount: AmountType
    customer_id: Annotated[str, StringConstraints(min_length=6, max_length=50)]
    status: StatusType  # Status do pagamento
    webhook_url: Optional[str] = None  # Webhook opcional para notificações externas
    created_at: datetime
    updated_at: datetime

class EmpresaModel(BaseModel):
    """
    Modelo para representar empresas cadastradas no sistema.
    """
    id: uuid.UUID
    nome: Annotated[str, StringConstraints(min_length=3, max_length=100)]
    cnpj: Annotated[str, StringConstraints(min_length=14, max_length=14)]  # CNPJ sem formatação
    created_at: datetime
    updated_at: datetime
