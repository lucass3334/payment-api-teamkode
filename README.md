# Payment Kode API

Uma API robusta para gestão de pagamentos com suporte a múltiplos gateways (Sicredi, Rede e Asaas), sistema de fallback automático e arquitetura multiempresa.

## ✨ Recursos Principais

- **Multiempresas**: Cada empresa possui suas próprias credenciais e configurações
- **Múltiplos Gateways**: Sicredi (PIX), Rede (Cartão) e Asaas (PIX/Cartão)
- **Fallback Automático**: Troca automaticamente entre provedores em caso de falha
- **Autenticação mTLS**: Certificados digitais para Sicredi via Supabase Storage
- **Tokenização de Cartões**: Armazenamento seguro de dados de cartão
- **Estornos**: Sistema completo de refund para PIX e cartão
- **Webhooks**: Notificações em tempo real sobre status de pagamentos
- **Sistema de Polling**: Monitoramento automático de status via APIs dos gateways

---

## 🏗️ Arquitetura

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   FastAPI App   │    │   Supabase DB   │    │ Supabase Storage│
│   (Port 8080)   │◄──►│   (Postgres)    │    │  (Certificados) │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Gateway APIs   │    │    Payments     │    │   mTLS Certs    │
│ Sicredi│Rede│   │    │   Empresas      │    │   (em memória)  │
│       Asaas     │    │   Tokens        │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

---

## 🛠️ Tecnologias

- **Backend**: FastAPI + Python 3.9+
- **Banco de Dados**: Supabase (PostgreSQL)
- **Storage**: Supabase Storage (certificados mTLS)
- **Containerização**: Docker + Docker Compose
- **Gerenciamento de Dependências**: Poetry
- **Logging**: Loguru
- **HTTP Client**: httpx (async)
- **Criptografia**: cryptography (RSA, mTLS)

---

## 📋 Pré-requisitos

- Docker e Docker Compose
- Python 3.9+ (para desenvolvimento local)
- Poetry (para gerenciamento de dependências)
- Conta no Supabase
- Credenciais dos gateways de pagamento

---

## 🚀 Instalação e Configuração

### 1. Clone o Repositório

```bash
git clone https://github.com/seu-usuario/payment-kode-api.git
cd payment-kode-api
```

### 2. Configure as Variáveis de Ambiente

Copie o arquivo de exemplo e configure:

```bash
cp .env.example .env
```

**Edite o `.env`:**

```env
# 🔹 Configuração de Banco de Dados
SUPABASE_URL=https://sua-url.supabase.co
SUPABASE_KEY=sua-chave-supabase

# 🔹 Configuração do Redis (Opcional - atualmente desabilitado)
# REDIS_URL=redis://localhost:6379

# 🔹 Controle de Ambiente
USE_SANDBOX=true
SICREDI_ENV=homologation
API_LOCAL=false

# 🔹 Configuração de Webhooks
WEBHOOK_PIX=https://seu-webhook.com/pix

# 🔹 Debug
DEBUG=true
```

### 3. Execute com Docker

```bash
# Modo desenvolvimento
docker-compose up --build

# Modo produção (background)
docker-compose up -d --build
```

### 4. Ou Execute Localmente

```bash
# Instale as dependências
poetry install

# Execute a aplicação
poetry run uvicorn payment_kode_api.app.main:app --host 0.0.0.0 --port 8080 --reload
```

---

## 📚 Estrutura do Banco de Dados

### Tabelas Principais

#### `empresas`
```sql
- empresa_id (UUID, PK)
- nome (VARCHAR)
- cnpj (VARCHAR, UNIQUE)
- email (VARCHAR)
- telefone (VARCHAR)
- access_token (VARCHAR, UNIQUE)
- created_at, updated_at
```

#### `empresas_config`
```sql
- id (UUID, PK)
- empresa_id (UUID, FK)
- asaas_api_key (VARCHAR)
- sicredi_client_id (VARCHAR)
- sicredi_client_secret (VARCHAR)
- sicredi_token (VARCHAR) -- Cache do token
- sicredi_token_expires_at (TIMESTAMP)
- rede_pv (VARCHAR)
- rede_api_key (VARCHAR)
- pix_provider (VARCHAR) -- 'sicredi' ou 'asaas'
- credit_provider (VARCHAR) -- 'rede' ou 'asaas'
- webhook_pix (VARCHAR)
- chave_pix (VARCHAR)
- use_sandbox (BOOLEAN)
```

#### `payments`
```sql
- id (UUID, PK)
- empresa_id (UUID, FK)
- transaction_id (VARCHAR, UNIQUE)
- txid (VARCHAR) -- Para PIX
- amount (DECIMAL)
- payment_type (VARCHAR) -- 'pix' ou 'credit_card'
- status (VARCHAR) -- 'pending', 'approved', 'failed', 'canceled'
- webhook_url (VARCHAR)
- rede_tid (VARCHAR) -- Para estornos Rede
- authorization_code (VARCHAR)
- return_code (VARCHAR)
- data_marketing (JSONB)
- created_at, updated_at
```

