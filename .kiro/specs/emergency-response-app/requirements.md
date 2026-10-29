# Requirements Document

## Introduction

O Aplicativo de Resposta a Emergências é uma plataforma desenvolvida em Python cujo objetivo é ajudar a população a se preparar e se orientar durante catástrofes e situações de emergência, como incêndios e enchentes. O foco inicial é o município de Ribeirão Preto, com possibilidade de expansão para outros municípios.

A plataforma conecta cidadãos, informações geográficas e órgãos responsáveis, permitindo visualizar áreas afetadas, identificar locais de abrigo, consultar rotas seguras e reportar ocorrências. Dessa forma, o aplicativo busca reduzir a desinformação e apoiar a tomada de decisão em momentos críticos.

Este documento define os requisitos funcionais e não funcionais que orientarão o projeto e o desenvolvimento subsequente.

## Glossary

- **Aplicativo**: O sistema de software completo de resposta a emergências desenvolvido em Python, exibido ao Cidadão com o nome "Refúgio".
- **Mockup_de_Referência**: Conjunto de telas de design pré-desenvolvidas (Início, Mapa, Ocorrência e Pedir ajuda) que servem como referência visual fiel para a implementação da Interface_Web.
- **Sistema_de_Design**: Conjunto de cores, tipografia, espaçamentos e componentes definidos nos Mockups_de_Referência que a Interface_Web deve replicar.
- **Cidadão**: Pessoa que utiliza o Aplicativo para consultar informações ou enviar relatos.
- **Órgão_Responsável**: Entidade pública ou de defesa civil autorizada a receber, validar e gerenciar informações de emergência no Aplicativo.
- **Relato**: Registro de ocorrência enviado por um Cidadão, composto por descrição textual, nível de gravidade e uma foto.
- **Nível_de_Gravidade**: Classificação do Relato entre os valores "baixo", "médio" e "alto".
- **Área_Afetada**: Região geográfica identificada no Aplicativo como atingida por uma emergência.
- **Abrigo**: Local físico cadastrado no Aplicativo destinado a acolher Cidadãos durante uma emergência.
- **Rota_Segura**: Caminho geográfico sugerido pelo Aplicativo que evita Áreas_Afetadas.
- **Mapa**: Componente do Aplicativo que exibe informações geográficas, incluindo Áreas_Afetadas, Abrigos e Rotas_Seguras.
- **Município**: Divisão geográfica administrativa; o Município inicial suportado é Ribeirão Preto.
- **Incidente**: Agrupamento de um ou mais Relatos que se referem a uma mesma ocorrência de emergência, identificado por localização e tipo de ocorrência.
- **Valor_de_Gravidade**: Valor numérico atribuído a cada Nível_de_Gravidade para permitir cálculos, sendo "baixo" igual a 1, "médio" igual a 2 e "alto" igual a 3.
- **Gravidade_Média**: Média aritmética dos Valores_de_Gravidade dos Relatos associados a um Incidente.
- **Veracidade**: Classificação da confiabilidade de um Incidente determinada pela quantidade de Relatos associados ao Incidente, entre os valores "baixa", "média" e "alta".
- **Interface_Web**: Página web responsiva por meio da qual o Cidadão acessa as funcionalidades do Aplicativo.
- **Navegador_Web**: Programa de navegação na internet utilizado pelo Cidadão para acessar a Interface_Web.
- **Dispositivo**: Equipamento utilizado pelo Cidadão para acessar a Interface_Web, do tipo desktop, notebook, tablet ou smartphone.
- **Pedido_de_Ajuda**: Solicitação de auxílio enviada por um Cidadão por meio do Aplicativo, composta por descrição textual e localização geográfica.
- **Filtro_de_Conteúdo**: Mecanismo do Aplicativo que analisa o texto de um Pedido_de_Ajuda para identificar Termos_Bloqueados.
- **Termo_Bloqueado**: Palavra ou expressão cadastrada no Aplicativo cujo uso em um Pedido_de_Ajuda é proibido.
- **Termos_Bloqueados**: Conjunto de Termos_Bloqueados cadastrados no Aplicativo, composto por "pix", "chave pix", "transferência", "ted", "doc", "boleto", "cartão", "paypal", "dinheiro", "pagamento" e "conta bancária".
- **Cor_de_Gravidade**: Cor utilizada no Mapa para representar visualmente um Nível_de_Gravidade, sendo amarelo para "baixo", laranja para "médio" e vermelho para "alto".
- **Container**: Unidade de software empacotada com o Aplicativo e suas dependências para execução isolada do protótipo.
- **Instância_EC2**: Máquina virtual provida pelo serviço Amazon EC2 na qual o Container do Aplicativo é hospedado para apresentação do protótipo.
- **Portal_de_Dados_Abertos**: O Portal Brasileiro de Dados Abertos (dados.gov.br), fonte pública de dados usada pelo Aplicativo para obter incidentes registrados.
- **Sincronização_de_Dados_Abertos**: Processo periódico em que o Aplicativo consulta o Portal_de_Dados_Abertos para importar incidentes e acrescentá-los aos dados do Aplicativo.
- **Incidente_Externo**: Incidente obtido do Portal_de_Dados_Abertos e incorporado aos dados do Aplicativo, distinguível por sua origem externa.

