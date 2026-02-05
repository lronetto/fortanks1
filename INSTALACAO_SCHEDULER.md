# Instalação do Serviço de Scheduler

Este documento descreve como instalar e configurar o serviço de scheduler do Fortanks como um serviço systemd no Linux.

## Pré-requisitos

- Sistema operacional Linux
- Python 3.x instalado
- Virtual environment configurado
- Permissões de root/sudo para instalar serviços systemd

## Instalação

### 1. Copiar o arquivo de serviço

Copie o arquivo `fortanks-scheduler.service` para o diretório de serviços systemd:

```bash
sudo cp fortanks-scheduler.service /etc/systemd/system/
```

### 2. Ajustar caminhos (se necessário)

Edite o arquivo de serviço se os caminhos forem diferentes:

```bash
sudo nano /etc/systemd/system/fortanks-scheduler.service
```

Verifique e ajuste os seguintes caminhos:
- `WorkingDirectory`: Diretório do projeto
- `ExecStart`: Caminho completo para o Python e o script scheduler_service.py
- `User` e `Group`: Usuário e grupo que executarão o serviço

### 3. Recarregar systemd

Após copiar o arquivo, recarregue o systemd:

```bash
sudo systemctl daemon-reload
```

### 4. Habilitar o serviço

Para que o serviço inicie automaticamente na inicialização do sistema:

```bash
sudo systemctl enable fortanks-scheduler.service
```

### 5. Iniciar o serviço

Para iniciar o serviço imediatamente:

```bash
sudo systemctl start fortanks-scheduler.service
```

### 6. Verificar status

Para verificar se o serviço está rodando:

```bash
sudo systemctl status fortanks-scheduler.service
```

## Comandos Úteis

### Parar o serviço
```bash
sudo systemctl stop fortanks-scheduler.service
```

### Reiniciar o serviço
```bash
sudo systemctl restart fortanks-scheduler.service
```

### Ver logs do serviço
```bash
sudo journalctl -u fortanks-scheduler.service -f
```

### Ver logs do arquivo
Os logs também são salvos em: `logs/scheduler.log`

### Desabilitar inicialização automática
```bash
sudo systemctl disable fortanks-scheduler.service
```

## Jobs Configurados

O scheduler executa os seguintes jobs:

- **Job de Email (5 minutos)**: Processa emails recebidos
- **Job de Email (15 minutos)**: Preparado para futuras funcionalidades
- **Job Diário (00:00)**: Executa importação de dados analíticos
- **Job Semanal (Domingo 23:59)**: Gera relatório semanal
- **Job Horário**: Processa importações do Arquivei

## Troubleshooting

### Serviço não inicia

1. Verifique os logs:
   ```bash
   sudo journalctl -u fortanks-scheduler.service -n 50
   ```

2. Verifique se o Python está no caminho correto:
   ```bash
   /home/sfortanks/sfortanks/venv/bin/python --version
   ```

3. Verifique se o arquivo scheduler_service.py existe e tem permissões de execução:
   ```bash
   ls -la /home/sfortanks/sfortanks/scheduler_service.py
   ```

### Erros de permissão

Certifique-se de que o usuário `sfortanks` tem permissões adequadas:
```bash
sudo chown -R sfortanks:www-data /home/sfortanks/sfortanks
```

### Verificar se o serviço está rodando

```bash
ps aux | grep scheduler_service
```

## Notas

- O serviço reinicia automaticamente em caso de falha (Restart=always)
- Os logs são salvos tanto no journalctl quanto no arquivo `logs/scheduler.log`
- O serviço usa o timezone 'America/Sao_Paulo'
