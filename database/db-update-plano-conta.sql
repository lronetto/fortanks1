-- Adicionar coluna plano_conta à tabela materiais
ALTER TABLE materiais ADD COLUMN plano_conta VARCHAR(30) AFTER categoria;

-- Criar tabela para gerenciar planos de conta
CREATE TABLE IF NOT EXISTS planos_conta (
    id INT AUTO_INCREMENT PRIMARY KEY,
    codigo VARCHAR(20) NOT NULL UNIQUE,
    descricao VARCHAR(100) NOT NULL,
    tipo ENUM('RECEITA', 'DESPESA', 'ATIVO', 'PASSIVO', 'PATRIMONIO') NOT NULL,
    ativo BOOLEAN DEFAULT TRUE,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Adicionar alguns planos de conta padrão
INSERT INTO planos_conta (codigo, descricao, tipo) VALUES
('1.1.1', 'Materiais de Escritório', 'DESPESA'),
('1.1.2', 'Equipamentos de Informática', 'ATIVO'),
('1.1.3', 'Materiais de Limpeza', 'DESPESA'),
('1.1.4', 'Materiais de Manutenção', 'DESPESA'),
('1.1.5', 'Equipamentos Operacionais', 'ATIVO');

-- Adicionando índice à coluna plano_conta na tabela materiais
CREATE INDEX idx_plano_conta ON materiais(plano_conta);