## Requirements

### Requirement 1: Visualização de Áreas Afetadas

**User Story:** Como Cidadão, quero visualizar as áreas afetadas por uma emergência no mapa, para que eu possa saber quais regiões evitar.

#### Acceptance Criteria

1. WHEN um Cidadão abre o Mapa, THE Aplicativo SHALL exibir as Áreas_Afetadas cadastradas para o Município selecionado.
2. WHEN uma Área_Afetada é exibida no Mapa, THE Aplicativo SHALL apresentar o Nível_de_Gravidade associado à Área_Afetada.
3. IF não existem Áreas_Afetadas cadastradas para o Município selecionado, THEN THE Aplicativo SHALL exibir uma mensagem informando a ausência de Áreas_Afetadas.
4. WHEN uma Área_Afetada é atualizada por um Órgão_Responsável, THE Aplicativo SHALL refletir a atualização no Mapa em até 60 segundos.

### Requirement 2: Identificação de Locais de Abrigo

**User Story:** Como Cidadão, quero identificar os locais de abrigo disponíveis, para que eu possa encontrar um lugar seguro durante uma emergência.

#### Acceptance Criteria

1. WHEN um Cidadão consulta Abrigos, THE Aplicativo SHALL exibir no Mapa os Abrigos cadastrados para o Município selecionado.
2. WHEN um Abrigo é exibido, THE Aplicativo SHALL apresentar o nome, o endereço e a capacidade do Abrigo.
3. IF nenhum Abrigo está cadastrado para o Município selecionado, THEN THE Aplicativo SHALL exibir uma mensagem informando a ausência de Abrigos.
4. WHEN um Cidadão seleciona um Abrigo, THE Aplicativo SHALL exibir a distância entre a localização do Cidadão e o Abrigo selecionado.

### Requirement 3: Consulta de Rotas Seguras

**User Story:** Como Cidadão, quero consultar rotas seguras até um destino, para que eu possa me deslocar evitando áreas de risco.

#### Acceptance Criteria

1. WHEN um Cidadão informa uma origem e um destino, THE Aplicativo SHALL calcular uma Rota_Segura que evite as Áreas_Afetadas conhecidas.
2. WHEN uma Rota_Segura é calculada, THE Aplicativo SHALL exibir a Rota_Segura no Mapa.
3. IF não existe Rota_Segura que evite todas as Áreas_Afetadas entre a origem e o destino, THEN THE Aplicativo SHALL exibir uma mensagem informando que nenhuma Rota_Segura foi encontrada.
4. WHEN uma Área_Afetada é adicionada ou atualizada, THE Aplicativo SHALL recalcular a Rota_Segura exibida ao Cidadão.

