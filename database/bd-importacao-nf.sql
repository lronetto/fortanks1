-- Estrutura do banco de dados para o módulo de importação de NF
-- Adicione este script ao seu banco de dados existente

-- Tabela para as notas fiscais
CREATE TABLE IF NOT EXISTS nf_notas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    chave_acesso VARCHAR(44) NOT NULL UNIQUE,
    data_emissao DATETIME NOT NULL,
    valor_total DECIMAL(15,2) NOT NULL,
    cnpj_emitente VARCHAR(14) NOT NULL,
    nome_emitente VARCHAR(100) NOT NULL,
    cnpj_destinatario VARCHAR(14) NOT NULL,
    nome_destinatario VARCHAR(100) NOT NULL,
    xml_data LONGTEXT,
    status_processamento ENUM('importado', 'processado', 'atualizado', 'erro') NOT NULL DEFAULT 'importado',
    data_importacao DATETIME NOT NULL,
    data_atualizacao DATETIME NULL,
    observacoes TEXT,
    INDEX idx_chave_acesso (chave_acesso),
    INDEX idx_cnpj_emitente (cnpj_emitente),
    INDEX idx_cnpj_destinatario (cnpj_destinatario),
    INDEX idx_data_emissao (data_emissao),
    INDEX idx_status (status_processamento)
);

-- Tabela para os itens das notas fiscais
CREATE TABLE IF NOT EXISTS nf_itens (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nf_id INT NOT NULL,
    codigo VARCHAR(60),
    descricao VARCHAR(255) NOT NULL,
    quantidade DECIMAL(15,4) NOT NULL,
    valor_unitario DECIMAL(15,4) NOT NULL,
    valor_total DECIMAL(15,2) NOT NULL,
    ncm VARCHAR(8),
    cfop VARCHAR(4),
    unidade VARCHAR(6),
    data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (nf_id) REFERENCES nf_notas(id) ON DELETE CASCADE,
    INDEX idx_nf_id (nf_id),
    INDEX idx_codigo (codigo),
    INDEX idx_descricao (descricao(191))
);

-- Adicionar campo na tabela de materiais para relacionar com produtos de NF
ALTER TABLE materiais ADD COLUMN codigo VARCHAR(60) NULL;
ALTER TABLE materiais ADD INDEX idx_codigo (codigo);

-- Adicionar campo na tabela de solicitações para relacionar com NF
ALTER TABLE solicitacoes ADD COLUMN nf_id INT NULL;
ALTER TABLE solicitacoes ADD CONSTRAINT fk_solicitacao_nf FOREIGN KEY (nf_id) REFERENCES nf_notas(id);

-- Adicionar campo na tabela de itens_solicitacao para valor unitário
ALTER TABLE itens_solicitacao ADD COLUMN valor_unitario DECIMAL(15,4) NULL;
