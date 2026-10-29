# Implementation Plan: Refúgio — Aplicativo de Resposta a Emergências

## Overview

Este plano converte o design do protótipo **Refúgio** em uma sequência incremental de tarefas de codificação em **Python**. Cada tarefa constrói sobre as anteriores, começando pela estrutura do projeto e camada de dados, passando pelas funções puras de domínio (validadas por property-based tests com Hypothesis), serviços, API FastAPI, sincronização com o Portal de Dados Abertos, frontend responsivo (4 telas + Leaflet), empacotamento Docker e, por fim, testes de integração/smoke e fiação final.

As 14 Correctness Properties do design são implementadas individualmente com **Hypothesis** (mínimo 100 iterações, uma propriedade por teste, com a tag de rastreabilidade `# Feature: emergency-response-app, Property N: ...`). Subtarefas de teste são marcadas como opcionais com `*` e não devem ser implementadas automaticamente.

Stack: FastAPI, Uvicorn, Pydantic, SQLite (via camada de acesso isolada), fotos em disco, APScheduler, httpx, pytest, Hypothesis. Mapa com Leaflet + OpenStreetMap no navegador.

## Tasks

- [x] 1. Configurar estrutura do projeto e dependências
  - Criar a estrutura de diretórios `app/` (ex.: `app/main.py`, `app/dominio/`, `app/servicos/`, `app/dados/`, `app/integracao/`, `app/web/static/`, `app/web/templates/`) e `tests/`
  - Criar `requirements.txt` com: `fastapi`, `uvicorn`, `pydantic`, `hypothesis`, `pytest`, `httpx`, `apscheduler`
  - Criar `app/config.py` com as variáveis de configuração (`FONTE_DADOSGOVBR_HABILITADA`=true, `FONTE_DADOSGOVBR_POLLING_SEGUNDOS`=21600, `FONTE_DADOSGOVBR_URL`, fontes opcionais desligadas) lidas de variáveis de ambiente com os padrões do design
  - Criar `pytest.ini`/configuração mínima para rodar `pytest`
  - _Requirements: 8.1, 15.1, 15.7_

- [x] 2. Implementar a camada de dados (SQLite) e o schema
  - [x] 2.1 Criar módulo de acesso a dados isolado e esquema do banco
    - Escrever `app/dados/db.py` com conexão SQLite em arquivo (`/data/refugio.db`) e função de inicialização de schema
    - Criar tabelas `municipio`, `usuario`, `area_afetada`, `abrigo`, `relato`, `incidente`, `pedido_ajuda` conforme o modelo de dados do design
    - Adicionar a **restrição de unicidade** `UNIQUE(origem, id_externo)` na tabela `incidente` para garantir idempotência da importação
    - Semear o Município padrão "Ribeirão Preto" (`padrao = true`) com centro geográfico, e usuários de exemplo (perfis `cidadao` e `orgao_responsavel`)
    - _Requirements: 7.1, 15.4, 15.5_
  - [ ]* 2.2 Escrever testes de exemplo para inicialização e seed do banco
    - Verificar criação das tabelas, presença do Município padrão e da restrição de unicidade `(origem, id_externo)`
    - _Requirements: 7.1, 15.5_