### Requirement 4: Envio de Relatos de Desastre

**User Story:** Como Cidadão, quero enviar relatos de desastre com descrição, gravidade e foto, para que os órgãos responsáveis e outros cidadãos tenham informações atualizadas.

#### Acceptance Criteria

1. WHEN um Cidadão envia um Relato, THE Aplicativo SHALL registrar a descrição textual, o Nível_de_Gravidade e a foto do Relato.
2. IF um Cidadão tenta enviar um Relato sem descrição textual, THEN THE Aplicativo SHALL rejeitar o Relato e exibir uma mensagem indicando que a descrição é obrigatória.
3. IF um Cidadão tenta enviar um Relato sem foto, THEN THE Aplicativo SHALL rejeitar o Relato e exibir uma mensagem indicando que a foto é obrigatória.
4. IF um Cidadão informa um Nível_de_Gravidade fora dos valores "baixo", "médio" e "alto", THEN THE Aplicativo SHALL rejeitar o Relato e exibir uma mensagem indicando os valores válidos.
5. WHEN um Relato é registrado com sucesso, THE Aplicativo SHALL associar ao Relato a localização geográfica e a data e hora do envio.
6. WHEN um Relato é registrado com sucesso, THE Aplicativo SHALL exibir ao Cidadão uma confirmação de recebimento.

### Requirement 5: Visualização de Relatos

**User Story:** Como Cidadão, quero visualizar os relatos enviados por outros cidadãos, para que eu possa conhecer a situação atual da minha região.

#### Acceptance Criteria

1. WHEN um Cidadão consulta os Relatos, THE Aplicativo SHALL exibir no Mapa a localização geográfica de cada Relato do Município selecionado.
2. WHEN um Relato é exibido, THE Aplicativo SHALL apresentar a descrição textual, o Nível_de_Gravidade e a foto do Relato.
3. WHERE um filtro por Nível_de_Gravidade está selecionado, THE Aplicativo SHALL exibir somente os Relatos que correspondem ao Nível_de_Gravidade selecionado.

### Requirement 6: Gestão de Informações pelos Órgãos Responsáveis

**User Story:** Como Órgão_Responsável, quero gerenciar áreas afetadas, abrigos e relatos, para que as informações apresentadas aos cidadãos sejam confiáveis e atualizadas.

#### Acceptance Criteria

1. WHEN um Órgão_Responsável cadastra uma Área_Afetada, THE Aplicativo SHALL registrar os limites geográficos e o Nível_de_Gravidade da Área_Afetada.
2. WHEN um Órgão_Responsável cadastra um Abrigo, THE Aplicativo SHALL registrar o nome, o endereço, a localização geográfica e a capacidade do Abrigo.
3. WHEN um Órgão_Responsável valida um Relato, THE Aplicativo SHALL marcar o Relato como validado e exibir a marcação aos Cidadãos.
4. IF um usuário sem perfil de Órgão_Responsável tenta cadastrar uma Área_Afetada ou um Abrigo, THEN THE Aplicativo SHALL negar a operação e exibir uma mensagem de acesso não autorizado.

### Requirement 7: Suporte a Múltiplos Municípios

**User Story:** Como Cidadão, quero selecionar o município de interesse, para que o aplicativo possa ser utilizado em Ribeirão Preto e expandido para outros municípios.

#### Acceptance Criteria

1. THE Aplicativo SHALL disponibilizar Ribeirão Preto como Município padrão.
2. WHEN um Cidadão seleciona um Município, THE Aplicativo SHALL exibir as Áreas_Afetadas, os Abrigos e os Relatos do Município selecionado.
3. WHERE um Município adicional está cadastrado, THE Aplicativo SHALL disponibilizar o Município adicional para seleção.

### Requirement 8: Restrição de Implementação

**User Story:** Como responsável técnico, quero que o aplicativo seja desenvolvido em Python, para que o projeto atenda à restrição técnica definida.

#### Acceptance Criteria

