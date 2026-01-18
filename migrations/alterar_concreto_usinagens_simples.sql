-- =====================================================
-- Script de Migração SIMPLIFICADO: Alterar tabela ConcretoUsinagens
-- Data: 2024
-- Descrição: Script simplificado para alterações comuns na tabela ConcretoUsinagens
-- 
-- ATENÇÃO: Execute apenas os comandos necessários. Descomente as linhas que deseja executar.
-- =====================================================

-- =====================================================
-- ADICIONAR CAMPOS COMUNS
-- =====================================================

-- Adicionar campo observações
-- ALTER TABLE `ConcretoUsinagens` 
-- ADD COLUMN `observacoes` TEXT NULL COMMENT 'Observações sobre a usinagem' 
-- AFTER `dados_adicionais`;

-- Adicionar campo status
-- ALTER TABLE `ConcretoUsinagens` 
-- ADD COLUMN `status` VARCHAR(20) NULL DEFAULT 'Ativo' COMMENT 'Status da usinagem' 
-- AFTER `nf`;

-- Adicionar campo volume_produzido
-- ALTER TABLE `ConcretoUsinagens` 
-- ADD COLUMN `volume_produzido` DECIMAL(10, 2) NULL COMMENT 'Volume produzido em m³' 
-- AFTER `volume`;

-- Adicionar campo concretagem_id (relacionar com ConcretoConcretagens)
-- ALTER TABLE `ConcretoUsinagens` 
-- ADD COLUMN `concretagem_id` INT NULL COMMENT 'ID da concretagem associada' 
-- AFTER `produto_composto_id`;
-- 
-- ALTER TABLE `ConcretoUsinagens` 
-- ADD CONSTRAINT `fk_concreto_usinagens_concretagem` 
-- FOREIGN KEY (`concretagem_id`) REFERENCES `ConcretoConcretagens`(`id`) 
-- ON DELETE SET NULL ON UPDATE CASCADE;

-- =====================================================
-- MODIFICAR CAMPOS EXISTENTES
-- =====================================================

-- Aumentar tamanho do campo serie
-- ALTER TABLE `ConcretoUsinagens` 
-- MODIFY COLUMN `serie` VARCHAR(200) NOT NULL;

-- Aumentar tamanho do campo flow
-- ALTER TABLE `ConcretoUsinagens` 
-- MODIFY COLUMN `flow` VARCHAR(100) NULL;

-- Aumentar tamanho do campo nf
-- ALTER TABLE `ConcretoUsinagens` 
-- MODIFY COLUMN `nf` VARCHAR(100) NULL;

-- Aumentar precisão do campo volume
-- ALTER TABLE `ConcretoUsinagens` 
-- MODIFY COLUMN `volume` DECIMAL(12, 3) NOT NULL;

-- =====================================================
-- ADICIONAR ÍNDICES PARA PERFORMANCE
-- =====================================================

-- Índice para data_usinagem (melhora buscas por data)
-- CREATE INDEX `idx_concreto_usinagens_data_usinagem` 
-- ON `ConcretoUsinagens`(`data_usinagem`);

-- Índice para produto_composto_id
-- CREATE INDEX `idx_concreto_usinagens_produto_composto` 
-- ON `ConcretoUsinagens`(`produto_composto_id`);

-- =====================================================
-- ATUALIZAR DADOS
-- =====================================================

-- Copiar volume para volume_produzido (se campo foi adicionado)
-- UPDATE `ConcretoUsinagens` 
-- SET `volume_produzido` = `volume` 
-- WHERE `volume_produzido` IS NULL;

-- Preencher nf vazias
-- UPDATE `ConcretoUsinagens` 
-- SET `nf` = CONCAT('NF-', `id`) 
-- WHERE `nf` IS NULL OR `nf` = '';

-- =====================================================
-- VERIFICAÇÕES
-- =====================================================

-- Ver estrutura da tabela
-- DESCRIBE `ConcretoUsinagens`;

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
