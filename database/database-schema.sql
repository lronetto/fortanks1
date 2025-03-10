-- Criação do banco de dados
CREATE DATABASE IF NOT EXISTS sistema_solicitacoes;
USE sistema_solicitacoes;

-- Tabela de usuários
CREATE TABLE IF NOT EXISTS usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    senha VARCHAR(255) NOT NULL,
    departamento VARCHAR(50) NOT NULL,
    cargo ENUM('colaborador', 'gerente', 'diretor', 'admin') NOT NULL,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabela de materiais
CREATE TABLE IF NOT EXISTS materiais (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    descricao TEXT,
    categoria VARCHAR(50) NOT NULL,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabela de solicitações
CREATE TABLE IF NOT EXISTS solicitacoes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    material_id INT NOT NULL,
    quantidade INT NOT NULL,
    justificativa TEXT NOT NULL,
    solicitante_id INT NOT NULL,
    aprovador_id INT,
    status ENUM('pendente', 'aprovada', 'rejeitada', 'finalizada') NOT NULL DEFAULT 'pendente',
    observacao TEXT,
    data_solicitacao TIMESTAMP NOT NULL,
    data_aprovacao TIMESTAMP NULL,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (material_id) REFERENCES materiais(id),
    FOREIGN KEY (solicitante_id) REFERENCES usuarios(id),
    FOREIGN KEY (aprovador_id) REFERENCES usuarios(id)
);

-- Usuário administrador padrão (senha: admin123)
INSERT INTO usuarios (nome, email, senha, departamento, cargo) VALUES 
('Administrador', 'admin@empresa.com', '$2b$12$1xxxxxxxxxxxxxxxxxxxxxxuZLbwxnPQ0FxXHhkn4kQuRZxVzQJxxxxxu', 'TI', 'admin');

-- Alguns materiais iniciais para teste
INSERT INTO materiais (nome, descricao, categoria) VALUES 
('Papel A4', 'Pacote com 500 folhas', 'Escritório'),
('Caneta esferográfica azul', 'Caixa com 50 unidades', 'Escritório'),
('Notebook Dell', 'Inspiron 15 Core i5 8GB RAM 256GB SSD', 'Equipamentos'),
('Mouse sem fio', 'Mouse óptico com pilhas inclusas', 'Equipamentos'),
('Toner HP', 'Compatível com impressoras HP LaserJet', 'Suprimentos');