1. THE Aplicativo SHALL ser implementado na linguagem de programação Python.

### Requirement 9: Agrupamento de Relatos em Incidentes com Gravidade Média e Veracidade

**User Story:** Como Cidadão, quero que o mapa agrupe os relatos por incidente e apresente a gravidade média e a veracidade de cada incidente, para que eu possa avaliar rapidamente a severidade e a confiabilidade das ocorrências.

#### Acceptance Criteria

1. WHEN um Cidadão consulta os Relatos no Mapa, THE Aplicativo SHALL agrupar em um único Incidente os Relatos que se referem a uma mesma ocorrência de emergência.
2. WHEN o Aplicativo calcula a Gravidade_Média de um Incidente, THE Aplicativo SHALL converter o Nível_de_Gravidade de cada Relato associado no respectivo Valor_de_Gravidade, atribuindo 1 para "baixo", 2 para "médio" e 3 para "alto".
3. WHEN o Aplicativo calcula a Gravidade_Média de um Incidente, THE Aplicativo SHALL calcular a Gravidade_Média como a média aritmética dos Valores_de_Gravidade dos Relatos associados ao Incidente.
4. WHEN o Aplicativo determina a Veracidade de um Incidente, THE Aplicativo SHALL classificar a Veracidade com base na quantidade de Relatos associados ao Incidente, de forma que uma quantidade maior de Relatos resulte em uma Veracidade maior.
5. WHEN o Aplicativo determina a Veracidade de um Incidente, THE Aplicativo SHALL classificar a Veracidade como "baixa" para 1 ou 2 Relatos associados, "média" para 3 a 5 Relatos associados e "alta" para 6 ou mais Relatos associados.
6. WHEN um Incidente é exibido no Mapa, THE Aplicativo SHALL apresentar a Gravidade_Média e a Veracidade do Incidente.
7. WHEN um novo Relato é associado a um Incidente existente, THE Aplicativo SHALL recalcular a Gravidade_Média e a Veracidade do Incidente e refletir os valores atualizados no Mapa.
8. IF um Incidente não possui Relatos associados, THEN THE Aplicativo SHALL omitir o Incidente da exibição no Mapa.

### Requirement 10: Acesso à Interface Web Responsiva e Acessível

**User Story:** Como Cidadão, quero acessar o aplicativo por meio de uma página web responsiva, para que eu possa utilizá-lo em qualquer tipo de dispositivo por um navegador, sem instalar um aplicativo nativo.

#### Acceptance Criteria

1. WHEN um Cidadão acessa o endereço do Aplicativo em um Navegador_Web, THE Aplicativo SHALL disponibilizar a Interface_Web como uma página web.
2. THE Aplicativo SHALL disponibilizar todas as funcionalidades voltadas ao Cidadão por meio da Interface_Web, sem exigir a instalação de aplicativo nativo.
3. WHEN a Interface_Web é exibida em um Dispositivo, THE Aplicativo SHALL adaptar o layout da Interface_Web ao tamanho de tela do Dispositivo para larguras de tela entre 320 pixels e 1920 pixels.
4. THE Aplicativo SHALL disponibilizar a Interface_Web para acesso em Dispositivos do tipo desktop, notebook, tablet e smartphone.
5. THE Aplicativo SHALL disponibilizar a Interface_Web para acesso nas versões estáveis mais recentes dos Navegadores_Web Google Chrome, Mozilla Firefox, Microsoft Edge e Safari.
6. WHEN a Interface_Web é exibida, THE Aplicativo SHALL fornecer texto alternativo descritivo para cada elemento não textual apresentado na Interface_Web.
7. WHEN a Interface_Web é exibida, THE Aplicativo SHALL permitir a navegação por teclado entre os elementos interativos da Interface_Web.
8. IF o Navegador_Web do Cidadão não suporta um recurso necessário para exibir a Interface_Web, THEN THE Aplicativo SHALL exibir uma mensagem informando os Navegadores_Web compatíveis.

