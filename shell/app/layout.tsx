import type { Metadata, Viewport } from "next";

import "./shell.css";
import { FIRST_PAINT } from "./lib/preferences";

export const metadata: Metadata = {
  title: "arga",
  description: "Tu sistema, tus datos.",
  manifest: "/manifest.webmanifest",
  icons: {
    icon: [{ url: "/icon.svg", type: "image/svg+xml" }],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180" }],
  },
  appleWebApp: { capable: true, statusBarStyle: "default", title: "arga" },
};

export const viewport: Viewport = {
  viewportFit: "cover",
  initialScale: 1,
  width: "device-width",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <head>
        <script dangerouslySetInnerHTML={{ __html: FIRST_PAINT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
