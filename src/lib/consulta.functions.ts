import { createServerFn } from "@tanstack/react-start";
import { z } from "zod";

const WEBHOOK_URL = "https://teste.rafael-agentes.com.br/webhook-test/Prontuario";

const inputSchema = z.object({
  audioBase64: z.string().min(1),
});

export const enviarConsulta = createServerFn({ method: "POST" })
  .inputValidator((input: unknown) => inputSchema.parse(input))
  .handler(async ({ data }) => {
    try {
      const bytes = Buffer.from(data.audioBase64, "base64");
      const blob = new Blob([bytes], { type: "audio/webm" });

      const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
      const filename = `consulta-${timestamp}.webm`;

      const formData = new FormData();
      formData.append("audio", blob, filename);

      const res = await fetch(WEBHOOK_URL, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        return {
          success: false as const,
          error: `Webhook respondeu com status ${res.status}`,
        };
      }

      return { success: true as const };
    } catch (err) {
      console.error("Erro ao enviar consulta para webhook:", err);
      return {
        success: false as const,
        error: err instanceof Error ? err.message : "Erro desconhecido",
      };
    }
  });
