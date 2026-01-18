-- =====================================================
-- Script de Migração: Sincronizar ConcretoUsinagens com o Modelo
-- Data: 2024
-- Descrição: Adiciona campos que estão sendo usados no controller mas podem não existir no banco
-- 
-- ATENÇÃO: Faça backup do banco de dados antes de executar este script!
-- Este script verifica se os campos existem antes de adicionar.
-- =====================================================

-- =====================================================
-- 1. ADICIONAR CAMPO volume_produzido
-- =====================================================
SET @column_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'ConcretoUsinagens'
    AND COLUMN_NAME = 'volume_produzido'
);

SET @sql = IF(@column_exists = 0,
    'ALTER TABLE `ConcretoUsinagens` 
     ADD COLUMN `volume_produzido` DECIMAL(10, 2) NULL COMMENT ''Volume produzido em m³'' 
     AFTER `volume`;',
    'SELECT ''Campo volume_produzido já existe na tabela ConcretoUsinagens'' AS mensagem;'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Copiar valores de volume para volume_produzido se estiver vazio
UPDATE `ConcretoUsinagens` 
SET `volume_produzido` = `volume` 
WHERE `volume_produzido` IS NULL;

-- =====================================================
-- 2. ADICIONAR CAMPO traco_id (se não existir, pode ser que produto_composto_id seja usado)
-- =====================================================
SET @column_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'ConcretoUsinagens'
    AND COLUMN_NAME = 'traco_id'
);

SET @sql = IF(@column_exists = 0,
    'ALTER TABLE `ConcretoUsinagens` 
     ADD COLUMN `traco_id` INT NULL COMMENT ''ID do traço de concreto (legado)'' 
     AFTER `produto_composto_id`;',
    'SELECT ''Campo traco_id já existe na tabela ConcretoUsinagens'' AS mensagem;'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- =====================================================
-- 3. ADICIONAR CAMPO responsavel_id
-- =====================================================
SET @column_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'ConcretoUsinagens'
    AND COLUMN_NAME = 'responsavel_id'
);

SET @sql = IF(@column_exists = 0,
    'ALTER TABLE `ConcretoUsinagens` 
     ADD COLUMN `responsavel_id` INT NULL COMMENT ''ID do colaborador responsável'' 
     AFTER `traco_id`;',
    'SELECT ''Campo responsavel_id já existe na tabela ConcretoUsinagens'' AS mensagem;'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Adicionar foreign key se a tabela Colaborador existir
SET @fk_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE 
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'ConcretoUsinagens'
    AND CONSTRAINT_NAME = 'fk_concreto_usinagens_responsavel'
);

SET @sql = IF(@fk_exists = 0,
    'ALTER TABLE `ConcretoUsinagens` 
     ADD CONSTRAINT `fk_concreto_usinagens_responsavel` 
     FOREIGN KEY (`responsavel_id`) REFERENCES `colaboradores`(`id`) 
     ON DELETE SET NULL ON UPDATE CASCADE;',
    'SELECT ''Foreign key fk_concreto_usinagens_responsavel já existe'' AS mensagem;'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- =====================================================
-- 4. ADICIONAR CAMPO umidade
-- =====================================================
SET @column_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'ConcretoUsinagens'
    AND COLUMN_NAME = 'umidade'
);

SET @sql = IF(@column_exists = 0,
    'ALTER TABLE `ConcretoUsinagens` 
     ADD COLUMN `umidade` DECIMAL(5, 2) NULL DEFAULT 0 COMMENT ''Umidade em porcentagem'' 
     AFTER `responsavel_id`;',
    'SELECT ''Campo umidade já existe na tabela ConcretoUsinagens'' AS mensagem;'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- =====================================================
-- 5. ADICIONAR CAMPO status
-- =====================================================
SET @column_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'ConcretoUsinagens'
    AND COLUMN_NAME = 'status'
);

SET @sql = IF(@column_exists = 0,
    'ALTER TABLE `ConcretoUsinagens` 
     ADD COLUMN `status` VARCHAR(20) NULL DEFAULT ''Ativo'' COMMENT ''Status da usinagem'' 
     AFTER `umidade`;',
    'SELECT ''Campo status já existe na tabela ConcretoUsinagens'' AS mensagem;'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Atualizar registros existentes com status padrão
UPDATE `ConcretoUsinagens` 
SET `status` = 'Ativo' 
WHERE `status` IS NULL OR `status` = '';

-- =====================================================
-- 6. ADICIONAR CAMPO observacoes
-- =====================================================
SET @column_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'ConcretoUsinagens'
    AND COLUMN_NAME = 'observacoes'
);

SET @sql = IF(@column_exists = 0,
    'ALTER TABLE `ConcretoUsinagens` 
     ADD COLUMN `observacoes` TEXT NULL COMMENT ''Observações sobre a usinagem'' 
     AFTER `status`;',
    'SELECT ''Campo observacoes já existe na tabela ConcretoUsinagens'' AS mensagem;'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- =====================================================
-- 7. ADICIONAR CAMPO quantidade_cps
-- =====================================================
SET @column_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'ConcretoUsinagens'
    AND COLUMN_NAME = 'quantidade_cps'
);

