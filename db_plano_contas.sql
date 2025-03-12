-- Criação da tabela plano_contas

CREATE TABLE IF NOT EXISTS plano_contas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    numero VARCHAR(50) NOT NULL COMMENT 'Número do plano de conta, exemplo: 1.1.01',
    indice VARCHAR(50) NOT NULL COMMENT 'Índice de referência, exemplo: A.1.01',
    descricao VARCHAR(255) NOT NULL COMMENT 'Descrição do plano de conta',
    sequencia INT DEFAULT 0 COMMENT 'Sequência para ordenação',
    ativo TINYINT(1) DEFAULT 1 COMMENT 'Status: 1=Ativo, 0=Inativo',
    criado_em DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT 'Data de criação',
    atualizado_em DATETIME NULL COMMENT 'Data da última atualização',
    UNIQUE KEY (numero),
    UNIQUE KEY (indice)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT 'Tabela de planos de conta'; 