-- =====================================================
-- Script de Migração: Adicionar campos em ConcretoUsinagensRompimentos
-- Data: 2024
-- Descrição: Adiciona os campos data_moldagem e fator_conversao
-- =====================================================

-- Verificar e adicionar campo data_moldagem
SET @column_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'ConcretoUsinagensRompimentos'
    AND COLUMN_NAME = 'data_moldagem'
);

SET @sql = IF(@column_exists = 0,
    'ALTER TABLE `ConcretoUsinagensRompimentos` 
     ADD COLUMN `data_moldagem` DATETIME NULL COMMENT ''Data e hora da moldagem do corpo de prova'' 
     AFTER `numero_serie`;',
    'SELECT ''Campo data_moldagem já existe na tabela ConcretoUsinagensRompimentos'' AS mensagem;'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Verificar e adicionar campo fator_conversao
SET @column_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'ConcretoUsinagensRompimentos'
    AND COLUMN_NAME = 'fator_conversao'
);

SET @sql = IF(@column_exists = 0,
    'ALTER TABLE `ConcretoUsinagensRompimentos` 
     ADD COLUMN `fator_conversao` DECIMAL(5,2) NOT NULL DEFAULT 1.20 COMMENT ''Fator de conversão de kg para MPa'' 
     AFTER `resultado`;',
    'SELECT ''Campo fator_conversao já existe na tabela ConcretoUsinagensRompimentos'' AS mensagem;'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Atualizar registros existentes que não possuem fator_conversao (caso o campo já exista mas sem default)
UPDATE `ConcretoUsinagensRompimentos` 
SET `fator_conversao` = 1.20 
WHERE `fator_conversao` IS NULL;

-- Verificar se o campo numero_serie existe, caso contrário pode ser necessário renomear numero_cp
SET @column_serie_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'ConcretoUsinagensRompimentos'
    AND COLUMN_NAME = 'numero_serie'
);

SET @column_cp_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'ConcretoUsinagensRompimentos'
    AND COLUMN_NAME = 'numero_cp'
);

-- Se numero_cp existe mas numero_serie não existe, renomear
SET @sql = IF(@column_serie_exists = 0 AND @column_cp_exists > 0,
    'ALTER TABLE `ConcretoUsinagensRompimentos` 
     CHANGE COLUMN `numero_cp` `numero_serie` INT NOT NULL COMMENT ''Número de série do corpo de prova'';',
    IF(@column_serie_exists > 0,
        'SELECT ''Campo numero_serie já existe na tabela ConcretoUsinagensRompimentos'' AS mensagem;',
        'SELECT ''Atenção: Nem numero_cp nem numero_serie foram encontrados. Verifique a estrutura da tabela.'' AS mensagem;'
    )
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Verificar se usinagem_id permite NULL (caso ainda não permita)
SET @column_nullable = (
    SELECT IS_NULLABLE 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'ConcretoUsinagensRompimentos'
    AND COLUMN_NAME = 'usinagem_id'
);

SET @sql = IF(@column_nullable = 'NO',
    'ALTER TABLE `ConcretoUsinagensRompimentos` 
     MODIFY COLUMN `usinagem_id` INT NULL;',
    'SELECT ''Campo usinagem_id já permite valores NULL'' AS mensagem;'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Exibir resumo das alterações
SELECT 
    'Migração concluída com sucesso!' AS status,
    'Campos adicionados/atualizados na tabela ConcretoUsinagensRompimentos' AS descricao;

