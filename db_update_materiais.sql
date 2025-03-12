-- Adicionar colunas pc e codigo_erp na tabela materiais
ALTER TABLE materiais
ADD COLUMN IF NOT EXISTS pc VARCHAR(255) NULL COMMENT 'Código PC do material',
ADD COLUMN IF NOT EXISTS codigo_erp VARCHAR(255) NULL COMMENT 'Código ERP do material';

-- Atualizar comentários de tabela
ALTER TABLE materiais
COMMENT = 'Tabela de materiais e insumos do sistema'; 