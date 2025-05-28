from pydantic import BaseModel, StringConstraints, condecimal, field_validator
from datetime import datetime
from typing import Annotated, Optional, Dict, Any
from decimal import Decimal  # ✅ Importado para corrigir o tipo AmountType
import uuid

# Tipos de dados validados
TransactionIDType = Annotated[str, StringConstraints(min_length=6, max_length=35)]
AmountType = Annotated[Decimal, condecimal(gt=0, decimal_places=2)]  # ✅ Corrigido: float → Decimal
StatusType = Annotated[str, StringConstraints(min_length=3, max_length=20)]  # Ex: "pending", "approved", "failed"

class PaymentModel(BaseModel):
    """
    🔧 ATUALIZADO: Modelo para representar pagamentos no banco de dados com campos da Rede.
    """
    id: uuid.UUID
    empresa_id: uuid.UUID  # Relaciona o pagamento a uma empresa específica
    transaction_id: TransactionIDType
    amount: AmountType
    customer_id: Optional[Annotated[str, StringConstraints(min_length=6, max_length=50)]] = None  # 🔧 CORRIGIDO: Opcional
    status: StatusType
    payment_type: Annotated[str, StringConstraints(min_length=3, max_length=15)]  # 🔧 NOVO: "pix", "credit_card"
    webhook_url: Optional[str] = None
    
    # 🔧 NOVOS CAMPOS DA REDE
    rede_tid: Optional[str] = None  # TID da Rede para estornos
    authorization_code: Optional[str] = None  # Código de autorização
    return_code: Optional[str] = None  # Código de retorno (00=sucesso)
    return_message: Optional[str] = None  # Mensagem descritiva
    
    # 🔧 CAMPOS PIX
    txid: Optional[str] = None  # TXID do Sicredi
    pix_link: Optional[str] = None  # Link/código PIX
    qr_code_base64: Optional[str] = None  # QR Code em base64
    
    # 🔧 CAMPOS EXTRAS
    installments: Optional[int] = 1  # Número de parcelas
    data_marketing: Optional[Dict[str, Any]] = None  # Dados de marketing
    description: Optional[str] = None  # Descrição do pagamento
    
    # Timestamps
    created_at: datetime
    updated_at: datetime

class EmpresaModel(BaseModel):
    """
    Modelo para representar empresas cadastradas no sistema.
    """
    id: uuid.UUID
    nome: Annotated[str, StringConstraints(min_length=3, max_length=100)]
    cnpj: Annotated[str, StringConstraints(min_length=14, max_length=14)]
    email: Annotated[str, StringConstraints(min_length=5, max_length=100)]  # 🔧 NOVO
    telefone: Annotated[str, StringConstraints(min_length=10, max_length=15)]  # 🔧 NOVO
    access_token: str  # 🔧 NOVO: Token de acesso da empresa
    created_at: datetime
    updated_at: datetime

class EmpresaConfigModel(BaseModel):
    """
    🔧 ATUALIZADO: Modelo para representar credenciais de pagamento da empresa.
    """
    id: uuid.UUID
    empresa_id: uuid.UUID
    
    # Credenciais Asaas
    asaas_api_key: Optional[str] = None
    
    # Credenciais Sicredi
    sicredi_client_id: Optional[str] = None
    sicredi_client_secret: Optional[str] = None
    sicredi_api_key: Optional[str] = None
    sicredi_token: Optional[str] = None  # 🔧 NOVO: Token em cache
    sicredi_token_expires_at: Optional[datetime] = None  # 🔧 NOVO: Expiração do token
    sicredi_env: Optional[str] = "production"  # 🔧 NOVO: Ambiente Sicredi
    
    # Credenciais Rede
    rede_pv: Optional[str] = None
    rede_api_key: Optional[str] = None
    rede_ambient: Optional[str] = "production"  # 🔧 NOVO: Ambiente Rede
    
    # Configurações de provider
    pix_provider: Optional[str] = 'sicredi'
    credit_provider: Optional[str] = 'rede'
    
    # Configurações extras
    webhook_pix: Optional[str] = None  # 🔧 NOVO: URL de webhook para PIX
    chave_pix: Optional[str] = None  # 🔧 NOVO: Chave PIX da empresa
    use_sandbox: Optional[bool] = False  # 🔧 NOVO: Usar ambiente sandbox
    
    # Timestamps
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

