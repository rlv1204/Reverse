# Clima Casa — controle dos ares-condicionados pelo computador

Programa para Windows que liga, desliga e ajusta os ares-condicionados da casa:

| Aparelho | Nome | Como o programa conversa com ele |
| --- | --- | --- |
| Gree (app Gree+) | **Ângelo** — MAC `9424b883c954` | Direto pela rede Wi-Fi da casa |
| Gree (app Gree+) | **Escritório** — MAC `9424b883d28b` | Direto pela rede Wi-Fi da casa |
| LG (app LG ThinQ) | (nome que está no app LG) | Pela API oficial da LG, via internet |

Em cada aparelho dá para controlar: ligar/desligar, temperatura (16 a 30 °C), modo
(Frio, Seco, Ventilar, Auto, Calor), velocidade do vento, direção do vento e funções
extras (Turbo, Sono, Silencioso, Luz do painel etc.). A tela também mostra a
temperatura do ambiente (e a umidade, quando o aparelho informa).

Os aplicativos do celular (Gree+ e LG ThinQ) **continuam funcionando normalmente**.
Os dois podem ser usados ao mesmo tempo que o Clima Casa.

---

## Passo 1 — Baixar o programa

1. Baixe o arquivo **clima-casa.zip** (enviado na conversa) ou, no GitHub, a pasta
   `clima-casa` do repositório.
2. Clique com o botão direito no arquivo `.zip` → **Extrair tudo…** → **Extrair**.
3. Mova a pasta `clima-casa` para um lugar fixo, por exemplo **Documentos**.
   O atalho criado no próximo passo aponta para essa pasta; se mudar a pasta de
   lugar depois, rode o `INSTALAR.bat` de novo.

## Passo 2 — Instalar

1. Abra a pasta `clima-casa` e dê **dois cliques em `INSTALAR.bat`**.
2. Se aparecer a tela azul **"O Windows protegeu o computador"**: clique em
   **Mais informações** → **Executar assim mesmo**. (Isso aparece para qualquer
   arquivo baixado da internet que não seja de uma loja.)
3. O instalador faz três coisas sozinho:
   - **instala o Python** (o "motor" do programa), se ainda não estiver instalado.
     Se o Windows pedir permissão, clique em **Sim**;
   - cria o atalho **Clima Casa** na Área de Trabalho e no Menu Iniciar;
   - procura os aparelhos Gree na rede e mostra quais encontrou.
4. Se aparecer o aviso do **Firewall do Windows** perguntando sobre o "Python":
   marque **Redes privadas** e clique em **Permitir acesso**. Sem isso o
   computador não consegue ouvir as respostas dos aparelhos Gree.
5. Quando aparecer **"Pronto!"**, aperte qualquer tecla para fechar.

### Passo 2 — plano B (só se o instalador não conseguir instalar o Python)

1. Acesse <https://www.python.org/downloads/> e clique em **Download Python 3.12**
   (ou a versão mais nova).
2. Abra o arquivo baixado. **Importante:** na primeira tela marque a caixa
   **"Add python.exe to PATH"** e clique em **Install Now**.
3. Depois rode o `INSTALAR.bat` de novo.

## Passo 3 — Abrir o programa

Dê dois cliques no atalho **Clima Casa** da Área de Trabalho (ou procure
"Clima Casa" no Menu Iniciar). Abre uma janela parecida com esta:

```
 [Ângelo] [Escritório] [LG]          ← um botão para cada aparelho
 Ângelo                      (⏻)     ← liga / desliga
 🌡 23°  💧 61%                       ← temperatura e umidade do ambiente
        [ desenho do aparelho ]
   (−)        24 °C        (+)       ← temperatura desejada
   ──────────●───────────            ← ou arraste a barrinha
 [Frio][Seco][Ventilar][Auto][Calor] ← modo
 [Vento: Médio ▾] [Direção: Ambas ▾]
 [Turbo] [Sono] [Silencioso] ...     ← funções extras (azul = ligada)
 🛡 Conectado pela rede local    ⚙   ← configurações
```

