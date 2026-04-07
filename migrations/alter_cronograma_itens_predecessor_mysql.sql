-- Índice predecessor — use se CronogramaItens já existir sem predecessor_id
-- Tabela esperada: CronogramaItens (PascalCase)

ALTER TABLE CronogramaItens
    ADD COLUMN predecessor_id INT NULL COMMENT 'Item predecessor (mesmo projeto)' AFTER indice_sort;

ALTER TABLE CronogramaItens
    ADD CONSTRAINT fk_cron_itens_predecessor FOREIGN KEY (predecessor_id) REFERENCES CronogramaItens(id) ON DELETE SET NULL;
