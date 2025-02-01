# Payment Kode API

Uma API para gestão de pagamentos com fallback entre gateways (Sicredi, Rede e Asaas), com suporte a multiempresas.

## ✨ Recursos Principais

- Suporte a **multiempresas** com configurações individuais por empresa.
- Integração com **Sicredi (Pix)**, **Rede (Cartão de Crédito)** e **Asaas (Pix e Cartão de Crédito)**.
- **Fallback** automático para garantir processamentos confiáveis.
- Webhooks para notificações de pagamento.
- Uso de **Redis** para cache e enfileiramento de tarefas assíncronas.
- Suporte a **certificados mTLS** para autenticação com Sicredi sem armazenamento local.

---

## 🛠️ Requisitos

- **Docker e Docker Compose**
- **Python 3.9+**
- **Poetry** para gerenciamento de dependências

---

## 📂 Configuração

### 1. Configurando Variáveis de Ambiente

Crie um arquivo `.env` na raiz do projeto baseado no `.env.example`:

```env
# 🛠️ Configuração do Banco de Dados
SUPABASE_URL=https://sua-url.supabase.co
SUPABASE_KEY=sua-chave-supabase

# 🤖 Configuração do Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=sua-senha-redis

# 💳 Credenciais dos Gateways de Pagamento
SICREDI_API_KEY=sua-chave-sicredi
ASAAS_API_KEY=sua-chave-asaas
REDE_API_KEY=sua-chave-rede

# 🌐 Webhooks
WEBHOOK_PIX=https://seu-webhook.com/pix
WEBHOOK_CARTAO=https://seu-webhook.com/credit-card

# 🔒 Ambiente
USE_SANDBOX=true  # true para ambiente de teste, false para produção
SICREDI_ENV=homologation  # 'homologation' ou 'production'
```

### 2. Configuração Multiempresas
As credenciais dos gateways (Sicredi, Asaas, Rede) são configuradas por empresa na tabela `empresas_config`. Certifique-se de que cada empresa cadastrada tenha suas credenciais associadas corretamente.

---

## 🚲 Executando o Projeto

### 1. Rodando com Docker

```sh
docker-compose up --build
```

### 2. Rodando Localmente (Sem Docker)

1. Instale as dependências:
   ```sh
   poetry install
   ```
2. Execute a aplicação:
   ```sh
   poetry run uvicorn payment_kode_api.app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

---

## 🌟 Endpoints Principais

### Criar Empresa
```http
POST /empresa
```
**Request Body:**
```json
{
  "nome": "Minha Empresa",
  "cnpj": "12345678000199",
  "email": "contato@empresa.com",
  "telefone": "11999999999"
}
```
**Response:**
```json
{
  "empresa_id": "uuid-gerado"
}
```

### Criar Pagamento Pix
```http
POST /payment/pix
```
**Request Body:**
```json
{
  "empresa_id": "uuid-da-empresa",
  "amount": 150.00,
  "chave_pix": "chave-do-pagamento",
  "txid": "txid-unico",
  "webhook_url": "https://seu-webhook.com"
}
```

### Criar Pagamento com Cartão de Crédito
```http
POST /payment/credit-card
```
**Request Body:**
```json
{
  "empresa_id": "uuid-da-empresa",
  "amount": 250.00,
  "installments": 3,
  "card_data": {
    "cardholder_name": "João Silva",
    "card_number": "4111111111111111",
    "expiration_month": "12",
    "expiration_year": "2025",
    "security_code": "123"
  },
  "webhook_url": "https://seu-webhook.com"
}
```

### Webhook Pix (Opcional)
```http
POST /webhook/pix
```

### Webhook Cartão de Crédito (Opcional)
```http
POST /webhook/credit-card
```
---

## 🔎 To-Do List
- [ ] Implementar suporte a **chargebacks**
- [ ] Melhorar logs de erros
- [ ] Criar interface de gestão no frontend

💪 Feito com dedicação por [Lucas Souza](https://github.com/lucass3334)

