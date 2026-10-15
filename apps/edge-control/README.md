# Edge Control

Aplicativo Windows que junta, em uma interface, a configuração do DualSense
Edge e o overclock USB feito pelo hidusbf.

> Status: **overclock, status e teste de entradas implementados**. A seção
> **Perfis** está bloqueada até o protocolo do PlayStation Accessories ser
> analisado e validado (veja [Pendências](#pendências)).

## Estrutura

| Pasta                          | Conteúdo                                                                                                  |
| ------------------------------ | --------------------------------------------------------------------------------------------------------- |
| `src/EdgeControl.Core`         | Regras sem dependência do Windows: tabela de taxas, plano de mudança, bloqueios de segurança, parser HID. |
| `src/EdgeControl.Windows`      | SetupAPI, consultas ao hub USB, registro e HID (P/Invoke).                                                |
| `src/EdgeControl.App`          | Interface WPF (.NET 8) em português.                                                                      |
| `tests/EdgeControl.Core.Tests` | Testes xUnit das regras (rodam em qualquer SO).                                                           |
| `installer`                    | Script Inno Setup 6 e texto exibido no instalador.                                                        |

## Compilar

```powershell
cd apps/edge-control
dotnet test tests/EdgeControl.Core.Tests
dotnet publish src/EdgeControl.App -c Release -r win-x64 --self-contained true `
  -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true `
  -p:EnableCompressionInSingleFile=true -p:DebugType=none -o artifacts/publish
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" installer\EdgeControl.iss
```

O workflow `.github/workflows/edge-control.yml` executa esses passos em
`windows-latest` e publica `EdgeControl-Setup` como artefato.

## Engenharia reversa do hidusbf

Fonte analisada: `Setup.exe` do hidusbf (build Battle Beaver), PE32 Delphi,
SHA-256 `c461d2ce02873b39b18a399e0ea961ec02cf0bee2a09a7321f87641178d9e314`.
O arquivo contém apenas a interface de configuração. O driver
(`hidusbf.sys`, `.inf`, `SX64.EXE`) é distribuído à parte e **não** está
neste projeto.

### Observado no código de máquina

| Função no Setup            | Endereço             | Comportamento                                                                                                                                                                                                                     |
| -------------------------- | -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Ler taxa                   | `0x6610c`            | `SetupDiOpenDevRegKey(DICS_FLAG_GLOBAL, 0, DIREG_DRV, KEY_ALL_ACCESS)` e `RegQueryValueEx("bInterval")` (DWORD).                                                                                                                  |
| Gravar taxa                | `0x66184`            | Mesma chave: `RegSetValueEx("bInterval", REG_DWORD)`. O valor 0 (padrão) vira `RegDeleteValue`.                                                                                                                                   |
| Índice para valor          | `0x66244`            | High-Speed ou mais rápido: grava o próprio índice (1..6). Low/Full-Speed: grava a tabela `{0,1,2,4,8,16,32}` (ms) em `0x79a8c`.                                                                                                   |
| Rótulo da taxa             | `0x6628c`            | High-Speed: `8000 >> (bInterval-1)` Hz. Full-Speed: rótulos `Default,1000,500,250,125,62,31`.                                                                                                                                     |
| Ativar filtro              | `0x66834`, `0x66490` | Lê `LowerFilters`. Para ativar, insere `hidusbf` no início se ainda não houver; para desativar, remove todas as ocorrências (sem diferenciar maiúsculas). Grava com `SetupDiSetDeviceRegistryProperty(SPDRP_LOWERFILTERS)` no NT. |
| Reiniciar                  | `0x66998`            | `SP_PROPCHANGE_PARAMS{DIF_PROPERTYCHANGE, DICS_PROPCHANGE, DICS_FLAG_CONFIGSPECIFIC}` e `SetupDiCallClassInstaller`. Em x64 o Setup de 32 bits delega ao `SX64.EXE`; este app é 64 bits e chama diretamente.                      |
| Velocidade e pipes         | `0x659b0`, `0x65b60` | IOCTLs do hub `0x220408` (node info), `0x220420` (driver key por porta), `0x220448` (connection info EX), `0x22040c`, `0x22045c` (EX V2).                                                                                         |
| Controladoras reconhecidas | `0x79ae8`            | `USBXHCI, USBEHCI, USBUHCI, USBOHCI, UHCD, OPENHCI, IUSB3XHC, XHCDRV`. Fora dessa lista, o Setup avisa que o overclock pode não funcionar.                                                                                        |

### Inferido (validar no hardware)

- O filtro é aplicado ao nó USB ligado à porta do hub
  (`USB\VID_054C&PID_0DF2\<serial>`, o pai composto), que é o nó cujo
  driver key o hub informa. Se houver um filtro antigo num nó de interface
  (`&MI_xx`), o app avisa e não mexe nele.
- O DualSense Edge enumera como High-Speed. Nesse caso as opções são
  250/500/1000/2000/4000/8000 Hz. Se ele aparecer como Full-Speed, o máximo
  é 1000 Hz, igual ao Setup.

## Protocolo HID usado (somente leitura)

- Relatório de entrada `0x01` via USB (64 bytes): layout público do DualSense
  (`hid-playstation.c`). Os bits Fn e dos botões traseiros do Edge seguem o
  driver `hidapi` do SDL. A tela "Teste de entradas" serve para conferir.
- Relatório de feature `0x20` (GET): versão de firmware e hardware.
- O app **nunca** envia relatórios de saída nem `SET_FEATURE`.

## Barreiras de segurança

- Escreve apenas dois valores: `LowerFilters` do nó do Edge e `bInterval` na
  chave do driver dele, e só em um dispositivo que corresponda a
  `VID_054C&PID_0DF2`.
- Para aumentar a taxa, exige: driver hidusbf instalado e ativo, controle sem
  código de problema, velocidade USB conhecida e app rodando como administrador.
- Avisos que exigem confirmação explícita: taxa acima de 1000 Hz e
  controladora USB não reconhecida.
- Antes de gravar, salva um backup em `%ProgramData%\EdgeControl\backups`.
  Depois reinicia o controle e espera até 15 s. Se ele não voltar, restaura
  os valores anteriores sozinho.
- "Restaurar padrão" nunca é bloqueado.

## Pendências

1. **Perfis do Edge**: falta a pasta instalada do PlayStation Accessories para
   recuperar os comandos de leitura e gravação de perfis. Até lá, a seção não
   envia nada ao controle.
2. **Validação em hardware real**: nada aqui foi executado num PC com o
   controle. A interface foi compilada, mas não foi aberta em um Windows.
