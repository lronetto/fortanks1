import os
import io
import shutil
import tempfile
import zipfile
import openpyxl
from openpyxl import load_workbook
import json
import subprocess
import platform
import time
import logging
import re
from datetime import datetime

def _converter_excel_para_pdf_libreoffice(excel_path, pdf_path=None):
    """
    Converte arquivo Excel/ODS para PDF usando LibreOffice em modo headless.
    Funciona tanto no Windows quanto no Linux.
    Aceita tanto arquivos XLSX quanto ODS - gera PDF diretamente do ODS quando disponível.
    
    Args:
        excel_path: Caminho do arquivo Excel (XLSX) ou ODS
        pdf_path: Caminho de saída do PDF (opcional, se None, usa mesmo nome do arquivo)
    
    Returns:
        Caminho do arquivo PDF gerado ou None em caso de erro
    """
    try:
        if not excel_path or not os.path.exists(excel_path):
            print(f'[_converter_excel_para_pdf_libreoffice] Arquivo não encontrado: {excel_path}')
            return None
        
        # Determinar caminho do PDF de saída
        if pdf_path is None:
            pdf_path = excel_path.replace('.xlsx', '.pdf').replace('.xls', '.pdf').replace('.ods', '.pdf')
        
        # Obter diretório de saída
        output_dir = os.path.dirname(pdf_path)
        if not output_dir:
            output_dir = os.path.dirname(excel_path)
        
        # Criar diretório se não existir
        os.makedirs(output_dir, exist_ok=True)
        
        # Detectar sistema operacional e comando do LibreOffice
        sistema = platform.system().lower()
        
        if sistema == 'windows':
            # Windows - tentar diferentes caminhos comuns do LibreOffice
            possiveis_caminhos = [
                r'C:\Program Files\LibreOffice\program\soffice.exe',
                r'C:\Program Files (x86)\LibreOffice\program\soffice.exe',
                r'C:\Program Files\LibreOffice 7\program\soffice.exe',
                r'C:\Program Files (x86)\LibreOffice 7\program\soffice.exe',
            ]
            
            # Verificar se existe variável de ambiente
            libreoffice_env = os.getenv('LIBREOFFICE_PATH')
            if libreoffice_env:
                possiveis_caminhos.insert(0, libreoffice_env)
            
            soffice_cmd = None
            for caminho in possiveis_caminhos:
                if os.path.exists(caminho):
                    soffice_cmd = caminho
                    break
            
            if not soffice_cmd:
                print('[_converter_excel_para_pdf_libreoffice] LibreOffice não encontrado no Windows')
                print('[_converter_excel_para_pdf_libreoffice] Configure a variável LIBREOFFICE_PATH ou instale o LibreOffice')
                return None
        else:
            # Linux/Unix - usar comando do sistema
            soffice_cmd = None
            
            # Verificar variável de ambiente primeiro
            libreoffice_env = os.getenv('LIBREOFFICE_PATH')
            if libreoffice_env and os.path.exists(libreoffice_env):
                soffice_cmd = libreoffice_env
                logging.info(f'[_converter_excel_para_pdf_libreoffice] Usando LIBREOFFICE_PATH: {soffice_cmd}')
            else:
                # Tentar encontrar o executável real do LibreOffice (não o wrapper script)
                # O wrapper /usr/bin/soffice pode ter problemas com PATH
                import glob
                import re
                
                # Primeiro, tentar encontrar o executável real diretamente
                possiveis_caminhos = []
                
                # Buscar em /usr/lib e /usr/lib64
                for lib_dir in ['/usr/lib', '/usr/lib64', '/usr/local/lib']:
                    # Tentar diferentes versões do LibreOffice
                    for version in ['', '7', '8', '6', '5']:
                        path = f'{lib_dir}/libreoffice{version}/program/soffice'
                        if os.path.exists(path):
                            possiveis_caminhos.append(path)
                            logging.info(f'[_converter_excel_para_pdf_libreoffice] Caminho encontrado: {path}')
                
                # Buscar em /opt
                opt_paths = glob.glob('/opt/libreoffice*/program/soffice')
                possiveis_caminhos.extend(opt_paths)
                for path in opt_paths:
                    logging.info(f'[_converter_excel_para_pdf_libreoffice] Caminho encontrado em /opt: {path}')
                
                logging.info(f'[_converter_excel_para_pdf_libreoffice] Total de caminhos a verificar: {len(possiveis_caminhos)}')
                
                # Verificar cada caminho
                for caminho in possiveis_caminhos:
                    logging.info(f'[_converter_excel_para_pdf_libreoffice] Verificando caminho: {caminho}')
                    if os.path.exists(caminho):
                        logging.info(f'[_converter_excel_para_pdf_libreoffice] Caminho existe: {caminho}')
                        if os.access(caminho, os.X_OK):
                            logging.info(f'[_converter_excel_para_pdf_libreoffice] Caminho tem permissão de execução: {caminho}')
                            # Verificar se é um executável real (ELF binary) ou um link simbólico válido
                            try:
                                # Verificar se é um link simbólico
                                if os.path.islink(caminho):
                                    real_path = os.path.realpath(caminho)
                                    logging.info(f'[_converter_excel_para_pdf_libreoffice] É um link simbólico apontando para: {real_path}')
                                    if os.path.exists(real_path) and os.access(real_path, os.X_OK):
                                        caminho = real_path
                                
                                with open(caminho, 'rb') as f:
                                    header = f.read(4)
                                    if header.startswith(b'\x7fELF'):  # ELF binary
                                        soffice_cmd = caminho
                                        logging.info(f'[_converter_excel_para_pdf_libreoffice] Encontrado executável real (ELF): {soffice_cmd}')
                                        break
                                    else:
                                        # Pode ser um script ou link simbólico, mas vamos usar se existir e tiver permissão
                                        logging.info(f'[_converter_excel_para_pdf_libreoffice] Arquivo não é ELF, mas existe e tem permissão: {caminho}')
                                        # Usar este arquivo se ainda não encontrou nenhum
                                        if not soffice_cmd:
                                            soffice_cmd = caminho
                                            logging.info(f'[_converter_excel_para_pdf_libreoffice] Usando arquivo encontrado: {soffice_cmd}')
                            except Exception as e:
                                logging.warning(f'[_converter_excel_para_pdf_libreoffice] Erro ao verificar {caminho}: {str(e)}')
                                # Se não encontrou nenhum ainda e o arquivo existe, usar como último recurso
                                if not soffice_cmd and os.path.exists(caminho):
                                    soffice_cmd = caminho
                                    logging.info(f'[_converter_excel_para_pdf_libreoffice] Usando como último recurso: {soffice_cmd}')
                        else:
                            logging.warning(f'[_converter_excel_para_pdf_libreoffice] Caminho existe mas não tem permissão de execução: {caminho}')
                    else:
                        logging.debug(f'[_converter_excel_para_pdf_libreoffice] Caminho não existe: {caminho}')
                
                # Se não encontrou o executável real, tentar extrair do wrapper
                if not soffice_cmd:
                    # Tentar encontrar usando shutil.which (pode retornar o wrapper)
                    wrapper_path = shutil.which('soffice')
                    if wrapper_path:
                        logging.info(f'[_converter_excel_para_pdf_libreoffice] Encontrado wrapper no PATH: {wrapper_path}')
                        # Tentar encontrar o executável real através do wrapper
                        try:
                            with open(wrapper_path, 'r') as f:
                                script_content = f.read()
                                # Procurar por padrões comuns no script
                                # Padrão 1: /usr/lib/libreoffice/program/soffice
                                # Padrão 2: /usr/lib64/libreoffice/program/soffice
                                # Padrão 3: variáveis como INSTALL_DIR
                                patterns = [
                                    r'(/usr/lib[^/\s]*/libreoffice[^/\s]*/program/soffice)',
                                    r'(/usr/lib64[^/\s]*/libreoffice[^/\s]*/program/soffice)',
                                    r'INSTALL_DIR[=:]\s*["\']?([^"\'\s]+)',
                                    r'exec\s+["\']?([^"\'\s]+/soffice)',
                                ]
                                
                                for pattern in patterns:
                                    matches = re.findall(pattern, script_content)
                                    for match in matches:
                                        if isinstance(match, tuple):
                                            match = match[0] if match else None
                                        if match and os.path.exists(match) and os.access(match, os.X_OK):
                                            # Verificar se é ELF
                                            try:
                                                with open(match, 'rb') as f:
                                                    header = f.read(4)
                                                    if header.startswith(b'\x7fELF'):
                                                        soffice_cmd = match
                                                        logging.info(f'[_converter_excel_para_pdf_libreoffice] Executável real encontrado via wrapper: {soffice_cmd}')
                                                        break
                                            except:
                                                continue
                                    if soffice_cmd:
                                        break
                        except Exception as e:
                            logging.warning(f'[_converter_excel_para_pdf_libreoffice] Não foi possível encontrar executável real via wrapper: {str(e)}')
                
                # Se ainda não encontrou, NÃO usar o wrapper - retornar erro
                if not soffice_cmd:
                    logging.error('[_converter_excel_para_pdf_libreoffice] Executável real do LibreOffice não encontrado')
                    logging.error('[_converter_excel_para_pdf_libreoffice] Tentou buscar em: /usr/lib/libreoffice/program/soffice, /usr/lib64/libreoffice/program/soffice, /opt/libreoffice*/program/soffice')
                    logging.error('[_converter_excel_para_pdf_libreoffice] Configure a variável LIBREOFFICE_PATH com o caminho completo do executável')
                    logging.error('[_converter_excel_para_pdf_libreoffice] Exemplo: export LIBREOFFICE_PATH=/usr/lib/libreoffice/program/soffice')
                    return None
        
        # Comando para converter Excel/ODS para PDF
        # --headless: modo sem interface gráfica
        # Aceita tanto XLSX quanto ODS - gera PDF diretamente do formato original
        # --convert-to pdf: converter para PDF
        # --outdir: diretório de saída
        cmd = [
            soffice_cmd,
            '--headless',
            '--convert-to', 'pdf',
            '--outdir', output_dir,
            excel_path
        ]
        
        # Verificar se o executável existe e tem permissões
        if not os.path.exists(soffice_cmd):
            logging.error(f'[_converter_excel_para_pdf_libreoffice] Executável não existe: {soffice_cmd}')
            return None
        
        if not os.access(soffice_cmd, os.X_OK):
            logging.error(f'[_converter_excel_para_pdf_libreoffice] Executável não tem permissão de execução: {soffice_cmd}')
            return None
        
        logging.info(f'[_converter_excel_para_pdf_libreoffice] Executando: {" ".join(cmd)}')
        logging.info(f'[_converter_excel_para_pdf_libreoffice] Arquivo de entrada: {excel_path}')
        logging.info(f'[_converter_excel_para_pdf_libreoffice] Diretório de saída: {output_dir}')
        logging.info(f'[_converter_excel_para_pdf_libreoffice] Executável: {soffice_cmd}')
        
        try:
            # Configurar ambiente completo para o LibreOffice funcionar
            env = os.environ.copy()
            
            # Garantir que comandos básicos estejam no PATH
            basic_paths = ['/usr/bin', '/bin', '/usr/local/bin', '/sbin', '/usr/sbin']
            current_path = env.get('PATH', '')
            for path in basic_paths:
                if path not in current_path:
                    env['PATH'] = f"{path}:{env.get('PATH', '')}"
            
            # Configurar LD_LIBRARY_PATH para encontrar bibliotecas do LibreOffice
            libreoffice_lib_dir = os.path.dirname(os.path.dirname(soffice_cmd))
            lib_paths = [
                f'{libreoffice_lib_dir}/program',
                f'{libreoffice_lib_dir}/ure/lib',
                '/usr/lib',
                '/usr/lib64',
                '/lib',
                '/lib64',
            ]
            
            current_ld_path = env.get('LD_LIBRARY_PATH', '')
            for lib_path in lib_paths:
                if os.path.exists(lib_path) and lib_path not in current_ld_path:
                    env['LD_LIBRARY_PATH'] = f"{lib_path}:{env.get('LD_LIBRARY_PATH', '')}"
            
            # Configurar variáveis específicas do LibreOffice
            env['SAL_USE_VCLPLUGIN'] = 'headless'
            env['SAL_DISABLE_OPENCL'] = '1'
            
            # Remover variáveis que podem causar problemas
            env.pop('DISPLAY', None)  # Garantirx modo headless
            
            logging.info(f'[_converter_excel_para_pdf_libreoffice] PATH: {env.get("PATH", "")[:200]}...')
            logging.info(f'[_converter_excel_para_pdf_libreoffice] LD_LIBRARY_PATH: {env.get("LD_LIBRARY_PATH", "")[:200]}...')
            
            # Executar conversão com ambiente configurado
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,  # Timeout de 2 minutos
                check=False,
                env=env,
                cwd=os.path.dirname(soffice_cmd)  # Executar no diretório do LibreOffice
            )
            
            if result.returncode != 0:
                logging.error(f'[_converter_excel_para_pdf_libreoffice] Erro ao converter (código {result.returncode})')
                logging.error(f'[_converter_excel_para_pdf_libreoffice] stdout: {result.stdout}')
                logging.error(f'[_converter_excel_para_pdf_libreoffice] stderr: {result.stderr}')
                return None
            else:
                logging.info(f'[_converter_excel_para_pdf_libreoffice] Comando executado com sucesso')
                if result.stdout:
                    print(f'[_converter_excel_para_pdf_libreoffice] stdout: {result.stdout}')
        except subprocess.TimeoutExpired:
            print('[_converter_excel_para_pdf_libreoffice] Timeout ao converter Excel para PDF')
            return None
        except Exception as e:
            print(f'[_converter_excel_para_pdf_libreoffice] Exceção ao executar comando: {str(e)}')
            import traceback
            print(traceback.format_exc())
            return None
        
        # O LibreOffice gera o PDF com o mesmo nome do arquivo Excel
        excel_basename = os.path.basename(excel_path)
        pdf_basename = excel_basename.replace('.xlsx', '.pdf').replace('.xls', '.pdf').replace('.ods', '.pdf')
        generated_pdf_path = os.path.join(output_dir, pdf_basename)
        
        print(f'[_converter_excel_para_pdf_libreoffice] Caminho esperado do PDF: {generated_pdf_path}')
        
        # Aguardar um pouco para garantir que o arquivo foi criado
        max_tentativas = 10
        tentativa = 0
        while tentativa < max_tentativas:
            if os.path.exists(generated_pdf_path):
                # Verificar se o arquivo não está sendo escrito (tamanho estável)
                tamanho_anterior = os.path.getsize(generated_pdf_path)
                time.sleep(0.5)
                tamanho_atual = os.path.getsize(generated_pdf_path)
                if tamanho_anterior == tamanho_atual and tamanho_atual > 0:
                    print(f'[_converter_excel_para_pdf_libreoffice] PDF gerado com sucesso: {generated_pdf_path} (tamanho: {tamanho_atual} bytes)')
                    return generated_pdf_path
                elif tamanho_anterior == tamanho_atual and tamanho_atual == 0:
                    print(f'[_converter_excel_para_pdf_libreoffice] PDF gerado mas está vazio: {generated_pdf_path}')
                    # Continuar tentando por mais um pouco
            else:
                print(f'[_converter_excel_para_pdf_libreoffice] Tentativa {tentativa + 1}/{max_tentativas}: PDF ainda não existe')
            tentativa += 1
            time.sleep(0.5)
        
        # Verificar se o arquivo existe mas está vazio
        if os.path.exists(generated_pdf_path):
            tamanho = os.path.getsize(generated_pdf_path)
            if tamanho == 0:
                print(f'[_converter_excel_para_pdf_libreoffice] PDF foi criado mas está vazio: {generated_pdf_path}')
                return None
        
        # Listar arquivos no diretório de saída para debug
        try:
            arquivos_no_dir = os.listdir(output_dir)
            print(f'[_converter_excel_para_pdf_libreoffice] Arquivos no diretório de saída: {arquivos_no_dir}')
            # Verificar se há algum PDF no diretório
            pdfs_no_dir = [f for f in arquivos_no_dir if f.endswith('.pdf')]
            if pdfs_no_dir:
                print(f'[_converter_excel_para_pdf_libreoffice] PDFs encontrados no diretório: {pdfs_no_dir}')
        except Exception as e:
            print(f'[_converter_excel_para_pdf_libreoffice] Erro ao listar diretório: {str(e)}')
        
        print(f'[_converter_excel_para_pdf_libreoffice] PDF não foi gerado após {max_tentativas} tentativas')
        print(f'[_converter_excel_para_pdf_libreoffice] Caminho esperado: {generated_pdf_path}')
        return None
        
    except subprocess.TimeoutExpired:
        print('[_converter_excel_para_pdf_libreoffice] Timeout ao converter Excel para PDF')
        return None
    except Exception as e:
        print(f'[_converter_excel_para_pdf_libreoffice] Erro ao converter Excel para PDF: {str(e)}')
        import traceback
        print(traceback.format_exc())
        return None

