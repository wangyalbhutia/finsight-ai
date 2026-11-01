import * as React from "react"; import { cn } from "@/lib/utils";
export function Card({className,...p}: React.HTMLAttributes<HTMLDivElement>) { return <div className={cn("rounded-2xl border border-zinc-200/80 bg-white shadow-[0_1px_3px_rgba(0,0,0,0.04)] dark:border-zinc-800 dark:bg-zinc-900",className)} {...p}/>; }
export function CardHeader({className,...p}: React.HTMLAttributes<HTMLDivElement>) { return <div className={cn("p-5 pb-2",className)} {...p}/>; }
export function CardTitle({className,...p}: React.HTMLAttributes<HTMLHeadingElement>) { return <h3 className={cn("font-semibold tracking-tight",className)} {...p}/>; }
export function CardContent({className,...p}: React.HTMLAttributes<HTMLDivElement>) { return <div className={cn("p-5 pt-2",className)} {...p}/>; }
