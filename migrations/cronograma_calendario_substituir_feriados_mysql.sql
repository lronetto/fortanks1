-- Substitui CronogramaFeriados por calendários com dias úteis (por semana) e feriados por calendário.
-- Execute manualmente em ambiente de homologação/produção após backup.

DROP TABLE IF EXISTS CronogramaFeriados;

CREATE TABLE IF NOT EXISTS CronogramaCalendarios (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nome VARCHAR(160) NOT NULL,
  observacao TEXT NULL,
  seg_util TINYINT(1) NOT NULL DEFAULT 1,
  ter_util TINYINT(1) NOT NULL DEFAULT 1,
  qua_util TINYINT(1) NOT NULL DEFAULT 1,
  qui_util TINYINT(1) NOT NULL DEFAULT 1,
  sex_util TINYINT(1) NOT NULL DEFAULT 1,
  sab_util TINYINT(1) NOT NULL DEFAULT 0,
  dom_util TINYINT(1) NOT NULL DEFAULT 0,
  criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Calendário: padrão de dias úteis na semana';

CREATE TABLE IF NOT EXISTS CronogramaCalendarioFeriados (
  id INT AUTO_INCREMENT PRIMARY KEY,
  calendario_id INT NOT NULL,
  data DATE NOT NULL,
  nome VARCHAR(200) NOT NULL,
  observacao TEXT NULL,
  criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_cron_cal_fer_cal FOREIGN KEY (calendario_id) REFERENCES CronogramaCalendarios(id) ON DELETE CASCADE,
  UNIQUE KEY uq_cron_cal_feriado_data (calendario_id, data),
  INDEX idx_cron_cal_fer_data (data)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Feriados por calendário';
