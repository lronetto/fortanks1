@mod_importacao_nf.route('/visualizar/<int:nf_id>')
def visualizar(nf_id):
    if 'usuario_id' not in session:
        flash('Faça login para acessar o sistema', 'warning')
        return redirect(url_for('login'))

    connection = get_db_connection()
    nota = None
    itens = []

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

            cursor.close()
        except Error as e:
            logger.error(f"Erro ao buscar detalhes da nota fiscal: {e}")
            flash(
                f'Erro ao buscar detalhes da nota fiscal: {str(e)}', 'danger')
        finally:
            connection.close()

    if not nota:
        flash('Nota fiscal não encontrada', 'warning')
        return redirect(url_for('importacao_nf.buscar'))

    return render_template('importacao_nf/visualizar.html', nota=nota, itens=itens)