def _converter_ods_para_xlsx_libreoffice(ods_path, xlsx_path=None):
    """
    Converte arquivo ODS para XLSX usando LibreOffice em modo headless.
    Funciona tanto no Windows quanto no Linux.
    
    Args:
        ods_path: Caminho do arquivo ODS
        xlsx_path: Caminho de saída do XLSX (opcional, se None, usa mesmo nome do ODS)
    
    Returns:
        Caminho do arquivo XLSX gerado ou None em caso de erro
    """
    try:
        if not ods_path or not os.path.exists(ods_path):
            logging.info(f'[_converter_ods_para_xlsx_libreoffice] Arquivo ODS não encontrado: {ods_path}')
            return None
        
        # Determinar caminho do XLSX de saída
        if xlsx_path is None:
            xlsx_path = ods_path.replace('.ods', '.xlsx')
        
        # Obter diretório de saída
        output_dir = os.path.dirname(xlsx_path)
        if not output_dir:
            output_dir = os.path.dirname(ods_path)
        
        # Criar diretório se não existir
        os.makedirs(output_dir, exist_ok=True)
        
        # Detectar sistema operacional e comando do LibreOffice
        sistema = platform.system().lower()
        
        if sistema == 'windows':
            possiveis_caminhos = [
                r'C:\Program Files\LibreOffice\program\soffice.exe',
                r'C:\Program Files (x86)\LibreOffice\program\soffice.exe',
                r'C:\Program Files\LibreOffice 7\program\soffice.exe',
                r'C:\Program Files (x86)\LibreOffice 7\program\soffice.exe',
            ]
            
            libreoffice_env = os.getenv('LIBREOFFICE_PATH')
            if libreoffice_env:
                possiveis_caminhos.insert(0, libreoffice_env)
            
            soffice_cmd = None
            for caminho in possiveis_caminhos:
                if os.path.exists(caminho):
                    soffice_cmd = caminho
                    break
            
            if not soffice_cmd:
                print('[_converter_ods_para_xlsx_libreoffice] LibreOffice não encontrado no Windows')
                return None
        else:
            logging.info(f'[_converter_ods_para_xlsx_libreoffice] Sistema operacional: {sistema}')
            # Linux/Unix - usar comando do sistema
            soffice_cmd = None
            
            # Verificar variável de ambiente primeiro
            libreoffice_env = os.getenv('LIBREOFFICE_PATH')
            if libreoffice_env and os.path.exists(libreoffice_env):
                soffice_cmd = libreoffice_env
                logging.info(f'[_converter_ods_para_xlsx_libreoffice] Usando LIBREOFFICE_PATH: {soffice_cmd}')
            else:
                # Tentar encontrar o executável real do LibreOffice (não o wrapper script)
                import glob
                import re
                
                # Primeiro, tentar encontrar o executável real diretamente
                possiveis_caminhos = []
                
                # Buscar em /usr/lib e /usr/lib64
                for lib_dir in ['/usr/lib', '/usr/lib64', '/usr/local/lib']:
                    # Tentar diferentes versões do LibreOffice
                    for version in ['', '7', '8', '6', '5']:
                        path = f'{lib_dir}/libreoffice{version}/program/soffice'
                        if os.path.exists(path):
                            possiveis_caminhos.append(path)
                
                # Buscar em /opt
                opt_paths = glob.glob('/opt/libreoffice*/program/soffice')
                possiveis_caminhos.extend(opt_paths)
                
                # Verificar cada caminho
                for caminho in possiveis_caminhos:
                    if os.path.exists(caminho) and os.access(caminho, os.X_OK):
                        # Verificar se é um executável real (ELF binary)
                        try:
                            with open(caminho, 'rb') as f:
                                header = f.read(4)
                                if header.startswith(b'\x7fELF'):  # ELF binary
                                    soffice_cmd = caminho
                                    break
                        except Exception as e:
                            logging.info(f'[_converter_ods_para_xlsx_libreoffice] Erro ao verificar {caminho}: {str(e)}')
                            continue
                
                # Se não encontrou o executável real, tentar extrair do wrapper
                if not soffice_cmd:
                    # Tentar encontrar usando shutil.which (pode retornar o wrapper)
                    wrapper_path = shutil.which('soffice')
                    if wrapper_path:
                        # Tentar encontrar o executável real através do wrapper
                        try:
                            with open(wrapper_path, 'r') as f:
                                script_content = f.read()
                                # Procurar por padrões comuns no script
                                patterns = [
                                    r'(/usr/lib[^/\s]*/libreoffice[^/\s]*/program/soffice)',
                                    r'(/usr/lib64[^/\s]*/libreoffice[^/\s]*/program/soffice)',
                                    r'INSTALL_DIR[=:]\s*["\']?([^"\'\s]+)',
                                    r'exec\s+["\']?([^"\'\s]+/soffice)',
                                ]
                                
                                for pattern in patterns:
                                    matches = re.findall(pattern, script_content)
                                    for match in matches:
                                        if isinstance(match, tuple):
                                            match = match[0] if match else None
                                        if match and os.path.exists(match) and os.access(match, os.X_OK):
                                            # Verificar se é ELF
                                            try:
                                                with open(match, 'rb') as f:
                                                    header = f.read(4)
                                                    if header.startswith(b'\x7fELF'):
                                                        soffice_cmd = match
                                                        break
                                            except:
                                                continue
                                    if soffice_cmd:
                                        break
                        except Exception as e:
                            logging.error(f'[_converter_ods_para_xlsx_libreoffice] Não foi possível encontrar executável real via wrapper: {str(e)}')
                
                # Se ainda não encontrou, NÃO usar o wrapper - retornar erro
                if not soffice_cmd:
                    print('[_converter_ods_para_xlsx_libreoffice] Executável real do LibreOffice não encontrado')
                    print('[_converter_ods_para_xlsx_libreoffice] Tentou buscar em: /usr/lib/libreoffice/program/soffice, /usr/lib64/libreoffice/program/soffice, /opt/libreoffice*/program/soffice')
                    print('[_converter_ods_para_xlsx_libreoffice] Configure a variável LIBREOFFICE_PATH com o caminho completo do executável')
                    print('[_converter_ods_para_xlsx_libreoffice] Exemplo: export LIBREOFFICE_PATH=/usr/lib/libreoffice/program/soffice')
                    return None
        
        logging.info(f'[_converter_ods_para_xlsx_libreoffice] Executável encontrado: {soffice_cmd}')
        # Observação: em algumas instalações Linux, `--convert-to xlsx` sem filtro pode falhar silenciosamente
        # (ou gerar outro formato). O filtro abaixo é o mais compatível para XLSX.
        convert_to_arg = 'xlsx'

        cmd = [
            soffice_cmd,
            '--headless',
            '--nologo',
            '--nolockcheck',
            '--nodefault',
            '--norestore',
            '--convert-to', convert_to_arg,
            '--outdir', output_dir,
            ods_path
        ]
        
        # Verificar se o executável existe e tem permissões
        if not os.path.exists(soffice_cmd):
            logging.info(f'[_converter_ods_para_xlsx_libreoffice] Executável não existe: {soffice_cmd}')
            return None
        
        if not os.access(soffice_cmd, os.X_OK):
            logging.info(f'[_converter_ods_para_xlsx_libreoffice] Executável não tem permissão de execução: {soffice_cmd}')
            return None
        
            
        try:
            logging.info(f'[_converter_ods_para_xlsx_libreoffice] Executando comando: {" ".join(cmd)}')
            # Configurar ambiente completo para o LibreOffice funcionar
            env = os.environ.copy()
            
            # Garantir que comandos básicos estejam no PATH
            basic_paths = ['/usr/bin', '/bin', '/usr/local/bin', '/sbin', '/usr/sbin']
            current_path = env.get('PATH', '')
            for path in basic_paths:
                if path not in current_path:
                    env['PATH'] = f"{path}:{env.get('PATH', '')}"
            
            # Configurar LD_LIBRARY_PATH para encontrar bibliotecas do LibreOffice
            libreoffice_lib_dir = os.path.dirname(os.path.dirname(soffice_cmd))
            lib_paths = [
                f'{libreoffice_lib_dir}/program',
                f'{libreoffice_lib_dir}/ure/lib',
                '/usr/lib',
                '/usr/lib64',
                '/lib',
                '/lib64',
            ]
            
            current_ld_path = env.get('LD_LIBRARY_PATH', '')
            for lib_path in lib_paths:
                if os.path.exists(lib_path) and lib_path not in current_ld_path:
                    env['LD_LIBRARY_PATH'] = f"{lib_path}:{env.get('LD_LIBRARY_PATH', '')}"
            
            # Configurar variáveis específicas do LibreOffice
            env['SAL_USE_VCLPLUGIN'] = 'headless'
            env['SAL_DISABLE_OPENCL'] = '1'
            
            # Remover variáveis que podem causar problemas
            env.pop('DISPLAY', None)  # Garantir modo headless
            
             
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
                env=env,
                cwd=os.path.dirname(soffice_cmd)  # Executar no diretório do LibreOffice
            )
            
            if result.returncode != 0:
                logging.info(f'[_converter_ods_para_xlsx_libreoffice] Erro ao converter (código {result.returncode})')
                logging.info(f'[_converter_ods_para_xlsx_libreoffice] stdout: {result.stdout}')
                logging.info(f'[_converter_ods_para_xlsx_libreoffice] stderr: {result.stderr}')
                return None
            else:
                # LibreOffice costuma escrever mensagens úteis no stdout mesmo quando dá certo
                if result.stdout:
                    print(f'[_converter_ods_para_xlsx_libreoffice] stdout: {result.stdout}')
                if result.stderr:
                    print(f'[_converter_ods_para_xlsx_libreoffice] stderr: {result.stderr}')
        except subprocess.TimeoutExpired:
            logging.error(f'[_converter_ods_para_xlsx_libreoffice] Timeout ao converter ODS para XLSX')
            return None
        except Exception as e:
            logging.error(f'[_converter_ods_para_xlsx_libreoffice] Exceção ao executar comando: {str(e)}')
            import traceback
            print(traceback.format_exc())
            return None
        
        ods_basename = os.path.basename(ods_path)
        xlsx_basename = ods_basename.replace('.ods', '.xlsx')
        generated_xlsx_path = os.path.join(output_dir, xlsx_basename)
        
        max_tentativas = 10
        tentativa = 0
        while tentativa < max_tentativas:
            # Caso 1: caminho "esperado" existe
            if os.path.exists(generated_xlsx_path):
                tamanho_anterior = os.path.getsize(generated_xlsx_path)
                time.sleep(0.5)
                tamanho_atual = os.path.getsize(generated_xlsx_path)
                if tamanho_anterior == tamanho_atual and tamanho_atual > 0:
                    logging.info(f'[_converter_ods_para_xlsx_libreoffice] XLSX gerado com sucesso: {generated_xlsx_path}')
                    if generated_xlsx_path != xlsx_path:
                        shutil.move(generated_xlsx_path, xlsx_path)
                    return xlsx_path

            # Caso 2 (Linux): LO pode gerar com nome ligeiramente diferente; procurar qualquer .xlsx no outdir
            try:
                candidatos = [
                    os.path.join(output_dir, f)
                    for f in os.listdir(output_dir)
                    if f.lower().endswith('.xlsx')
                ]
                if candidatos:
                    # Pegar o mais recente
                    candidatos.sort(key=lambda p: os.path.getmtime(p), reverse=True)
                    candidato = candidatos[0]
                    tamanho = os.path.getsize(candidato)
                    if tamanho > 0:
                        if candidato != xlsx_path:
                            shutil.move(candidato, xlsx_path)
                        return xlsx_path
            except Exception as e:
                logging.error(f'[_converter_ods_para_xlsx_libreoffice] Erro ao procurar XLSX no diretório de saída: {str(e)}')

            tentativa += 1
            time.sleep(0.5)
        
        print(f'[_converter_ods_para_xlsx_libreoffice] XLSX não foi gerado após {max_tentativas} tentativas')
        try:
            arquivos_no_dir = os.listdir(output_dir)
            print(f'[_converter_ods_para_xlsx_libreoffice] Arquivos no diretório de saída: {arquivos_no_dir}')
        except Exception:
            pass
        return None
        
    except subprocess.TimeoutExpired:
        print('[_converter_ods_para_xlsx_libreoffice] Timeout ao converter ODS para XLSX')
        return None
    except Exception as e:
        print(f'[_converter_ods_para_xlsx_libreoffice] Erro ao converter ODS para XLSX: {str(e)}')
        import traceback
        print(traceback.format_exc())
        return None

