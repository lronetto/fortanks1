# Segurança de Senhas no Sistema Fortanks

## Visão Geral

O sistema Fortanks implementa uma solução segura para armazenamento e gerenciamento de senhas, especialmente para credenciais de acesso a sistemas ERP externos. As senhas são protegidas usando criptografia forte através da biblioteca Fernet (parte do pacote `cryptography`).

## Como Funciona

- **Criptografia Fernet**: Utiliza o algoritmo AES-128 em modo CBC com PKCS#7 para padding
- **Gerenciamento de Chaves**: A chave de criptografia é armazenada no arquivo `.env` e gerada aleatoriamente
- **Compatibilidade**: O sistema mantém compatibilidade com senhas criptografadas pelo método antigo (base64)

## Arquivos Relevantes

- `utils/crypto.py`: Contém todas as funções de criptografia e descriptografia
- `scripts/migrate_passwords.py`: Script para migrar senhas do formato antigo para o novo
- `.env`: Armazena a chave de criptografia no parâmetro `ENCRYPTION_KEY`

## Funções Principais

- `encrypt_password(senha)`: Criptografa uma senha usando Fernet
- `decrypt_password(senha_criptografada)`: Descriptografa uma senha
- `recrypt_password(senha_criptografada_antiga)`: Converte senhas do formato antigo para o novo

## Migração de Senhas

Após atualizar o código para usar o novo sistema de criptografia, é necessário migrar as senhas existentes. Siga os passos abaixo:

1. Instale a dependência necessária:
   ```
   pip install cryptography==42.0.5
   ```

2. Execute primeiro uma simulação da migração para verificar o impacto:
   ```
   python scripts/migrate_passwords.py --dry-run
   ```

3. Se a simulação for bem-sucedida, execute a migração real:
   ```
   python scripts/migrate_passwords.py
   ```

4. Verifique o arquivo de log para confirmar que todas as senhas foram migradas com sucesso.

## Configuração da Chave de Criptografia

A primeira vez que o sistema for executado após a atualização, ele gerará uma nova chave de criptografia e exibirá uma mensagem no log. **É essencial** adicionar esta chave ao arquivo `.env`:

```
ENCRYPTION_KEY=sua_chave_gerada_aqui
```

**ATENÇÃO:** A chave de criptografia é necessária para descriptografar senhas. Sem ela, não será possível acessar as senhas já criptografadas. Mantenha um backup seguro desta chave.

## Segurança Adicional

Recomendações para aumentar ainda mais a segurança:

1. **Rotação de Chaves**: Considere implementar um sistema de rotação de chaves periodicamente
2. **Armazenamento Seguro**: Em produção, considere usar um gerenciador de segredos como HashiCorp Vault ou AWS KMS
3. **Logs de Auditoria**: Implemente logs detalhados de todas as operações que envolvem acesso às senhas
4. **Monitoramento**: Configure alertas para tentativas de acesso não autorizado às credenciais

## Implementação Técnica

A implementação utiliza:

- **PBKDF2HMAC**: Para a derivação de chaves a partir de dados aleatórios
- **SHA256**: Como algoritmo de hash
- **Chaves de 32 bytes**: Para máxima segurança com AES-128
- **Tratamento de exceções**: Robusto para lidar com falhas de criptografia/descriptografia

## Atualizações Futuras

Possíveis melhorias para implementações futuras:

- Implementar rotação de chaves automática
- Adicionar monitoramento de tentativas de acesso às senhas
- Implementar expiração de senhas
- Adicionar verificação de entropia para garantir senhas fortes 