import type { Metadata, Viewport } from "next";
import { headers } from "next/headers";

import "./shell.css";
import { FIRST_PAINT } from "./lib/preferences";
import { fromHeaders } from "./lib/regional";

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

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const person = fromHeaders(await headers());
  return (
    <html lang={person.locale}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: FIRST_PAINT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
