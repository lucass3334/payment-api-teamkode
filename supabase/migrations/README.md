# 🔑 Migrations - Sistema de Chaves PIX Multi-Gateway

## 📋 Status: AGUARDANDO APROVAÇÃO DO TECH LEAD

---

## Migration: `add_gateway_specific_pix_keys.sql`

### Objetivo
Permitir que empresas tenham **chaves PIX diferentes para cada gateway** (Sicredi e Asaas), possibilitando:
- ✅ Fallback entre gateways sem conflito de chaves
- ✅ Clientes omitam `chave_pix` no payload (sistema busca do banco)
- ✅ Backward compatibility (clientes ainda podem enviar chave no payload)

---

## 📊 O que foi feito

### 1. **Schema Database (Supabase)**
```sql
ALTER TABLE empresas_config
  ADD COLUMN sicredi_chave_pix TEXT,
  ADD COLUMN asaas_chave_pix TEXT;
```

**Dados migrados automaticamente**:
- Empresas com `pix_provider='sicredi'` → `chave_pix` copiada para `sicredi_chave_pix`
- Empresas com `pix_provider='asaas'` → `chave_pix` copiada para `asaas_chave_pix`

**Coluna `chave_pix` original**:
- ❗ **Mantida** para backward compatibility e webhooks
- 📌 Marcada como DEPRECATED no comentário

**Índices criados**:
- `idx_empresas_config_sicredi_chave_pix` (partial index)
- `idx_empresas_config_asaas_chave_pix` (partial index)

---

### 2. **Código Python**

#### Arquivo: `payment_kode_api/app/api/routes/payments.py`

**Linha 82 - Schema do Request**:
```python
# ANTES:
chave_pix: PixKeyType  # Obrigatório

# DEPOIS:
chave_pix: Optional[PixKeyType] = None  # Opcional
```

**Linhas 610-620 - Fluxo Sicredi**:
```python
# NOVO: Busca do banco se não vier no payload
chave_pix = payment_data.chave_pix or config.get("sicredi_chave_pix")

if not chave_pix:
    raise HTTPException(400, detail="Chave PIX Sicredi não configurada")

# Log indica origem: 'payload' ou 'banco'
logger.info(f"🔑 Usando chave: ...{chave_pix[:8]} (origem: {'payload' if payment_data.chave_pix else 'banco'})")
```

**Linhas 662-671 - Fluxo Asaas**:
```python
# NOVO: Busca do banco se não vier no payload
chave_pix = payment_data.chave_pix or config.get("asaas_chave_pix")

if not chave_pix:
    raise HTTPException(400, detail="Chave PIX Asaas não configurada")

# Usa a chave selecionada em toda lógica subsequente
```

---

## 🔄 Comportamento da API

### Cenário A: Cliente envia chave (backward compatible)
```bash
curl -X POST /payments/payment/pix \
  -H "Authorization: Bearer TOKEN" \
  -d '{
    "amount": 10.50,
    "chave_pix": "b8722c7a-0e43-43ff-b059-bf33edf4a63f"
  }'
```
✅ **Funciona igual hoje** - usa a chave enviada no payload

---

### Cenário B: Cliente NÃO envia chave (novo)
```bash
curl -X POST /payments/payment/pix \
  -H "Authorization: Bearer TOKEN" \
  -d '{
    "amount": 10.50
  }'
```
✅ **Sistema busca do banco** - usa `sicredi_chave_pix` ou `asaas_chave_pix` baseado no `pix_provider`

---

### Cenário C: Chave não configurada
```bash
curl -X POST /payments/payment/pix \
  -H "Authorization: Bearer TOKEN" \
  -d '{"amount": 10.50}'
```
❌ **HTTP 400**:
```json
{
  "detail": "Chave PIX Sicredi não configurada. Configure em empresas_config.sicredi_chave_pix ou envie no payload."
}
```

---

## 📦 Arquivos Modificados

