# Migração da Estrutura do Banco de Dados

Este documento descreve os scripts de migração para a estrutura do banco de dados do sistema Fortanks, especialmente relacionados às tabelas de credenciais do ERP.

## Script para Adicionar Coluna configuracao_id

A migração adiciona e configura a coluna `configuracao_id` na tabela `erp_credenciais`, estabelecendo um relacionamento correto entre as tabelas `erp_configuracoes` e `erp_credenciais`.

### Objetivo

Este processo corrige a estrutura do banco de dados para garantir que:

1. A tabela `erp_credenciais` tenha uma coluna `configuracao_id` que referencia a tabela `erp_configuracoes`
2. Os dados existentes sejam migrados corretamente da coluna `usuario_id` para `configuracao_id`
3. Uma chave estrangeira seja criada para manter a integridade referencial

### Opções de Migração

Existem duas maneiras de executar esta migração:

#### 1. Utilizando o Script Python:

O script Python gerencia todo o processo de migração, incluindo verificações e log detalhado.

```bash
# Para executar uma simulação (sem alterar o banco de dados):
python scripts/migrate_configuracao_id.py --dry-run

# Para executar a migração real:
python scripts/migrate_configuracao_id.py
```

#### 2. Utilizando o Script SQL:

O script SQL pode ser executado diretamente no MySQL:

```bash
# Via linha de comando:
mysql -u seu_usuario -p seu_banco < scripts/migrate_configuracao_id.sql

# Ou através de alguma ferramenta de administração de banco de dados
# como phpMyAdmin, MySQL Workbench, etc.
```

### O Que o Script Faz

1. **Verifica se a coluna existe**: O script primeiro verifica se a coluna já existe para evitar erros
2. **Adiciona a coluna**: Se necessário, adiciona a coluna `configuracao_id` após a coluna `usuario_id`
3. **Migra os dados**: Copia os valores da coluna `usuario_id` para `configuracao_id`
4. **Adiciona chave estrangeira**: Cria um relacionamento entre as tabelas `erp_credenciais` e `erp_configuracoes`

### Impacto no Sistema

Esta migração é segura e não deve causar interrupções no sistema. No entanto, recomenda-se:

- Executar a migração durante horários de baixo uso do sistema
- Fazer um backup do banco de dados antes da migração
- Verificar se todas as credenciais continuam funcionando após a migração

### Verificação Pós-Migração

Após executar a migração, você pode verificar se foi bem-sucedida com a seguinte consulta SQL:

```sql
SELECT COUNT(*) FROM erp_credenciais 
WHERE configuracao_id IS NULL OR configuracao_id = 0;
```

O resultado deve ser zero se todos os registros foram migrados corretamente.

## Motivação da Mudança

Esta mudança foi necessária para corrigir uma inconsistência na estrutura do banco de dados, onde a relação entre credenciais e configurações do ERP estava usando a coluna `usuario_id` ao invés de uma coluna específica `configuracao_id`. 

A correção permite:

1. Melhor semântica na estrutura do banco (nomes de colunas mais claros)
2. Integridade referencial adequada através de chaves estrangeiras
3. Preparação para futuras melhorias no módulo de integração com ERP 