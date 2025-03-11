# Sistema de Solicitações

Sistema web para gerenciamento de solicitações de materiais, importação de notas fiscais e integração com ERP.

## Requisitos

- Python 3.8 ou superior
- MySQL 5.7 ou superior
- wkhtmltopdf (para geração de PDFs)

## Instalação

1. Clone o repositório:
```bash
git clone [url-do-repositorio]
cd [nome-do-diretorio]
```

2. Crie um ambiente virtual e ative-o:
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

3. Instale as dependências:
```bash
pip install -r requirements.txt
```

4. Instale o wkhtmltopdf:
- Windows: Baixe e instale do site oficial (https://wkhtmltopdf.org/downloads.html)
- Linux: `sudo apt-get install wkhtmltopdf`
- Mac: `brew install wkhtmltopdf`

5. Configure o arquivo .env:
- Copie o arquivo `.env.example` para `.env`
- Preencha as variáveis com suas configurações

## Configuração do Banco de Dados

1. Crie um banco de dados MySQL
2. Execute os scripts de criação das tabelas localizados em `database/`

## Executando o Sistema

```bash
python app.py
```

O sistema estará disponível em `http://localhost:5000`

## Módulos

- **Importação NF**: Gerenciamento de notas fiscais
- **Integração ERP**: Integração com sistema ERP
- **Checklist**: Gerenciamento de checklists
- **Solicitações**: Gerenciamento de solicitações de materiais

## Usuários e Permissões

- **Admin**: Acesso total ao sistema
- **Gerente/Diretor**: Aprovação de solicitações e acesso a relatórios
- **Usuário**: Criação de solicitações e visualização própria

## Suporte

Para suporte, entre em contato com a equipe de desenvolvimento. 