from pydantic import BaseModel, StringConstraints, condecimal, field_validator
from typing import Annotated, Optional, Dict, Any
from decimal import Decimal, ROUND_HALF_UP
import uuid
from datetime import date, datetime

from enum import Enum

class PixProviderEnum(str, Enum):
    sicredi = "sicredi"
    asaas = "asaas"

class CreditProviderEnum(str, Enum):
    rede = "rede"
    asaas = "asaas"


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
    # 🔧 NOVO: Campo para ambiente da Rede
    rede_ambient: Optional[str] = "production"  # "sandbox" ou "production"

class EmpresaCertificadosSchema(BaseModel):
    """
    Estrutura para armazenar certificados mTLS do Sicredi.
    """
    id: uuid.UUID
    empresa_id: uuid.UUID
    sicredi_cert_base64: Optional[str] = None
    sicredi_key_base64: Optional[str] = None
    sicredi_ca_base64: Optional[str] = None


class EmpresaGatewayConfigSchema(BaseModel):
    """
    Permite configurar os gateways de pagamento (Pix e Crédito) usados por uma empresa.
    """
    empresa_id: uuid.UUID
    pix_provider: PixProviderEnum = PixProviderEnum.sicredi  # Default: Sicredi
    credit_provider: CreditProviderEnum = CreditProviderEnum.rede  # Default: Rede

class Devedor(BaseModel):
    """
    🔧 CORRIGIDO: Removida duplicação e melhorada validação.
    """
    nome: Annotated[str, StringConstraints(min_length=3, max_length=100)]
    cpf:  Optional[Annotated[str, StringConstraints(min_length=11, max_length=11)]] = None
    cnpj: Optional[Annotated[str, StringConstraints(min_length=14, max_length=14)]] = None
    
    @field_validator('cpf', 'cnpj', mode='before')
    @classmethod
    def validate_documents(cls, v):
        """Remove formatação de CPF/CNPJ se presente."""
        if v:
            return ''.join(filter(str.isdigit, str(v)))
        return v

class PaymentSchema(BaseModel):
    """
    🔧 CORRIGIDO: Schema principal de pagamento com novos campos da Rede.
    """
    empresa_id:       uuid.UUID
    transaction_id:   Annotated[str, StringConstraints(min_length=6, max_length=35)]
    txid:             Optional[Annotated[str, StringConstraints(min_length=4, max_length=35)]] = None
    amount:           Decimal
    description:      Annotated[str, StringConstraints(min_length=3, max_length=255)]
    payment_type:     Annotated[str, StringConstraints(min_length=3, max_length=15)]
    status:           Optional[Annotated[str, StringConstraints(min_length=3, max_length=20)]] = "pending"
    customer:         CustomerInfo
    webhook_url:      Optional[str] = None

    # CAMPOS PIX
    due_date:         Optional[date] = None
    expiration:       Optional[int] = None
    refund_deadline:  Optional[datetime] = None
    pix_link:         Optional[str] = None
    qr_code_base64:   Optional[str] = None
    devedor:          Optional[Devedor] = None

    # 🔧 NOVOS CAMPOS DA REDE
    rede_tid:         Optional[str] = None
    authorization_code: Optional[str] = None
    return_code:      Optional[str] = None
    return_message:   Optional[str] = None

    # CAMPOS EXTRAS
    data_marketing:   Optional[Dict[str, Any]] = None  # 🔧 CORRIGIDO: any → Any
    installments:     Optional[int] = 1

    @field_validator('amount', mode='before')
    @classmethod
    def normalize_amount(cls, v):
        try:
            dec = Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except Exception as e:
            raise ValueError(f"Valor inválido para amount: {v}. Erro: {e}")
        if dec <= 0:
            raise ValueError("O valor de 'amount' deve ser maior que 0.")
        return dec


# 🔧 NOVOS SCHEMAS PARA API

