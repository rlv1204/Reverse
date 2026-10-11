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

## Instalação no Windows

1. Instale o Python 3.10+ em <https://www.python.org/downloads/windows/> (marque "Add python.exe to PATH").
2. Abra o PowerShell nesta pasta e rode:

   ```powershell
   py -m pip install -r requirements.txt
   ```
3. Na primeira execução, o Firewall do Windows pode perguntar sobre o Python: permita em **Redes privadas**.

## Uso

```powershell
py gree.py scan                         # descobre e pareia os aparelhos
py gree.py rename f4911e123456 Sala      # nome amigável
py gree.py status Sala
py gree.py set Sala Pow=1 Mod=1 SetTem=23 WdSpd=0
py gree.py set Sala Pow=0
py gree.py gui                          # janela com liga/desliga, modo, temperatura, ventilador
```

Se o broadcast não achar nada, por exemplo com roteador mesh ou rede de convidados, use o
broadcast da sua sub-rede (`py gree.py scan --broadcast 192.168.0.255`) ou cadastre o aparelho
direto pelo IP e MAC, que aparecem no roteador ou no Gree+ em *Configurações do aparelho*:

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
