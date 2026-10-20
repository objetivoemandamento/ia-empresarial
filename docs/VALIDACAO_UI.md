# Validação visual e simulador

O arquivo enviado `chatgpt-apps-sdk-devtools` declara `react ^18` e `react-dom ^18` como peer dependencies. A aplicação atual do repositório usa React 19. Não forcei a instalação do DevTools dentro do frontend principal porque isso introduziria um conflito de peer dependencies ou exigiria downgrade de React sem validação de regressão.

Como validação executável, o CI usa Playwright/Chromium para navegar pelas abas Escritório, Agentes IA, Permissões e Conexões em desktop e viewport móvel. O job captura screenshots e traces em artefatos do GitHub Actions quando os testes executam.

Para usar o SDK DevTools diretamente, primeiro escolha uma das opções:
1. atualizar/validar uma versão do DevTools compatível com React 19; ou
2. testar o downgrade do app para React 18.3.1 em branch isolada, com build e regressão completos.

Não declarar o SDK DevTools conectado enquanto essa compatibilidade não estiver resolvida. Playwright verifica a interface do aplicativo real; ele não comprova chamadas reais a modelos ou execução de ferramentas externas.
