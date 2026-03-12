# Configuração do servidor para uploads grandes (413 Request Entity Too Large)

Ao importar vários PDFs em **Notas Fiscais → Protocolos**, o tamanho da requisição pode passar do limite padrão do proxy no Linux, gerando **413 Request Entity Too Large**.

## O que já está configurado na aplicação

- Em `config/config.py`, `MAX_CONTENT_LENGTH` está definido como **150 MB** para a aplicação Flask aceitar o corpo da requisição.

## O que configurar no servidor Linux

O 413 costuma vir do **proxy reverso** (Nginx ou Apache), que tem limite próprio e deve ser aumentado.

### Nginx

No bloco `http` ou no `server` do seu site, defina:

```nginx
client_max_body_size 150M;
```

Exemplo em um `server`:

```nginx
server {
    listen 80;
    server_name seu-dominio.com;
    client_max_body_size 150M;   # permite uploads até 150 MB

    location / {
        proxy_pass http://127.0.0.1:5000;  # ou a porta do gunicorn/uwsgi
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Depois, recarregue o Nginx:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

### Apache (mod_proxy)

No VirtualHost ou em `.htaccess`:

```apache
LimitRequestBody 157286400
```

(157286400 bytes ≈ 150 MB.)

Ou no VirtualHost:

```apache
<VirtualHost *:80>
    ...
    LimitRequestBody 157286400
    ...
</VirtualHost>
```

Reinicie o Apache após alterar:

```bash
sudo systemctl restart apache2
```

### Gunicorn / uWSGI

Em geral não impõem limite de tamanho do body; o 413 costuma vir do Nginx/Apache à frente. Se o request chegar direto ao Gunicorn (sem proxy), o limite é o `MAX_CONTENT_LENGTH` do Flask (150 MB).

---

Resumo: na aplicação o limite já é 150 MB; no Linux é necessário aumentar o limite de tamanho do body no **Nginx** (`client_max_body_size 150M`) ou no **Apache** (`LimitRequestBody`) para o mesmo valor.
