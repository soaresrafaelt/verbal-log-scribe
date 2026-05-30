import { createFileRoute } from "@tanstack/react-router";
import { ConsultaPage } from "./-consulta-page";

export const Route = createFileRoute("/consulta")({
  head: () => ({
    meta: [
      { title: "Consulta — Prontuário" },
      { name: "description", content: "Gravação de áudio para prontuário médico." },
    ],
  }),
  component: ConsultaPage,
});
