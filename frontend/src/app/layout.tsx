/** Root layout with a restrained local-first product identity. */
import type { Metadata } from 'next';
import Link from 'next/link';
import './globals.css';
import './groups.css';
import './agents.css';
export const metadata: Metadata = { title: '说话即记 · SpeakLink', description: '从一段声音，到一张知识地图。' };
/** Wrap all routes in the shared navigation and visual system. */
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="zh-CN"><body><header className="topbar"><Link href="/" className="brand"><span className="brand-mark">⌁</span><strong>说话即记</strong><span className="brand-en">SpeakLink</span></Link><nav><Link href="/">我的速记</Link><a href="/api/health" target="_blank" rel="noreferrer" className="local-status"><i />本地优先</a></nav></header>{children}<footer className="site-footer"><span>把声音留下，让知识生长。</span><span>LOCAL FIRST · EVIDENCE ALWAYS</span></footer></body></html>; }

