# payment_kode_api/app/services/validators.py

from decimal import Decimal
from typing import Dict, Any, Optional, Union
import re
from datetime import datetime, date

from ..interfaces import PaymentValidatorInterface
from ..utilities.logging_config import logger


class PaymentValidator:
    """Implementação completa das validações de pagamento"""
    
    # ========== VALIDAÇÃO DE PARCELAS ==========
    
    def validate_installments_by_gateway(self, installments: int, gateway: str, amount: Decimal) -> int:
        """
        Valida e ajusta parcelas conforme regras específicas dos gateways.
        Movido de payments.py para centralizar validações.
        """
        # Normalizar installments para faixa válida
        installments = max(1, min(installments, 12))
        
        if gateway.lower() == "rede":
            # Rede: máximo 12 parcelas, valor mínimo por parcela R$ 5,00
            min_amount_per_installment = Decimal("5.00")
            max_installments_by_amount = int(amount // min_amount_per_installment)
            
            if installments > max_installments_by_amount:
                logger.warning(
                    f"⚠️ Rede: Reduzindo parcelas de {installments} para {max_installments_by_amount} "
                    f"(valor mínimo R$ 5,00 por parcela)"
                )
                installments = max(1, max_installments_by_amount)
        
        elif gateway.lower() == "asaas":
            # Asaas: máximo 12 parcelas, valor mínimo por parcela R$ 3,00
            min_amount_per_installment = Decimal("3.00")
            max_installments_by_amount = int(amount // min_amount_per_installment)
            
            if installments > max_installments_by_amount:
                logger.warning(
                    f"⚠️ Asaas: Reduzindo parcelas de {installments} para {max_installments_by_amount} "
                    f"(valor mínimo R$ 3,00 por parcela)"
                )
                installments = max(1, max_installments_by_amount)
        
        elif gateway.lower() == "sicredi":
            # Sicredi não suporta parcelamento (apenas PIX)
            if installments > 1:
                logger.warning("⚠️ Sicredi: PIX não suporta parcelamento, ajustando para 1 parcela")
                installments = 1
        
        else:
            # Gateway desconhecido - aplicar regra conservadora
            logger.warning(f"⚠️ Gateway desconhecido '{gateway}', aplicando regra padrão")
            min_amount_per_installment = Decimal("10.00")  # Regra mais restritiva
            max_installments_by_amount = int(amount // min_amount_per_installment)
            installments = max(1, min(installments, max_installments_by_amount))
        
        return installments
    
    # ========== VALIDAÇÕES DE DADOS DE PAGAMENTO ==========
    
    def validate_payment_amount(self, amount: Union[Decimal, float, str]) -> Decimal:
        """Valida e normaliza valor de pagamento"""
        try:
            if isinstance(amount, str):
                # Remove caracteres não numéricos exceto ponto e vírgula
                amount = re.sub(r'[^\d.,]', '', amount)
                # Substitui vírgula por ponto
                amount = amount.replace(',', '.')
            
            decimal_amount = Decimal(str(amount))
            
            # Validações de faixa
            if decimal_amount <= 0:
                raise ValueError("Valor deve ser maior que zero")
            
            if decimal_amount < Decimal("0.01"):
                raise ValueError("Valor mínimo é R$ 0,01")
            
            if decimal_amount > Decimal("100000.00"):
                raise ValueError("Valor máximo é R$ 100.000,00")
            
            # Normalizar para 2 casas decimais
            return decimal_amount.quantize(Decimal("0.01"))
            
        except (ValueError, TypeError) as e:
            raise ValueError(f"Valor inválido para pagamento: {amount}. Erro: {str(e)}")
    
    def validate_transaction_id(self, transaction_id: str) -> str:
        """Valida formato do transaction_id"""
        if not transaction_id or not isinstance(transaction_id, str):
            raise ValueError("Transaction ID é obrigatório e deve ser string")
        
        # Remove espaços
        transaction_id = transaction_id.strip()
        
        # Validar comprimento
        if len(transaction_id) < 6:
            raise ValueError("Transaction ID deve ter pelo menos 6 caracteres")
        
        if len(transaction_id) > 35:
            raise ValueError("Transaction ID deve ter no máximo 35 caracteres")
        
        # Validar caracteres (apenas alfanuméricos, hífen e underscore)
        if not re.match(r'^[a-zA-Z0-9_-]+$', transaction_id):
            raise ValueError("Transaction ID deve conter apenas letras, números, hífen e underscore")
        
        return transaction_id
    
    def validate_txid(self, txid: str) -> str:
        """Valida formato do TXID para PIX (Sicredi)"""
        if not txid or not isinstance(txid, str):
            raise ValueError("TXID é obrigatório para PIX")
        
        # Remove espaços e converte para uppercase
        txid = txid.strip().upper()
        
        # TXID deve ter entre 1 e 35 caracteres
        if len(txid) < 1 or len(txid) > 35:
            raise ValueError("TXID deve ter entre 1 e 35 caracteres")
        
        # Apenas caracteres alfanuméricos (Sicredi recomenda hex)
        if not re.match(r'^[A-Z0-9]+$', txid):
            raise ValueError("TXID deve conter apenas letras maiúsculas e números")
        
        return txid
    
    # ========== VALIDAÇÕES DE DADOS DO CLIENTE ==========
    
    def validate_cpf_cnpj(self, document: str) -> str:
        """Valida e limpa CPF ou CNPJ"""
        if not document:
            raise ValueError("CPF/CNPJ é obrigatório")
        
        # Remove formatação
        clean_doc = re.sub(r'[^0-9]', '', document)
        
        if len(clean_doc) == 11:
            # Validação básica de CPF
            if clean_doc == clean_doc[0] * 11:  # Todos os dígitos iguais
                raise ValueError("CPF inválido")
            return clean_doc
        elif len(clean_doc) == 14:
            # Validação básica de CNPJ
            if clean_doc == clean_doc[0] * 14:  # Todos os dígitos iguais
                raise ValueError("CNPJ inválido")
            return clean_doc
        else:
            raise ValueError("CPF deve ter 11 dígitos ou CNPJ deve ter 14 dígitos")
    
    def validate_phone(self, phone: str) -> str:
        """Valida e limpa telefone"""
        if not phone:
            raise ValueError("Telefone é obrigatório")
        
        # Remove formatação
        clean_phone = re.sub(r'[^0-9]', '', phone)
        
        # Validar comprimento (10-11 dígitos no Brasil)
        if len(clean_phone) < 10 or len(clean_phone) > 11:
            raise ValueError("Telefone deve ter 10 ou 11 dígitos")
        
        return clean_phone
    
    def validate_email(self, email: str) -> str:
        """Valida formato de email"""
        if not email:
            raise ValueError("Email é obrigatório")
        
        email = email.strip().lower()
        
        # Validação básica de email
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            raise ValueError("Formato de email inválido")
        
        return email
    
    # ========== VALIDAÇÕES DE CARTÃO ==========
    
    def validate_card_number(self, card_number: str) -> str:
        """Valida número do cartão"""
        if not card_number:
            raise ValueError("Número do cartão é obrigatório")
        
        # Remove espaços e hífens
        clean_number = re.sub(r'[\s-]', '', card_number)
        
        # Deve conter apenas números
        if not clean_number.isdigit():
            raise ValueError("Número do cartão deve conter apenas dígitos")
        
        # Validar comprimento (13-19 dígitos)
        if len(clean_number) < 13 or len(clean_number) > 19:
            raise ValueError("Número do cartão deve ter entre 13 e 19 dígitos")
        
        return clean_number
    
    def validate_expiration_date(self, month: str, year: str) -> tuple[str, str]:
        """Valida data de expiração do cartão"""
        try:
            month_int = int(month)
            year_int = int(year)
            
            # Validar mês
            if month_int < 1 or month_int > 12:
                raise ValueError("Mês deve estar entre 1 e 12")
            
            # Validar ano (assumindo 4 dígitos)
            current_year = datetime.now().year
            if year_int < current_year or year_int > current_year + 20:
                raise ValueError(f"Ano deve estar entre {current_year} e {current_year + 20}")
            
            # Verificar se não está expirado
            current_month = datetime.now().month
            if year_int == current_year and month_int < current_month:
                raise ValueError("Cartão está expirado")
            
            return f"{month_int:02d}", str(year_int)
            
        except ValueError as e:
            if "invalid literal" in str(e):
                raise ValueError("Mês e ano devem ser números válidos")
            raise
    
    def validate_security_code(self, cvv: str) -> str:
        """Valida código de segurança do cartão"""
        if not cvv:
            raise ValueError("Código de segurança é obrigatório")
        
        # Remove espaços
        clean_cvv = cvv.strip()
        
        # Deve conter apenas números
        if not clean_cvv.isdigit():
            raise ValueError("Código de segurança deve conter apenas dígitos")
        
        # Deve ter 3 ou 4 dígitos
        if len(clean_cvv) < 3 or len(clean_cvv) > 4:
            raise ValueError("Código de segurança deve ter 3 ou 4 dígitos")
        
        return clean_cvv
    
    # ========== VALIDAÇÕES DE PIX ==========
    
    def validate_pix_key(self, pix_key: str) -> str:
        """Valida chave PIX"""
        if not pix_key:
            raise ValueError("Chave PIX é obrigatória")
        
        pix_key = pix_key.strip()
        
        # Validações por tipo de chave PIX
        if re.match(r'^[0-9]{11}$', pix_key):
            # CPF
            return pix_key
        elif re.match(r'^[0-9]{14}$', pix_key):
            # CNPJ
            return pix_key
        elif re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', pix_key):
            # Email
            return pix_key.lower()
        elif re.match(r'^\+55[0-9]{10,11}$', pix_key):
            # Telefone com código do país
            return pix_key
        elif re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', pix_key.lower()):
            # Chave aleatória (UUID)
            return pix_key.lower()
        else:
            raise ValueError("Formato de chave PIX inválido")
    
    def validate_due_date(self, due_date: Union[date, str]) -> date:
        """Valida data de vencimento para PIX"""
        if isinstance(due_date, str):
            try:
                due_date = datetime.strptime(due_date, "%Y-%m-%d").date()
            except ValueError:
                raise ValueError("Data de vencimento deve estar no formato YYYY-MM-DD")
        
        if not isinstance(due_date, date):
            raise ValueError("Data de vencimento deve ser uma data válida")
        
        # Não pode ser no passado
        if due_date < datetime.now().date():
            raise ValueError("Data de vencimento não pode ser no passado")
        
        # Não pode ser muito distante (máximo 1 ano)
        max_date = datetime.now().date().replace(year=datetime.now().year + 1)
        if due_date > max_date:
            raise ValueError("Data de vencimento não pode ser superior a 1 ano")
        
        return due_date
    
    # ========== VALIDAÇÃO COMPLETA DE PAYLOADS ==========
    
    def validate_pix_payment_data(self, payment_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validação completa para pagamentos PIX"""
        validated = {}
        
        # Campos obrigatórios
        validated["amount"] = self.validate_payment_amount(payment_data["amount"])
        validated["chave_pix"] = self.validate_pix_key(payment_data["chave_pix"])
        
        # Transaction ID (opcional, será gerado se não fornecido)
        if payment_data.get("transaction_id"):
            validated["transaction_id"] = self.validate_transaction_id(payment_data["transaction_id"])
        
        # TXID (opcional, será gerado se não fornecido)
        if payment_data.get("txid"):
            validated["txid"] = self.validate_txid(payment_data["txid"])
        
        # Data de vencimento (opcional)
        if payment_data.get("due_date"):
            validated["due_date"] = self.validate_due_date(payment_data["due_date"])
        
        # Dados do devedor (obrigatórios se tem due_date)
        if validated.get("due_date"):
            if not payment_data.get("nome_devedor"):
                raise ValueError("Nome do devedor é obrigatório para cobrança com vencimento")
            
            validated["nome_devedor"] = payment_data["nome_devedor"].strip()
            
            if payment_data.get("cpf"):
                validated["cpf"] = self.validate_cpf_cnpj(payment_data["cpf"])
            elif payment_data.get("cnpj"):
                validated["cnpj"] = self.validate_cpf_cnpj(payment_data["cnpj"])
            else:
                raise ValueError("CPF ou CNPJ é obrigatório para cobrança com vencimento")
        
        # Email (opcional)
        if payment_data.get("email"):
            validated["email"] = self.validate_email(payment_data["email"])
        
        return validated
    
    def validate_credit_card_payment_data(self, payment_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validação completa para pagamentos com cartão"""
        validated = {}
        
        # Campos obrigatórios
        validated["amount"] = self.validate_payment_amount(payment_data["amount"])
        
        # Parcelas
        installments = payment_data.get("installments", 1)
        validated["installments"] = max(1, min(int(installments), 12))
        
        # Transaction ID (opcional)
        if payment_data.get("transaction_id"):
            validated["transaction_id"] = self.validate_transaction_id(payment_data["transaction_id"])
        
        # Validar dados do cartão OU token
        if payment_data.get("card_token"):
            validated["card_token"] = payment_data["card_token"].strip()
        elif payment_data.get("card_data"):
            card_data = payment_data["card_data"]
            validated["card_data"] = {
                "card_number": self.validate_card_number(card_data["card_number"]),
                "cardholder_name": card_data["cardholder_name"].strip(),
                "security_code": self.validate_security_code(card_data["security_code"])
            }
            
            month, year = self.validate_expiration_date(
                card_data["expiration_month"], 
                card_data["expiration_year"]
            )
            validated["card_data"]["expiration_month"] = month
            validated["card_data"]["expiration_year"] = year
        else:
            raise ValueError("É necessário fornecer card_token ou card_data")
        
        return validated


# ========== EXPORTS ==========

__all__ = [
    "PaymentValidator",
]