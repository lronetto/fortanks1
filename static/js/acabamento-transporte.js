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
    var checkPecas = $('.checkPeca:checked').map(function() { return this.value; }).get();
    data = data.filter(function(item) { return item.name !== 'peca_ids'; });
    data.push({name: 'peca_ids', value: checkPecas});
    console.log(data);
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

  $('#datalistPecas').on('focus', function() {
    var tanque_ids = $('#tanque_id').val();
    if (!tanque_ids || tanque_ids.length === 0) return;
    fetch('/concretagens/api/tanques/' + tanque_ids + '/pecas')
    .then(response => response.json())
    .then(data => {
      const datalist = document.getElementById('datalistPecas');
      datalist.innerHTML = '';
      data.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.nome;
        datalist.appendChild(opt);  
      });
    });
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
          appendTo: $('#peca_nomes'),
          select: function(event, ui) {
            $('#peca_nomes').val(ui.item.value);
            return false;
          },

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
    $.get('/acabamento-transporte/api/pecas', { tanque_ids: tanque_ids, nome: nome, apenas_acabadas: apenasAcabadas })
      .done(function(data) {
        var tbody = $('#tabelaPecasSelecionar tbody');
        tbody.empty();
        if (!Array.isArray(data)) {
          tbody.append('<tr><td colspan="3" class="text-center text-danger">Erro ao buscar peças</td></tr>');
          alert('Erro ao buscar peças. Tente novamente.');
          return;
        }
        if (data.length === 0) {
          tbody.append('<tr><td colspan="3" class="text-center">Nenhuma peça encontrada</td></tr>');
          return;
        }
        data.forEach(function(p) {
          tbody.append('<tr>' +
            '<td><input type="checkbox" class="checkPeca" value="' + p.id + '"></td>' +
            '<td>' + p.nome + '</td>' +
            '<td>' + p.tanque_nome + '</td>' +
            '</tr>');
        });
      })
      .fail(function(xhr) {
        var tbody = $('#tabelaPecasSelecionar tbody');
        tbody.empty();
        tbody.append('<tr><td colspan="3" class="text-center text-danger">Erro ao buscar peças</td></tr>');
        alert('Erro ao buscar peças: ' + xhr.statusText);
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

  // Inicialização do select2 para o campo de peça no acabamento (agora múltiplo)
  $('#peca_id').select2({
    dropdownParent: $('#modalAcabamento'),
    theme: 'bootstrap-5',
    placeholder: 'Pesquise a peça pelo nome',
    allowClear: true,
    multiple: true,
    ajax: {
      url: '/acabamento-transporte/api/pecas',
      method: 'GET',
      dataType: 'json',
      delay: 250,
      data: function(params) {
        return {
          tanque_ids: [$('#tanque_id').val()],
          nome: params.term || '',
          apenas_concretadas: 1,
          apenas_acabadas:0,
          nao_acabadas: 1
        };
      },
      processResults: function(data) {
        return {
          results: data.map(function(peca) {
            return {
              id: peca.id,
              text: peca.nome + ' (' + peca.numero_sequencial + ')',
              tanque_nome: peca.tanque_nome
            };
          })
        };
      },
      cache: true
    },
    minimumInputLength: 2
  });

  // Limpar o select2 ao trocar o tanque
  $('#tanque_id').on('change', function() {
    $('#peca_id').val(null).trigger('change');
  });

  // Remover autocomplete/datalist antigo do campo de peça no acabamento, se existir
  $('#peca_nome').autocomplete && $('#peca_nome').autocomplete('destroy');
  $('#datalistPecas').remove();
}); 