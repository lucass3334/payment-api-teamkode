-- payment_kode_api/app/database/migrations/improve_encryption_system.sql
-- Migração para melhorar o sistema de criptografia por empresa

-- ========== ATUALIZAR TABELA DE CHAVES ==========

-- Adicionar colunas para melhor tracking
ALTER TABLE empresas_keys 
ADD COLUMN IF NOT EXISTS key_version VARCHAR(20) DEFAULT 'fernet_v2',
ADD COLUMN IF NOT EXISTS key_type VARCHAR(20) DEFAULT 'random',
ADD COLUMN IF NOT EXISTS is_deterministic BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS backup_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS last_validated_at TIMESTAMP WITH TIME ZONE,
ADD COLUMN IF NOT EXISTS validation_status VARCHAR(20) DEFAULT 'pending';

-- Comentários para documentação
COMMENT ON COLUMN empresas_keys.key_version IS 'Versão do algoritmo de geração da chave (fernet_v2, etc)';
COMMENT ON COLUMN empresas_keys.key_type IS 'Tipo da chave: random (recomendado) ou deterministic (fallback)';
COMMENT ON COLUMN empresas_keys.is_deterministic IS 'Se true, chave foi gerada deterministicamente';
COMMENT ON COLUMN empresas_keys.backup_count IS 'Número de backups criados para esta chave';
COMMENT ON COLUMN empresas_keys.last_validated_at IS 'Última vez que a chave foi validada';
COMMENT ON COLUMN empresas_keys.validation_status IS 'Status da última validação: pending, valid, invalid';

-- ========== CRIAR TABELA DE BACKUP DE CHAVES ==========

CREATE TABLE IF NOT EXISTS empresas_keys_backup (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id UUID NOT NULL REFERENCES empresas(empresa_id) ON DELETE CASCADE,
    old_key_hash VARCHAR(64) NOT NULL,
    backed_up_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    reason VARCHAR(100) DEFAULT 'key_rotation',
    backup_version INTEGER DEFAULT 1,
    
    -- Índices
    INDEX idx_empresas_keys_backup_empresa_id (empresa_id),
    INDEX idx_empresas_keys_backup_backed_up_at (backed_up_at)
);

COMMENT ON TABLE empresas_keys_backup IS 'Backup de chaves antigas para auditoria e recuperação de emergência';
COMMENT ON COLUMN empresas_keys_backup.old_key_hash IS 'Hash da chave que foi substituída';
COMMENT ON COLUMN empresas_keys_backup.reason IS 'Motivo do backup: key_rotation, security_breach, migration, etc';
COMMENT ON COLUMN empresas_keys_backup.backup_version IS 'Versão sequencial do backup para a empresa';

-- ========== MELHORAR TABELA DE AUDITORIA ==========

-- Adicionar colunas para melhor tracking na auditoria
ALTER TABLE empresas_keys_audit 
ADD COLUMN IF NOT EXISTS key_version VARCHAR(20),
ADD COLUMN IF NOT EXISTS operation_source VARCHAR(50) DEFAULT 'api',
ADD COLUMN IF NOT EXISTS user_agent TEXT,
ADD COLUMN IF NOT EXISTS ip_address INET,
ADD COLUMN IF NOT EXISTS session_id VARCHAR(100);

COMMENT ON COLUMN empresas_keys_audit.operation_source IS 'Origem da operação: api, admin_panel, migration, emergency';
COMMENT ON COLUMN empresas_keys_audit.user_agent IS 'User-Agent da requisição (para operações via API)';
COMMENT ON COLUMN empresas_keys_audit.ip_address IS 'Endereço IP da origem da operação';
COMMENT ON COLUMN empresas_keys_audit.session_id IS 'ID da sessão/transação para agrupamento';

-- ========== ATUALIZAR TRIGGERS DE AUDITORIA ==========

-- Atualizar trigger para incluir novas informações
CREATE OR REPLACE FUNCTION audit_empresas_keys()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        INSERT INTO empresas_keys_audit (
            empresa_id, operation, old_hash, key_version, operation_source
        ) VALUES (
            OLD.empresa_id, 
            'DELETE', 
            OLD.decryption_key_hash,
            OLD.key_version,
            COALESCE(current_setting('audit.operation_source', true), 'unknown')
        );
        RETURN OLD;
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO empresas_keys_audit (
            empresa_id, operation, old_hash, new_hash, key_version, operation_source
        ) VALUES (
            NEW.empresa_id, 
            'UPDATE', 
            OLD.decryption_key_hash, 
            NEW.decryption_key_hash,
            NEW.key_version,
            COALESCE(current_setting('audit.operation_source', true), 'api')
        );
        RETURN NEW;
    ELSIF TG_OP = 'INSERT' THEN
        INSERT INTO empresas_keys_audit (
            empresa_id, operation, new_hash, key_version, operation_source
        ) VALUES (
            NEW.empresa_id, 
            'INSERT', 
            NEW.decryption_key_hash,
            NEW.key_version,
            COALESCE(current_setting('audit.operation_source', true), 'api')
        );
        RETURN NEW;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- ========== FUNÇÕES DE GESTÃO ==========

-- Função para obter estatísticas de chaves por empresa
CREATE OR REPLACE FUNCTION get_encryption_key_stats(input_empresa_id UUID DEFAULT NULL)
RETURNS TABLE (
    empresa_id UUID,
    empresa_nome TEXT,
    has_key BOOLEAN,
    key_version VARCHAR(20),
    key_type VARCHAR(20),
    is_deterministic BOOLEAN,
    created_at TIMESTAMP WITH TIME ZONE,
    last_validated_at TIMESTAMP WITH TIME ZONE,
    validation_status VARCHAR(20),
    backup_count INTEGER,
    total_tokens BIGINT,
    tokens_with_safe_data BIGINT,
    tokens_fernet_encrypted BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        e.empresa_id,
        e.nome::TEXT as empresa_nome,
        (ek.decryption_key_hash IS NOT NULL) as has_key,
        ek.key_version,
        ek.key_type,
        ek.is_deterministic,
        ek.created_at,
        ek.last_validated_at,
        ek.validation_status,
        ek.backup_count,
        COALESCE(token_stats.total_tokens, 0) as total_tokens,
        COALESCE(token_stats.tokens_with_safe_data, 0) as tokens_with_safe_data,
        COALESCE(token_stats.tokens_fernet_encrypted, 0) as tokens_fernet_encrypted
    FROM empresas e
    LEFT JOIN empresas_keys ek ON ek.empresa_id = e.empresa_id
    LEFT JOIN (
        SELECT 
            ct.empresa_id,
            COUNT(*) as total_tokens,
            COUNT(CASE WHEN ct.safe_card_data IS NOT NULL THEN 1 END) as tokens_with_safe_data,
            COUNT(CASE 
                WHEN ct.safe_card_data IS NOT NULL 
                AND (ct.safe_card_data::text LIKE '%fernet%' OR ct.safe_card_data::text LIKE '%company_encryption%') 
                THEN 1 
            END) as tokens_fernet_encrypted
        FROM cartoes_tokenizados ct
        GROUP BY ct.empresa_id
    ) token_stats ON token_stats.empresa_id = e.empresa_id
    WHERE (input_empresa_id IS NULL OR e.empresa_id = input_empresa_id)
    ORDER BY e.nome;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_encryption_key_stats IS 'Retorna estatísticas detalhadas de chaves e tokens por empresa';

