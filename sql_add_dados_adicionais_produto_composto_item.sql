-- SQL para adicionar campo dados_adicionais (JSON) na tabela ProdutoCompostoItem
-- Execute este SQL manualmente no MySQL

ALTER TABLE `ProdutoCompostoItem` 
ADD COLUMN `dados_adicionais` JSON NULL AFTER `observacao`;

-- O campo JSON permitirá armazenar dados adicionais como:
-- {
--   "data_inicio": "2024-01-01",
--   "data_termino": "2024-12-31"
-- }

