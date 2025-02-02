from pydantic import BaseModel, StringConstraints, condecimal
from datetime import datetime
from typing import Annotated, Optional
import uuid

# Tipos de dados validados
TransactionIDType = Annotated[str, StringConstraints(min_length=6, max_length=35)]
AmountType = Annotated[float, condecimal(gt=0, decimal_places=2)]
StatusType = Annotated[str, StringConstraints(min_length=3, max_length=20)]  # Ex: "pending", "approved", "failed"

class PaymentModel(BaseModel):
    """
    Modelo para representar pagamentos no banco de dados.
    """
    id: uuid.UUID
    empresa_id: uuid.UUID  # Relaciona o pagamento a uma empresa específica
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

class EmpresaConfigModel(BaseModel):
    """
    Modelo para representar credenciais de pagamento da empresa.
    """
    id: uuid.UUID
    empresa_id: uuid.UUID
    asaas_api_key: Optional[str] = None
    sicredi_client_id: Optional[str] = None
    sicredi_client_secret: Optional[str] = None
    sicredi_api_key: Optional[str] = None
    rede_pv: Optional[str] = None
    rede_api_key: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class EmpresaCertificadosModel(BaseModel):
    """
    Modelo para armazenar certificados mTLS do Sicredi separadamente.
    """
    id: uuid.UUID
    empresa_id: uuid.UUID
    sicredi_cert_base64: Optional[str] = None
    sicredi_key_base64: Optional[str] = None
    sicredi_ca_base64: Optional[str] = None
    created_at: datetime
    updated_at: datetime