### Requirement 11: Sistema de Pedido de Ajuda com Filtro de Conteúdo

**User Story:** Como Cidadão, quero publicar um pedido de ajuda descrevendo minha situação durante uma crise, para que outros cidadãos e órgãos responsáveis possam me auxiliar, sem que o canal seja usado para golpes financeiros.

#### Acceptance Criteria

1. WHEN um Cidadão cria um Pedido_de_Ajuda, THE Aplicativo SHALL registrar a descrição textual da situação informada pelo Cidadão.
2. IF um Cidadão tenta publicar um Pedido_de_Ajuda sem descrição textual, THEN THE Aplicativo SHALL rejeitar o Pedido_de_Ajuda e exibir uma mensagem indicando que a descrição é obrigatória.
3. WHEN um Cidadão submete um Pedido_de_Ajuda, THE Filtro_de_Conteúdo SHALL verificar a presença de Termos_Bloqueados na descrição textual do Pedido_de_Ajuda.
4. WHEN o Filtro_de_Conteúdo compara a descrição textual com os Termos_Bloqueados, THE Filtro_de_Conteúdo SHALL realizar a correspondência sem diferenciar maiúsculas e minúsculas e sem diferenciar acentuação.
5. IF a descrição textual de um Pedido_de_Ajuda contém ao menos um Termo_Bloqueado, THEN THE Aplicativo SHALL rejeitar a publicação do Pedido_de_Ajuda e exibir uma mensagem informando que solicitações de pagamento não são permitidas por motivo de segurança.
6. WHEN um Pedido_de_Ajuda é publicado com sucesso, THE Aplicativo SHALL associar ao Pedido_de_Ajuda a localização geográfica e a data e hora da publicação.
7. WHEN um Pedido_de_Ajuda é publicado com sucesso, THE Aplicativo SHALL exibir ao Cidadão uma confirmação de publicação.
8. WHEN um Cidadão consulta os Pedidos_de_Ajuda, THE Aplicativo SHALL exibir os Pedidos_de_Ajuda publicados para o Município selecionado, apresentando a descrição textual, a localização geográfica e a data e hora de cada Pedido_de_Ajuda.
9. WHEN um Órgão_Responsável consulta os Pedidos_de_Ajuda, THE Aplicativo SHALL exibir os Pedidos_de_Ajuda publicados para o Município selecionado.

### Requirement 12: Representação por Cor dos Níveis de Gravidade no Mapa

**User Story:** Como Cidadão, quero que o mapa use cores para representar os níveis de gravidade, para que eu identifique visualmente e rapidamente a severidade das ocorrências.

#### Acceptance Criteria

1. WHEN o Mapa exibe um elemento com Nível_de_Gravidade "baixo", THE Aplicativo SHALL representá-lo com a Cor_de_Gravidade amarela.
2. WHEN o Mapa exibe um elemento com Nível_de_Gravidade "médio", THE Aplicativo SHALL representá-lo com a Cor_de_Gravidade laranja.
3. WHEN o Mapa exibe um elemento com Nível_de_Gravidade "alto", THE Aplicativo SHALL representá-lo com a Cor_de_Gravidade vermelha.
4. WHEN o Mapa exibe um Incidente com base na sua Gravidade_Média, THE Aplicativo SHALL mapear a Gravidade_Média para a Cor_de_Gravidade da seguinte forma: amarela para Gravidade_Média de 1,0 a 1,5; laranja para Gravidade_Média maior que 1,5 e até 2,5; vermelha para Gravidade_Média maior que 2,5 e até 3,0.
5. WHERE a Cor_de_Gravidade é utilizada no Mapa, THE Aplicativo SHALL apresentar uma legenda associando cada Cor_de_Gravidade ao respectivo Nível_de_Gravidade.

### Requirement 13: Hospedagem do Protótipo em Container no Amazon EC2

**User Story:** Como responsável técnico, quero que a aplicação web do protótipo seja executada em um container hospedado em uma instância Amazon EC2, para que o protótipo possa ser demonstrado de forma acessível pela internet durante a apresentação.

