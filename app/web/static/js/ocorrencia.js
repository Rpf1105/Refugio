/*
 * Refúgio — Tela Ocorrência (lógica do cliente)
 * -----------------------------------------------------------------------------
 * Responsabilidades:
 *  - Carregar os Relatos existentes via GET /api/relatos e renderizá-los como
 *    cards: descrição, Nível_de_Gravidade (com Cor_de_Gravidade), foto servida
 *    em /fotos/<basename> (com texto alternativo) e selo de validado (R5.2).
 *  - Enviar um novo Relato via POST /api/relatos (multipart/form-data): monta o
 *    FormData com municipio_id (do Município padrão em /api/municipios),
 *    usuario_id=1 (Cidadão semeado — ver nota abaixo), descrição, nível de
 *    gravidade, a foto obrigatória e, quando disponível, a geolocalização
 *    (lat/lng). Exibe a confirmação no sucesso (R4.6) ou a mensagem `erro`
 *    retornada pela API em caso de 400 (R4.1–R4.4).
 *
 * Nota de protótipo: o backend exige `usuario_id` no POST. Como esta demonstração
 * não tem autenticação, usamos o Cidadão semeado com id = 1 (documentado no seed
 * do banco). Em produção, o id viria da sessão autenticada.
 *
 * Todas as chamadas usam fetch() com caminhos relativos.
 */

