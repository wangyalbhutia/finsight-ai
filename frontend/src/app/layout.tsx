import type { Metadata } from "next"; import { Inter } from "next/font/google"; import "./globals.css"; import { Providers } from "@/context/Providers";
const inter = Inter({ subsets:["latin"], variable:"--font-inter" });
export const metadata: Metadata = { title:"FinSight AI — Personal Finance Intelligence", description:"Understand, forecast and improve your finances with explainable AI." };
export default function RootLayout({children}:{children:React.ReactNode}) { return <html lang="en" suppressHydrationWarning><body className={`${inter.variable} font-sans`}><Providers>{children}</Providers></body></html>; }