- [x] 3. Implementar funções puras de domínio e seus property-based tests
  - [x] 3.1 Implementar valor de gravidade e gravidade média do incidente
    - Escrever `app/dominio/gravidade.py` com `valor_gravidade(nivel)` (baixo→1, médio→2, alto→3) e `gravidade_media(relatos)` (média aritmética, assume ≥1 relato, resultado em [1.0, 3.0])
    - _Requirements: 9.2, 9.3_
  - [ ]* 3.2 Escrever property test para gravidade média
    - `# Feature: emergency-response-app, Property 1: Gravidade Média está sempre nos limites e é a média aritmética`
    - Hypothesis, mínimo 100 iterações; gerar listas não vazias de relatos
    - **Property 1** — **Validates: Requirements 9.2, 9.3**
  - [ ]* 3.3 Escrever teste de exemplo para valor de gravidade
    - Casos fixos baixo→1, médio→2, alto→3
    - _Requirements: 9.2_
  - [x] 3.4 Implementar classificação de veracidade
    - Escrever `app/dominio/veracidade.py` com `veracidade(qtd_relatos)` (baixa: 1–2, média: 3–5, alta: ≥6), garantindo monotonicidade
    - _Requirements: 9.4, 9.5_
  - [ ]* 3.5 Escrever property test para veracidade
    - `# Feature: emergency-response-app, Property 2: Veracidade é corretamente classificada e monotônica`
    - Hypothesis, mínimo 100 iterações; validar faixas e que aumentar a quantidade nunca reduz a veracidade
    - **Property 2** — **Validates: Requirements 9.4, 9.5**
  - [x] 3.6 Implementar mapeamento de cor por gravidade média e por nível
    - Escrever `app/dominio/cores.py` com `cor_por_media(media)` (amarelo 1.0–1.5, laranja >1.5–2.5, vermelho >2.5–3.0) e `cor_por_nivel(nivel)` (baixo→amarelo, médio→laranja `#E8A028`, alto→vermelho `#C9291C`)
    - _Requirements: 12.1, 12.2, 12.3, 12.4_
  - [ ]* 3.7 Escrever property test para cor por gravidade média
    - `# Feature: emergency-response-app, Property 3: Gravidade Média mapeia para a Cor de Gravidade correta`
    - Hypothesis, mínimo 100 iterações; floats em [1.0, 3.0] incluindo bordas 1.5 e 2.5
    - **Property 3** — **Validates: Requirements 12.4**
  - [ ]* 3.8 Escrever property test para consistência entre cor por nível e cor por média
    - `# Feature: emergency-response-app, Property 4: Cor por nível é consistente com a cor por média`
    - Hypothesis, mínimo 100 iterações; listas de relatos todas no mesmo nível
    - **Property 4** — **Validates: Requirements 12.1, 12.2, 12.3**
  - [ ]* 3.9 Escrever teste de exemplo para cor por nível
    - Três casos fixos (baixo/médio/alto)
    - _Requirements: 12.1, 12.2, 12.3_
  - [x] 3.10 Implementar distância Haversine
    - Escrever `app/dominio/geo.py` com `haversine(lat1, lng1, lat2, lng2)` retornando metros (≥0, nula na identidade, simétrica)
    - _Requirements: 2.4_
  - [ ]* 3.11 Escrever property test para distância ao abrigo
    - `# Feature: emergency-response-app, Property 11: A distância ao Abrigo é não-negativa, nula na identidade e simétrica`
    - Hypothesis, mínimo 100 iterações; pares de coordenadas geográficas
    - **Property 11** — **Validates: Requirements 2.4**
  - [x] 3.12 Implementar Filtro de Conteúdo
    - Escrever `app/dominio/filtro_conteudo.py` com `TERMOS_BLOQUEADOS`, `normalizar(texto)` (minúsculas + remoção de acentos NFD) e `contem_termo_bloqueado(descricao)` com limite de palavra para termos simples e substring para expressões compostas
    - _Requirements: 11.3, 11.4, 11.5_
  - [ ]* 3.13 Escrever property test para detecção de termos bloqueados
    - `# Feature: emergency-response-app, Property 6: O Filtro de Conteúdo detecta todo Termo Bloqueado independentemente de caixa e acento`
    - Hypothesis, mínimo 100 iterações; injetar termos em variações de caixa/acento
    - **Property 6** — **Validates: Requirements 11.3, 11.4, 11.5**
  - [ ]* 3.14 Escrever property test para descrições limpas aceitas pelo filtro
    - `# Feature: emergency-response-app, Property 7: Descrições sem Termos Bloqueados são aceitas pelo Filtro`
    - Hypothesis, mínimo 100 iterações; construir textos a partir de alfabeto sem termos bloqueados
    - **Property 7** — **Validates: Requirements 11.3, 11.5**

- [x] 4. Checkpoint — Garantir que os testes das funções puras de domínio passam
  - Garantir que todos os testes passam; perguntar ao usuário em caso de dúvidas.

