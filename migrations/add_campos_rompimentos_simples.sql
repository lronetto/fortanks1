-- =====================================================
-- Script de Migração SIMPLIFICADO: Adicionar campos em ConcretoUsinagensRompimentos
-- Data: 2024
-- Descrição: Adiciona os campos data_moldagem e fator_conversao
-- 
-- ATENÇÃO: Execute este script apenas se os campos ainda não existirem.
-- Se os campos já existirem, o script gerará erro.
-- =====================================================

-- Adicionar campo data_moldagem
ALTER TABLE `ConcretoUsinagensRompimentos` 
ADD COLUMN `data_moldagem` DATETIME NULL COMMENT 'Data e hora da moldagem do corpo de prova' 
AFTER `numero_serie`;

-- Adicionar campo fator_conversao
ALTER TABLE `ConcretoUsinagensRompimentos` 
ADD COLUMN `fator_conversao` DECIMAL(5,2) NOT NULL DEFAULT 1.20 COMMENT 'Fator de conversão de kg para MPa' 
AFTER `resultado`;

-- Atualizar registros existentes com o valor padrão do fator de conversão
UPDATE `ConcretoUsinagensRompimentos` 
SET `fator_conversao` = 1.20 
WHERE `fator_conversao` IS NULL;

-- (Opcional) Se ainda não foi feito, renomear numero_cp para numero_serie
-- Descomente as linhas abaixo se necessário:
-- ALTER TABLE `ConcretoUsinagensRompimentos` 
-- CHANGE COLUMN `numero_cp` `numero_serie` INT NOT NULL COMMENT 'Número de série do corpo de prova';

-- (Opcional) Se usinagem_id ainda não permite NULL, descomente:
-- ALTER TABLE `ConcretoUsinagensRompimentos` 
-- MODIFY COLUMN `usinagem_id` INT NULL;