#### `cartoes_tokenizados`
```sql
- id (UUID, PK)
- empresa_id (UUID, FK)
- customer_id (VARCHAR)
- card_token (VARCHAR, UNIQUE)
- encrypted_card_data (TEXT)
- expires_at (TIMESTAMP)
```

#### `empresas_certificados`
```sql
- id (UUID, PK)
- empresa_id (UUID, FK)
- sicredi_cert_base64 (TEXT)
- sicredi_key_base64 (TEXT)
- sicredi_ca_base64 (TEXT)
```

---

## 🔐 Sistema de Certificados mTLS

O Sicredi exige autenticação mTLS. Os certificados são armazenados no Supabase Storage e carregados em memória:

### Estrutura no Storage
```
certificados-sicredi/
└── {empresa_id}/
    ├── sicredi-cert.pem  (Certificado da empresa)
    ├── sicredi-key.key   (Chave privada)
    └── sicredi-ca.pem    (Cadeia de certificação)
```

### Upload de Certificados
```http
POST /certificados/upload
Content-Type: multipart/form-data

empresa_id: {uuid}
arquivo: sicredi-cert.pem
```

### Validação
```http
GET /certificados/validate?empresa_id={uuid}
```

---

## 📡 Endpoints da API

### Autenticação
Todas as rotas (exceto criação de empresa) usam Bearer Token:
```http
Authorization: Bearer {access_token}
```

### 🏢 Empresas

#### Criar Empresa
```http
POST /empresas/empresa
Content-Type: application/json

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
  "empresa_id": "uuid-gerado",
  "access_token": "token-de-acesso"
}
```

#### Configurar Gateways
```http
POST /empresas/empresa/configurar_gateway
Authorization: Bearer {access_token}

{
  "pix_provider": "sicredi",      # ou "asaas"
  "credit_provider": "rede"       # ou "asaas"
}
```

### 💳 Pagamentos

#### PIX (Sicredi/Asaas)
```http
POST /payments/payment/pix
Authorization: Bearer {access_token}

{
  "amount": 150.00,
  "chave_pix": "usuario@email.com",
  "txid": "txid-opcional",
  "webhook_url": "https://seu-webhook.com",
  "due_date": "2024-12-31",      # Opcional (cobrança com vencimento)
  "nome_devedor": "João Silva",   # Obrigatório se due_date
  "cpf": "12345678901",          # Obrigatório se due_date
  "data_marketing": {            # Opcional
    "origem": "site",
    "campanha": "black-friday"
  }
}
```

**Response:**
```json
{
  "status": "approved",
  "transaction_id": "uuid",
  "pix_link": "00020126...",
  "qr_code_base64": "data:image/png;base64,...",
  "expiration": 900,
  "refund_deadline": "2024-12-07T23:59:59"
}
```

#### Cartão de Crédito (Rede/Asaas)
```http
POST /payments/payment/credit-card
Authorization: Bearer {access_token}

{
  "amount": 250.00,
  "installments": 3,
  "webhook_url": "https://seu-webhook.com",
  "card_data": {
    "cardholder_name": "João Silva",
    "card_number": "4111111111111111",
    "expiration_month": "12",
    "expiration_year": "2025",
    "security_code": "123"
  }
}
```

### 🔄 Estornos

#### Estorno PIX
```http
POST /payments/payment/pix/refund
Authorization: Bearer {access_token}

{
  "transaction_id": "uuid-da-transacao",
  "amount": 50.00  # Opcional (senão, estorno total)
}
```

#### Estorno Cartão
```http
POST /payments/payment/credit-card/refund
Authorization: Bearer {access_token}

{
  "transaction_id": "uuid-da-transacao",
  "amount": 100.00  # Opcional (senão, estorno total)
}
```

### 🎯 Tokenização

#### Tokenizar Cartão
```http
POST /payments/payment/tokenize-card
Authorization: Bearer {access_token}

{
  "customer_id": "cliente-123",
  "card_number": "4111111111111111",
  "expiration_month": "12",
  "expiration_year": "2025",
  "security_code": "123",
  "cardholder_name": "João Silva"
}
```

### 🔗 Webhooks

A API enviará notificações para sua URL configurada:

```json
{
  "transaction_id": "uuid",
  "status": "approved",
  "provedor": "sicredi",
  "txid": "ABC123",
  "data_marketing": {
    "origem": "site",
    "campanha": "black-friday"
  },
  "payload": {
    // Resposta bruta do gateway
  }
}
```

---

## ⚙️ Configuração dos Gateways

