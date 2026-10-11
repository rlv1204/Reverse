# Gree local para Windows

Cliente em Python que controla ar-condicionado Gree pela rede local usando o mesmo
protocolo do app **Gree+** (e do antigo **EWPE Smart**). Não depende da nuvem da Gree.

## Como o Gree+ funciona

O app fala com o aparelho por dois caminhos:

| Caminho | Quando é usado | Transporte |
|---|---|---|
| **Local (LAN)** | celular na mesma rede Wi-Fi do aparelho | UDP porta 7000, JSON + AES |
| **Nuvem** | celular fora de casa | servidores Gree (região escolhida no app), conta Gree+ |

Este projeto replica o caminho **local**. O fluxo é:

1. **Descoberta**: o app envia `{"t":"scan"}` em broadcast para UDP 7000. Cada módulo Wi-Fi
   responde com um `pack` criptografado contendo MAC, nome, modelo e versão do firmware.
2. **Bind (pareamento)**: o app envia `{"t":"bind","mac":...,"uid":0}` criptografado com uma
   **chave genérica** de fábrica. O aparelho responde `bindok` com uma **chave exclusiva** dele.
3. **Leitura**: `{"t":"status","cols":["Pow","Mod","SetTem",...]}` → resposta `dat` com valores.
4. **Comando**: `{"t":"cmd","opt":["Pow","SetTem"],"p":[1,23]}` → resposta `res`.

A criptografia depende da geração do firmware do módulo Wi-Fi:

| Versão | Algoritmo | Chave genérica |
|---|---|---|
| v1 (antigos) | AES-128-ECB, padding PKCS7, base64 | `a3K8Bx%2r8Y7#xDh` |
| v2 (recentes) | AES-128-GCM, nonce e AAD fixos, tag no campo `tag` | `{yxAHAY_Lm6pbC/<` |

O programa detecta a versão sozinho (tenta v1 e depois v2). A chave exclusiva de cada
aparelho fica salva em `%APPDATA%\gree-local\devices.json`.

### Principais parâmetros

| Código | Função | Valores |
|---|---|---|
| `Pow` | Liga/desliga | 0, 1 |
| `Mod` | Modo | 0 Auto, 1 Frio, 2 Desumidificar, 3 Ventilar, 4 Calor |
| `SetTem` | Temperatura alvo | 16–30 °C |
| `WdSpd` | Ventilador | 0 Auto, 1–5 (baixo → alto) |
| `SwUpDn` / `SwingLfRig` | Aletas vertical/horizontal | 0 padrão, 1 oscilar, 2–6 fixas |
| `Tur`, `Quiet`, `Lig`, `Blo`, `Health`, `SwhSlp`, `SvSt` | Turbo, silencioso, luz, X-Fan, ionizador, sono, economia | 0, 1 |
| `TemSen` | Temperatura ambiente (só leitura) | alguns firmwares somam 40 |

## Instalação no Windows (passo a passo)

Não precisa saber programar. Você vai fazer isso **uma única vez** e leva uns 10 minutos.
Use um computador ligado no **mesmo Wi-Fi** dos ar-condicionados.

### Passo 1: baixar os arquivos deste programa

1. Abra o navegador e entre no GitHub com a sua conta.
2. Acesse o repositório, escolha o branch `claude/gree-plus-windows-replication-gy70q9` e clique no
   botão verde **Code** e depois em **Download ZIP**.
3. Vá na pasta **Downloads**, clique com o botão direito no arquivo `.zip` e escolha
   **Extrair tudo...** e depois **Extrair**.
4. Dentro da pasta extraída, entre na pasta **`gree-windows`**. Ela deve ter os arquivos
   `gree.py`, `instalar.cmd` e `abrir-gree.cmd`.
   Dica: copie essa pasta para um lugar fácil, como **Documentos**.

### Passo 2: instalar o Python (o "motor" que roda o programa)

1. Acesse <https://www.python.org/downloads/> e clique no botão amarelo **Download Python**.
2. Abra o arquivo baixado.
3. **Muito importante:** na primeira tela, marque a caixinha
   **"Add python.exe to PATH"** (fica embaixo da janela).
4. Clique em **Install Now** e espere terminar. Clique em **Close**.

> Se o Windows perguntar "Deseja permitir que este aplicativo faça alterações?", clique em **Sim**.

### Passo 3: instalar o programa Gree

