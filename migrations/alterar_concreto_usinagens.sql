-- =====================================================
-- Script de Migração: Alterar tabela ConcretoUsinagens
-- Data: 2024
-- Descrição: Script para alterações manuais na tabela ConcretoUsinagens
-- 
-- ATENÇÃO: Faça backup do banco de dados antes de executar este script!
-- =====================================================

-- =====================================================
-- 1. ADICIONAR NOVOS CAMPOS
-- =====================================================

-- Exemplo: Adicionar campo de observações
-- ALTER TABLE `ConcretoUsinagens` 
-- ADD COLUMN `observacoes` TEXT NULL COMMENT 'Observações sobre a usinagem' 
-- AFTER `dados_adicionais`;

-- Exemplo: Adicionar campo de status
-- ALTER TABLE `ConcretoUsinagens` 
-- ADD COLUMN `status` VARCHAR(20) NULL DEFAULT 'Ativo' COMMENT 'Status da usinagem' 
-- AFTER `nf`;

-- Exemplo: Adicionar campo de volume_produzido (se diferente de volume)
-- ALTER TABLE `ConcretoUsinagens` 
-- ADD COLUMN `volume_produzido` DECIMAL(10, 2) NULL COMMENT 'Volume produzido em m³' 
-- AFTER `volume`;

-- Exemplo: Adicionar campo de concretagem_id (se necessário relacionar com ConcretoConcretagens)
-- ALTER TABLE `ConcretoUsinagens` 
-- ADD COLUMN `concretagem_id` INT NULL COMMENT 'ID da concretagem associada' 
-- AFTER `produto_composto_id`;
-- 
-- ALTER TABLE `ConcretoUsinagens` 
-- ADD CONSTRAINT `fk_concreto_usinagens_concretagem` 
-- FOREIGN KEY (`concretagem_id`) REFERENCES `ConcretoConcretagens`(`id`) 
-- ON DELETE SET NULL ON UPDATE CASCADE;

-- =====================================================
-- 2. MODIFICAR CAMPOS EXISTENTES
-- =====================================================

-- Exemplo: Alterar tamanho do campo serie
-- ALTER TABLE `ConcretoUsinagens` 
-- MODIFY COLUMN `serie` VARCHAR(200) NOT NULL COMMENT 'Série única como referência';

-- Exemplo: Alterar tamanho do campo flow
-- ALTER TABLE `ConcretoUsinagens` 
-- MODIFY COLUMN `flow` VARCHAR(100) NULL COMMENT 'Fluidez';

-- Exemplo: Alterar tamanho do campo nf (nota fiscal)
-- ALTER TABLE `ConcretoUsinagens` 
-- MODIFY COLUMN `nf` VARCHAR(100) NULL COMMENT 'Nota fiscal';

-- Exemplo: Alterar precisão do campo volume
-- ALTER TABLE `ConcretoUsinagens` 
-- MODIFY COLUMN `volume` DECIMAL(12, 3) NOT NULL COMMENT 'Volume produzido em m³';

-- Exemplo: Tornar campo nullable
-- ALTER TABLE `ConcretoUsinagens` 
-- MODIFY COLUMN `flow` VARCHAR(50) NULL COMMENT 'Fluidez';

-- Exemplo: Tornar campo NOT NULL (cuidado: verifique se não há valores NULL)
-- ALTER TABLE `ConcretoUsinagens` 
-- MODIFY COLUMN `flow` VARCHAR(50) NOT NULL COMMENT 'Fluidez';

-- =====================================================
-- 3. RENOMEAR CAMPOS
-- =====================================================

-- Exemplo: Renomear campo
-- ALTER TABLE `ConcretoUsinagens` 
-- CHANGE COLUMN `flow` `fluidez` VARCHAR(50) NULL COMMENT 'Fluidez do concreto';

-- =====================================================
-- 4. REMOVER CAMPOS (CUIDADO!)
-- =====================================================

-- Exemplo: Remover campo (apenas se tiver certeza!)
-- ALTER TABLE `ConcretoUsinagens` 
-- DROP COLUMN `campo_nao_usado`;

-- =====================================================
-- 5. ADICIONAR ÍNDICES
-- =====================================================

-- Exemplo: Adicionar índice para melhorar performance em buscas por data
-- CREATE INDEX `idx_concreto_usinagens_data_usinagem` 
-- ON `ConcretoUsinagens`(`data_usinagem`);

-- Exemplo: Adicionar índice para produto_composto_id
-- CREATE INDEX `idx_concreto_usinagens_produto_composto` 
-- ON `ConcretoUsinagens`(`produto_composto_id`);

-- Exemplo: Adicionar índice composto
-- CREATE INDEX `idx_concreto_usinagens_data_produto` 
-- ON `ConcretoUsinagens`(`data_usinagem`, `produto_composto_id`);

