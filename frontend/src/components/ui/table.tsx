import { cn } from "@/lib/utils"; import * as React from "react";
export function Table({className,...p}: React.TableHTMLAttributes<HTMLTableElement>) { return <div className="w-full overflow-auto"><table className={cn("w-full text-sm",className)} {...p}/></div>; }
export function THead(p: React.HTMLAttributes<HTMLTableSectionElement>) { return <thead className="border-b text-left text-zinc-500" {...p}/>; }
export function TBody(p: React.HTMLAttributes<HTMLTableSectionElement>) { return <tbody {...p}/>; }
export function TR({className,...p}: React.HTMLAttributes<HTMLTableRowElement>) { return <tr className={cn("border-b last:border-0 hover:bg-zinc-50 dark:hover:bg-zinc-800/50",className)} {...p}/>; }
export function TH({className,...p}: React.ThHTMLAttributes<HTMLTableCellElement>) { return <th className={cn("px-3 py-3 font-medium",className)} {...p}/>; }
export function TD({className,...p}: React.TdHTMLAttributes<HTMLTableCellElement>) { return <td className={cn("px-3 py-3",className)} {...p}/>; }