#### Acceptance Criteria

1. THE Aplicativo SHALL ser empacotado como um Container para execução do protótipo.
2. THE Aplicativo SHALL ser executado em um Container hospedado em uma Instância_EC2 para fins de apresentação do protótipo.
3. WHEN o Container do Aplicativo está em execução na Instância_EC2, THE Aplicativo SHALL disponibilizar a Interface_Web para acesso pela internet por meio de um Navegador_Web.

### Requirement 14: Conformidade da Interface Web com os Mockups de Referência

**User Story:** Como Cidadão, quero que a interface web reproduza fielmente os mockups de referência, para que eu tenha uma experiência visual consistente e reconhecível ao utilizar o Aplicativo.

#### Acceptance Criteria

1. THE Interface_Web SHALL implementar as quatro telas correspondentes aos Mockups_de_Referência: Início, Mapa, Ocorrência e Pedir ajuda.
2. THE Interface_Web SHALL replicar o Sistema_de_Design dos Mockups_de_Referência, utilizando a cor primária de ação #C9291C, o fundo de tela #EFEFEC, as superfícies em #DEDEDB, a cor de alerta #F6D9A6, a cor laranja #E8A028, a cor vermelha #C9291C e a cor verde #9DC48C.
3. THE Interface_Web SHALL utilizar a tipografia Helvetica Neue ou Arial, da família sans-serif, conforme os Mockups_de_Referência.
4. THE Interface_Web SHALL apresentar os botões em formato de pílula com raio de borda de 99 pixels e os cards com raio de borda entre 22 pixels e 28 pixels, conforme os Mockups_de_Referência.
5. THE Interface_Web SHALL exibir o nome do Aplicativo como "Refúgio".
6. THE Interface_Web SHALL manter os elementos interativos com altura mínima de 44 pixels, em conformidade com os Mockups_de_Referência.
7. WHERE a Cor_de_Gravidade é aplicada, THE Aplicativo SHALL utilizar as cores do Sistema_de_Design, representando o Nível_de_Gravidade "baixo" com a cor amarela, o Nível_de_Gravidade "médio" com a cor laranja #E8A028 e o Nível_de_Gravidade "alto" com a cor vermelha #C9291C, de forma consistente com os Mockups_de_Referência.

### Requirement 15: Sincronização Periódica com o Portal Brasileiro de Dados Abertos

**User Story:** Como Cidadão, quero que o aplicativo importe periodicamente incidentes do Portal Brasileiro de Dados Abertos, para que as informações exibidas sejam enriquecidas com dados públicos oficiais.

#### Acceptance Criteria

1. WHILE a Sincronização_de_Dados_Abertos está habilitada, THE Aplicativo SHALL executar a Sincronização_de_Dados_Abertos a cada 6 horas.
2. WHEN a Sincronização_de_Dados_Abertos é executada, THE Aplicativo SHALL requisitar ao Portal_de_Dados_Abertos os incidentes registrados.
3. WHEN o Aplicativo recebe incidentes do Portal_de_Dados_Abertos, THE Aplicativo SHALL acrescentar os incidentes como Incidentes_Externos aos dados do Aplicativo e disponibilizá-los junto aos Relatos no Mapa.
4. WHEN o Aplicativo importa um Incidente_Externo, THE Aplicativo SHALL registrar a origem do Incidente_Externo como Portal_de_Dados_Abertos.
5. IF um incidente recebido já foi importado anteriormente, THEN THE Aplicativo SHALL evitar a duplicação do registro com base no identificador e na origem do incidente.
6. IF o Portal_de_Dados_Abertos está indisponível ou a requisição falha, THEN THE Aplicativo SHALL manter os dados existentes, continuar operando e registrar a falha.
7. WHERE a Sincronização_de_Dados_Abertos está desabilitada por configuração, THE Aplicativo SHALL omitir as requisições ao Portal_de_Dados_Abertos.
