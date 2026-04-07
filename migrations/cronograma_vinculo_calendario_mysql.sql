-- Vincula um calendário a um prefixo de índice do cronograma (contrato).
-- Itens com índice igual ao prefixo ou descendente (ex.: 1, 1.1, 1.2.1) usam esse calendário
-- na distribuição prevista (dias úteis + feriados). Prefixo mais longo prevalece.

CREATE TABLE IF NOT EXISTS CronogramaVinculosCalendario (
    id INT AUTO_INCREMENT PRIMARY KEY,
    contrato_id INT NOT NULL,
    indice_prefixo VARCHAR(50) NOT NULL COMMENT 'Ex.: 1 ou 2.3 — raiz da árvore',
    indice_sort VARCHAR(200) NOT NULL DEFAULT '' COMMENT 'Chave de ordenação (mesmo padrão de CronogramaItens)',
    calendario_id INT NOT NULL,
    criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
    atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_cron_vinc_contrato_indice (contrato_id, indice_prefixo),
    INDEX idx_cron_vinc_contrato (contrato_id),
    CONSTRAINT fk_cron_vinc_contrato FOREIGN KEY (contrato_id) REFERENCES contratos(id) ON DELETE CASCADE,
    CONSTRAINT fk_cron_vinc_cal FOREIGN KEY (calendario_id) REFERENCES CronogramaCalendarios(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Calendário por prefixo de índice no cronograma do contrato';
