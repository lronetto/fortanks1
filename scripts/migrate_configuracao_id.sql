-- Script para adicionar e configurar a coluna configuracao_id na tabela erp_credenciais
-- Este script deve ser executado com privilégios administrativos no banco de dados
-- Autor: Equipe de Desenvolvimento
-- Data: 2024

-- Verificar se a coluna já existe antes de adicioná-la
SET @column_exists = 0;
SELECT COUNT(*) INTO @column_exists 
FROM information_schema.COLUMNS 
WHERE TABLE_SCHEMA = DATABASE() 
  AND TABLE_NAME = 'erp_credenciais' 
  AND COLUMN_NAME = 'configuracao_id';

-- Adicionar a coluna configuracao_id se ela não existir
SET @sql = IF(@column_exists = 0, 
    'ALTER TABLE erp_credenciais ADD COLUMN configuracao_id INT UNSIGNED AFTER usuario_id',
    'SELECT "Coluna configuracao_id já existe."');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Verificar quantos registros precisam ser migrados
SELECT COUNT(*) AS registros_para_migrar 
FROM erp_credenciais 
WHERE usuario_id IS NOT NULL 
  AND (configuracao_id IS NULL OR configuracao_id = 0);

-- Migrar dados da coluna usuario_id para configuracao_id
UPDATE erp_credenciais 
SET configuracao_id = usuario_id 
WHERE usuario_id IS NOT NULL 
  AND (configuracao_id IS NULL OR configuracao_id = 0);

-- Verificar se já existe a chave estrangeira
SET @fk_exists = 0;
SELECT COUNT(*) INTO @fk_exists 
FROM information_schema.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'erp_credenciais'
  AND COLUMN_NAME = 'configuracao_id'
  AND REFERENCED_TABLE_NAME = 'erp_configuracoes';

-- Adicionar a chave estrangeira se ela não existir
SET @sql = IF(@fk_exists = 0,
    'ALTER TABLE erp_credenciais ADD CONSTRAINT fk_credenciais_configuracao FOREIGN KEY (configuracao_id) REFERENCES erp_configuracoes(id) ON DELETE CASCADE',
    'SELECT "Chave estrangeira já existe."');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Verificar resultado
SELECT 
    (SELECT COUNT(*) FROM information_schema.COLUMNS 
     WHERE TABLE_SCHEMA = DATABASE() 
       AND TABLE_NAME = 'erp_credenciais' 
       AND COLUMN_NAME = 'configuracao_id') AS coluna_existe,
    (SELECT COUNT(*) FROM erp_credenciais 
     WHERE configuracao_id IS NOT NULL) AS registros_migrados,
    (SELECT COUNT(*) FROM information_schema.KEY_COLUMN_USAGE
     WHERE TABLE_SCHEMA = DATABASE()
       AND TABLE_NAME = 'erp_credenciais'
       AND COLUMN_NAME = 'configuracao_id'
       AND REFERENCED_TABLE_NAME = 'erp_configuracoes') AS chave_estrangeira_existe; 