class PaymentCreateRequest(BaseModel):
    """
    Schema para criação de pagamentos via API.
    """
    amount: Decimal
    payment_type: Annotated[str, StringConstraints(pattern=r'^(pix|credit_card)$')]
    description: Optional[str] = "Pagamento via Payment Kode API"
    webhook_url: Optional[str] = None
    transaction_id: Optional[str] = None
    
    # Dados PIX
    chave_pix: Optional[str] = None
    due_date: Optional[date] = None
    nome_devedor: Optional[str] = None
    cpf: Optional[str] = None
    cnpj: Optional[str] = None
    
    # Dados Cartão
    card_token: Optional[str] = None
    installments: Optional[int] = 1
    
    @field_validator('amount', mode='before')
    @classmethod
    def normalize_amount(cls, v):
        try:
            dec = Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if dec <= 0:
                raise ValueError("O valor deve ser maior que 0.")
            return dec
        except Exception as e:
            raise ValueError(f"Valor inválido: {v}. Erro: {e}")


class PaymentResponse(BaseModel):
    """
    Schema padronizado para resposta de pagamentos.
    """
    status: str
    transaction_id: str
    message: Optional[str] = None
    
    # Dados PIX
    pix_link: Optional[str] = None
    qr_code_base64: Optional[str] = None
    expiration: Optional[int] = None
    due_date: Optional[str] = None
    
    # Dados Rede
    rede_tid: Optional[str] = None
    authorization_code: Optional[str] = None
    return_code: Optional[str] = None
    
    # Dados gerais
    amount: Optional[Decimal] = None
    created_at: Optional[datetime] = None


class RefundRequest(BaseModel):
    """
    Schema para solicitações de estorno.
    """
    transaction_id: uuid.UUID
    amount: Optional[Decimal] = None  # Se None, estorno total
    reason: Optional[str] = "Estorno solicitado pelo cliente"


class RefundResponse(BaseModel):
    """
    Schema para resposta de estornos.
    """
    status: str
    transaction_id: str
    provider: str
    message: Optional[str] = None
    refund_id: Optional[str] = None  # ID do estorno no gateway


class WebhookPayload(BaseModel):
    """
    Schema para payloads de webhook enviados aos clientes.
    """
    transaction_id: str
    status: str
    provedor: str
    amount: Optional[Decimal] = None
    
    # Dados específicos por gateway
    txid: Optional[str] = None
    rede_tid: Optional[str] = None
    authorization_code: Optional[str] = None
    
    # Dados extras
    data_marketing: Optional[Dict[str, Any]] = None  # 🔧 CORRIGIDO: any → Any
    payload: Optional[Dict[str, Any]] = None         # 🔧 CORRIGIDO: any → Any

class CardTokenRequest(BaseModel):
    """
    Schema para tokenização de cartões.
    """
    customer_id: str
    card_number: Annotated[str, StringConstraints(min_length=13, max_length=19)]
    expiration_month: Annotated[str, StringConstraints(min_length=1, max_length=2)]
    expiration_year: Annotated[str, StringConstraints(min_length=4, max_length=4)]
    security_code: Annotated[str, StringConstraints(min_length=3, max_length=4)]
    cardholder_name: Annotated[str, StringConstraints(min_length=3, max_length=100)]


class CardTokenResponse(BaseModel):
    """
    Schema para resposta de tokenização.
    """
    card_token: str
    expires_at: Optional[datetime] = None
    last_four_digits: Optional[str] = None


# 🔧 SCHEMAS DE CONFIGURAÇÃO

class EmpresaCreateRequest(BaseModel):
    """
    Schema para criação de empresas.
    """
    nome: Annotated[str, StringConstraints(min_length=3, max_length=100)]
    cnpj: Annotated[str, StringConstraints(min_length=14, max_length=14)]
    email: Annotated[str, StringConstraints(min_length=5, max_length=100)]
    telefone: Annotated[str, StringConstraints(min_length=10, max_length=15)]


class EmpresaResponse(BaseModel):
    """
    Schema para resposta de criação de empresas.
    """
    empresa_id: str
    access_token: str
    message: Optional[str] = "Empresa criada com sucesso"


class GatewayConfigRequest(BaseModel):
    """
    Schema para configuração de gateways.
    """
    pix_provider: PixProviderEnum = PixProviderEnum.sicredi
    credit_provider: CreditProviderEnum = CreditProviderEnum.rede


class HealthCheckResponse(BaseModel):
    """
    Schema para health check da API.
    """
    status: str = "OK"
    message: str = "Payment Kode API operacional"
    timestamp: datetime
    version: Optional[str] = "1.0.0"
    api_local: Optional[bool] = False