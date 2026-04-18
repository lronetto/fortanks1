-- Tabela TanquesTransportes — transporte em lote (NF, peças em JSON, etc.)
-- Compatível com models/tanque/entities/transportes.py
-- MySQL 5.7+ / 8.0, InnoDB, utf8mb4
--
-- Aplicação:
--   mysql -u USUARIO -p NOME_BANCO < scripts/sql/criar_tanques_transportes.sql
--
-- Em MySQL 5.7, se der erro em duas colunas DATETIME com CURRENT_TIMESTAMP,
-- remova DEFAULT da created_at e preencha só pela aplicação, ou use apenas uma com ON UPDATE.

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- DROP TABLE IF EXISTS `TanquesTransportes`;

CREATE TABLE IF NOT EXISTS `TanquesTransportes` (
  `id` int NOT NULL AUTO_INCREMENT,
  `nota` int DEFAULT NULL COMMENT 'Número da NF (inteiro)',
  `cte` varchar(64) DEFAULT NULL,
  `transportadora` varchar(255) DEFAULT NULL,
  `data_transporte` date DEFAULT NULL,
  `pecas` text DEFAULT NULL COMMENT 'JSON: array de ids de TanquesPecas',
  `dados_adicionais` text DEFAULT NULL COMMENT 'JSON: placa_carreta, cte, etc.',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_TanquesTransportes_nota` (`nota`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET FOREIGN_KEY_CHECKS = 1;
