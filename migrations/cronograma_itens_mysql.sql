-- Itens de linha do cronograma por projeto (contrato): nome, índice hierárquico, peso, tanque opcional
-- Execute após cronograma_modulo_mysql.sql (requer contratos e Tanques).
-- Tabela: CronogramaItens

CREATE TABLE IF NOT EXISTS CronogramaItens (
    id INT AUTO_INCREMENT PRIMARY KEY,
    contrato_id INT NOT NULL,
    nome VARCHAR(200) NOT NULL,
    indice VARCHAR(50) NOT NULL DEFAULT '' COMMENT 'Hierárquico: 1, 1.1, 1.1.1',
    indice_sort VARCHAR(200) NOT NULL DEFAULT '' COMMENT 'Derivação para ORDER BY (segmentos preenchidos)',
    predecessor_id INT NULL COMMENT 'Item predecessor (mesmo projeto)',
    peso DECIMAL(12, 4) NOT NULL DEFAULT 0.0000 COMMENT 'Peso para ponderação do cronograma',
    tanque_id INT NULL COMMENT 'Opcional: vincula o item a um tanque do projeto',
    data_inicio DATE NULL COMMENT 'Início planejado do item',
    criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
    atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_cron_itens_contrato (contrato_id),
    INDEX idx_cron_itens_ordem (contrato_id, indice_sort),
    CONSTRAINT fk_cron_itens_contrato FOREIGN KEY (contrato_id) REFERENCES contratos(id) ON DELETE CASCADE,
    CONSTRAINT fk_cron_itens_predecessor FOREIGN KEY (predecessor_id) REFERENCES CronogramaItens(id) ON DELETE SET NULL,
    CONSTRAINT fk_cron_itens_tanque FOREIGN KEY (tanque_id) REFERENCES Tanques(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Linhas/itens do cronograma por contrato';