# Funções auxiliares para gerenciar pasta temporária do projeto
def _obter_pasta_temp_projeto():
    """
    Obtém ou cria a pasta temporária exclusiva do projeto.
    Retorna o caminho da pasta temporária.
    """
    # Obter diretório base do projeto (onde está o arquivo atual)
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    temp_dir = os.path.join(base_dir, 'temp', 'databook_inspecao')
    
    # Criar pasta se não existir
    os.makedirs(temp_dir, exist_ok=True)
    
    return temp_dir

def _deve_manter_arquivos_temp():
    """
    Verifica se deve manter os arquivos temporários ou deletá-los.
    Por padrão, mantém os arquivos (True).
    """
    manter_temp = os.getenv('MANTER_ARQUIVOS_TEMP', 'true').lower()
    return manter_temp in ('true', '1', 'yes', 'sim')

def _criar_arquivo_temp_projeto(suffix='', prefix='temp_'):
    """
    Cria um arquivo temporário na pasta do projeto.
    
    Args:
        suffix: Sufixo do arquivo (ex: '.xlsx', '.pdf')
        prefix: Prefixo do arquivo (padrão: 'temp_')
    
    Returns:
        Caminho do arquivo temporário criado
    """
    temp_dir = _obter_pasta_temp_projeto()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    filename = f'{prefix}{timestamp}{suffix}'
    filepath = os.path.join(temp_dir, filename)
    
    # Criar arquivo vazio
    open(filepath, 'a').close()
    
    return filepath