### Sicredi (PIX)
1. Obtenha certificados mTLS do Sicredi
2. Faça upload via `/certificados/upload`
3. Configure credenciais na tabela `empresas_config`:
   - `sicredi_client_id`
   - `sicredi_client_secret`
   - `sicredi_env` (production/homologation)

### Rede (Cartão)
Configure na tabela `empresas_config`:
- `rede_pv` (Número do estabelecimento)
- `rede_api_key` (Chave de integração)

### Asaas (PIX/Cartão)
Configure na tabela `empresas_config`:
- `asaas_api_key`
- `use_sandbox` (true/false)

---

## 🔄 Sistema de Fallback

A API implementa fallback automático:

### PIX
1. **Primário**: Sicredi (mais comum)
2. **Fallback**: Asaas

### Cartão de Crédito
1. **Primário**: Rede (taxas menores)
2. **Fallback**: Asaas

### Estornos
A API tenta o mesmo provedor do pagamento original e faz fallback se necessário.

---

## 📊 Monitoramento e Logs

### Health Check
```http
GET /
```

### Logs
- Console: nível INFO
- Arquivo: `logs/app.log` (rotativo, 10MB, 10 dias)

### Validação de Certificados
```http
GET /certificados/validate?empresa_id={uuid}
```

### Token Sicredi
```http
GET /auth_gateway/sicredi_token?empresa_id={uuid}
```

---

## 🧪 Testes

```bash
# Execute os testes
poetry run pytest

# Com coverage
poetry run pytest --cov=payment_kode_api

# Testes específicos
poetry run pytest payment_kode_api/tests/test_payments.py
```

---

## 📄 Estrutura do Projeto

```
payment_kode_api/
├── app/
│   ├── api/routes/           # Endpoints da API
│   │   ├── payments.py       # Pagamentos PIX/Cartão
│   │   ├── refunds.py        # Estornos
│   │   ├── empresas.py       # Gestão de empresas
│   │   ├── webhooks.py       # Recebimento de webhooks
│   │   └── upload_certificados.py # Upload de certificados
│   ├── services/
│   │   ├── gateways/         # Clientes dos gateways
│   │   │   ├── sicredi_client.py
│   │   │   ├── rede_client.py
│   │   │   └── asaas_client.py
│   │   ├── config_service.py # Gestão de configurações
│   │   └── webhook_services.py # Envio de webhooks
│   ├── database/             # Camada de dados
│   │   ├── database.py       # Operações principais
│   │   ├── customers.py      # Gestão de clientes Asaas
│   │   └── supabase_storage.py # Storage de certificados
│   ├── security/             # Autenticação e criptografia
│   ├── utilities/            # Utilitários
│   └── models/               # Schemas e modelos
├── tests/                    # Testes automatizados
├── docker-compose.yml        # Configuração Docker
├── Dockerfile                # Imagem da aplicação
└── pyproject.toml           # Dependências Poetry
```

---

## 🚨 Troubleshooting

### Erro de Certificado Sicredi
```
certificate verify failed: unable to get local issuer certificate
```
**Solução**: Verifique se `sicredi-ca.pem` contém a cadeia completa (intermediário + raiz).

### Token Sicredi Expirado
A API gerencia automaticamente a renovação, mas verifique:
- Credenciais válidas em `empresas_config`
- Certificados válidos no Storage

### Pagamento Falhou em Todos os Gateways
Verifique:
- Credenciais dos gateways
- Configuração de `pix_provider` e `credit_provider`
- Logs da aplicação

---

## 🔒 Segurança

- **Certificados mTLS**: Armazenados com segurança no Supabase Storage
- **Tokens de Cartão**: Criptografados com RSA por empresa
- **Access Tokens**: Únicos por empresa
- **HTTPS**: Obrigatório em produção
- **Logs**: Não expõem dados sensíveis

---

## 📈 Roadmap

- [ ] Interface de gestão (frontend)
- [ ] Suporte a mais gateways
- [ ] Sistema de chargebacks
- [ ] Analytics de pagamentos
- [ ] Webhooks com retry automático
- [ ] Rate limiting
- [ ] Documentação interativa (Swagger)

---

## 🤝 Contribuição

1. Fork o projeto
2. Crie uma branch (`git checkout -b feature/nova-funcionalidade`)
3. Commit suas mudanças (`git commit -am 'Adiciona nova funcionalidade'`)
4. Push para a branch (`git push origin feature/nova-funcionalidade`)
5. Abra um Pull Request

---

## 📞 Suporte

- **Email**: administrativo@teamkode.com
- **Issues**: [GitHub Issues](https://github.com/lucass3334/payment-kode-api/issues)
- **Documentação**: Este README + comentários no código

---

## 📜 Licença

Este projeto está licenciado sob a Licença MIT - veja o arquivo [LICENSE](LICENSE) para detalhes.

---

**Desenvolvido com ❤️ pela [Team Kode](https://github.com/lucass3334)**
