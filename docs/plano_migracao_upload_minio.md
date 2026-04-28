# Plano de migracao Upload -> MinIO

## Objetivo

Migrar o dominio de `Upload` de armazenamento em banco (`Uploads.blob` base64) para objeto em MinIO, com risco controlado e sem parada longa.

## Premissas

- A tabela `Uploads` continua sendo a fonte de metadados.
- O binario passa a ser armazenado no MinIO.
- O campo `dados_adicionais` recebe metadados de storage durante a transicao.
- O campo `blob` pode ser mantido no inicio e limpo apenas na fase final.

## Fase 0 - Preparacao

1. Provisionar MinIO (bucket, credenciais e politica minima).
2. Definir variaveis de ambiente:
   - `MINIO_ENDPOINT`
   - `MINIO_ACCESS_KEY`
   - `MINIO_SECRET_KEY`
   - `MINIO_SECURE`
3. Atualizar dependencias do projeto:
   - `minio>=7.2.18` (ja incluido no `pyproject.toml`)
4. Validar acesso com teste simples de upload/download.

## Fase 1 - Backfill seguro (sem impacto funcional)

1. Executar script de migracao em modo simulacao:
   - `python scripts/migrar_uploads_para_minio.py --bucket uploads --dry-run`
2. Executar migracao real sem apagar `blob`:
   - `python scripts/migrar_uploads_para_minio.py --bucket uploads`
3. Validar indicadores:
   - contagem migrada
   - taxa de erro
   - consistencia de tamanho/hash
4. Reexecutar com checkpoint para cobrir novos registros.

## Fase 2 - Leitura dual (cutover gradual)

1. Ajustar dominio `Upload.get_blob()` para:
   - tentar MinIO quando `dados_adicionais.storage.provider == "minio"`
   - fallback para `blob` legado quando necessario
2. Ajustar endpoints de download para usar esse mesmo fluxo unificado.
3. Monitorar erros por rota e por tipo de upload.

## Fase 3 - Escrita no MinIO por padrao

1. Centralizar criacao de upload em um service unico.
2. Novo upload grava no MinIO e persiste metadados no `dados_adicionais`.
3. Opcional: dual-write temporario para rollback rapido.

## Fase 4 - Limpeza do legado

1. Rodar script com `--clear-blob` apos estabilidade:
   - `python scripts/migrar_uploads_para_minio.py --bucket uploads --clear-blob`
2. Executar auditoria final de registros sem `storage.provider=minio`.
3. Planejar migracao de schema para remover `blob` em etapa separada.

## Rollback

- Se houver incidente:
  1. manter leitura com fallback para `blob`
  2. pausar novos uploads no MinIO
  3. reprocessar apenas ids afetados via `--start-id`/checkpoint

## Script de migracao

Arquivo: `scripts/migrar_uploads_para_minio.py`

Capacidades:

- processamento em lote (`--batch-size`)
- checkpoint para retomada (`--checkpoint-file`)
- modo simulacao (`--dry-run`)
- limite de registros para janela controlada (`--max-registros`)
- opcao de limpeza do legado (`--clear-blob`)

Exemplos:

```bash
python scripts/migrar_uploads_para_minio.py --bucket uploads --dry-run
python scripts/migrar_uploads_para_minio.py --bucket uploads --batch-size 500
python scripts/migrar_uploads_para_minio.py --bucket uploads --clear-blob
```