(function () {
  "use strict";

  // Cidadão semeado usado pelo protótipo (sem autenticação). Ver nota acima.
  var USUARIO_ID_PADRAO = 1;

  // Mapeia o Nível_de_Gravidade de armazenamento para o rótulo exibido e a
  // classe utilitária de Cor_de_Gravidade do Sistema de Design (R12.*, R14.7).
  var GRAVIDADE = {
    baixo: { rotulo: "Baixo", classe: "gravidade-baixo" },
    medio: { rotulo: "Médio", classe: "gravidade-medio" },
    alto: { rotulo: "Alto", classe: "gravidade-alto" },
  };

  var listaRelatos = document.getElementById("lista-relatos");
  var statusRelatos = document.getElementById("status-relatos");
  var modeloRelato = document.getElementById("modelo-relato");
  var formRelato = document.getElementById("form-relato");
  var mensagemEnvio = document.getElementById("mensagem-envio");

  /**
   * Extrai o nome base (basename) de um caminho de foto. O `foto_path` pode vir
   * como caminho absoluto do servidor; as fotos são servidas em /fotos/<basename>.
   */
  function basename(caminho) {
    if (!caminho) {
      return "";
    }
    var partes = String(caminho).split(/[\\/]/);
    return partes[partes.length - 1];
  }

  /** Atualiza a região de status do formulário (aria-live) com uma cor. */
  function definirMensagem(texto, ehErro) {
    mensagemEnvio.textContent = texto;
    mensagemEnvio.style.color = ehErro
      ? "var(--cor-acao)"
      : "var(--cor-texto)";
  }

  /** Obtém o id do Município padrão a partir de GET /api/municipios (R7.1). */
  function obterMunicipioPadrao() {
    return fetch("/api/municipios")
      .then(function (resp) {
        if (!resp.ok) {
          throw new Error("Falha ao carregar municípios.");
        }
        return resp.json();
      })
      .then(function (dados) {
        var municipios = (dados && dados.municipios) || [];
        var padrao = municipios.filter(function (m) {
          return m.padrao;
        })[0];
        var escolhido = padrao || municipios[0];
        if (!escolhido) {
          throw new Error("Nenhum município disponível.");
        }
        return escolhido.id;
      });
  }

  /** Obtém a geolocalização do navegador; resolve com null quando indisponível. */
  function obterLocalizacao() {
    return new Promise(function (resolver) {
      if (!navigator.geolocation) {
        resolver(null);
        return;
      }
      navigator.geolocation.getCurrentPosition(
        function (pos) {
          resolver({ lat: pos.coords.latitude, lng: pos.coords.longitude });
        },
        function () {
          resolver(null);
        },
        { timeout: 5000 }
      );
    });
  }

  /** Cria o card de um Relato clonando o template (R5.2). */
  function renderizarRelato(relato) {
    var fragmento = modeloRelato.content.cloneNode(true);

    var info = GRAVIDADE[relato.nivel_gravidade] || {
      rotulo: relato.nivel_gravidade,
      classe: "gravidade-baixo",
    };

    // Selo de status: "Validado" quando o Órgão confirmou (R6.3); caso
    // contrário, "Em verificação". A cor segue a gravidade (R12.*).
    var selo = fragmento.querySelector(".selo-status");
    selo.textContent = relato.validado ? "Validado" : "Em verificação";
    selo.classList.add(info.classe);
    selo.setAttribute(
      "aria-label",
      (relato.validado ? "Relato validado" : "Relato em verificação") +
        ", gravidade " +
        info.rotulo.toLowerCase()
    );

    // Tempo (data/hora do envio), quando disponível.
    var tempo = fragmento.querySelector(".selo-tempo");
    if (relato.criado_em) {
      var data = new Date(relato.criado_em);
      tempo.textContent = isNaN(data.getTime())
        ? ""
        : data.toLocaleString("pt-BR");
    }

    // Descrição.
    fragmento.querySelector(".relato-descricao").textContent =
      relato.descricao || "";

    // Foto servida em /fotos/<basename>, com texto alternativo descritivo (R10.6).
    var img = fragmento.querySelector(".relato-foto");
    var nome = basename(relato.foto_path);
    if (nome) {
      img.src = "/fotos/" + encodeURIComponent(nome);
      img.alt =
        "Foto do relato: " +
        (relato.descricao || "ocorrência") +
        " (gravidade " +
        info.rotulo.toLowerCase() +
        ")";
    } else {
      img.remove();
    }

    // Contador de confirmações (placeholder — a contagem real virá de uma
    // tarefa futura; por ora refletimos o estado de validação).
    var confirmacoes = fragmento.querySelector(".relato-confirmacoes");
    confirmacoes.textContent = relato.validado
      ? "Confirmado por um órgão responsável"
      : "0 confirmações";

    return fragmento;
  }

  /** Carrega e renderiza a lista de Relatos (R5.2). */
  function carregarRelatos() {
    statusRelatos.textContent = "Carregando relatos…";
    return fetch("/api/relatos")
      .then(function (resp) {
        if (!resp.ok) {
          throw new Error("Falha ao carregar relatos.");
        }
        return resp.json();
      })
      .then(function (dados) {
        var relatos = (dados && dados.relatos) || [];
        listaRelatos.innerHTML = "";
        if (relatos.length === 0) {
          statusRelatos.textContent = "Nenhum relato na sua região ainda.";
          return;
        }
        statusRelatos.textContent = "";
        relatos.forEach(function (relato) {
          listaRelatos.appendChild(renderizarRelato(relato));
        });
      })
      .catch(function (erro) {
        statusRelatos.textContent =
          "Não foi possível carregar os relatos. " + erro.message;
      });
  }

  /** Envia o Relato via POST /api/relatos (multipart) (R4.1). */
  function enviarRelato(evento) {
    evento.preventDefault();

    var descricao = document.getElementById("descricao").value.trim();
    var nivel = document.getElementById("nivel_gravidade").value;
    var inputFoto = document.getElementById("foto");
    var arquivo = inputFoto.files && inputFoto.files[0];

    // Validações no cliente (o servidor é a fonte da verdade, R4.2–R4.4).
    if (!descricao) {
      definirMensagem("A descrição é obrigatória.", true);
      return;
    }
    if (!arquivo) {
      definirMensagem("A foto é obrigatória.", true);
      return;
    }

    definirMensagem("Enviando relato…", false);
    var botao = formRelato.querySelector('button[type="submit"]');
    botao.disabled = true;

    Promise.all([obterMunicipioPadrao(), obterLocalizacao()])
      .then(function (resultados) {
        var municipioId = resultados[0];
        var local = resultados[1];

        var dados = new FormData();
        dados.append("municipio_id", municipioId);
        dados.append("usuario_id", USUARIO_ID_PADRAO);
        dados.append("descricao", descricao);
        dados.append("nivel_gravidade", nivel);
        dados.append("foto", arquivo);
        if (local) {
          dados.append("lat", local.lat);
          dados.append("lng", local.lng);
        }

        return fetch("/api/relatos", { method: "POST", body: dados });
      })
      .then(function (resp) {
        return resp.json().then(function (corpo) {
          return { ok: resp.ok, corpo: corpo };
        });
      })
      .then(function (resultado) {
        if (!resultado.ok) {
          // A API retorna { erro, campo } em caso de 400 (R4.2–R4.4).
          var msg =
            (resultado.corpo && resultado.corpo.erro) ||
            "Não foi possível enviar o relato.";
          definirMensagem(msg, true);
          return;
        }
        // Confirmação de recebimento (R4.6).
        definirMensagem(
          (resultado.corpo && resultado.corpo.mensagem) ||
            "Relato recebido com sucesso.",
          false
        );
        formRelato.reset();
        carregarRelatos();
      })
      .catch(function () {
        definirMensagem(
          "Erro de conexão ao enviar o relato. Tente novamente.",
          true
        );
      })
      .finally(function () {
        botao.disabled = false;
      });
  }

  // Inicialização.
  if (formRelato) {
    formRelato.addEventListener("submit", enviarRelato);
  }
  carregarRelatos();
})();
