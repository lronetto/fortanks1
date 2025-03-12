"""
Script de correção para problemas de autenticação no módulo integracao_erp
"""

# As correções que precisam ser feitas são:

# 1. Substituir todas as verificações de 'logado' not in session por 'usuario_id' not in session
#    Em todas as rotas do módulo integracao_erp/app.py, como:
#    - index
#    - importar_manual
#    - importar_automatico
#    - listar_transacoes
#    - visualizar_transacao
#    - relatorios
#    - importar_programado
#    - executar_importacao_programada
#    - API routes (dados_centro_custo, dados_categoria, api_importacoes)

# 2. Substituir todas as referências a session['id_usuario'] por session['usuario_id']
#    Isso inclui chamadas como:
#    - registrar_importacao_iniciada(session['id_usuario'])
#    - usuario_id = session.get('id_usuario')

# 3. Garantir que os redirecionamentos estejam apontando para 'login' em vez de 'index'
#    Por exemplo, mudar:
#    return redirect(url_for('index'))
#    para:
#    return redirect(url_for('login'))

# 4. Separar a verificação de cargo administrativo da verificação de login
#    Por exemplo, mudar:
#    if 'logado' not in session or session['cargo'] != 'admin':
#    para:
#    if 'usuario_id' not in session:
#        flash('Faça login para acessar o sistema', 'warning')
#        return redirect(url_for('login'))
#
#    if session.get('cargo') != 'admin':
#        flash('Acesso restrito para administradores', 'danger')
#        return redirect(url_for('dashboard'))

# 5. Melhorar as mensagens de erro nas APIs REST
#    Por exemplo, mudar:
#    return jsonify({'error': 'Não autorizado', 'data': []}), 401
#    para:
#    return jsonify({'error': 'Não autorizado. Faça login para continuar.', 'data': []}), 401

print("Este script contém instruções para corrigir problemas de autenticação no módulo integracao_erp.")
print("Por favor, aplique essas correções manualmente ao arquivo modulos/integracao_erp/app.py.")
