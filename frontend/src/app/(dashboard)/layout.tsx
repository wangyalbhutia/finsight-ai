"use client";
import { useEffect } from "react"; import { useRouter } from "next/navigation"; import { useAuth } from "@/hooks/useAuth"; import { DashboardShell } from "@/components/layout/Sidebar"; import { Skeleton } from "@/components/ui/skeleton"; import { getToken } from "@/lib/api";
export default function Layout({children}:{children:React.ReactNode}) { const {user,loading}=useAuth(); const router=useRouter();
 useEffect(()=>{ if(!loading && !user && !getToken()) router.replace("/login"); },[loading,user,router]);
 if(loading) return <div className="p-8"><Skeleton className="h-64"/></div>;
 return <DashboardShell>{children}</DashboardShell>; }
