## Objetivo

Criar uma página MVP em `/consulta` para gravar áudio de prontuário médico e enviar a um webhook externo via server function (evitando CORS).

## Arquivos a criar

1. **`src/routes/consulta.tsx`** — configuração da rota (head + componente)
   - `createFileRoute("/consulta")` com `head()` (title "Consulta — Prontuário", description) e `component`
   - Importa e renderiza `ConsultaPage` de `./-consulta-page`

2. **`src/routes/-consulta-page.tsx`** — componente React da tela
   - Constante `PACIENTE = { nome: "Pedro Henrique Alves", nascimento: "15/05/2002" }` no topo
   - Estado: `status` (`"idle" | "recording" | "sending" | "success" | "error" | "permission-denied"`), `elapsed` (segundos), refs para `MediaRecorder`, `MediaStream`, chunks `Blob[]`, e intervalo do cronômetro
   - UI (Tailwind, tokens semânticos do design system):
     - Card centralizado com nome em fonte grande (`text-4xl font-bold`) e data de nascimento abaixo (`text-muted-foreground`)
     - Botão principal grande mudando label/cor por estado:
       - idle/success/error → "Iniciar consulta" (primary)
       - recording → "Finalizar consulta" (destructive)
       - sending → "Enviando..." (disabled)
     - Durante recording: ponto vermelho pulsante (`animate-pulse bg-destructive rounded-full`) + cronômetro `mm:ss`
     - Mensagens de feedback abaixo do botão:
       - success: "Consulta enviada com sucesso"
       - error: "Não foi possível enviar a gravação, tente novamente"
       - permission-denied: "Permissão de microfone negada. Habilite o microfone para gravar a consulta."
   - Lógica:
     - `iniciar()`: `navigator.mediaDevices.getUserMedia({ audio: true })`; em erro → status `permission-denied`. Cria `MediaRecorder` com `mimeType: "audio/webm;codecs=opus"`, acumula chunks no `ondataavailable`, inicia, dispara `setInterval` 1s pro cronômetro
     - `finalizar()`: `mediaRecorder.stop()`; no `onstop` monta Blob webm, para todas as tracks do stream (`stream.getTracks().forEach(t => t.stop())`), limpa interval, converte Blob → base64 (via `FileReader.readAsDataURL` removendo prefixo), chama a server function, atualiza status conforme resultado
     - Helper `formatTime(s)` → `mm:ss`
     - `useEffect` de cleanup ao desmontar (parar tracks/interval se ativos)

3. **`src/lib/consulta.functions.ts`** — server function
   - `import { createServerFn } from "@tanstack/react-start"` + `z`
   - `export const enviarConsulta = createServerFn({ method: "POST" })`
     - `.inputValidator(z.object({ audioBase64: z.string().min(1) }).parse)`
     - `.handler(async ({ data }) => { ... })`
   - Handler:
     - Decodifica base64 para `Uint8Array` (`Buffer.from(data.audioBase64, "base64")`)
     - Monta `Blob` (`new Blob([bytes], { type: "audio/webm" })`)
     - Cria `FormData`, append `"audio"` com filename `consulta-<timestamp>.webm` (timestamp ISO com `:` trocados por `-`)
     - `fetch("https://teste.rafael-agentes.com.br/webhook-test/Prontuario", { method: "POST", body: formData })`
     - Try/catch: retorna `{ success: true }` ou `{ success: false, error: string }` (DTO simples)

## Detalhes técnicos

- Sem alterações em `vite.config.ts`, `__root.tsx`, `index.tsx`, ou qualquer outro arquivo existente
- Tailwind apenas; sem CSS inline nem `.css` novo
- Tokens do design system (`bg-primary`, `text-destructive`, `bg-card`, `text-muted-foreground`, etc.)
- Webhook chamado **só** no handler da server function — frontend chama via `useServerFn(enviarConsulta)`
- Cleanup garantido: `stream.getTracks().forEach(t => t.stop())` no `onstop` e no unmount
- Conversão base64 no client com `FileReader.readAsDataURL(blob)` + split do prefixo `data:...;base64,`

## Estados do botão (resumo visual)

```text
idle           → [Iniciar consulta]            primary
recording      → ● 00:12  [Finalizar consulta] destructive
sending        → [Enviando...]                 disabled
success/error  → mensagem + [Iniciar consulta] primary
permission-denied → mensagem + [Iniciar consulta] primary
```