- [x] 5. Implementar a Rota Segura (abordagem simplificada por grade)
  - [x] 5.1 Implementar grade, bloqueio por Área Afetada e busca de caminho
    - Escrever `app/dominio/rotas.py`: sobrepor grade sobre a região do Município, marcar células dentro de polígonos de Áreas Afetadas como bloqueadas, executar busca (A*/BFS) e converter o caminho em polyline; retornar "nenhuma Rota Segura encontrada" quando não houver caminho livre
    - _Requirements: 3.1, 3.2, 3.3_
  - [ ]* 5.2 Escrever property test para rota segura
    - `# Feature: emergency-response-app, Property 12: A Rota Segura nunca atravessa uma Área Afetada`
    - Hypothesis, mínimo 100 iterações; conjuntos de polígonos e pares origem/destino; verificar que nenhum ponto da rota está dentro de Área Afetada e que ausência de caminho é sinalizada
    - **Property 12** — **Validates: Requirements 3.1, 3.2, 3.3**

- [x] 6. Implementar validações de Relato e Pedido de Ajuda (domínio)
  - [x] 6.1 Implementar validação de Relato
    - Escrever `app/dominio/validacao.py` com `validar_relato(descricao, nivel, tem_foto)`: rejeitar descrição vazia/apenas espaços ("a descrição é obrigatória"), sem foto ("a foto é obrigatória"), e nível fora de {baixo, médio, alto} (mensagem com valores válidos)
    - _Requirements: 4.2, 4.3, 4.4_
  - [ ]* 6.2 Escrever property test para rejeição de Relatos inválidos
    - `# Feature: emergency-response-app, Property 8: Relatos inválidos são rejeitados`
    - Hypothesis, mínimo 100 iterações; gerar relatos sem descrição, sem foto ou com nível inválido
    - **Property 8** — **Validates: Requirements 4.2, 4.3, 4.4**
  - [x] 6.3 Implementar validação de Pedido de Ajuda
    - Adicionar `validar_pedido(descricao)`: rejeitar descrição vazia/apenas espaços ("a descrição é obrigatória")
    - _Requirements: 11.2_
  - [ ]* 6.4 Escrever property test para rejeição de Pedido sem descrição
    - `# Feature: emergency-response-app, Property 9: Pedido de Ajuda sem descrição é rejeitado`
    - Hypothesis, mínimo 100 iterações; descrições vazias/somente espaços
    - **Property 9** — **Validates: Requirements 11.2**

- [x] 7. Implementar os serviços de domínio sobre a camada de dados
  - [x] 7.1 Implementar Serviço de Áreas Afetadas e Serviço de Abrigos
    - Escrever `app/servicos/areas.py` e `app/servicos/abrigos.py`: CRUD e consultas por `municipio_id`; cálculo de distância Cidadão→Abrigo via `haversine`
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 2.4, 6.1, 6.2_
  - [x] 7.2 Implementar Serviço de Relatos
    - Escrever `app/servicos/relatos.py`: validação, armazenamento de foto em `/data/fotos` (persistir Relato só após a foto salva), associação de localização/data-hora, consulta com filtro por gravidade e por Município; marcação de validado
    - _Requirements: 4.1, 4.5, 4.6, 5.1, 5.2, 5.3, 6.3, 7.2_
  - [x] 7.3 Implementar Serviço de Incidentes
    - Escrever `app/servicos/incidentes.py`: agrupar Relatos por tipo + proximidade, derivar Gravidade_Média/Veracidade/cor dos Relatos associados, recalcular ao adicionar Relato, omitir Incidentes locais sem Relatos
    - _Requirements: 9.1, 9.6, 9.7, 9.8_
  - [ ]* 7.4 Escrever property test para recálculo consistente do Incidente
    - `# Feature: emergency-response-app, Property 5: Recalcular após adicionar um Relato é consistente com calcular sobre a lista estendida`
    - Hypothesis, mínimo 100 iterações; comparar recálculo incremental com cálculo direto sobre a lista estendida
    - **Property 5** — **Validates: Requirements 9.7**
  - [ ]* 7.5 Escrever teste de exemplo para omissão de Incidente sem Relatos
    - Incidente local sem Relatos é omitido da listagem
    - _Requirements: 9.8_
  - [x] 7.6 Implementar Serviço de Pedidos de Ajuda
    - Escrever `app/servicos/pedidos.py`: validação de descrição, aplicação do Filtro de Conteúdo, associação de localização/data-hora, listagem por Município
    - _Requirements: 11.1, 11.5, 11.6, 11.7, 11.8, 11.9_
  - [x] 7.7 Implementar Controle de Acesso por perfil
    - Escrever `app/servicos/acesso.py`: distinguir perfis `cidadao`/`orgao_responsavel` (via cabeçalho/sessão simples) e proteger operações de gestão com mensagem "acesso não autorizado"
    - _Requirements: 6.4_
  - [ ]* 7.8 Escrever property test para controle de acesso de gestão
    - `# Feature: emergency-response-app, Property 13: Operações de gestão exigem perfil de Órgão Responsável`
    - Hypothesis, mínimo 100 iterações; perfis variados tentando cadastrar Área/Abrigo
    - **Property 13** — **Validates: Requirements 6.4**
  - [ ]* 7.9 Escrever property test para consultas por Município e filtro de gravidade
    - `# Feature: emergency-response-app, Property 10: Consultas respeitam o Município e o filtro de gravidade`
    - Hypothesis, mínimo 100 iterações; conjuntos de dados em múltiplos Municípios e filtros de gravidade
    - **Property 10** — **Validates: Requirements 1.1, 2.1, 5.1, 5.3, 7.2**

