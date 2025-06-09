-- 1) Adiciona a coluna que armazenará a chave Fernet em texto
ALTER TABLE public.empresas_keys
  ADD COLUMN IF NOT EXISTS decryption_key TEXT NULL;

-- 2) (Opcional) Adiciona comentário para a nova coluna
COMMENT ON COLUMN public.empresas_keys.decryption_key IS
  'Chave Fernet usada para descriptografar tokens da empresa';
