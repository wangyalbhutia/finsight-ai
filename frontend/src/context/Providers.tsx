"use client";
import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { User } from "@/types";
import { api, clearTokens, getToken, setTokens } from "@/lib/api";

interface AuthCtx { user: User | null; loading: boolean; login: (e:string,p:string)=>Promise<void>; register: (n:string,e:string,p:string)=>Promise<void>; logout: ()=>void; refreshUser: ()=>Promise<void> }
const AuthContext = createContext<AuthCtx | null>(null);
interface ThemeCtx { theme: "light"|"dark"; toggle: ()=>void; setTheme:(t:"light"|"dark")=>void }
const ThemeContext = createContext<ThemeCtx>({ theme:"light", toggle:()=>{}, setTheme:()=>{} });
export const useTheme = () => useContext(ThemeContext);
export function useAuthContext() { const c=useContext(AuthContext); if(!c) throw new Error("useAuth must be used within Providers"); return c; }

export function Providers({children}:{children:React.ReactNode}) {
  const router = useRouter();
  const [user,setUser]=useState<User|null>(null); const [loading,setLoading]=useState(true);
  const [theme,setThemeState]=useState<"light"|"dark">("light");
  useEffect(()=>{ const t=(localStorage.getItem("finsight_theme") as "light"|"dark")||(window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"); setThemeState(t); document.documentElement.classList.toggle("dark",t==="dark"); },[]);
  const setTheme=useCallback((t:"light"|"dark")=>{ setThemeState(t); localStorage.setItem("finsight_theme",t); document.documentElement.classList.toggle("dark",t==="dark"); },[]);
  const toggle=useCallback(()=>setTheme(theme==="dark"?"light":"dark"),[theme,setTheme]);
  const refreshUser=useCallback(async()=>{ if(!getToken()){ setLoading(false); return; } try{ setUser(await api.me()); }catch{ clearTokens(); setUser(null); } finally{ setLoading(false); } },[]);
  useEffect(()=>{ void refreshUser(); },[refreshUser]);
  const login=useCallback(async(email:string,password:string)=>{ const r=await api.login(email,password); setTokens(r.access_token,r.refresh_token); if(r.user) setUser(r.user); else await refreshUser(); router.push("/dashboard"); },[router,refreshUser]);
  const register=useCallback(async(name:string,email:string,password:string)=>{ const r=await api.register(name,email,password); setTokens(r.access_token,r.refresh_token); if(r.user) setUser(r.user); else await refreshUser(); router.push("/dashboard"); },[router,refreshUser]);
  const logout=useCallback(()=>{ void api.logout(); clearTokens(); setUser(null); router.push("/login"); },[router]);
  return <ThemeContext.Provider value={{theme,toggle,setTheme}}><AuthContext.Provider value={{user,loading,login,register,logout,refreshUser}}>{children}</AuthContext.Provider></ThemeContext.Provider>;
}
