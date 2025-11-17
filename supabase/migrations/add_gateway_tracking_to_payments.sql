-- Migration: Adicionar rastreamento de gateway na tabela payments
-- Objetivo: Rastrear qual gateway (Sicredi, Asaas, Rede) processou cada pagamento
-- Data: 2025-11-13
-- Context: Sistema multi-gateway precisa saber qual gateway usar para polling de status

-- 1. Adicionar colunas para rastrear gateway usado
ALTER TABLE payments
  ADD COLUMN IF NOT EXISTS pix_gateway TEXT,
  ADD COLUMN IF NOT EXISTS credit_gateway TEXT;

-- 2. Adicionar comentários para documentação
COMMENT ON COLUMN payments.pix_gateway IS
  'Gateway usado para processar PIX: sicredi, asaas, etc. Usado pelo sistema de polling para saber onde consultar status.';

COMMENT ON COLUMN payments.credit_gateway IS
  'Gateway usado para processar cartão de crédito: rede, asaas, etc. Usado para reconciliação e troubleshooting.';

-- 3. Criar índices para performance
CREATE INDEX IF NOT EXISTS idx_payments_pix_gateway
  ON payments(pix_gateway)
  WHERE pix_gateway IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_payments_credit_gateway
  ON payments(credit_gateway)
  WHERE credit_gateway IS NOT NULL;

-- 4. Migrar dados históricos (best effort)
-- Usa pix_provider da empresa para inferir gateway de pagamentos antigos
UPDATE payments p
SET pix_gateway = (
  SELECT pix_provider
  FROM empresas_config ec
  WHERE ec.empresa_id = p.empresa_id
  LIMIT 1
)
WHERE payment_type = 'pix'
  AND pix_gateway IS NULL
  AND txid IS NOT NULL;

-- Mesma lógica para cartões (usa credit_provider)
UPDATE payments p
SET credit_gateway = (
  SELECT credit_provider
  FROM empresas_config ec
  WHERE ec.empresa_id = p.empresa_id
  LIMIT 1
)
WHERE payment_type IN ('credit', 'credit_card')
  AND credit_gateway IS NULL;

-- 5. Verificação de dados após migração
DO $$
DECLARE
  total_payments INTEGER;
  pix_with_gateway INTEGER;
  credit_with_gateway INTEGER;
BEGIN
  SELECT COUNT(*) INTO total_payments FROM payments;
  SELECT COUNT(*) INTO pix_with_gateway FROM payments WHERE pix_gateway IS NOT NULL;
  SELECT COUNT(*) INTO credit_with_gateway FROM payments WHERE credit_gateway IS NOT NULL;

  RAISE NOTICE '✅ Migration concluída:';
  RAISE NOTICE '   - Total de pagamentos: %', total_payments;
  RAISE NOTICE '   - PIX com gateway: %', pix_with_gateway;
  RAISE NOTICE '   - Cartão com gateway: %', credit_with_gateway;
END $$;

-- ROLLBACK (se necessário):
-- ALTER TABLE payments DROP COLUMN IF EXISTS pix_gateway;
-- ALTER TABLE payments DROP COLUMN IF EXISTS credit_gateway;
-- DROP INDEX IF EXISTS idx_payments_pix_gateway;
-- DROP INDEX IF EXISTS idx_payments_credit_gateway;