- [x] 8. Checkpoint — Garantir que os testes dos serviços de domínio passam
  - Garantir que todos os testes passam; perguntar ao usuário em caso de dúvidas.

- [x] 9. Implementar a aplicação FastAPI e endpoints da API
  - [x] 9.1 Criar aplicação FastAPI, modelos Pydantic e tratamento de erros padronizado
    - Escrever `app/main.py` inicializando o app, montando estáticos (`/static`, `/fotos`), inicializando o banco no startup; definir modelos Pydantic e handler de erros JSON `{ "erro", "campo" }` com status 400/403/404
    - _Requirements: 8.1, 10.1, 10.2_
  - [x] 9.2 Implementar endpoints de Municípios, Áreas e Abrigos
    - `GET /api/municipios`, `GET/POST /api/areas`, `GET/POST /api/abrigos` (POST restrito a Órgão), incluindo nível/cor e distância quando lat/lng informados, e mensagens de ausência de dados
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 2.4, 6.1, 6.2, 6.4, 7.1, 7.2, 7.3_
  - [x] 9.3 Implementar endpoints de Relatos e Incidentes
    - `GET/POST /api/relatos` (multipart com foto; filtro por gravidade), `POST /api/relatos/{id}/validar` (Órgão), `GET /api/incidentes` (gravidade média, cor, veracidade)
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.1, 5.2, 5.3, 6.3, 6.4, 9.1, 9.6, 9.7, 9.8, 12.4_
  - [x] 9.4 Implementar endpoints de Rotas e Pedidos de Ajuda
    - `GET /api/rotas` (rota evitando Áreas Afetadas, recálculo na consulta), `POST /api/pedidos` (Filtro de Conteúdo + confirmação), `GET /api/pedidos`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 11.1, 11.2, 11.5, 11.6, 11.7, 11.8, 11.9_
  - [ ]* 9.5 Escrever testes de integração dos endpoints de envio
    - Fluxos `POST /api/relatos` (persistência + foto + confirmação) e `POST /api/pedidos` (filtro + persistência + confirmação); listagem de Pedidos para Cidadão e Órgão, usando `httpx`/TestClient
    - _Requirements: 4.1, 4.5, 4.6, 11.1, 11.6, 11.7, 11.8, 11.9_

