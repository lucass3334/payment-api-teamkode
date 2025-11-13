-- Migration: Adicionar chaves PIX específicas por gateway
-- Objetivo: Permitir fallback entre gateways PIX mantendo chaves separadas
-- Data: 2025-11-08
-- Status: AGUARDANDO APROVAÇÃO DO TECH LEAD

-- 1. Adicionar colunas para chaves PIX específicas de cada gateway
ALTER TABLE empresas_config
  ADD COLUMN IF NOT EXISTS sicredi_chave_pix TEXT,
  ADD COLUMN IF NOT EXISTS asaas_chave_pix TEXT;

-- 2. Migrar dados existentes da coluna `chave_pix` para as colunas específicas
-- Empresas que usam Sicredi como provider → copiar para sicredi_chave_pix
UPDATE empresas_config
SET sicredi_chave_pix = TRIM(chave_pix)
WHERE pix_provider = 'sicredi'
  AND chave_pix IS NOT NULL
  AND chave_pix != '';

-- Empresas que usam Asaas como provider → copiar para asaas_chave_pix
UPDATE empresas_config
SET asaas_chave_pix = TRIM(chave_pix)
WHERE pix_provider = 'asaas'
  AND chave_pix IS NOT NULL
  AND chave_pix != '';

-- 3. Adicionar comentários nas colunas para documentação
COMMENT ON COLUMN empresas_config.sicredi_chave_pix IS
  'Chave PIX registrada no Sicredi para recebimento de pagamentos. Formato: UUID, CPF, CNPJ, Email ou telefone.';

COMMENT ON COLUMN empresas_config.asaas_chave_pix IS
  'Chave PIX registrada no Asaas para recebimento de pagamentos. Formato: UUID, CPF, CNPJ, Email ou telefone.';

COMMENT ON COLUMN empresas_config.chave_pix IS
  'DEPRECATED: Usar sicredi_chave_pix ou asaas_chave_pix. Mantida para compatibilidade com webhooks.';

-- 4. Criar índices para melhorar performance de busca
CREATE INDEX IF NOT EXISTS idx_empresas_config_sicredi_chave_pix
  ON empresas_config(sicredi_chave_pix)
  WHERE sicredi_chave_pix IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_empresas_config_asaas_chave_pix
  ON empresas_config(asaas_chave_pix)
  WHERE asaas_chave_pix IS NOT NULL;

-- 5. Verificação de dados após migração
DO $$
DECLARE
  total_empresas INTEGER;
  com_sicredi INTEGER;
  com_asaas INTEGER;
  usando_sicredi INTEGER;
  usando_asaas INTEGER;
BEGIN
  SELECT COUNT(*) INTO total_empresas FROM empresas_config;
  SELECT COUNT(*) INTO com_sicredi FROM empresas_config WHERE sicredi_chave_pix IS NOT NULL;
  SELECT COUNT(*) INTO com_asaas FROM empresas_config WHERE asaas_chave_pix IS NOT NULL;
  SELECT COUNT(*) INTO usando_sicredi FROM empresas_config WHERE pix_provider = 'sicredi';
  SELECT COUNT(*) INTO usando_asaas FROM empresas_config WHERE pix_provider = 'asaas';

  RAISE NOTICE '✅ Migration concluída:';
  RAISE NOTICE '   - Total de empresas: %', total_empresas;
  RAISE NOTICE '   - Com chave Sicredi: %', com_sicredi;
  RAISE NOTICE '   - Com chave Asaas: %', com_asaas;
  RAISE NOTICE '   - Usando Sicredi: %', usando_sicredi;
  RAISE NOTICE '   - Usando Asaas: %', usando_asaas;
END $$;

-- ROLLBACK (se necessário):
-- ALTER TABLE empresas_config DROP COLUMN IF EXISTS sicredi_chave_pix;
-- ALTER TABLE empresas_config DROP COLUMN IF EXISTS asaas_chave_pix;
-- DROP INDEX IF EXISTS idx_empresas_config_sicredi_chave_pix;
-- DROP INDEX IF EXISTS idx_empresas_config_asaas_chave_pix;