1. Na pasta `gree-windows`, dê **dois cliques** em **`instalar.cmd`**.
2. Se aparecer uma tela azul "O Windows protegeu o computador", clique em
   **Mais informações** e depois em **Executar assim mesmo**. Isso acontece com qualquer
   arquivo baixado da internet.
3. Uma janela preta vai mostrar alguns textos. Espere aparecer
   **"Pronto!"** e aperte qualquer tecla para fechar.

### Passo 4: abrir e encontrar os aparelhos

1. Dê **dois cliques** em **`abrir-gree.cmd`**. Vai abrir a janela **"Gree local"**.
2. Clique em **Procurar** e espere alguns segundos.
3. Se o Windows mostrar o aviso do **Firewall**, marque **Redes privadas** e clique em
   **Permitir acesso**. Sem isso o programa não consegue falar com os aparelhos.
   Se você permitiu só agora, clique em **Procurar** de novo.
4. Os aparelhos aparecem na lista **Aparelho**. Escolha um, ajuste **Ligado**, **Modo**,
   **Temperatura** e **Ventilador** e clique em **Aplicar**.

Nas próximas vezes, basta dar dois cliques em **`abrir-gree.cmd`**.
Para ter um atalho na área de trabalho, clique com o botão direito em `abrir-gree.cmd` e escolha
**Enviar para > Área de trabalho (criar atalho)**.

### Se algo der errado

