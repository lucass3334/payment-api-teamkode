# payment_kode_api/app/services/card_tokenization_service.py

import hashlib
import json
import uuid
import re
from typing import Dict, Any, Optional, Protocol
from datetime import datetime, timezone, timedelta
from ..utilities.logging_config import logger


class CardTokenizationServiceInterface(Protocol):
    """Interface para abstração do serviço de tokenização."""
    
    def create_card_token(self, empresa_id: str, card_data: Dict[str, Any]) -> Dict[str, Any]: ...
    def verify_card_hash(self, empresa_id: str, stored_hash: str, card_number: str, security_code: str) -> bool: ...
    def detect_card_brand(self, card_number: str) -> str: ...
    def is_token_expired(self, expires_at: str) -> bool: ...


class CardTokenizationService:
    """
    Serviço de tokenização simples e seguro para cartões.
    
    ✅ Características:
    - Não armazena dados sensíveis (número, CVV)
    - Hash seguro para verificação futura
    - Compatível com múltiplos gateways
    - Sem dependência de RSA/Sicredi
    """
    
    def __init__(self, token_expiry_days: int = 730):  # 2 anos padrão
        self.token_expiry_days = token_expiry_days
        self.hash_version = "v1"
    
    def create_card_token(self, empresa_id: str, card_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Cria token seguro para cartão sem armazenar dados sensíveis.
        
        Args:
            empresa_id: ID da empresa
            card_data: Dados do cartão (número, CVV, etc.)
            
        Returns:
            Dict com dados seguros para armazenar
        """
        try:
            # Validar dados obrigatórios
            required_fields = ["card_number", "security_code", "expiration_month", "expiration_year", "cardholder_name"]
            missing_fields = [field for field in required_fields if not card_data.get(field)]
            
            if missing_fields:
                raise ValueError(f"Campos obrigatórios ausentes: {missing_fields}")
            
            # Extrair e limpar dados
            card_number = self._clean_card_number(card_data["card_number"])
            security_code = str(card_data["security_code"]).strip()
            
            # Validações básicas
            self._validate_card_data(card_number, security_code, card_data)
            
            # Gerar token único
            card_token = str(uuid.uuid4())
            
            # Criar hash seguro dos dados sensíveis
            card_hash = self._create_card_hash(empresa_id, card_number, security_code)
            
            # Detectar bandeira
            card_brand = self.detect_card_brand(card_number)
            
            # Calcular expiração do token
            expires_at = self._calculate_token_expiry()
            
            # Dados seguros para armazenar
            safe_data = {
                "card_token": card_token,
                "empresa_id": empresa_id,
                "cardholder_name": card_data["cardholder_name"].strip(),
                "last_four_digits": card_number[-4:],
                "card_brand": card_brand,
                "expiration_month": str(card_data["expiration_month"]).zfill(2),
                "expiration_year": str(card_data["expiration_year"]),
                "card_hash": card_hash,
                "expires_at": expires_at,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "metadata": {
                    "tokenization_method": f"simple_hash_{self.hash_version}",
                    "hash_algorithm": "sha256",
                    "created_by": "CardTokenizationService"
                }
            }
            
            logger.info(f"✅ Token criado com sucesso para empresa {empresa_id} | Bandeira: {card_brand} | Finais: ****{card_number[-4:]}")
            return safe_data
            
        except Exception as e:
            logger.error(f"❌ Erro ao criar token para empresa {empresa_id}: {e}")
            raise
    
    def verify_card_hash(self, empresa_id: str, stored_hash: str, card_number: str, security_code: str) -> bool:
        """
        Verifica se dados do cartão batem com o hash armazenado.
        Útil para validar pagamentos sem descriptografar.
        """
        try:
            card_number = self._clean_card_number(card_number)
            expected_hash = self._create_card_hash(empresa_id, card_number, security_code)
            
            # Comparação segura contra timing attacks
            return hashlib.sha256(stored_hash.encode()).hexdigest() == hashlib.sha256(expected_hash.encode()).hexdigest()
            
        except Exception as e:
            logger.error(f"❌ Erro ao verificar hash: {e}")
            return False
    
    def detect_card_brand(self, card_number: str) -> str:
        """Detecta bandeira do cartão baseado no número."""
        clean_number = self._clean_card_number(card_number)
        
        # Regras de detecção das bandeiras
        if clean_number.startswith('4'):
            return 'VISA'
        elif clean_number.startswith(('5', '2')):
            return 'MASTERCARD'
        elif clean_number.startswith(('34', '37')):
            return 'AMEX'
        elif clean_number.startswith('6'):
            return 'DISCOVER'
        elif clean_number.startswith(('38', '60')):
            return 'HIPERCARD'
        elif clean_number.startswith(('4011', '4312', '4389', '4514', '4573')):
            return 'ELO'
        else:
            return 'UNKNOWN'
    
    def is_token_expired(self, expires_at: str) -> bool:
        """Verifica se token expirou."""
        try:
            if not expires_at:
                return True
                
            expiry_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
            if expiry_dt.tzinfo is None:
                expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
                
            return expiry_dt < datetime.now(timezone.utc)
            
        except Exception as e:
            logger.warning(f"⚠️ Erro ao verificar expiração do token: {e}")
            return True  # Consideramos expirado em caso de erro
    
    def _clean_card_number(self, card_number: str) -> str:
        """Remove espaços, hífens e outros caracteres do número do cartão."""
        return re.sub(r'[^0-9]', '', str(card_number))
    
    def _validate_card_data(self, card_number: str, security_code: str, card_data: Dict[str, Any]) -> None:
        """Validações básicas dos dados do cartão."""
        # Validar número do cartão
        if not card_number.isdigit():
            raise ValueError("Número do cartão deve conter apenas dígitos")
        
        if len(card_number) < 13 or len(card_number) > 19:
            raise ValueError("Número do cartão deve ter entre 13 e 19 dígitos")
        
        # Validar CVV
        if not security_code.isdigit():
            raise ValueError("Código de segurança deve conter apenas dígitos")
        
        if len(security_code) < 3 or len(security_code) > 4:
            raise ValueError("Código de segurança deve ter 3 ou 4 dígitos")
        
        # Validar mês
        try:
            month = int(card_data["expiration_month"])
            if month < 1 or month > 12:
                raise ValueError("Mês de expiração deve estar entre 1 e 12")
        except (ValueError, TypeError):
            raise ValueError("Mês de expiração inválido")
        
        # Validar ano
        try:
            year = int(card_data["expiration_year"])
            current_year = datetime.now().year
            
            # Aceitar tanto 2 dígitos (25) quanto 4 dígitos (2025)
            if year < 100:
                year += 2000
            
            if year < current_year or year > current_year + 20:
                raise ValueError(f"Ano de expiração deve estar entre {current_year} e {current_year + 20}")
                
        except (ValueError, TypeError):
            raise ValueError("Ano de expiração inválido")
        
        # Validar nome do portador
        if not card_data.get("cardholder_name", "").strip():
            raise ValueError("Nome do portador é obrigatório")
    
    def _create_card_hash(self, empresa_id: str, card_number: str, security_code: str) -> str:
        """
        Cria hash seguro e único dos dados sensíveis.
        
        Usa salt único por empresa + versão + período para:
        - Evitar rainbow tables
        - Permitir rotação de hash
        - Manter unicidade por empresa
        """
        # Salt único inclui empresa, versão e período (mês/ano)
        period = datetime.now().strftime('%Y%m')  # YYYYMM para rotação mensal
        salt = f"{empresa_id}:card_security_{self.hash_version}:{period}"
        
        # Dados para hash: salt + número + cvv
        data_to_hash = f"{salt}:{card_number}:{security_code}"
        
        # Hash SHA-256 
        return hashlib.sha256(data_to_hash.encode('utf-8')).hexdigest()
    
    def _calculate_token_expiry(self) -> str:
        """Calcula data de expiração do token."""
        expiry = datetime.now(timezone.utc) + timedelta(days=self.token_expiry_days)
        return expiry.isoformat()


# ========== IMPLEMENTAÇÃO PARA DEPENDENCY INJECTION ==========

class CardTokenizationServiceImpl(CardTokenizationService):
    """Implementação concreta para dependency injection."""
    pass


# ========== FACTORY FUNCTIONS ==========

def create_card_tokenization_service(expiry_days: int = 730) -> CardTokenizationServiceInterface:
    """Factory function para criar serviço de tokenização."""
    return CardTokenizationServiceImpl(token_expiry_days=expiry_days)


def create_test_tokenization_service() -> CardTokenizationServiceInterface:
    """Factory function para testes (tokens expiram em 1 dia)."""
    return CardTokenizationServiceImpl(token_expiry_days=1)


# ========== UTILITIES ==========

class CardTokenizationError(Exception):
    """Exceção específica para erros de tokenização."""
    pass


class CardValidationError(CardTokenizationError):
    """Exceção para erros de validação de cartão."""
    pass


class TokenExpiredError(CardTokenizationError):
    """Exceção para tokens expirados."""
    pass


# ========== EXPORTS ==========

__all__ = [
    "CardTokenizationService",
    "CardTokenizationServiceInterface", 
    "CardTokenizationServiceImpl",
    "create_card_tokenization_service",
    "create_test_tokenization_service",
    "CardTokenizationError",
    "CardValidationError", 
    "TokenExpiredError",
]