class TokenizedCardModel(BaseModel):
    """
    🔧 NOVO: Modelo para cartões tokenizados.
    """
    id: uuid.UUID
    empresa_id: uuid.UUID
    customer_id: str
    card_token: str
    encrypted_card_data: str
    last_four_digits: Optional[str] = None  # Últimos 4 dígitos para exibição
    card_brand: Optional[str] = None  # Bandeira do cartão (Visa, Master, etc.)
    expires_at: datetime
    created_at: datetime
    updated_at: datetime

class AsaasCustomerModel(BaseModel):
    """
    🔧 NOVO: Modelo para mapeamento de clientes Asaas.
    """
    id: uuid.UUID
    empresa_id: uuid.UUID
    local_customer_id: str  # ID do cliente no sistema local
    asaas_customer_id: str  # ID do cliente no Asaas
    created_at: datetime

class WebhookLogModel(BaseModel):
    """
    🔧 NOVO: Modelo para log de webhooks enviados.
    """
    id: uuid.UUID
    empresa_id: uuid.UUID
    transaction_id: str
    webhook_url: str
    payload: Dict[str, Any]
    status_code: Optional[int] = None
    response_body: Optional[str] = None
    attempts: int = 1
    success: bool = False
    created_at: datetime
    updated_at: datetime

class RefundModel(BaseModel):
    """
    🔧 NOVO: Modelo para estornos.
    """
    id: uuid.UUID
    empresa_id: uuid.UUID
    transaction_id: str  # ID da transação original
    refund_id: str  # ID único do estorno
    amount: AmountType
    provider: str  # "rede", "sicredi", "asaas"
    provider_refund_id: Optional[str] = None  # ID do estorno no gateway
    status: StatusType
    reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class ApiKeyModel(BaseModel):
    """
    🔧 NOVO: Modelo para chaves de API (futuro).
    """
    id: uuid.UUID
    empresa_id: uuid.UUID
    key_name: str
    api_key: str
    permissions: Dict[str, Any]  # Permissões da chave
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

# 🔧 MODELOS DE VALIDAÇÃO PARA RESPONSES

class DatabaseResponse(BaseModel):
    """
    Modelo base para respostas de operações no banco.
    """
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class PaymentStatusUpdate(BaseModel):
    """
    Modelo para atualizações de status de pagamento.
    """
    transaction_id: str
    empresa_id: str
    old_status: str
    new_status: str
    extra_data: Optional[Dict[str, Any]] = None
    updated_at: datetime

class CertificateValidation(BaseModel):
    """
    Modelo para validação de certificados.
    """
    empresa_id: str
    certificate_type: str  # "cert", "key", "ca"
    is_valid: bool
    md5_hash: Optional[str] = None
    expires_at: Optional[datetime] = None
    validated_at: datetime

# 🔧 ENUMS E CONSTANTES

class PaymentStatus:
    """
    Constantes para status de pagamentos.
    """
    PENDING = "pending"
    APPROVED = "approved"
    FAILED = "failed"
    CANCELED = "canceled"
    REFUNDED = "refunded"
    
    ALL_STATUSES = {PENDING, APPROVED, FAILED, CANCELED, REFUNDED}

class PaymentType:
    """
    Constantes para tipos de pagamento.
    """
    PIX = "pix"
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    
    ALL_TYPES = {PIX, CREDIT_CARD, DEBIT_CARD}

class Provider:
    """
    Constantes para provedores de pagamento.
    """
    SICREDI = "sicredi"
    ASAAS = "asaas"
    REDE = "rede"
    
    PIX_PROVIDERS = {SICREDI, ASAAS}
    CREDIT_PROVIDERS = {REDE, ASAAS}
    ALL_PROVIDERS = {SICREDI, ASAAS, REDE}