## Objetivo

Polir o acabamento visual de `/consulta` mantendo a estrutura atual (mobile + desktop iClinic) e toda a lógica de gravação intacta. Apenas classes Tailwind.

## Mudanças

### 1. Tokens de cor em `src/styles.css`
Ajustar o `--primary` para um teal/azul-petróleo médico (≈ `#0EA5B7`) em oklch, mantendo `--primary-foreground` branco. Ajustar `--background` para um cinza muito claro (slate-50 equivalente em oklch) e `--card` para branco puro. Manter `--destructive` vermelho. Sem mudanças em outros tokens.

> Resultado: todas as classes `bg-primary`, `text-primary`, `bg-background`, `bg-card` já existentes herdam a nova paleta sem refactor.

### 2. `src/routes/-consulta-page.tsx` — apenas classes

**Wrapper raiz**: `bg-muted/40` → `bg-slate-50`.

**Avatar (mobile e desktop)**: fundo `bg-primary/10 text-primary` → `bg-primary text-primary-foreground` (mais presença visual).

**Card do paciente (desktop)**:
- `rounded-lg` → `rounded-xl`, `p-6` mantido, `shadow-sm` mantido
- Nome: `text-2xl` → `text-3xl font-semibold text-slate-800`, `leading-relaxed` no bloco de infos
- Labels "Idade:", "Nascimento:", "Convênio:", "Primeira consulta em:": envolver label em `text-slate-500` e valor em `text-slate-800 font-medium`, com `space-y-2` no container
- Botão "Visualizar cadastro": mudar para outline → `border border-border bg-card text-slate-700 hover:bg-slate-100 transition-colors`

**Bloco do cronômetro (sidebar desktop)**:
- Container do clock: `rounded-md` → `rounded-xl`, manter borda fina, `transition-colors`
- Botão principal de gravação: já usa `bg-primary` (herda nova cor); adicionar `transition-colors` e `rounded-lg`

**Filtros / botões secundários** (Todos, Compartilhar, Imprimir, Inserir informações, ícone Printer):
- Padronizar como ghost/outline: `border border-border bg-card text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition-colors rounded-lg`

**Timeline**:
- Card de data: `rounded-md` → `rounded-xl`; número do dia em `text-primary` (já está); fundo `bg-primary/10` → `bg-card border border-border`, com apenas o número grande em `text-primary`
- Card da timeline: `rounded-lg` → `rounded-xl`, `shadow-sm` mantido
- Título "Consulta por áudio": `text-sm font-medium` → `text-base font-semibold text-slate-800`
- Estado vazio: manter `italic text-muted-foreground`

**Espaçamento**:
- `<section>` main: `space-y-6` → `space-y-8`
- Card do paciente: `gap-6` mantido, info block ganha `space-y-2`

**Hover/transições**:
- Adicionar `transition-colors` em todos os botões clicáveis (filtros, ações, "Visualizar cadastro", botão principal)
- Itens da nav do header: adicionar `transition-opacity`

**Mobile**:
- Avatar: mesmo tratamento (primary sólido)
- Hero do paciente: nome continua `text-3xl text-primary` → manter, mas trocar para `text-slate-800` para hierarquia; adicionar `leading-relaxed` nas linhas de info
- Botão circular: já `bg-primary`/`bg-destructive`; adicionar `transition-colors`
- Bloco timer: manter, garantir `tabular-nums` (já tem)
- Ponto pulsante: `animate-pulse` mantido

### 3. Nada muda em
- `src/routes/consulta.tsx`
- `src/lib/consulta.functions.ts`
- Toda a lógica (`handleIniciar`, `handleFinalizar`, refs, `useEffect`, `enviarConsulta`)
- Estrutura JSX (sem adicionar/remover blocos)
- Responsividade (`md:` breakpoints preservados)
- `vite.config.ts`

## Detalhes técnicos

Tokens em `src/styles.css` (oklch aproximado de `#0EA5B7` / slate-50):
```
--primary: oklch(0.68 0.11 210);
--primary-foreground: oklch(1 0 0);
--background: oklch(0.984 0.003 248);
--card: oklch(1 0 0);
```
Aplicar tanto em `:root` quanto em `.dark` se necessário (revisar arquivo antes de editar).
