-- SQL para criação da tabela EstoqueTerceiro
-- Execute este script manualmente no banco de dados MySQL

CREATE TABLE IF NOT EXISTS `EstoqueTerceiro` (
    `id` INT(11) NOT NULL AUTO_INCREMENT,
    `data` DATE NOT NULL,
    `codigo_erp` VARCHAR(50) NOT NULL,
    `nome` VARCHAR(200) NULL DEFAULT NULL COMMENT 'Nome do material na planilha do terceiro',
    `tipo` VARCHAR(50) NULL DEFAULT NULL,
    `unidade` VARCHAR(20) NULL DEFAULT NULL,
    `quantidade` DECIMAL(15,4) NOT NULL DEFAULT 0.0000,
    `ValorUnitario` DECIMAL(15,4) NULL DEFAULT NULL,
    `ValorTotal` DECIMAL(15,4) NULL DEFAULT NULL,
    `criado_em` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `usuario_id` INT(11) NULL DEFAULT NULL,
    PRIMARY KEY (`id`),
    INDEX `idx_codigo_erp` (`codigo_erp`),
    INDEX `idx_data` (`data`),
    INDEX `idx_data_codigo_erp` (`data`, `codigo_erp`),
    INDEX `fk_estoque_terceiro_usuario` (`usuario_id`),
    CONSTRAINT `fk_estoque_terceiro_usuario` FOREIGN KEY (`usuario_id`) 
        REFERENCES `usuarios` (`id`) 
        ON DELETE SET NULL 
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Comentários sobre a tabela
ALTER TABLE `EstoqueTerceiro` 
    COMMENT = 'Tabela para armazenar estoques de terceiros importados via planilha';

-- Migração: adicionar coluna nome se a tabela já existir sem ela (execute se necessário)
-- ALTER TABLE `EstoqueTerceiro` ADD COLUMN `nome` VARCHAR(200) NULL DEFAULT NULL COMMENT 'Nome do material na planilha do terceiro' AFTER `codigo_erp`;
