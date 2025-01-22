# Payment Kode API

Uma API para gestão de pagamentos com fallback entre gateways (Sicredi, Rede e Asaas).

## Requisitos

- Docker e Docker Compose
- Python 3.9+
- Poetry para gerenciamento de dependências

## Configuração

### Configurando Variáveis de Ambiente
Crie um arquivo `.env` na raiz do projeto baseado no `.env.example`:

```env
SUPABASE_URL=https://sua-url.supabase.co
SUPABASE_KEY=sua-chave-supabase
REDIS_HOST=localhost
REDIS_PORT=6379
SICREDI_API_KEY=sua-chave-sicredi
ASAAS_API_KEY=sua-chave-asaas
REDE_API_KEY=sua-chave-rede
