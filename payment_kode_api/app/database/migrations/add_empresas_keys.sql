-- payment_kode_api/app/database/migrations/add_empresas_keys.sql
-- Migração para adicionar tabela de chaves de descriptografia por empresa

-- ========== CRIAR TABELA DE CHAVES ==========
CREATE TABLE IF NOT EXISTS empresas_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id UUID NOT NULL REFERENCES empresas(empresa_id) ON DELETE CASCADE,
    decryption_key_hash VARCHAR(64) NOT NULL, -- Hash da chave para verificação de integridade
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    
    -- Constraints
    UNIQUE(empresa_id)
);

-- ========== ÍNDICES PARA PERFORMANCE ==========
CREATE INDEX IF NOT EXISTS idx_empresas_keys_empresa_id ON empresas_keys(empresa_id);
CREATE INDEX IF NOT EXISTS idx_empresas_keys_created_at ON empresas_keys(created_at);

-- ========== COMMENTS PARA DOCUMENTAÇÃO ==========
COMMENT ON TABLE empresas_keys IS 'Armazena chaves de descriptografia únicas por empresa para tokenização segura';
COMMENT ON COLUMN empresas_keys.empresa_id IS 'Referência à empresa proprietária da chave';
COMMENT ON COLUMN empresas_keys.decryption_key_hash IS 'Hash SHA-256 da chave de descriptografia para verificação de integridade';
COMMENT ON COLUMN empresas_keys.created_at IS 'Data de criação da chave';
COMMENT ON COLUMN empresas_keys.updated_at IS 'Data da última atualização da chave';

-- ========== TRIGGER PARA AUTO-UPDATE ==========
CREATE OR REPLACE FUNCTION update_empresas_keys_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_empresas_keys_updated_at
    BEFORE UPDATE ON empresas_keys
    FOR EACH ROW
    EXECUTE FUNCTION update_empresas_keys_updated_at();

-- ========== ADICIONAR COLUNAS À TABELA DE CARTÕES ==========
-- Adicionar suporte a dados seguros (safe_card_data) em cartoes_tokenizados
-- para compatibilidade com o novo método de tokenização

ALTER TABLE cartoes_tokenizados 
ADD COLUMN IF NOT EXISTS safe_card_data JSONB;

-- Adicionar índice para performance nas consultas de dados seguros
CREATE INDEX IF NOT EXISTS idx_cartoes_tokenizados_safe_card_data 
ON cartoes_tokenizados USING GIN (safe_card_data);

-- ========== COMMENTS PARA NOVA COLUNA ==========
COMMENT ON COLUMN cartoes_tokenizados.safe_card_data IS 'Dados seguros do cartão (sem informações sensíveis) em formato JSON';

-- ========== MIGRAÇÃO DE DADOS EXISTENTES (OPCIONAL) ==========
-- Esta seção pode ser executada posteriormente para migrar tokens RSA existentes
-- para o novo formato simples

/*
-- Script para migrar tokens RSA para formato simples (executar separadamente se necessário)
-- NOTA: Este script é apenas um exemplo, a migração real deve ser feita via código

UPDATE cartoes_tokenizados 
SET safe_card_data = jsonb_build_object(
    'tokenization_method', 'migration_pending',
    'last_four_digits', last_four_digits,
    'card_brand', card_brand,
    'created_at', created_at::text,
    'migration_needed', true
)
WHERE safe_card_data IS NULL 
AND encrypted_card_data IS NOT NULL;
*/

-- ========== VALIDAÇÕES E CONSTRAINTS ADICIONAIS ==========

-- Verificar se a chave hash tem o tamanho correto (64 caracteres para SHA-256)
ALTER TABLE empresas_keys 
ADD CONSTRAINT check_decryption_key_hash_length 
CHECK (char_length(decryption_key_hash) = 64);

-- Verificar se o hash contém apenas caracteres hexadecimais
ALTER TABLE empresas_keys 
ADD CONSTRAINT check_decryption_key_hash_format 
CHECK (decryption_key_hash ~ '^[a-f0-9]{64}$');

