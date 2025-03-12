# utils/file_handlers.py
import os
import uuid
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import current_app


def save_uploaded_file(file, directory, allowed_extensions=None, filename=None):
    """
    Salva um arquivo enviado pelo usuário de forma segura, verificando sua extensão.

    Args:
        file: Objeto arquivo do request.files.
        directory: Diretório onde o arquivo será salvo (a partir da raiz da aplicação).
        allowed_extensions: Lista de extensões permitidas (e.g., ['.pdf', '.jpg']).
        filename: Nome personalizado para o arquivo, se None, usa um UUID.

    Returns:
        tuple: (sucesso, mensagem, caminho_relativo_do_arquivo)
    """
    if not file or not file.filename:
        return False, "Nenhum arquivo enviado", None

    # Verificar extensão
    original_filename = file.filename
    extension = os.path.splitext(original_filename)[1].lower()

    if allowed_extensions and extension not in allowed_extensions:
        return False, f"Formato de arquivo não permitido. Use: {', '.join(allowed_extensions)}", None

    # Gerar nome seguro para o arquivo
    if not filename:
        filename = f"{uuid.uuid4()}{extension}"
    else:
        # Tornar o nome seguro e manter a extensão original
        filename = secure_filename(filename) + extension

    # Criar diretório se não existir
    upload_dir = os.path.join(current_app.root_path, directory)
    os.makedirs(upload_dir, exist_ok=True)

    # Caminho completo do arquivo
    file_path = os.path.join(upload_dir, filename)

    try:
        # Salvar o arquivo
        file.save(file_path)

        # Retornar o caminho relativo para uso no banco/HTML
        relative_path = os.path.join(directory, filename).replace('\\', '/')
        return True, "Arquivo salvo com sucesso", relative_path

    except Exception as e:
        return False, f"Erro ao salvar arquivo: {str(e)}", None


def get_file_info(filepath):
    """
    Obtém informações sobre um arquivo.

    Args:
        filepath: Caminho do arquivo (relativo à raiz da aplicação).

    Returns:
        dict: Dicionário com informações do arquivo, ou None se não existir.
    """
    try:
        full_path = os.path.join(current_app.root_path, filepath)

        if not os.path.exists(full_path):
            return None

        stats = os.stat(full_path)
        size_bytes = stats.st_size
        modified_time = datetime.fromtimestamp(stats.st_mtime)

        # Converter tamanho para formato legível
        if size_bytes < 1024:
            size_str = f"{size_bytes} bytes"
        elif size_bytes < 1024 * 1024:
            size_str = f"{size_bytes/1024:.1f} KB"
        else:
            size_str = f"{size_bytes/(1024*1024):.1f} MB"

        return {
            'name': os.path.basename(filepath),
            'size': size_bytes,
            'size_formatted': size_str,
            'modified': modified_time,
            'extension': os.path.splitext(filepath)[1].lower(),
            'path': filepath
        }

    except Exception:
        return None


def delete_file(filepath):
    """
    Exclui um arquivo do sistema.

    Args:
        filepath: Caminho do arquivo (relativo à raiz da aplicação).

    Returns:
        bool: True se o arquivo foi excluído com sucesso, False caso contrário.
    """
    try:
        full_path = os.path.join(current_app.root_path, filepath)

        if not os.path.exists(full_path):
            return False

        os.remove(full_path)
        return True

    except Exception:
        return False
