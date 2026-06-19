import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "AO Copilot",
  description: "Réponds plus vite et mieux à tes appels d'offres",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
