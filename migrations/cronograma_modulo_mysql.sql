-- =====================================================
-- Módulo Cronograma (por projeto/contrato, tanques, linhas de base, feriados)
-- MySQL / InnoDB / utf8mb4 — nomes de tabelas em PascalCase (CronogramaFeriados, etc.)
-- Execute após backup. Ajuste se os nomes das tabelas Tanques/contratos/usuarios forem diferentes.
-- =====================================================

-- Feriados (cadastro geral; usados para planejamento e exibição)
CREATE TABLE IF NOT EXISTS CronogramaFeriados (
    id INT AUTO_INCREMENT PRIMARY KEY,
    data DATE NOT NULL,
    nome VARCHAR(200) NOT NULL,
    tipo ENUM('nacional','estadual','municipal','facultativo','ponto_facultativo') NOT NULL DEFAULT 'nacional',
    uf CHAR(2) NULL COMMENT 'Sigla do estado, quando aplicável',
    municipio VARCHAR(120) NULL,
    recorrente TINYINT(1) NOT NULL DEFAULT 0 COMMENT '1 = repete todo ano (usa dia/mês)',
    ativo TINYINT(1) NOT NULL DEFAULT 1,
    observacao TEXT NULL,
    criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
    atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_cron_feriados_data (data),
    INDEX idx_cron_feriados_ativo (ativo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Feriados e pontos facultativos para o cronograma';

-- Cronograma atual por tanque no projeto (contrato)
CREATE TABLE IF NOT EXISTS CronogramaTanques (
    id INT AUTO_INCREMENT PRIMARY KEY,
    contrato_id INT NOT NULL,
    tanque_id INT NOT NULL,
    data_inicio_prevista DATE NULL,
    data_fim_prevista DATE NULL,
    data_inicio_real DATE NULL,
    data_fim_real DATE NULL,
    observacao TEXT NULL,
    criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
    atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_cronograma_contrato_tanque (contrato_id, tanque_id),
    INDEX idx_cron_tanques_contrato (contrato_id),
    INDEX idx_cron_tanques_tanque (tanque_id),
    CONSTRAINT fk_cron_tanques_contrato FOREIGN KEY (contrato_id) REFERENCES contratos(id) ON DELETE CASCADE,
    CONSTRAINT fk_cron_tanques_tanque FOREIGN KEY (tanque_id) REFERENCES Tanques(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Datas planejadas e reais do cronograma por tanque no contrato';

-- Linha de base (snapshot nomeado do cronograma de um projeto)
CREATE TABLE IF NOT EXISTS CronogramaLinhasBase (
    id INT AUTO_INCREMENT PRIMARY KEY,
    contrato_id INT NOT NULL,
    nome VARCHAR(200) NOT NULL,
    descricao TEXT NULL,
    data_snapshot DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario_id INT NULL,
    INDEX idx_cron_lb_contrato (contrato_id),
    CONSTRAINT fk_cron_lb_contrato FOREIGN KEY (contrato_id) REFERENCES contratos(id) ON DELETE CASCADE,
    CONSTRAINT fk_cron_lb_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Linhas de base (versões congeladas do cronograma)';

-- Itens da linha de base por tanque
CREATE TABLE IF NOT EXISTS CronogramaLinhasBaseTanques (
    id INT AUTO_INCREMENT PRIMARY KEY,
    linha_base_id INT NOT NULL,
    tanque_id INT NOT NULL,
    data_inicio_prevista DATE NULL,
    data_fim_prevista DATE NULL,
    UNIQUE KEY uq_lb_tanque (linha_base_id, tanque_id),
    INDEX idx_lb_tanques_tanque (tanque_id),
    CONSTRAINT fk_lb_tanques_linha FOREIGN KEY (linha_base_id) REFERENCES CronogramaLinhasBase(id) ON DELETE CASCADE,
    CONSTRAINT fk_lb_tanques_tanque FOREIGN KEY (tanque_id) REFERENCES Tanques(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Datas previstas por tanque em cada linha de base';

-- Módulo de permissão (ajuste ordem se necessário)
INSERT INTO modulos (nome, descricao, icone, url, ordem, status) VALUES
('cronograma', 'Cronograma por projeto, linhas de base e feriados', 'fas fa-calendar-alt', '/cronograma', 95, 'Ativo')
ON DUPLICATE KEY UPDATE
    descricao = VALUES(descricao),
    icone = VALUES(icone),
    url = VALUES(url),
    status = VALUES(status);

-- Conceda permissões pelo painel Admin (Permissões) ou insira em permissoes
-- vinculando modulo_id = (SELECT id FROM modulos WHERE nome = 'cronograma' LIMIT 1)
-- a usuário, departamento ou cargo conforme o padrão do sistema.

-- Itens de linha do cronograma: execute também migrations/cronograma_itens_mysql.sql
