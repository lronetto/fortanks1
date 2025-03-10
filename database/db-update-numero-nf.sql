-- Execute este script SQL para adicionar a coluna numero_nf à tabela nf_notas
ALTER TABLE nf_notas ADD COLUMN numero_nf VARCHAR(20) AFTER chave_acesso;

-- Atualizar índice para incluir numero_nf
CREATE INDEX idx_numero_nf ON nf_notas(numero_nf);
