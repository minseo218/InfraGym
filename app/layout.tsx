import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://infragym.sites.openai.com"),
  title: "InfraGym — Train like a Real Systems Engineer",
  description: "A scenario-driven AI infrastructure training platform for Systems Engineers, SREs, DevOps, and AI Platform Engineers.",
  icons: { icon: "/favicon.svg", shortcut: "/favicon.svg" },
  openGraph: {
    title: "InfraGym — Train like a Real Systems Engineer",
    description: "Investigate production-grade incidents through metrics, logs, events, topology, and a scenario-aware terminal.",
    images: [{ url: "/og.png", width: 1200, height: 630, alt: "InfraGym incident training platform" }],
  },
  twitter: { card: "summary_large_image", title: "InfraGym — Train like a Real Systems Engineer", description: "Build real incident-response muscle memory.", images: ["/og.png"] },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
