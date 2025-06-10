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
    $.post(form.attr('action'), form.serialize())
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
  

 
  // Inicialização do select2 para o campo de peça no acabamento (agora múltiplo)
  $('#acabamento-peca_id').select2({
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
          tanque_ids: [$('#acabamento-tanque_id').val()],
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
  $('#transporte-peca_id').select2({
    dropdownParent: $('#modalTransporte'),
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
          tanque_ids: [$('#transporte-tanque_ids').val()],
          nome: params.term || '',
          apenas_concretadas: 1,
          apenas_acabadas:0,
          nao_acabadas: 0
        };
      },
      processResults: function(data) {
        return {
          results: data.map(function(peca) {
            return {
              id: peca.id,
              text: peca.tanque_nome + ' - ' + peca.nome,
              tanque_nome: peca.tanque_nome
            };
          })
        };
      },
      cache: true
    },
    minimumInputLength: 2
  });
  $('#transporte-tanque_id').select2({
    dropdownParent: $('#modalTransporte'),
    theme: 'bootstrap-5',
    placeholder: 'Pesquise a peça pelo nome',
    allowClear: true,
    multiple: true,
    ajax: {
      url: '/acabamento-transporte/api/tanques',
      method: 'GET',
      dataType: 'json',
      delay: 250,

      processResults: function(data) {
        return {
          results: data.map(function(tanque) {
            return {
              id: tanque.id,
              text: tanque.nome
            };
          })
        };
      },
      cache: true
    },
  });
  // Limpar o select2 ao trocar o tanque
  $('#tanque_id').on('change', function() {
    $('#peca_id').val(null).trigger('change');
  });

  // Remover autocomplete/datalist antigo do campo de peça no acabamento, se existir
  $('#peca_nome').autocomplete && $('#peca_nome').autocomplete('destroy');
  $('#datalistPecas').remove();
}); 