- Para **fechar**, basta fechar a janela. O programa encerra sozinho cerca de
  2 minutos depois.
- Dica: para deixar o programa sempre à mão, clique com o botão direito no
  atalho → **Mostrar mais opções** → **Fixar na barra de tarefas**.
- Atalhos de teclado: setas **↑** e **↓** sobem e descem a temperatura.

## Passo 4 — Aparelhos Gree (Ângelo e Escritório)

Na primeira vez que o programa abre, ele procura os aparelhos Gree sozinho e
eles aparecem com os nomes **Ângelo** e **Escritório**.

Se não aparecerem:

1. Confira se o computador está ligado no **mesmo roteador/Wi-Fi** dos aparelhos
   (não pode ser a rede de "visitantes").
2. Clique no ícone **⚙ (Configurações)**, no canto inferior direito, e depois em
   **Procurar aparelhos Gree**.
3. Ainda não apareceu? Descubra o IP do aparelho na página do seu roteador
   (lista de "dispositivos conectados"; procure pelos MACs `94:24:b8:83:c9:54` e
   `94:24:b8:83:d2:8b`), digite o IP no campo **"IP (opcional)"** e clique em
   **Adicionar**.

> Sobre a **atualização de firmware** que o app Gree+ está oferecendo (a bolinha
> vermelha): não é necessária para o Clima Casa. Se você atualizar, o programa
> detecta sozinho o novo tipo de criptografia dos aparelhos.

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
| "Nenhum aparelho Gree respondeu" | Computador e aparelhos no mesmo Wi-Fi? Ar-condicionado ligado na tomada? Permitiu o Python no Firewall (Passo 2, item 4)? Se não permitiu: Menu Iniciar → "Firewall do Windows Defender" → "Permitir um aplicativo…" → marque **Python** em **Privada**. |
| "Aparelho sem resposta na rede local" | O aparelho pode ter sido desligado da tomada ou trocado de IP. O programa procura de novo sozinho em até 1 minuto. |
| "Token da LG inválido" | Gere um novo token (Passo 5) e cole de novo. |
| "Ligue o aparelho antes de alterar esta opção" | O LG não aceita mudar o modo com o aparelho desligado. Ligue primeiro. |
| "Muitos pedidos à LG em pouco tempo" | A LG limita os pedidos. Espere um minuto. |
| "O ar-condicionado LG está desconectado da internet" | Abra o app LG ThinQ e confira se o aparelho aparece como conectado. |
| A janela não abre | Dê dois cliques em `ABRIR-CLIMA-CASA.bat` dentro da pasta. Se nada acontecer, rode o `INSTALAR.bat` de novo e leia as mensagens. |
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

1. Apague a pasta `clima-casa`.
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
`WdSpd` (0 auto … 5 alto), `SwUpDn`/`SwingLfRig` (oscilação vertical/horizontal),
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
├── INSTALAR.bat            instala o Python (se faltar) e cria o atalho
├── ABRIR-CLIMA-CASA.bat    abre o programa sem o atalho
├── LEIA-ME.md              este guia
├── climacasa/
│   ├── __main__.py         início: abre a janela e o servidor local
│   ├── gree.py             protocolo local dos aparelhos Gree
│   ├── lg.py               API LG ThinQ Connect
│   ├── aes.py              criptografia AES (sem bibliotecas externas)
│   ├── devices.py          junta Gree e LG num formato único para a tela
│   ├── server.py           servidor local (só 127.0.0.1) que serve a tela
│   ├── config.py           configurações salvas
│   ├── instalar.py         cria atalhos e ícone no Windows
│   └── web/                a tela (HTML, CSS e JavaScript)
└── testes/                 testes automáticos e simuladores dos aparelhos
```

O programa não precisa de nenhuma biblioteca além do próprio Python.
Para rodar os testes: `python -m unittest discover -s testes`.
Para ver a tela com aparelhos simulados: `python testes/simuladores.py` e abra
o endereço mostrado.