-- ========== ESTATÍSTICAS E RELATÓRIOS ==========

-- View para monitoramento das chaves de empresa
CREATE OR REPLACE VIEW v_empresas_keys_status AS
SELECT 
    ek.empresa_id,
    e.nome as empresa_nome,
    e.cnpj as empresa_cnpj,
    ek.created_at as chave_criada_em,
    ek.updated_at as chave_atualizada_em,
    CASE 
        WHEN ek.decryption_key_hash IS NOT NULL THEN 'Configurada'
        ELSE 'Não configurada'
    END as status_chave,
    -- Contar cartões tokenizados da empresa
    (SELECT COUNT(*) FROM cartoes_tokenizados ct WHERE ct.empresa_id = ek.empresa_id) as total_cartoes,
    -- Contar cartões com dados seguros
    (SELECT COUNT(*) FROM cartoes_tokenizados ct WHERE ct.empresa_id = ek.empresa_id AND ct.safe_card_data IS NOT NULL) as cartoes_com_safe_data
FROM empresas_keys ek
JOIN empresas e ON e.empresa_id = ek.empresa_id;

COMMENT ON VIEW v_empresas_keys_status IS 'View para monitoramento do status das chaves de empresa e tokenização';

-- ========== FUNÇÃO PARA GERAR ESTATÍSTICAS ==========

