import { createFileRoute } from "@tanstack/react-router";
import { ConsultaDemoPage } from "./-consulta-demo-page";

export const Route = createFileRoute("/consulta-demo")({
  head: () => ({
    meta: [
      { title: "Consulta DEMO — Prontuário" },
      { name: "description", content: "Demonstração visual do fluxo de gravação e anamnese." },
    ],
  }),
  component: ConsultaDemoPage,
});
