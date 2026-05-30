## Objetivo

Reestilizar a página `/consulta` para imitar o layout do iClinic da referência: topbar, sidebar esquerda com timer + botão de atendimento, e área principal com card de cabeçalho do paciente e timeline de atendimentos. Mantém toda a lógica de gravação/envio que já existe; muda apenas a apresentação.

## Mudanças

### 1. `src/routes/-consulta-page.tsx` (reestrutura visual)

Manter intactos: `PACIENTE`, estados (`status`, `elapsed`), refs, `handleIniciar`, `handleFinalizar`, cleanup, chamada à server function `enviarConsulta`. Trocar apenas o JSX e adicionar campos mockados de apoio.

Novo mock estendido (constante no topo):
```ts
const PACIENTE = {
  nome: "Pedro Henrique Alves",
  nascimento: "15/05/2002",
  idade: "23 anos",
  primeiraConsulta: "29/10/2017",
  convenio: "Unimed",
  atendimentos: 2,
  faltas: 0,
  iniciais: "PA",
};
```

Estrutura (Tailwind, tokens semânticos):

```text
<main min-h-screen bg-muted/40>
  ├─ Topbar (h-14, bg-primary, text-primary-foreground)
  │   ├─ Logo "Prontuário" (esquerda)
  │   └─ Links mock: Painel · Agenda · Pacientes · Gestão · Outros
  │
  └─ <div flex>
       ├─ Sidebar (w-64, bg-card, border-r)
       │   ├─ Título "Prontuários"
       │   ├─ Bloco "Duração da consulta"
       │   │   └─ Caixa com ícone relógio + cronômetro mm:ss
       │   │      (mostra elapsed quando recording, 00:00 quando idle)
       │   ├─ Botão principal (Iniciar/Finalizar/Enviando) — full width
       │   │   • idle/success/error → bg-primary  "▶ Iniciar consulta"
       │   │   • recording → bg-destructive  "■ Finalizar consulta"
       │   │   • sending → disabled  "Enviando..."
       │   ├─ Indicador "● gravando" pulsante quando recording
       │   └─ Item de menu "Resumo" ativo (borda esquerda primary)
       │
       └─ <section flex-1 p-8 space-y-6>
            ├─ Heading "Resumo"
            ├─ Card paciente (bg-card rounded-lg border p-6)
            │   ├─ Avatar circular (iniciais sobre bg-primary/10)
            │   ├─ Coluna principal:
            │   │   • Nome destacado (text-2xl font-semibold text-primary)
            │   │   • "Idade: 23 anos"
            │   │   • "Primeira consulta em: 29/10/2017"
            │   │   • "Convênio: Unimed"
            │   ├─ Coluna stats: "Atendimentos: 2" / "Faltas: 0"
            │   └─ Botão outline "VISUALIZAR CADASTRO" (alinhado à direita)
            │
            ├─ Linha filtro: "Filtrar: [Todos ▾]"  +  ações "Compartilhar / Imprimir"
            │
            └─ Timeline de atendimento (mock 1 entrada):
                ├─ Coluna data esquerda (bloco bg-primary/10 com dia/mês/ano)
                ├─ Card consulta (bg-card border rounded-lg)
                │   ├─ Header "Por: Dr. ... 🔒"  +  "🕐 hh:mm" (direita)
                │   ├─ Label "Retorno" (text-primary)
                │   ├─ Conteúdo: feedback da última gravação
                │   │   • success → "Consulta enviada com sucesso"
                │   │   • error → mensagem de erro + sugestão
                │   │   • permission-denied → mensagem de permissão
                │   │   • idle → placeholder "Nenhum atendimento registrado nesta sessão"
                │   └─ Footer com botão outline "+ Inserir informações"
```

Notas de design:
- Paleta atual já é azul/cinza (tokens primary/muted), combina com a referência.
- Sem CSS inline nem `.css` novo.
- Mensagens de feedback continuam existindo, mas agora dentro do card da timeline (em vez de soltas embaixo do botão). A mensagem de `permission-denied` aparece também na sidebar logo abaixo do botão para visibilidade imediata.
- Cronômetro `mm:ss` (via `formatTime`) renderizado no bloco "Duração da consulta" da sidebar — único local; o ponto pulsante fica logo abaixo do botão durante recording.

### 2. Arquivos NÃO tocados
- `src/routes/consulta.tsx` (rota)
- `src/lib/consulta.functions.ts` (server function)
- Toda a lógica de gravação/envio existente
- `vite.config.ts`, `__root.tsx`, `index.tsx`, qualquer outro arquivo

## Resultado
Layout idêntico em estrutura ao print do iClinic (topbar azul, sidebar com timer e CTA, área central com card do paciente e timeline), mantendo 100% da funcionalidade de gravação por áudio.