- [x] 10. Implementar a integração com o Portal de Dados Abertos
  - [x] 10.1 Implementar adaptador do Portal de Dados Abertos e importação idempotente
    - Escrever `app/integracao/dados_abertos.py` com interface `buscar_incidentes(municipio) -> list[IncidenteExterno]` usando `httpx`, parser de normalização, e importação via upsert pela chave `(origem="portal_dados_abertos", id_externo)`; degradação graciosa (preservar dados, continuar operando, registrar falha em log) em caso de erro/timeout/payload inválido
    - _Requirements: 15.2, 15.3, 15.4, 15.5, 15.6_
  - [ ]* 10.2 Escrever property test para idempotência da importação
    - `# Feature: emergency-response-app, Property 14: A importação de Incidentes_Externos é idempotente`
    - Hypothesis, mínimo 100 iterações; conjuntos com chaves `(origem, id_externo)` repetidas; importar 1+ vezes resulta no mesmo estado sem duplicatas
    - **Property 14** — **Validates: Requirements 15.5**
  - [ ]* 10.3 Escrever testes de exemplo da sincronização com stub do Portal
    - Importação com `origem="portal_dados_abertos"` e exibição junto aos Relatos; dupla importação sem duplicatas; degradação graciosa quando o stub falha
    - _Requirements: 15.2, 15.3, 15.4, 15.5, 15.6_
  - [x] 10.4 Implementar o Agendador periódico (6h) com clock injetável
    - Escrever `app/integracao/agendador.py` usando APScheduler com interval trigger de 21600s, iniciado no startup apenas quando `FONTE_DADOSGOVBR_HABILITADA`; receber o relógio por injeção; omitir requisições quando desabilitado
    - _Requirements: 15.1, 15.7_
  - [ ]* 10.5 Escrever testes do agendador com clock falso
    - Com relógio falso injetado, confirmar disparo no intervalo de 6h e omissão quando desabilitado por configuração
    - _Requirements: 15.1, 15.7_
  - [x] 10.6 Implementar endpoints de Incidentes Externos e sincronização manual
    - `GET /api/incidentes-externos` e `POST /api/admin/sincronizar-dados-abertos` (restrito a Órgão), diferenciando procedência no retorno e aplicando `gravidade_externa` na cor quando informada
    - _Requirements: 15.3, 15.4_

- [x] 11. Checkpoint — Garantir que os testes de API e sincronização passam
  - Garantir que todos os testes passam; perguntar ao usuário em caso de dúvidas.

- [x] 12. Implementar o frontend responsivo (Sistema de Design e telas)
  - [x] 12.1 Implementar o Sistema de Design e base responsiva/acessível
    - Criar `app/web/static/css/estilo.css` com os tokens (cores `#C9291C`, `#EFEFEC`, `#DEDEDB`, `#F6D9A6`, `#E8A028`, `#9DC48C`; tipografia Helvetica Neue/Arial; botão pílula `border-radius:99px`; card `border-radius:22–28px`; alvo de toque mínimo 44px) e layout fluido de 320px a 1920px; incluir base de acessibilidade (navegação por teclado, foco visível) e mensagem de navegadores compatíveis
    - _Requirements: 10.3, 10.6, 10.7, 10.8, 14.2, 14.3, 14.4, 14.6, 14.7_
  - [x] 12.2 Implementar as telas Início e Ocorrência
    - Criar templates/HTML das telas Início (título "Refúgio", card de alerta `#F6D9A6`, botão primário e atalhos) e Ocorrência (exibição de Relato com selo/status/foto/confirmações e formulário com descrição, seletor de gravidade e foto obrigatória), com texto alternativo nos elementos não textuais
    - _Requirements: 4.1, 5.2, 10.6, 14.1, 14.5_
  - [x] 12.3 Implementar a tela Mapa com Leaflet, cores de gravidade e legenda
    - Criar o HTML/JS do Mapa integrando Leaflet + OpenStreetMap: consumir `/api/*`, desenhar Áreas/Abrigos/Relatos/Incidentes/Incidentes_Externos com cores por gravidade, botões-pílula de filtro, card de detalhe, legenda de cores e diferenciação visual de procedência externa; aviso quando tiles não carregarem
    - _Requirements: 1.1, 1.2, 2.1, 2.2, 5.1, 5.2, 5.3, 9.6, 12.1, 12.2, 12.3, 12.4, 12.5, 14.1, 15.3_
  - [x] 12.4 Implementar a tela Pedir ajuda
    - Criar o HTML/JS da tela Pedir ajuda (título, campo de descrição, localização, botão "Enviar pedido", aviso legal), consumindo `POST /api/pedidos` e exibindo a mensagem de rejeição do Filtro de Conteúdo quando aplicável
    - _Requirements: 11.1, 11.2, 11.5, 11.7, 11.8, 14.1_
  - [ ]* 12.5 Escrever testes de exemplo de conformidade do Sistema de Design
    - Verificar tokens (cores, tipografia, raio de botão 99px, raio de card 22–28px, alvo 44px, nome "Refúgio") e presença das 4 telas e da legenda de cores
    - _Requirements: 12.5, 14.1, 14.2, 14.3, 14.4, 14.5, 14.6_

