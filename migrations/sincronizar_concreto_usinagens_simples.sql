-- =====================================================
-- Script de Migração SIMPLIFICADO: Sincronizar ConcretoUsinagens
-- Data: 2024
-- Descrição: Adiciona campos usados no controller que podem não existir no banco
-- 
-- ATENÇÃO: Faça backup antes de executar!
-- Este script não verifica se os campos existem - execute apenas se necessário.
-- =====================================================

-- Adicionar campo volume_produzido (remova IF NOT EXISTS se seu MySQL não suportar)
ALTER TABLE `ConcretoUsinagens` 
ADD COLUMN `volume_produzido` DECIMAL(10, 2) NULL COMMENT 'Volume produzido em m³' 
AFTER `volume`;

-- Copiar valores de volume para volume_produzido
UPDATE `ConcretoUsinagens` 
SET `volume_produzido` = `volume` 
WHERE `volume_produzido` IS NULL;

-- Adicionar campo traco_id (remova IF NOT EXISTS se seu MySQL não suportar)
ALTER TABLE `ConcretoUsinagens` 
ADD COLUMN `traco_id` INT NULL COMMENT 'ID do traço de concreto (legado)' 
AFTER `produto_composto_id`;

-- Adicionar campo concretagem_id
ALTER TABLE `ConcretoUsinagens` 
ADD COLUMN `concretagem_id` INT NULL COMMENT 'ID da concretagem associada' 
AFTER `produto_composto_id`;

-- Adicionar foreign key para concretagem_id (comente se já existir)
-- ALTER TABLE `ConcretoUsinagens` 
-- ADD CONSTRAINT `fk_concreto_usinagens_concretagem` 
-- FOREIGN KEY (`concretagem_id`) REFERENCES `ConcretoConcretagens`(`id`) 
-- ON DELETE SET NULL ON UPDATE CASCADE;

-- Adicionar campo responsavel_id
ALTER TABLE `ConcretoUsinagens` 
ADD COLUMN `responsavel_id` INT NULL COMMENT 'ID do colaborador responsável' 
AFTER `traco_id`;

-- Adicionar foreign key para responsavel_id (comente se já existir)
-- ALTER TABLE `ConcretoUsinagens` 
-- ADD CONSTRAINT `fk_concreto_usinagens_responsavel` 
-- FOREIGN KEY (`responsavel_id`) REFERENCES `colaboradores`(`id`) 
-- ON DELETE SET NULL ON UPDATE CASCADE;

-- Adicionar campo umidade
ALTER TABLE `ConcretoUsinagens` 
ADD COLUMN `umidade` DECIMAL(5, 2) NULL DEFAULT 0 COMMENT 'Umidade em porcentagem' 
AFTER `responsavel_id`;

-- Adicionar campo status
ALTER TABLE `ConcretoUsinagens` 
ADD COLUMN `status` VARCHAR(20) NULL DEFAULT 'Ativo' COMMENT 'Status da usinagem' 
AFTER `umidade`;

-- Atualizar status dos registros existentes
UPDATE `ConcretoUsinagens` 
SET `status` = 'Ativo' 
WHERE `status` IS NULL OR `status` = '';

-- Adicionar campo observacoes
ALTER TABLE `ConcretoUsinagens` 
ADD COLUMN `observacoes` TEXT NULL COMMENT 'Observações sobre a usinagem' 
AFTER `status`;

-- Adicionar campo quantidade_cps
ALTER TABLE `ConcretoUsinagens` 
ADD COLUMN `quantidade_cps` INT NULL DEFAULT 0 COMMENT 'Quantidade de corpos de prova' 
AFTER `observacoes`;

-- Adicionar campo nota
ALTER TABLE `ConcretoUsinagens` 
ADD COLUMN `nota` VARCHAR(50) NULL COMMENT 'Nota da usinagem' 
AFTER `nf`;

-- Copiar valores de nf para nota
UPDATE `ConcretoUsinagens` 
SET `nota` = `nf` 
WHERE (`nota` IS NULL OR `nota` = '') AND `nf` IS NOT NULL;

-- Adicionar campo nbt
ALTER TABLE `ConcretoUsinagens` 
ADD COLUMN `nbt` VARCHAR(50) NULL COMMENT 'Número do NBT' 
AFTER `nota`;

-- Adicionar índices para melhorar performance (comente se já existirem)
-- CREATE INDEX `idx_concreto_usinagens_data_usinagem` ON `ConcretoUsinagens`(`data_usinagem`);
-- CREATE INDEX `idx_concreto_usinagens_produto_composto` ON `ConcretoUsinagens`(`produto_composto_id`);
-- CREATE INDEX `idx_concreto_usinagens_status` ON `ConcretoUsinagens`(`status`);
-- CREATE INDEX `idx_concreto_usinagens_concretagem` ON `ConcretoUsinagens`(`concretagem_id`);

-- Verificar estrutura final
DESCRIBE `ConcretoUsinagens`;
