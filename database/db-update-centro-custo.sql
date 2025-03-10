-- Tabela de centros de custo
CREATE TABLE IF NOT EXISTS centros_custo (
    id INT AUTO_INCREMENT PRIMARY KEY,
    codigo VARCHAR(20) NOT NULL UNIQUE,
    nome VARCHAR(100) NOT NULL,
    descricao TEXT,
    ativo BOOLEAN DEFAULT TRUE,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Adicionar coluna centro_custo_id à tabela de solicitações
ALTER TABLE solicitacoes ADD COLUMN centro_custo_id INT AFTER solicitante_id;
ALTER TABLE solicitacoes ADD CONSTRAINT fk_centro_custo FOREIGN KEY (centro_custo_id) REFERENCES centros_custo(id);

-- Inserir alguns centros de custo para teste
INSERT INTO centros_custo (codigo, nome, descricao) VALUES 
('CC001', 'Administração', 'Centro de custo para despesas administrativas'),
('CC002', 'Comercial', 'Centro de custo para equipe comercial e vendas'),
('CC003', 'TI', 'Centro de custo para departamento de tecnologia'),
('CC004', 'Operações', 'Centro de custo para operações e logística'),
('CC005', 'Marketing', 'Centro de custo para marketing e publicidade');