| O que aconteceu | O que fazer |
|---|---|
| "O Python não foi encontrado" | Refaça o Passo 2 e confira se marcou **Add python.exe to PATH**. Depois reinicie o computador. |
| Clicou em **Procurar** e a lista ficou vazia | Confira se o computador está no mesmo Wi-Fi dos aparelhos (não use a rede de **convidados**). Confira o aviso do Firewall (Passo 4.3). |
| Lista vazia e você tem **dois roteadores** | Veja a seção [Rede com dois roteadores](#rede-com-dois-roteadores-operadora--tp-link). |
| Ainda vazia | Veja o IP e o MAC do aparelho no app Gree+ (configurações do aparelho) ou no roteador e use o comando `add` da seção abaixo. |
| A janela abre e fecha na hora | Rode `instalar.cmd` de novo e veja se aparece alguma mensagem de erro. |

## Rede com dois roteadores (operadora + TP-Link)

É comum ter esta montagem:

```
Roteador da operadora ──cabo──► Computador (desktop)
        │
        └──cabo──► Switch ──cabo──► Roteador TP-Link ──Wi-Fi──► Ar-condicionados
```

O programa precisa que o computador e os ar-condicionados estejam na **mesma rede**. Se o TP-Link
estiver como **roteador** (cabo ligado na porta azul **WAN/Internet**), ele cria uma segunda rede,
separada da primeira. O computador não enxerga os aparelhos, a busca volta vazia e não é defeito do
programa. O celular no Wi-Fi do TP-Link funciona porque fica do mesmo lado dos aparelhos.

### Como saber se é o seu caso

1. **IP do computador:** aperte **Windows + R**, digite `cmd` e Enter. Na janela preta, digite
   `ipconfig` e Enter. Anote o **Endereço IPv4** (exemplo: `192.168.1.15`).
2. **IP do ar-condicionado:** no app **Gree+**, abra o aparelho, toque em **⋯ / Configurações** e
   procure as informações do aparelho. Você também pode olhar a lista de dispositivos conectados
   no TP-Link (`http://tplinkwifi.net`). Exemplo: `192.168.0.104`.
3. **Compare os três primeiros números.** Se forem iguais (`192.168.1.x` e `192.168.1.y`), a rede
   já está certa. Se forem diferentes (`192.168.1.x` e `192.168.0.y`), são redes separadas: siga a
   solução abaixo.

### Solução recomendada: TP-Link em modo "Ponto de Acesso"

Nesse modo o TP-Link só distribui o Wi-Fi, e quem entrega os endereços é o roteador da operadora.
Tudo fica numa rede só. A internet continua funcionando igual, e o nome e a senha do Wi-Fi não mudam.

**TP-Link Archer mais novo (tem a opção "Modo de Operação"):**

1. No computador, abra o navegador e acesse `http://tplinkwifi.net`. Se não abrir, use o IP
   do TP-Link, como `http://192.168.0.1`. Entre com a senha de administrador do TP-Link.
2. Vá em **Avançado → Sistema → Modo de Operação** (em alguns modelos fica no topo da página).
3. Escolha **Ponto de Acesso (Access Point)** e clique em **Salvar**. O TP-Link reinicia.
4. Pode deixar o cabo na porta azul (WAN). No modo Ponto de Acesso ela vira porta comum.

**TP-Link sem a opção "Modo de Operação" (modelos mais antigos, ex.: TL-WR840N, TL-WR940N):**

1. Acesse `http://tplinkwifi.net` (ou `http://192.168.0.1`) e entre.
2. **Rede → LAN:** troque o IP do TP-Link para um endereço livre **na rede da operadora**. Se o
   computador é `192.168.1.15`, use por exemplo `192.168.1.250`. Salve; o TP-Link reinicia.
3. **DHCP → Configurações DHCP:** marque **Desativar** e salve.
4. **Mude o cabo** que vem do switch da porta azul **WAN** para uma das portas amarelas **LAN**.

**Depois de qualquer uma das duas opções:**

- Desligue e ligue os ar-condicionados no disjuntor (ou espere uns 10 minutos), para eles pegarem
  um IP novo da operadora.
- Repita o teste do `ipconfig`: agora os três primeiros números devem ser iguais.
- Abra o `abrir-gree.cmd` e clique em **Procurar**.
- O app Gree+ no celular continua funcionando; ele identifica o aparelho pelo MAC, não pelo IP.
- Para entrar de novo na configuração do TP-Link, use o IP que você definiu (ex.:
  `http://192.168.1.250`) ou procure o TP-Link na lista de dispositivos do roteador da operadora.

### Alternativa (sem mexer no modo do TP-Link): redirecionar portas

Se não puder mudar o TP-Link, dá para abrir uma porta para cada aparelho:

1. No TP-Link, reserve IP fixo para cada ar-condicionado (**DHCP → Reserva de endereço**).
2. Em **NAT / Encaminhamento → Servidores Virtuais**, crie uma regra por aparelho, protocolo **UDP**:
   porta externa `7000` → IP do 1º aparelho, porta interna `7000`; porta externa `7001` → IP do
   2º aparelho, porta interna `7000`; e assim por diante.
3. Descubra o IP do TP-Link na rede da operadora (porta WAN, em **Status**), ex.: `192.168.1.20`.
4. No computador, cadastre cada aparelho pelo IP do TP-Link, com a porta e o MAC dele:

   ```powershell
   py gree.py add 192.168.1.20 f4911e123456 --port 7000 --name Sala
   py gree.py add 192.168.1.20 f4911e654321 --port 7001 --name Quarto
   ```

Nesse modo o botão **Procurar** não encontra os aparelhos, mas o controle funciona depois do
cadastro. O MAC aparece no Gree+ ou na lista de dispositivos do TP-Link.

## Uso avançado (linha de comando)

Abra a pasta `gree-windows`, clique na barra de endereço do Explorer, digite `powershell` e
aperte Enter. Na janela que abrir:

```powershell
py gree.py scan                         # descobre e pareia os aparelhos
py gree.py rename f4911e123456 Sala      # nome amigável
py gree.py status Sala
py gree.py set Sala Pow=1 Mod=1 SetTem=23 WdSpd=0
py gree.py set Sala Pow=0
py gree.py gui                          # mesma janela do abrir-gree.cmd
```

Se o broadcast não achar nada, por exemplo com roteador mesh ou rede de convidados, use o
broadcast da sua sub-rede (`py gree.py scan --broadcast 192.168.0.255`) ou cadastre o aparelho
direto pelo IP e MAC:

```powershell
py gree.py add 192.168.0.50 f4911e123456 --name Quarto
```

Dica: reserve IP fixo (DHCP reservation) para os aparelhos no roteador.

## Limitações

- Só funciona na **mesma rede local** do aparelho. Para controle remoto, use VPN para casa
  (WireGuard/Tailscale) ou o próprio Gree+.
- Não usa a nuvem nem a conta Gree+. O app do celular continua funcionando normalmente.
- Alguns módulos muito recentes foram relatados com o controle local desativado de fábrica.
  Nesses casos o `scan` responde, mas o `bind` falha.
- Multi-split/VRF com subunidades não é tratado aqui (exige endereçar cada subunidade).

## Testes

`python -m unittest test_gree` sobe um aparelho simulado em `127.0.0.1:7000` e valida
descoberta, bind, status e comando nas duas cifras.
