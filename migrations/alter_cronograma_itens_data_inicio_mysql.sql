-- Data de início opcional por item do cronograma
ALTER TABLE CronogramaItens
  ADD COLUMN data_inicio DATE NULL COMMENT 'Início planejado do item' AFTER tanque_id;