CREATE OR REPLACE FUNCTION get_tokenization_stats(input_empresa_id UUID DEFAULT NULL)
RETURNS TABLE (
    empresa_id UUID,
    empresa_nome TEXT,
    total_cartoes BIGINT,
    cartoes_rsa BIGINT,
    cartoes_simples BIGINT,
    cartoes_migrados BIGINT,
    chave_configurada BOOLEAN,
    primeira_tokenizacao TIMESTAMP WITH TIME ZONE,
    ultima_tokenizacao TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        e.empresa_id,
        e.nome::TEXT as empresa_nome,
        COALESCE(stats.total_cartoes, 0) as total_cartoes,
        COALESCE(stats.cartoes_rsa, 0) as cartoes_rsa,
        COALESCE(stats.cartoes_simples, 0) as cartoes_simples,
        COALESCE(stats.cartoes_migrados, 0) as cartoes_migrados,
        (ek.decryption_key_hash IS NOT NULL) as chave_configurada,
        stats.primeira_tokenizacao,
        stats.ultima_tokenizacao
    FROM empresas e
    LEFT JOIN empresas_keys ek ON ek.empresa_id = e.empresa_id
    LEFT JOIN (
        SELECT 
            ct.empresa_id,
            COUNT(*) as total_cartoes,
            COUNT(CASE WHEN ct.encrypted_card_data IS NOT NULL AND ct.safe_card_data IS NULL THEN 1 END) as cartoes_rsa,
            COUNT(CASE WHEN ct.safe_card_data IS NOT NULL AND (ct.safe_card_data->>'tokenization_method') LIKE '%simple%' THEN 1 END) as cartoes_simples,
            COUNT(CASE WHEN ct.safe_card_data IS NOT NULL AND (ct.safe_card_data->>'tokenization_method') LIKE '%migrated%' THEN 1 END) as cartoes_migrados,
            MIN(ct.created_at) as primeira_tokenizacao,
            MAX(ct.created_at) as ultima_tokenizacao
        FROM cartoes_tokenizados ct
        GROUP BY ct.empresa_id
    ) stats ON stats.empresa_id = e.empresa_id
    WHERE (input_empresa_id IS NULL OR e.empresa_id = input_empresa_id);
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_tokenization_stats IS 'Retorna estatísticas de tokenização por empresa';

-- ========== CLEANUP E MANUTENÇÃO ==========

-- Função para limpar chaves não utilizadas (empresas inativas há mais de 1 ano)
CREATE OR REPLACE FUNCTION cleanup_unused_encryption_keys(
    inactive_days INTEGER DEFAULT 365
) RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM empresas_keys 
    WHERE empresa_id IN (
        SELECT e.empresa_id 
        FROM empresas e 
        LEFT JOIN cartoes_tokenizados ct ON ct.empresa_id = e.empresa_id
        LEFT JOIN payments p ON p.empresa_id = e.empresa_id
        WHERE 
            -- Sem cartões tokenizados recentes
            (ct.created_at IS NULL OR ct.created_at < now() - (inactive_days || ' days')::interval)
            -- Sem pagamentos recentes
            AND (p.created_at IS NULL OR p.created_at < now() - (inactive_days || ' days')::interval)
    );
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION cleanup_unused_encryption_keys IS 'Remove chaves de empresas inativas por período especificado';

-- ========== TRIGGERS DE AUDITORIA ==========

-- Tabela de log para auditoria de operações nas chaves
CREATE TABLE IF NOT EXISTS empresas_keys_audit (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id UUID NOT NULL,
    operation VARCHAR(10) NOT NULL, -- INSERT, UPDATE, DELETE
    old_hash VARCHAR(64),
    new_hash VARCHAR(64),
    changed_by VARCHAR(100), -- Pode ser usado para identificar o usuário/sistema
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Trigger para auditoria
CREATE OR REPLACE FUNCTION audit_empresas_keys()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        INSERT INTO empresas_keys_audit (empresa_id, operation, old_hash)
        VALUES (OLD.empresa_id, 'DELETE', OLD.decryption_key_hash);
        RETURN OLD;
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO empresas_keys_audit (empresa_id, operation, old_hash, new_hash)
        VALUES (NEW.empresa_id, 'UPDATE', OLD.decryption_key_hash, NEW.decryption_key_hash);
        RETURN NEW;
    ELSIF TG_OP = 'INSERT' THEN
        INSERT INTO empresas_keys_audit (empresa_id, operation, new_hash)
        VALUES (NEW.empresa_id, 'INSERT', NEW.decryption_key_hash);
        RETURN NEW;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_audit_empresas_keys
    AFTER INSERT OR UPDATE OR DELETE ON empresas_keys
    FOR EACH ROW
    EXECUTE FUNCTION audit_empresas_keys();

COMMENT ON TABLE empresas_keys_audit IS 'Log de auditoria para operações na tabela empresas_keys';

-- ========== VERIFICAÇÕES DE INTEGRIDADE ==========

-- Função para verificar integridade das chaves
CREATE OR REPLACE FUNCTION verify_keys_integrity()
RETURNS TABLE (
    empresa_id UUID,
    issue TEXT,
    severity VARCHAR(10)
) AS $$
BEGIN
    -- Empresas sem chave configurada mas com cartões tokenizados
    RETURN QUERY
    SELECT 
        ct.empresa_id,
        'Empresa tem cartões tokenizados mas não possui chave de descriptografia configurada'::TEXT as issue,
        'HIGH'::VARCHAR(10) as severity
    FROM cartoes_tokenizados ct
    LEFT JOIN empresas_keys ek ON ek.empresa_id = ct.empresa_id
    WHERE ek.empresa_id IS NULL
    GROUP BY ct.empresa_id;
    
    -- Chaves configuradas mas sem cartões
    RETURN QUERY
    SELECT 
        ek.empresa_id,
        'Empresa tem chave configurada mas nenhum cartão tokenizado'::TEXT as issue,
        'LOW'::VARCHAR(10) as severity
    FROM empresas_keys ek
    LEFT JOIN cartoes_tokenizados ct ON ct.empresa_id = ek.empresa_id
    WHERE ct.empresa_id IS NULL;
    
    -- Cartões com dados inconsistentes
    RETURN QUERY
    SELECT 
        ct.empresa_id,
        'Cartões com encrypted_card_data mas sem safe_card_data'::TEXT as issue,
        'MEDIUM'::VARCHAR(10) as severity
    FROM cartoes_tokenizados ct
    WHERE ct.encrypted_card_data IS NOT NULL 
    AND ct.safe_card_data IS NULL
    GROUP BY ct.empresa_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION verify_keys_integrity IS 'Verifica integridade e consistência das chaves e dados de tokenização';