SET @sql = IF(@column_exists = 0,
    'ALTER TABLE `ConcretoUsinagens` 
     ADD COLUMN `quantidade_cps` INT NULL DEFAULT 0 COMMENT ''Quantidade de corpos de prova'' 
     AFTER `observacoes`;',
    'SELECT ''Campo quantidade_cps já existe na tabela ConcretoUsinagens'' AS mensagem;'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- =====================================================
-- 8. ADICIONAR CAMPO nota (se diferente de nf)
-- =====================================================
SET @column_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'ConcretoUsinagens'
    AND COLUMN_NAME = 'nota'
);

SET @sql = IF(@column_exists = 0,
    'ALTER TABLE `ConcretoUsinagens` 
     ADD COLUMN `nota` VARCHAR(50) NULL COMMENT ''Nota da usinagem'' 
     AFTER `nf`;',
    'SELECT ''Campo nota já existe na tabela ConcretoUsinagens'' AS mensagem;'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Copiar valores de nf para nota se estiver vazio
UPDATE `ConcretoUsinagens` 
SET `nota` = `nf` 
WHERE (`nota` IS NULL OR `nota` = '') AND `nf` IS NOT NULL;

-- =====================================================
-- 9. ADICIONAR CAMPO nbt
-- =====================================================
SET @column_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'ConcretoUsinagens'
    AND COLUMN_NAME = 'nbt'
);

SET @sql = IF(@column_exists = 0,
    'ALTER TABLE `ConcretoUsinagens` 
     ADD COLUMN `nbt` VARCHAR(50) NULL COMMENT ''Número do NBT'' 
     AFTER `nota`;',
    'SELECT ''Campo nbt já existe na tabela ConcretoUsinagens'' AS mensagem;'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- =====================================================
-- 10. ADICIONAR CAMPO concretagem_id (se necessário)
-- =====================================================
SET @column_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'ConcretoUsinagens'
    AND COLUMN_NAME = 'concretagem_id'
);

SET @sql = IF(@column_exists = 0,
    'ALTER TABLE `ConcretoUsinagens` 
     ADD COLUMN `concretagem_id` INT NULL COMMENT ''ID da concretagem associada'' 
     AFTER `produto_composto_id`;',
    'SELECT ''Campo concretagem_id já existe na tabela ConcretoUsinagens'' AS mensagem;'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Adicionar foreign key se a tabela ConcretoConcretagens existir
SET @fk_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE 
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'ConcretoUsinagens'
    AND CONSTRAINT_NAME = 'fk_concreto_usinagens_concretagem'
);

SET @sql = IF(@fk_exists = 0,
    'ALTER TABLE `ConcretoUsinagens` 
     ADD CONSTRAINT `fk_concreto_usinagens_concretagem` 
     FOREIGN KEY (`concretagem_id`) REFERENCES `ConcretoConcretagens`(`id`) 
     ON DELETE SET NULL ON UPDATE CASCADE;',
    'SELECT ''Foreign key fk_concreto_usinagens_concretagem já existe'' AS mensagem;'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- =====================================================
-- 11. ADICIONAR ÍNDICES PARA MELHORAR PERFORMANCE
-- =====================================================

-- Índice para data_usinagem
SET @index_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.STATISTICS 
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'ConcretoUsinagens'
    AND INDEX_NAME = 'idx_concreto_usinagens_data_usinagem'
);

SET @sql = IF(@index_exists = 0,
    'CREATE INDEX `idx_concreto_usinagens_data_usinagem` ON `ConcretoUsinagens`(`data_usinagem`);',
    'SELECT ''Índice idx_concreto_usinagens_data_usinagem já existe'' AS mensagem;'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Índice para produto_composto_id
SET @index_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.STATISTICS 
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'ConcretoUsinagens'
    AND INDEX_NAME = 'idx_concreto_usinagens_produto_composto'
);

SET @sql = IF(@index_exists = 0,
    'CREATE INDEX `idx_concreto_usinagens_produto_composto` ON `ConcretoUsinagens`(`produto_composto_id`);',
    'SELECT ''Índice idx_concreto_usinagens_produto_composto já existe'' AS mensagem;'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Índice para status
SET @index_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.STATISTICS 
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'ConcretoUsinagens'
    AND INDEX_NAME = 'idx_concreto_usinagens_status'
);

SET @sql = IF(@index_exists = 0,
    'CREATE INDEX `idx_concreto_usinagens_status` ON `ConcretoUsinagens`(`status`);',
    'SELECT ''Índice idx_concreto_usinagens_status já existe'' AS mensagem;'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- =====================================================
-- 12. VERIFICAÇÃO FINAL
-- =====================================================

-- Exibir estrutura final da tabela
SELECT 
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    COLUMN_COMMENT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'ConcretoUsinagens'
ORDER BY ORDINAL_POSITION;

-- Exibir mensagem de conclusão
SELECT 'Migração concluída com sucesso! Verifique a estrutura da tabela acima.' AS mensagem;
