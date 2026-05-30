## Objetivo

Otimizar `/consulta` para mobile: priorizar nome do paciente e um botão GRANDE de gravação, mantendo o layout desktop iClinic intacto. Corrigir silenciosamente o hydration mismatch causado por `toLocaleTimeString` (servidor x cliente em fusos diferentes).

## Mudanças em `src/routes/-consulta-page.tsx`

### 1. Fix hydration (silencioso)
Os valores `horaAgora`/`dia`/`mes`/`ano` são calculados no render — render do servidor e do cliente produzem strings diferentes. Mover para um `useState` inicializado vazio + `useEffect` que preenche no client. Renderiza string vazia até o efeito rodar (evita mismatch).

### 2. Layout mobile (`< md`)

Adicionar, ANTES da topbar/sidebar/main atuais, um bloco visível só em mobile (`md:hidden`) que será a tela principal em telas pequenas. Esconder topbar/sidebar/main desktop em mobile com `hidden md:flex` / `hidden md:block`.

Estrutura mobile:
```text
<div md:hidden flex flex-col min-h-screen bg-muted/40>
  ├─ Topbar slim (bg-primary, h-12) — só logo "Prontuário"
  │
  ├─ Hero do paciente (px-5 py-6 bg-card border-b)
  │   ├─ Avatar grande (h-16 w-16) centralizado
  │   ├─ Nome (text-3xl font-bold text-primary text-center, leading-tight)
  │   └─ "Nascimento: 15/05/2002" (text-sm text-muted-foreground text-center)
  │
  ├─ Bloco timer (px-5 pt-6)
  │   ├─ Label "Duração da consulta"
  │   └─ Cronômetro grande (font-mono text-4xl tabular-nums centralizado)
  │   └─ Quando recording: ponto pulsante + "Gravando…"
  │
  ├─ Botão GIGANTE (mx-5 mt-6)
  │   • Circular grande (h-40 w-40 rounded-full mx-auto) com ícone Play/Square
  │     central + label embaixo
  │   • idle/success/error → bg-primary
  │   • recording → bg-destructive + animate-pulse sutil (ring)
  │   • sending → opacity-60, label "Enviando..."
  │   • Tamanho generoso para toque confortável (h-40 w-40 ≈ 160px)
  │
  ├─ Mensagem de feedback (px-5 mt-6 text-center)
  │   • success: "Consulta enviada com sucesso" (verde via text-foreground)
  │   • error: vermelho destructive
  │   • permission-denied: vermelho destructive
  │   • idle: nada (ou texto leve "Toque para iniciar")
  │
  └─ Footer com mock "Resumo" link (opcional, mt-auto)
</div>

<!-- Desktop atual (inalterado, apenas com hidden md:...) -->
<header className="hidden md:flex ..."> ... </header>
<div className="hidden md:flex"> ... sidebar + main ... </div>
```

Detalhes:
- Reaproveita estados/handlers/refs já existentes — `handleIniciar`, `handleFinalizar`, `formatTime`, `status`, `elapsed`.
- Botão circular usa `flex flex-col items-center justify-center gap-2` com ícone `h-12 w-12` + label `text-base font-semibold`.
- Toque confortável: alvo ≥ 160px de diâmetro, fácil de acertar com polegar.
- Sem CSS inline nem `.css` novo.

### 3. Mudar viewport do preview para mobile

Usar `preview_ui--set_preview_device_viewport` com `mobile` para o usuário ver o resultado.

## Não tocar
- `src/routes/consulta.tsx`
- `src/lib/consulta.functions.ts`
- Lógica de gravação/envio
- Layout desktop (apenas envolvido em `hidden md:flex`)
