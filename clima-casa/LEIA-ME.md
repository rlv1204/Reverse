# Clima Casa — controle dos ares-condicionados pelo computador

Programa para Windows que liga, desliga e ajusta os ares-condicionados da casa:

| Aparelho | Nome | Como o programa conversa com ele |
| --- | --- | --- |
| Gree (app Gree+) | **Ângelo** — MAC `9424b883c954` | Direto pela rede da casa (sem internet) |
| Gree (app Gree+) | **Escritório** — MAC `9424b883d28b` | Direto pela rede da casa (sem internet) |
| LG (app LG ThinQ) | (nome que está no app LG) | Pela API oficial da LG, via internet |

Em cada aparelho dá para controlar: ligar/desligar, temperatura (16 a 30 °C), modo
(Frio, Seco, Ventilar, Auto, Calor), velocidade do vento, **posição das aletas**
(nos Gree: Auto, Oscilar ou posições fixas 1 a 5, como no app Gree+) e funções
extras (Turbo, Sono, Silencioso, Luz do painel etc.). A tela também mostra a
temperatura do ambiente (e a umidade, quando o aparelho informa).

Funciona com o computador ligado **por cabo de rede** (sem Wi-Fi) — veja a seção
[Computador ligado por cabo](#computador-ligado-por-cabo-de-rede).

Os aplicativos do celular (Gree+ e LG ThinQ) **continuam funcionando normalmente**.
Os dois podem ser usados ao mesmo tempo que o Clima Casa.

---

## Passo 1 — Baixar o programa

1. Baixe o arquivo **clima-casa.zip** (enviado na conversa) ou, no GitHub, a pasta
   `clima-casa` do repositório.
2. Clique com o botão direito no arquivo `.zip` → **Extrair tudo…** → **Extrair**.

O instalador copia o programa para a pasta
`%LOCALAPPDATA%\Programs\ClimaCasa`. Depois de instalar, a pasta extraída do
zip pode ser apagada.

## Passo 2 — Instalar

1. Abra a pasta `clima-casa` e dê **dois cliques em `INSTALAR.bat`**.
2. Se aparecer a tela azul **"O Windows protegeu o computador"**: clique em
   **Mais informações** → **Executar assim mesmo**. (Isso aparece para qualquer
   arquivo baixado da internet que não seja de uma loja.)
3. O instalador faz três coisas sozinho:
   - **instala o Python** (o "motor" do programa), se ainda não estiver instalado.
     Se o Windows pedir permissão, clique em **Sim**;
   - copia o programa para a pasta de instalação — **se já houver uma versão
     anterior, ela é substituída automaticamente** (não precisa apagar nada antes;
     seus aparelhos, nomes e o token da LG continuam salvos);
   - cria o atalho **Clima Casa** na Área de Trabalho e no Menu Iniciar;
   - procura os aparelhos Gree na rede e mostra quais encontrou.
4. Se aparecer o aviso do **Firewall do Windows** perguntando sobre o "Python":
   marque **Redes privadas** e clique em **Permitir acesso**. Sem isso o
   computador não consegue ouvir as respostas dos aparelhos Gree.
5. Quando aparecer **"Pronto!"**, o programa abre sozinho. Aperte qualquer tecla
   para fechar a janela preta do instalador.

### Passo 2 — plano B (só se o instalador não conseguir instalar o Python)

1. Acesse <https://www.python.org/downloads/> e clique em **Download Python 3.12**
   (ou a versão mais nova).
2. Abra o arquivo baixado. **Importante:** na primeira tela marque a caixa
   **"Add python.exe to PATH"** e clique em **Install Now**.
3. Depois rode o `INSTALAR.bat` de novo.

## Passo 3 — Abrir o programa

Dê dois cliques no atalho **Clima Casa** da Área de Trabalho (ou procure
"Clima Casa" no Menu Iniciar). A janela tem, de cima para baixo:

| Parte da tela | Para que serve |
| --- | --- |
| **Cartões dos aparelhos** (Ângelo, Escritório, LG) | Escolher qual aparelho controlar. Cada cartão mostra a temperatura do ambiente e se está ligado (bolinha verde). |
| **Mostrador redondo** | Temperatura desejada. Arraste a bolinha pelo arco, use os botões **−** e **+** ou as setas **↑ ↓** do teclado. Embaixo do número aparecem a temperatura e a umidade do ambiente. |
| **Botão redondo azul** (canto do mostrador) | Liga e desliga o aparelho. |
| **Modo** | Frio, Seco, Ventilar, Auto e Calor. As cores da tela acompanham o modo (azul = frio, laranja = calor…). |
| **Ventilação** | Auto ou velocidades de 1 a 5 (Baixo → Alto). |
| **Aletas** | Direção do ar na vertical: **Auto**, **Oscilar** ou **posições fixas 1 a 5** (1 = mais horizontal, 5 = mais para baixo) — as mesmas "Direç.1" a "Direç.5" do app Gree+. |
| **Funções** | Turbo, Sono, Silencioso, Luz do painel, Saúde, X-Fan e Economia. Em destaque = ligada. |
| **⚙ (canto superior direito)** | Configurações: procurar aparelhos, conta LG, nomes, tema claro/escuro e atualizações. |

- **Pode deixar a janela aberta o tempo que quiser**, mesmo parada ou
  minimizada: a conexão é mantida. Se o programa ficar fora do ar por algum
  motivo, aparece **"Reconectando…"** no topo e ele volta sozinho.
- Para **fechar**, basta fechar a janela; o programa encerra uns 15 segundos
  depois.
- **Tema:** ⚙ → Aparência → Automático (segue o Windows), Claro ou Escuro.
- Dica: para deixar o programa sempre à mão, clique com o botão direito no
  atalho → **Mostrar mais opções** → **Fixar na barra de tarefas**.

### Aletas no aparelho LG

O acesso oficial da LG (ThinQ Connect) só permite **ligar ou desligar a
oscilação** (vertical e, se o modelo tiver, horizontal). As posições fixas de
ângulo não fazem parte desse acesso — no LG elas só podem ser escolhidas no
controle remoto ou no app LG ThinQ.

## Atualizações

Quando houver uma versão nova, aparece uma faixa azul no topo da janela:
**"Nova versão X disponível — Atualizar"**. Clique em **Atualizar** e confirme.
O programa baixa a versão nova, confere se os arquivos chegaram inteiros,
substitui os antigos e reinicia sozinho em alguns segundos. Nada precisa ser
apagado ou desinstalado, e suas configurações são mantidas.

- O programa verifica sozinho a cada 6 horas. Para verificar na hora:
  ⚙ → **Atualizações** → **Verificar agora**.
- Também dá para atualizar "à moda antiga": baixe o zip novo, extraia e rode o
  `INSTALAR.bat`. Ele fecha o programa aberto e substitui a versão anterior.

> **Vindo da versão 1.0?** Ela ainda não sabia se atualizar sozinha. Desta vez,
> baixe o zip novo e rode o `INSTALAR.bat` (passo 2). A partir da 1.1 as
> atualizações são feitas pela própria janela. A pasta da versão 1.0 pode ser
> apagada depois.

## Passo 4 — Aparelhos Gree (Ângelo e Escritório)

Na primeira vez que o programa abre, ele procura os aparelhos Gree sozinho e
eles aparecem com os nomes **Ângelo** e **Escritório**.

Se não aparecerem:

1. Confira se o cabo de rede do computador está ligado no **mesmo roteador** que
   fornece o Wi-Fi dos aparelhos (veja a seção
   [Computador ligado por cabo](#computador-ligado-por-cabo-de-rede)).
2. Clique no ícone **⚙ (Configurações)**, no canto inferior direito, e depois em
   **Procurar aparelhos Gree**.
3. Ainda não apareceu? Descubra o IP do aparelho na página do seu roteador
   (lista de "dispositivos conectados"; procure pelos MACs `94:24:b8:83:c9:54` e
   `94:24:b8:83:d2:8b`), digite o IP no campo **"IP (opcional)"** e clique em
   **Adicionar**.

> Sobre a **atualização de firmware** que o app Gree+ está oferecendo (a bolinha
> vermelha): não é necessária para o Clima Casa. Se você atualizar, o programa
> detecta sozinho o novo tipo de criptografia dos aparelhos.

## Computador ligado por cabo de rede

Não é preciso ter Wi-Fi no computador. Os aparelhos Gree ficam no Wi-Fi, o
computador fica no cabo, e o **roteador liga os dois** — desde que o cabo esteja
no **mesmo roteador** que transmite o Wi-Fi dos aparelhos (ou num switch/ponto
de rede que vá até ele). O aparelho LG não depende disso, pois é controlado pela
internet.

**Como conferir se estão na mesma rede** (só se os Gree não forem encontrados):

1. Rode o `INSTALAR.bat`. Ele mostra o endereço do computador, por exemplo
   `Endereço(s) deste computador na rede: 192.168.0.15`.
2. No celular, ligado no Wi-Fi da casa, veja o endereço IP dele:
   iPhone: **Ajustes → Wi-Fi → (i)** ao lado da rede → **Endereço IP**.
   Android: **Configurações → Wi-Fi → engrenagem** da rede → **Avançado**.
3. Compare os **três primeiros números**. Exemplo: `192.168.0.15` (computador) e
   `192.168.0.42` (celular) → mesma rede, tudo certo.
   Se forem diferentes (ex.: `192.168.1.15` e `192.168.0.42`), há **dois
   roteadores** na casa (comum quando a operadora instala um modem e há outro
   roteador de Wi-Fi). Soluções, da mais simples para a mais trabalhosa:
   - ligue o cabo do computador numa porta do **roteador do Wi-Fi**; ou
   - digite o IP do aparelho em **⚙ Configurações → IP (opcional) → Adicionar**
     (o IP aparece na lista de dispositivos do roteador do Wi-Fi); ou
   - peça para colocar o segundo roteador em modo **"bridge"/"ponto de acesso"**.

**Tipo de rede do Windows.** O Windows às vezes classifica a conexão por cabo
como **Pública**, o que faz o Firewall bloquear os aparelhos. O `INSTALAR.bat`
mostra o tipo da rede. Se aparecer "rede Pública":
**Configurações → Rede e Internet → Ethernet → Tipo de perfil de rede →
Rede privada**.

**VPN.** Se o computador usa VPN (por exemplo, do trabalho), desligue-a ao usar
o Clima Casa: muitas VPNs bloqueiam o acesso à rede da casa.

## Passo 5 — Aparelho LG (LG ThinQ)

A LG oferece um acesso oficial para programas como este. Você só precisa gerar
uma "chave" (token) uma única vez:

1. No computador, acesse **<https://connect-pat.lgthinq.com>**.
2. Clique em **Login** e entre com **a mesma conta do app LG ThinQ** (mesmo
   e-mail/Google/Apple que você usa no celular).
3. Clique em **ADD NEW TOKEN** (Criar novo token).
4. Em **Token name** escreva `Clima Casa`.
5. Em **Select authorized scopes** (permissões), **marque todas as opções**
   (lista de aparelhos, estado e controle dos aparelhos etc.).
6. Clique em **CREATE TOKEN**. Vai aparecer o token na lista — um texto longo,
   normalmente começando com `thinqpat_`. Copie esse texto (botão de copiar ao
   lado dele, ou selecione e aperte **Ctrl+C**).
7. No Clima Casa, clique em **⚙ (Configurações)** → cole o token no campo
   **"Cole aqui o token…"** (Ctrl+V) → confira se o país é **Brasil** → clique
   em **Salvar e testar**.
8. Deve aparecer **"Conectado! 1 ar-condicionado(s) LG encontrado(s)."**

O token fica salvo só no seu computador. Se um dia ele parar de funcionar, gere
outro no mesmo site e cole de novo.

## Problemas comuns

| O que aparece | O que fazer |
| --- | --- |
| "Nenhum aparelho Gree respondeu" | Cabo do computador no mesmo roteador do Wi-Fi dos aparelhos (seção "Computador ligado por cabo")? Rede do Windows como **Privada**? VPN desligada? Ar-condicionado ligado na tomada? Permitiu o Python no Firewall (Passo 2, item 4)? Se não permitiu: Menu Iniciar → "Firewall do Windows Defender" → "Permitir um aplicativo…" → marque **Python** em **Privada**. |
| "Aparelho sem resposta na rede local" | O aparelho pode ter sido desligado da tomada ou trocado de IP. O programa procura de novo sozinho em até 1 minuto. |
| "Token da LG inválido" | Gere um novo token (Passo 5) e cole de novo. |
| "Ligue o aparelho antes de alterar esta opção" | O LG não aceita mudar o modo com o aparelho desligado. Ligue primeiro. |
| "Muitos pedidos à LG em pouco tempo" | A LG limita os pedidos. Espere um minuto. |
| "O ar-condicionado LG está desconectado da internet" | Abra o app LG ThinQ e confira se o aparelho aparece como conectado. |
| A janela não abre | Rode o `INSTALAR.bat` de novo e leia as mensagens. Erros ficam registrados em `%APPDATA%\ClimaCasa\clima-casa.log`. |
| "Reconectando…" não some | Feche a janela e abra pelo atalho de novo. |
| "Não foi possível verificar" (atualizações) | O computador está sem internet ou o GitHub está fora do ar. Tente mais tarde; o programa continua funcionando normalmente. |
| Quero fechar o programa na hora | ⚙ Configurações → **Encerrar o programa**. |

## Privacidade e segurança

- Os aparelhos **Gree** são controlados **só dentro da sua casa**, pela rede local.
  Nada passa pela internet.
- O aparelho **LG** é controlado pela API oficial da LG
  (`api-aic.lgthinq.com`), usando o token que você gerou.
- As configurações (inclusive o token da LG) ficam em
  `%APPDATA%\ClimaCasa\config.json` — só no seu computador.
- A janela do programa só aceita comandos do próprio computador; outros sites
  abertos no navegador não conseguem mexer nos aparelhos.

## Desinstalar

1. Feche o programa e apague a pasta `%LOCALAPPDATA%\Programs\ClimaCasa`
   (cole esse endereço na barra do Explorador de Arquivos).
2. Apague o atalho **Clima Casa** da Área de Trabalho.
3. (Opcional) Apague a pasta `%APPDATA%\ClimaCasa` — cole esse endereço na barra
   do Explorador de Arquivos para encontrá-la.

---

## Para quem tiver curiosidade: como o programa funciona

### Gree (mesmo protocolo do app Gree+)

O módulo Wi-Fi dos aparelhos Gree escuta na **porta UDP 7000** da rede local e
troca mensagens em JSON criptografadas com AES-128:

1. **Descoberta** — o programa envia `{"t":"scan"}` para a rede; cada aparelho
   responde com seu MAC, nome e versão de firmware.
2. **Pareamento** — o programa pede a chave do aparelho (`{"t":"bind"}`); a
   resposta `bindok` traz uma chave própria de 16 caracteres, guardada na
   configuração.
3. **Leitura** — `{"t":"status","cols":["Pow","Mod","SetTem",...]}` devolve os
   valores atuais (ligado, modo, temperatura, ventilação…).
4. **Comando** — `{"t":"cmd","opt":["Pow","SetTem"],"p":[1,24]}` altera os valores.

Há duas gerações de criptografia: **AES-ECB** (firmware antigo, chave genérica
`a3K8Bx%2r8Y7#xDh`) e **AES-GCM** (firmware novo, chave genérica
`{yxAHAY_Lm6pbC/<`). O programa detecta qual o aparelho usa.

Principais propriedades: `Pow` (liga), `Mod` (0 auto, 1 frio, 2 seco,
3 ventilar, 4 calor), `SetTem` (°C), `TemSen` (sensor, com +40 de deslocamento),
`WdSpd` (0 auto … 5 alto), `SwUpDn` (aleta vertical: 0 auto, 1 oscilar, 2 a 6 = posições fixas 1 a 5), `SwingLfRig` (aleta horizontal),
`Tur` (turbo), `Quiet`, `SwhSlp` (sono), `Lig` (luz), `Health`, `Blo` (X-Fan),
`SvSt` (economia).

### LG (API oficial LG ThinQ Connect)

O programa usa a API pública da LG (a mesma da biblioteca oficial
`thinqconnect`): `GET /devices` lista os aparelhos, `GET /devices/{id}/profile`
diz o que cada um aceita (modos, faixas de temperatura, velocidades),
`GET /devices/{id}/state` traz o estado e `POST /devices/{id}/control` envia
comandos como `{"operation":{"airConOperationMode":"POWER_ON"}}`. Como as
opções vêm do perfil do próprio aparelho, a tela só mostra o que o seu modelo
realmente suporta.

### Estrutura dos arquivos

```
clima-casa/
├── INSTALAR.bat            instala o Python (se faltar), instala/atualiza o programa e cria o atalho
├── ABRIR-CLIMA-CASA.bat    abre o programa sem o atalho
├── LEIA-ME.md              este guia
├── versao.json             número da versão e impressão digital (SHA-256) de cada arquivo
├── climacasa/
│   ├── __main__.py         início: abre a janela e o servidor local
│   ├── gree.py             protocolo local dos aparelhos Gree
│   ├── lg.py               API LG ThinQ Connect
│   ├── aes.py              criptografia AES (sem bibliotecas externas)
│   ├── devices.py          junta Gree e LG num formato único para a tela
│   ├── server.py           servidor local (só 127.0.0.1) que serve a tela
│   ├── config.py           configurações salvas
│   ├── instalar.py         copia o programa para a pasta de instalação e cria os atalhos
│   ├── atualizar.py        atualização pela janela (baixa, confere e substitui os arquivos)
│   ├── instancia.py        localiza/encerra a cópia aberta do programa
│   └── web/                a tela (HTML, CSS e JavaScript)
└── testes/                 testes automáticos e simuladores dos aparelhos
```

O programa não precisa de nenhuma biblioteca além do próprio Python.
Para rodar os testes: `python -m unittest discover -s testes`.
Para ver a tela com aparelhos simulados: `python testes/simuladores.py` e abra
o endereço mostrado.