- [x] 13. Empacotar o protótipo em container Docker
  - Criar o `Dockerfile` (base `python:3.12-slim`, instalar `requirements.txt`, `VOLUME ["/data"]`, `EXPOSE 8000`, `CMD uvicorn app.main:app --host 0.0.0.0 --port 8000`) e um `.dockerignore`
  - Observação: o provisionamento e a execução da Instância EC2 real são operação manual (fora do escopo de tarefas de código); seguir o passo a passo do design para `docker build`/`docker run`
  - _Requirements: 13.1, 13.2, 13.3_

- [x] 14. Fiação final e testes de integração/smoke
  - [x] 14.1 Integrar startup, rotas de página e assets estáticos
    - Garantir que `app/main.py` registra todos os routers da API, serve as 4 páginas (`/`, `/mapa`, `/ocorrencia`, `/pedir-ajuda`), monta `/static` e `/fotos`, inicializa o banco e inicia o agendador quando habilitado
    - _Requirements: 10.1, 10.2, 13.3_
  - [ ]* 14.2 Escrever teste de smoke da aplicação
    - Subir o app via TestClient e verificar que as páginas e endpoints principais respondem com sucesso na porta exposta
    - _Requirements: 13.3_

- [x] 15. Checkpoint final — Garantir que todos os testes passam
  - Garantir que todos os testes passam; perguntar ao usuário em caso de dúvidas.

## Notes

- Tarefas marcadas com `*` são opcionais (testes) e podem ser puladas para um MVP mais rápido; não devem ser implementadas automaticamente.
- Cada tarefa referencia requisitos específicos para rastreabilidade.
- As 14 Correctness Properties do design têm, cada uma, uma subtarefa de property-based test correspondente (Properties 1–14), implementada com Hypothesis (mín. 100 iterações) e tag de rastreabilidade.
- Checkpoints garantem validação incremental entre as fases.
- O provisionamento/execução da Instância EC2 é operação manual e intencionalmente fica fora das tarefas executáveis (apenas documentado como observação na tarefa 13).
- As fontes de dados opcionais (Defesa Civil SP e Defesa Civil Alerta) permanecem desligadas por padrão e não possuem tarefas dedicadas no escopo do protótipo.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "3.1", "3.4", "3.6", "3.10", "3.12", "6.1", "6.3"] },
    { "id": 3, "tasks": ["3.2", "3.3", "3.5", "3.7", "3.8", "3.9", "3.11", "3.13", "3.14", "5.1", "6.2", "6.4"] },
    { "id": 4, "tasks": ["5.2", "7.1", "7.2", "7.6", "7.7"] },
    { "id": 5, "tasks": ["7.3", "7.8", "7.9"] },
    { "id": 6, "tasks": ["7.4", "7.5", "9.1"] },
    { "id": 7, "tasks": ["9.2", "9.3", "9.4"] },
    { "id": 8, "tasks": ["9.5", "10.1", "10.4"] },
    { "id": 9, "tasks": ["10.2", "10.3", "10.5", "10.6"] },
    { "id": 10, "tasks": ["12.1"] },
    { "id": 11, "tasks": ["12.2", "12.3", "12.4"] },
    { "id": 12, "tasks": ["12.5", "13"] },
    { "id": 13, "tasks": ["14.1"] },
    { "id": 14, "tasks": ["14.2"] }
  ]
}
```