-- =====================================================
-- 6. REMOVER ÍNDICES
-- =====================================================

-- Exemplo: Remover índice
-- DROP INDEX `idx_concreto_usinagens_data_usinagem` 
-- ON `ConcretoUsinagens`;

-- =====================================================
-- 7. ATUALIZAR DADOS EXISTENTES
-- =====================================================

-- Exemplo: Atualizar campo volume_produzido com valor de volume (se campo foi adicionado)
-- UPDATE `ConcretoUsinagens` 
-- SET `volume_produzido` = `volume` 
-- WHERE `volume_produzido` IS NULL;

-- Exemplo: Atualizar campo nf para valores específicos
-- UPDATE `ConcretoUsinagens` 
-- SET `nf` = CONCAT('NF-', `id`) 
-- WHERE `nf` IS NULL OR `nf` = '';

-- Exemplo: Atualizar campo flow baseado em condições
-- UPDATE `ConcretoUsinagens` 
-- SET `flow` = '650' 
-- WHERE `flow` IS NULL AND `volume` > 10;

-- Exemplo: Atualizar dados_adicionais (JSON)
-- UPDATE `ConcretoUsinagens` 
-- SET `dados_adicionais` = JSON_SET(
--     COALESCE(`dados_adicionais`, '{}'), 
--     '$.observacao', 'Usinagem processada'
-- ) 
-- WHERE `id` = 1;

-- =====================================================
-- 8. CORRIGIR DADOS
-- =====================================================

-- Exemplo: Corrigir séries duplicadas (manter apenas a mais antiga)
-- UPDATE `ConcretoUsinagens` u1
-- INNER JOIN (
--     SELECT `serie`, MIN(`id`) as min_id
--     FROM `ConcretoUsinagens`
--     GROUP BY `serie`
--     HAVING COUNT(*) > 1
-- ) u2 ON u1.`serie` = u2.`serie` AND u1.`id` > u2.min_id
-- SET u1.`serie` = CONCAT(u1.`serie`, '-', u1.`id`);

-- Exemplo: Corrigir volumes negativos ou zero
-- UPDATE `ConcretoUsinagens` 
-- SET `volume` = ABS(`volume`) 
-- WHERE `volume` <= 0;

-- =====================================================
-- 9. ADICIONAR CONSTRAINTS
-- =====================================================

-- Exemplo: Adicionar constraint para garantir volume positivo
-- ALTER TABLE `ConcretoUsinagens` 
-- ADD CONSTRAINT `chk_volume_positivo` 
-- CHECK (`volume` > 0);

-- =====================================================
-- 10. REMOVER CONSTRAINTS
-- =====================================================

-- Exemplo: Remover constraint
-- ALTER TABLE `ConcretoUsinagens` 
-- DROP CONSTRAINT `chk_volume_positivo`;

-- =====================================================
-- 11. VERIFICAÇÕES E CONSULTAS ÚTEIS
-- =====================================================

-- Verificar estrutura atual da tabela
-- DESCRIBE `ConcretoUsinagens`;

-- Verificar índices da tabela
-- SHOW INDEX FROM `ConcretoUsinagens`;

-- Verificar foreign keys
-- SELECT 
--     CONSTRAINT_NAME,
--     TABLE_NAME,
--     COLUMN_NAME,
--     REFERENCED_TABLE_NAME,
--     REFERENCED_COLUMN_NAME
-- FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
-- WHERE TABLE_SCHEMA = DATABASE()
--     AND TABLE_NAME = 'ConcretoUsinagens'
--     AND REFERENCED_TABLE_NAME IS NOT NULL;

-- Verificar registros com dados inconsistentes
-- SELECT * FROM `ConcretoUsinagens` 
-- WHERE `volume` <= 0;

-- Verificar séries duplicadas
-- SELECT `serie`, COUNT(*) as quantidade
-- FROM `ConcretoUsinagens`
-- GROUP BY `serie`
-- HAVING COUNT(*) > 1;

-- Verificar registros sem produto_composto válido
-- SELECT u.* 
-- FROM `ConcretoUsinagens` u
-- LEFT JOIN `ProdutoComposto` p ON u.`produto_composto_id` = p.`id`
-- WHERE p.`id` IS NULL;

-- =====================================================
-- 12. BACKUP E RESTAURAÇÃO
-- =====================================================

-- Criar backup da tabela antes de alterações importantes
-- CREATE TABLE `ConcretoUsinagens_backup_YYYYMMDD` AS 
-- SELECT * FROM `ConcretoUsinagens`;

-- Restaurar de backup (se necessário)
-- TRUNCATE TABLE `ConcretoUsinagens`;
-- INSERT INTO `ConcretoUsinagens` 
-- SELECT * FROM `ConcretoUsinagens_backup_YYYYMMDD`;

-- =====================================================
-- FIM DO SCRIPT
-- =====================================================