```
✅ supabase/migrations/add_gateway_specific_pix_keys.sql (NOVO)
✅ payment_kode_api/app/api/routes/payments.py (MODIFICADO)
   - Linha 82: chave_pix → Optional
   - Linhas 610-620: Lógica Sicredi
   - Linhas 662-691: Lógica Asaas
```

---

## 🧪 Testes Necessários (Após Aprovação)

### 1. **Teste com chave no payload** (backward compatibility)
```bash
curl -X POST https://payment-api-teamkode-1.onrender.com/payments/payment/pix \
  -H "Authorization: Bearer TOKEN" \
  -d '{"amount": 10.50, "chave_pix": "b8722c7a-..."}'
```
**Esperado**: ✅ PIX criado normalmente

---

### 2. **Teste sem chave no payload** (nova funcionalidade)
```bash
curl -X POST https://payment-api-teamkode-1.onrender.com/payments/payment/pix \
  -H "Authorization: Bearer TOKEN" \
  -d '{"amount": 10.50}'
```
**Esperado**: ✅ Sistema usa chave do banco (`sicredi_chave_pix` ou `asaas_chave_pix`)

---

### 3. **Logs esperados**
```
🔍 [create_pix_payment] pix_provider configurado: sicredi
🔑 [create_pix_payment] Usando chave PIX: b8722c7a... (origem: banco)
✅ Token Sicredi renovado
📤 Enviando Pix para Sicredi...
```

---

## 🚀 Deploy

### Ordem de Execução:
1. ✅ **Executar migration SQL no Supabase** (adiciona colunas + migra dados)
2. ✅ **Deploy do código Python** (dev → main)
3. ✅ **Testes em DEV** com as 2 abordagens (com/sem chave no payload)
4. ✅ **Verificar logs** - deve mostrar "origem: banco" quando chave não enviada
5. ✅ **Deploy em produção**

### Rollback (se necessário):
```sql
ALTER TABLE empresas_config
  DROP COLUMN IF EXISTS sicredi_chave_pix,
  DROP COLUMN IF EXISTS asaas_chave_pix;

DROP INDEX IF EXISTS idx_empresas_config_sicredi_chave_pix;
DROP INDEX IF EXISTS idx_empresas_config_asaas_chave_pix;
```

---

## 📈 Benefícios

1. **Fallback entre gateways** (preparado para implementação futura)
   - Se Sicredi falhar → pode tentar Asaas com `asaas_chave_pix`
   - Se Asaas falhar → pode tentar Sicredi com `sicredi_chave_pix`

2. **Menos dados no payload**
   - Clientes não precisam enviar `chave_pix` em toda requisição
   - Chave centralizada no banco (single source of truth)

3. **Segurança**
   - Chaves PIX não trafegam desnecessariamente
   - Controle centralizado por empresa

4. **Backward compatible**
   - Nenhuma integração existente quebra
   - Clientes podem continuar enviando chave normalmente

---

## ⚠️ Notas Importantes

- ⚠️ **Coluna `chave_pix` original NÃO será removida** - necessária para webhooks
- ⚠️ **Migration é idempotente** - pode ser executada múltiplas vezes sem problemas
- ⚠️ **Não afeta integrações existentes** - totalmente backward compatible
- ⚠️ **Logs mostram origem da chave** - facilita debugging

---

## 👨‍💻 Para o Tech Lead

**Revisão necessária**:
- ✅ Migration SQL está correta?
- ✅ Lógica de fallback (payload → banco) está adequada?
- ✅ Mensagens de erro são claras?
- ✅ Logs estão adequados para troubleshooting?
- ✅ Índices estão otimizados?

**Após aprovação**:
1. Executar migration em DEV
2. Testar ambos os cenários (com/sem chave)
3. Revisar logs do Render
4. Aprovar para produção

---

**Data**: 2025-11-08
**Status**: ⏳ Aguardando aprovação do tech lead
**Impacto**: ✅ Baixo - Backward compatible
