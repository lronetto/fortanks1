$(function() {
  // Submissão AJAX do acabamento
  $('#formAcabamento').on('submit', function(e) {
    e.preventDefault();
    var form = $(this);
    $.post(form.attr('action'), form.serialize())
      .done(function(resp) {
        if (resp.success) {
          alert('Acabamento registrado com sucesso!');
          location.reload();
        } else {
          alert(resp.message || 'Erro ao registrar acabamento.');
        }
      })
      .fail(function(xhr) {
        alert('Erro ao registrar acabamento: ' + (xhr.responseJSON && xhr.responseJSON.message ? xhr.responseJSON.message : 'Erro desconhecido.'));
      });
  });

  // Submissão AJAX do transporte
  $('#formTransporte').on('submit', function(e) {
    e.preventDefault();
    var form = $(this);
    // Transformar campos múltiplos em arrays
    var data = form.serializeArray();
    // Corrigir campos múltiplos (peca_nomes, placas)
    var peca_nomes = $('#peca_nomes').val().split(',').map(function(s) { return s.trim(); }).filter(Boolean);
    var placas = $('#placas').val().split(',').map(function(s) { return s.trim(); }).filter(Boolean);
    data = data.filter(function(item) { return item.name !== 'peca_nomes' && item.name !== 'placas'; });
    data.push({name: 'peca_nomes', value: peca_nomes});
    data.push({name: 'placas', value: placas});
    $.post(form.attr('action'), $.param(data))
      .done(function(resp) {
        if (resp.success) {
          alert('Transporte registrado com sucesso!');
          location.reload();
        } else {
          alert(resp.message || 'Erro ao registrar transporte.');
        }
      })
      .fail(function(xhr) {
        alert('Erro ao registrar transporte: ' + (xhr.responseJSON && xhr.responseJSON.message ? xhr.responseJSON.message : 'Erro desconhecido.'));
      });
  });

  // Autocomplete de peça por nome no acabamento
  $('#peca_nome').autocomplete({
    source: function(request, response) {
      var tanque_id = $('#tanque_id').val();
      if (!tanque_id) return response([]);
      $.getJSON('/concretagens/api/tanque/' + tanque_id + '/pecas', function(data) {
        var nomes = data.map(function(p) { return p.nome; });
        response($.ui.autocomplete.filter(nomes, request.term));
      });
    },
    minLength: 2
  });
 // Autocomplete de transporte
 $('#transportadora').on('focus', function() {
    var tanque_ids = $('#tanque_ids').val();
    if (!tanque_ids || tanque_ids.length === 0) return;
    // Buscar peças dos tanques selecionados
    $.ajax({
      url: '/acabamento-transporte/api/transportadoras',
      method: 'POST',
      contentType: 'application/json',
      data: JSON.stringify({ tanque_ids: tanque_ids }),
      headers: {
        'X-CSRFToken': $('input[name="csrf_token"]').val()
      },
      success: function(data) {
        console.log(data);
        var transportadoras = data.map(function(p) { return p; });
        $('#transportadora').autocomplete({
          source: transportadoras,
          minLength: 2
        });
      }
    });
  });
  // Autocomplete de peças por nome no transporte (sugestão, mas aceita múltiplos)
  $('#peca_nomes').on('focus', function() {
    var tanque_ids = $('#tanque_ids').val();
    if (!tanque_ids || tanque_ids.length === 0) return;
    // Buscar peças dos tanques selecionados
    $.ajax({
      url: '/concretagens/api/tanques/pecas',
      method: 'POST',
      contentType: 'application/json',
      data: JSON.stringify({ tanque_ids: tanque_ids }),
      headers: {
        'X-CSRFToken': '{{ csrf_token }}'
      },
      success: function(data) {
        var nomes = data.map(function(p) { return p.nome; });
        $('#peca_nomes').autocomplete({
          source: nomes,
          minLength: 2
        });
      }
    });
  });

  // Busca e seleção de peças para transporte
  $('#btnBuscarPecas').on('click', function() {
    var tanque_ids = $('#tanque_ids').val();
    var nome = $('#peca_nome_search').val();
    var apenasAcabadas = $('#apenasAcabadas').is(':checked') ? 1 : 0;
    if (!tanque_ids || tanque_ids.length === 0) {
      alert('Selecione ao menos um tanque.');
      return;
    }
    $.ajax({
      url: '/acabamento-transporte/api/pecas',
      method: 'GET',
      contentType: 'application/json',
      data: JSON.stringify({ tanque_ids: tanque_ids, nome: nome, apenas_acabadas: apenasAcabadas }),
      headers: {
        'X-CSRFToken': '{{ csrf_token }}'
      },
      success: function(data) {
      var tbody = $('#tabelaPecasSelecionar tbody');
      tbody.empty();
      if (data.length === 0) {
        tbody.append('<tr><td colspan="4" class="text-center">Nenhuma peça encontrada</td></tr>');
        return;
      }
      data.forEach(function(p) {
        tbody.append('<tr>' +
          '<td><input type="checkbox" class="checkPeca" value="' + p.id + '"></td>' +
          '<td>' + p.nome + '</td>' +
          '<td>' + p.tanque_nome + '</td>' +
          '</tr>');
      });
    }
    });
  });

  // Selecionar todos
  $(document).on('change', '#checkAllPecas', function() {
    $('.checkPeca').prop('checked', this.checked);
  });

  // Atualizar hidden com IDs das peças selecionadas antes de enviar
  $('#formTransporte').on('submit', function(e) {
    var selecionadas = $('.checkPeca:checked').map(function() { return this.value; }).get();
    if (selecionadas.length === 0) {
      alert('Selecione ao menos uma peça para transporte.');
      e.preventDefault();
      return false;
    }
    $('#peca_ids').val(selecionadas.join(','));
  });
}); 