-- Estrutura do banco de dados para o módulo de integração ERP
-- Adicione este script ao seu banco de dados existente

-- Tabela para armazenar as transações importadas do ERP
CREATE TABLE IF NOT EXISTS erp_transacoes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    centro_custo VARCHAR(20) NOT NULL,
    categoria VARCHAR(20),
    data_pagamento VARCHAR(50),
    documento VARCHAR(100),
    emitente VARCHAR(255),
    historico TEXT,
    valor DECIMAL(15,2) NOT NULL,
    data_processamento DATETIME NOT NULL,
    importado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_centro_custo (centro_custo),
    INDEX idx_categoria (categoria),
    INDEX idx_data_pagamento (data_pagamento),
    INDEX idx_emitente (emitente(100))
);

-- Tabela para armazenar configurações de integração
CREATE TABLE IF NOT EXISTS erp_configuracoes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    url_login VARCHAR(255) NOT NULL,
    url_relatorio VARCHAR(255) NOT NULL,
    tipo_relatorio VARCHAR(50) NOT NULL,
    periodo VARCHAR(50) DEFAULT 'atual',
    ultimo_acesso DATETIME,
    ativo BOOLEAN DEFAULT TRUE,
    criado_por INT,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (criado_por) REFERENCES usuarios(id)
);

-- Tabela para armazenar credenciais de acesso (criptografadas)
CREATE TABLE IF NOT EXISTS erp_credenciais (
    id INT AUTO_INCREMENT PRIMARY KEY,
    configuracao_id INT NOT NULL,
    usuario VARCHAR(100) NOT NULL,
    senha_encriptada BLOB NOT NULL,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (configuracao_id) REFERENCES erp_configuracoes(id) ON DELETE CASCADE
);

-- Tabela para armazenar histórico de importações
CREATE TABLE IF NOT EXISTS erp_importacoes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    configuracao_id INT,
    usuario_id INT,
    tipo ENUM('MANUAL', 'AUTOMATICA') NOT NULL,
    arquivo_nome VARCHAR(255),
    total_registros INT DEFAULT 0,
    valor_total DECIMAL(15,2) DEFAULT 0,
    status ENUM('SUCESSO', 'ERRO', 'PARCIAL') NOT NULL,
    mensagem TEXT,
    data_inicio DATETIME NOT NULL,
    data_fim DATETIME,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (configuracao_id) REFERENCES erp_configuracoes(id),
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
);