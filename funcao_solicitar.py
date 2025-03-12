@mod_importacao_nf.route('/solicitar/<int:nf_id>', methods=['GET', 'POST'])
def solicitar(nf_id):
    if 'usuario_id' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('login'))

    # Criar uma instância de formulário vazio para obter o token CSRF
    form = FlaskForm()

    connection = get_db_connection()
    nota = None
    itens = []
    centros_custo = []

    if connection:
        try:
            cursor = connection.cursor(dictionary=True)

            # Buscar dados da nota fiscal
            cursor.execute("SELECT * FROM nf_notas WHERE id = %s", (nf_id,))
            nota = cursor.fetchone()

            if nota:
                # Buscar itens da nota fiscal
                cursor.execute(
                    "SELECT * FROM nf_itens WHERE nf_id = %s", (nf_id,))
                itens = cursor.fetchall()

                # Se for uma requisição POST, criar a solicitação
                if request.method == 'POST' and nota and itens:
                    justificativa = request.form.get('justificativa', '')
                    centro_custo_id = request.form.get('centro_custo_id', '')
                    itens_selecionados = request.form.getlist('item_id')

                    if justificativa and centro_custo_id and itens_selecionados:
                        # Adicione aqui o código para processar a solicitação
                        pass

            cursor.close()
        except Exception as e:
            logger.error(f"Erro ao processar solicitação: {e}")
            flash(f'Erro ao processar solicitação: {str(e)}', 'danger')
            if connection.is_connected():
                connection.rollback()
        finally:
            if connection.is_connected():
                connection.close()

    if not nota:
        flash('Nota fiscal não encontrada', 'warning')
        return redirect(url_for('importacao_nf.buscar'))

    return render_template('importacao_nf/solicitar.html',
                           nota=nota,
                           itens=itens,
                           form=form,
                           centros_custo=centros_custo)