def _criar_diretorio_temp_projeto(prefix='temp_dir_'):
    """
    Cria um diretório temporário na pasta do projeto.
    
    Args:
        prefix: Prefixo do diretório (padrão: 'temp_dir_')
    
    Returns:
        Caminho do diretório temporário criado
    """
    temp_dir = _obter_pasta_temp_projeto()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    dirname = f'{prefix}{timestamp}'
    dirpath = os.path.join(temp_dir, dirname)
    
    # Criar diretório
    os.makedirs(dirpath, exist_ok=True)
    
    return dirpath

def _limpar_arquivo_temp(filepath):
    """
    Remove um arquivo temporário se a configuração permitir.
    
    Args:
        filepath: Caminho do arquivo a ser removido
    """
    if not _deve_manter_arquivos_temp():
        try:
            if os.path.isfile(filepath):
                os.unlink(filepath)
            elif os.path.isdir(filepath):
                shutil.rmtree(filepath)
        except Exception as e:
            print(f'Erro ao limpar arquivo temporário {filepath}: {str(e)}')

def _limpar_diretorio_temp(dirpath):
    """
    Remove um diretório temporário se a configuração permitir.
    
    Args:
        dirpath: Caminho do diretório a ser removido
    """
    if not _deve_manter_arquivos_temp():
        try:
            if os.path.exists(dirpath) and os.path.isdir(dirpath):
                shutil.rmtree(dirpath)
        except Exception as e:
            print(f'Erro ao limpar diretório temporário {dirpath}: {str(e)}')
