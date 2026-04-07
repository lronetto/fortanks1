-- Migração: índice INT -> hierárquico + indice_sort (tabela CronogramaItens)
-- Use APENAS se CronogramaItens já existia com a coluna indice como INT.
-- Se a tabela foi criada com migrations/cronograma_itens_mysql.sql (versão nova), ignore.

ALTER TABLE CronogramaItens
    MODIFY COLUMN indice VARCHAR(50) NOT NULL DEFAULT '' COMMENT 'Hierárquico: 1, 1.1, 1.1.1';

ALTER TABLE CronogramaItens
    ADD COLUMN indice_sort VARCHAR(200) NOT NULL DEFAULT '' COMMENT 'Derivação para ORDER BY' AFTER indice;

UPDATE CronogramaItens SET indice_sort = LPAD(CAST(indice AS UNSIGNED), 6, '0')
WHERE indice REGEXP '^[0-9]+$' AND indice_sort = '';

ALTER TABLE CronogramaItens DROP INDEX idx_cron_itens_ordem;
ALTER TABLE CronogramaItens ADD INDEX idx_cron_itens_ordem (contrato_id, indice_sort);
