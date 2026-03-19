import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  MessageSquare, Mail, Bot, BarChart3, TerminalSquare, 
  Activity, Settings, X, Sliders, LogOut, Key, User, 
  Cpu, HardDrive, ShieldCheck, Lock, UserPlus
} from 'lucide-react';
import { api } from './services/api';

import MetaSChatDashboard from './components/MetaSChatDashboard';
import MetaSInbox from './components/MetaSInbox';
import AgentWorkflowVisualizer from './components/AgentWorkflowVisualizer';
import MetaSAnalytics from './components/MetaSAnalytics';

const NAV_ITEMS = [
  { id: 'chat', icon: MessageSquare, label: 'Conversations', topLabel: 'Chat UI' },
  { id: 'inbox', icon: Mail, label: 'Email Inbox', topLabel: 'Inbox Triage' },
  { id: 'visualizer', icon: Bot, label: 'AI Agents', topLabel: 'Visualizer' },
  { id: 'analytics', icon: BarChart3, label: 'Analytics', topLabel: 'Analytics' }
];

export default function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [activeView, setActiveView] = useState('chat');
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  
  // Auth state
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loginError, setLoginError] = useState('');
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [isRegisterMode, setIsRegisterMode] = useState(false); // NEW: Toggle between Login/Register

  const [systemConfig, setSystemConfig] = useState({
    model: 'phi-3.5',
    quantization: '4-bit',
    vramLimit: 4.0,
    maxReflexion: 2
  });

  const userMenuRef = useRef(null);

  useEffect(() => {
    const token = localStorage.getItem('meta_s_token');
    if (token) setIsAuthenticated(true);

    const handleAuthExpired = () => setIsAuthenticated(false);
    window.addEventListener('auth-expired', handleAuthExpired);

    function handleClickOutside(event) {
      if (userMenuRef.current && !userMenuRef.current.contains(event.target)) {
        setIsUserMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      window.removeEventListener('auth-expired', handleAuthExpired);
    };
  }, []);

  const handleAuth = async (e) => {
    e.preventDefault();
    setIsLoggingIn(true);
    setLoginError('');
    try {
      let res;
      if (isRegisterMode) {
        // Handle Registration
        res = await api.register(email, password);
        // Note: Some backends return the token on register, others require a separate login call.
        // Assuming your backend auto-logs in after registration and returns access_token:
        if (!res.data.access_token) {
           // If backend doesn't return token on register, force login call
           res = await api.login(email, password);
        }
      } else {
        // Handle Login
        res = await api.login(email, password);
      }
      
      localStorage.setItem('meta_s_token', res.data.access_token);
      setIsAuthenticated(true);
    } catch (err) {
      setLoginError(err.response?.data?.detail || `${isRegisterMode ? 'Registration' : 'Authentication'} failed. Please check credentials.`);
    } finally {
      setIsLoggingIn(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('meta_s_token');
    setIsAuthenticated(false);
  };

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-[#0F172A] flex items-center justify-center p-4 selection:bg-[#06B6D4]/30">
        <div className="bg-[#1E293B] p-8 rounded-2xl border border-white/10 w-full max-w-md shadow-2xl relative overflow-hidden">
          <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-[#7C3AED] via-[#06B6D4] to-[#10b981]"></div>
          
          <div className="flex flex-col items-center justify-center mb-8 gap-3">
            <div className="p-3 bg-gradient-to-br from-[#7C3AED]/20 to-[#06B6D4]/20 rounded-xl border border-white/5">
              <Activity size={32} className="text-[#22D3EE]" />
            </div>
            <h1 className="text-2xl font-black tracking-widest text-white mt-2">META-S</h1>
            <p className="text-xs text-slate-400 font-mono text-center">
              {isRegisterMode ? 'Register New Operator Credential' : 'Neural Core Operations Terminal'}
            </p>
          </div>

          <form onSubmit={handleAuth} className="space-y-4">
            {loginError && <div className="p-3 bg-rose-500/10 border border-rose-500/20 text-rose-400 text-sm rounded-lg text-center">{loginError}</div>}
            
            <div>
              <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-2 block">Operator Email</label>
              <input 
                type="email" required value={email} onChange={e => setEmail(e.target.value)}
                className="w-full bg-[#0F172A] border border-white/10 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-[#22D3EE] focus:ring-1 focus:ring-[#22D3EE] transition-all"
                placeholder="admin@kingsengineering.edu"
              />
            </div>
            
            <div>
              <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-2 block">Authorization Key</label>
              <input 
                type="password" required value={password} onChange={e => setPassword(e.target.value)}
                className="w-full bg-[#0F172A] border border-white/10 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-[#22D3EE] focus:ring-1 focus:ring-[#22D3EE] transition-all"
                placeholder="••••••••"
                minLength={8}
              />
            </div>
            
            <button disabled={isLoggingIn} type="submit" className="w-full bg-gradient-to-r from-[#06B6D4] to-[#3b82f6] hover:from-[#22D3EE] hover:to-[#60a5fa] text-white font-bold py-3.5 rounded-xl transition-all shadow-[0_0_20px_rgba(6,182,212,0.2)] hover:shadow-[0_0_25px_rgba(6,182,212,0.4)] mt-6 flex items-center justify-center gap-2 disabled:opacity-70">
              {isLoggingIn 
                ? (isRegisterMode ? 'Creating Credentials...' : 'Establishing Secure Uplink...') 
                : (isRegisterMode ? <><UserPlus size={16} /> Register Operator</> : <><Lock size={16} /> Initialize Connection</>)
              }
            </button>
          </form>

          {/* Toggle between Login and Register */}
          <div className="mt-6 text-center">
            <button 
              type="button"
              onClick={() => { setIsRegisterMode(!isRegisterMode); setLoginError(''); }}
              className="text-xs text-slate-500 hover:text-[#22D3EE] transition-colors font-mono"
            >
              {isRegisterMode 
                ? "Already authorized? Authenticate here." 
                : "No credentials? Request access here."}
            </button>
          </div>

        </div>
      </div>
    );
  }

  const renderView = () => {
    switch (activeView) {
      case 'chat': return <MetaSChatDashboard config={systemConfig} />;
      case 'inbox': return <MetaSInbox config={systemConfig} />;
      case 'visualizer': return <AgentWorkflowVisualizer />;
      case 'analytics': return <MetaSAnalytics />;
      default: return <MetaSChatDashboard config={systemConfig} />;
    }
  };

  return (
    <div className="flex flex-col h-screen bg-[#0F172A] text-slate-200 font-sans overflow-hidden selection:bg-[#06B6D4]/30">
      <header className="h-14 bg-[#0B0F17] border-b border-white/10 flex items-center justify-between px-4 shrink-0 z-30">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2 text-[#22D3EE] font-black tracking-widest text-xs">
            <TerminalSquare size={16} /> DEV VIEWER
          </div>
          <nav className="hidden md:flex items-center gap-1 bg-white/5 p-1 rounded-lg border border-white/5">
            {NAV_ITEMS.map((item) => (
              <button
                key={`top-${item.id}`} onClick={() => setActiveView(item.id)}
                className={`px-3 py-1 rounded-md text-xs font-bold transition-all ${activeView === item.id ? 'bg-[#06B6D4]/20 text-[#22D3EE] shadow-[0_0_10px_rgba(6,182,212,0.2)]' : 'text-slate-400 hover:text-white hover:bg-white/5'}`}
              >
                {item.topLabel}
              </button>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 px-3 py-1 bg-emerald-500/10 border border-emerald-500/20 rounded-full text-[10px] font-bold text-emerald-400 uppercase tracking-wider hidden sm:flex">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
            System Online ({systemConfig.vramLimit}GB VRAM)
          </div>
          <button onClick={() => setIsSettingsOpen(true)} className="p-2 rounded-lg bg-white/5 hover:bg-white/10 border border-white/5 hover:border-white/10 transition-all text-slate-400 hover:text-white">
            <Settings size={18} />
          </button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden relative">
        <aside className="w-64 bg-[#1E293B]/60 backdrop-blur-xl border-r border-white/5 flex flex-col z-20 shrink-0 shadow-2xl">
          <div className="h-16 flex items-center px-6 border-b border-white/5">
            <div className="bg-gradient-to-br from-[#7C3AED] to-[#06B6D4] p-[1px] rounded-lg shadow-[0_0_15px_rgba(124,58,237,0.3)]">
              <div className="bg-[#0F172A] p-1.5 rounded-lg"><Activity size={18} color="#22D3EE" /></div>
            </div>
            <span className="ml-3 font-bold text-lg tracking-wide text-transparent bg-clip-text bg-gradient-to-r from-white to-[#E2E8F0]">META-S</span>
          </div>
          
          <nav className="flex-1 px-3 py-6 space-y-1">
            <div className="px-3 text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">Workspace</div>
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              const isActive = activeView === item.id;
              return (
                <button
                  key={`side-${item.id}`} onClick={() => setActiveView(item.id)}
                  className={`w-full flex items-center space-x-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-300 relative group ${isActive ? 'text-white bg-white/5' : 'text-slate-400 hover:text-white hover:bg-white/[0.02]'}`}
                >
                  {isActive && <motion.div layoutId="sidebar-active" className="absolute left-0 top-2 bottom-2 w-1 rounded-r-full bg-[#06B6D4] shadow-[0_0_10px_#06B6D4]" />}
                  <Icon size={18} className={isActive ? 'text-[#22D3EE]' : 'group-hover:text-slate-300 transition-colors'} />
                  <span>{item.label}</span>
                </button>
              )
            })}
          </nav>

          <div className="p-4 border-t border-white/5 relative" ref={userMenuRef}>
            <AnimatePresence>
              {isUserMenuOpen && (
                <motion.div initial={{ opacity: 0, y: 10, scale: 0.95 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 10, scale: 0.95 }} transition={{ duration: 0.2 }}
                  className="absolute bottom-full left-4 right-4 mb-2 bg-[#0F172A] border border-white/10 rounded-xl shadow-2xl overflow-hidden z-50">
                  <div className="p-3 border-b border-white/5 bg-white/[0.02]">
                    <div className="text-xs font-bold text-white">System Operator</div>
                    <div className="text-[10px] text-slate-400 truncate">Authenticated Session</div>
                  </div>
                  <div className="p-1 border-t border-white/5">
                    <button onClick={handleLogout} className="w-full flex items-center gap-2 px-3 py-2 text-xs font-medium text-rose-400 hover:bg-rose-500/10 rounded-lg transition-colors">
                      <LogOut size={14} /> Terminate Session
                    </button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            <div onClick={() => setIsUserMenuOpen(!isUserMenuOpen)} className={`flex items-center gap-3 p-2 rounded-xl transition-colors cursor-pointer border ${isUserMenuOpen ? 'bg-white/10 border-white/10' : 'hover:bg-white/5 border-transparent'}`}>
              <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-[#7C3AED] to-[#06B6D4] flex items-center justify-center text-white font-bold text-xs shadow-lg">OP</div>
              <div className="text-left flex-1">
                <div className="text-sm font-bold text-white leading-tight">Operator</div>
                <div className="text-[10px] text-[#22D3EE] font-mono leading-tight">Active Node</div>
              </div>
            </div>
          </div>
        </aside>

        <main className="flex-1 flex flex-col overflow-hidden bg-[#0A0D14] relative z-10">
          {renderView()}
        </main>
      </div>

      <AnimatePresence>
        {isSettingsOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center">
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setIsSettingsOpen(false)} className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
            <motion.div initial={{ opacity: 0, scale: 0.95, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 20 }} className="relative w-full max-w-lg bg-[#0F172A] border border-white/10 rounded-2xl shadow-2xl overflow-hidden">
              <div className="flex items-center justify-between p-5 border-b border-white/5 bg-white/[0.02]">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-blue-500/10 rounded-lg text-blue-400"><Sliders size={18} /></div>
                  <h3 className="text-lg font-bold text-white">System Configuration</h3>
                </div>
                <button onClick={() => setIsSettingsOpen(false)} className="p-1.5 text-slate-400 hover:text-white hover:bg-white/10 rounded-md transition-colors"><X size={18} /></button>
              </div>

              <div className="p-6 space-y-6">
                <div className="space-y-3">
                  <label className="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center gap-2"><Cpu size={14} /> Active Inference Engine</label>
                  <div className="grid grid-cols-2 gap-3">
                    <button onClick={() => setSystemConfig({...systemConfig, model: 'phi-3.5'})} className={`p-3 rounded-xl border text-left transition-all ${systemConfig.model === 'phi-3.5' ? 'bg-purple-500/10 border-purple-500/50 shadow-[0_0_15px_rgba(168,85,247,0.15)]' : 'bg-[#1E293B] border-white/5 hover:border-white/20'}`}>
                      <div className={`font-bold text-sm ${systemConfig.model === 'phi-3.5' ? 'text-purple-400' : 'text-slate-300'}`}>Phi-3.5 Mini</div>
                      <div className="text-xs text-slate-500 font-mono mt-1">3.8B Parameters</div>
                    </button>
                    <button onClick={() => setSystemConfig({...systemConfig, model: 'qwen-2.5'})} className={`p-3 rounded-xl border text-left transition-all ${systemConfig.model === 'qwen-2.5' ? 'bg-cyan-500/10 border-cyan-500/50 shadow-[0_0_15px_rgba(6,182,212,0.15)]' : 'bg-[#1E293B] border-white/5 hover:border-white/20'}`}>
                      <div className={`font-bold text-sm ${systemConfig.model === 'qwen-2.5' ? 'text-cyan-400' : 'text-slate-300'}`}>Qwen-2.5 3B</div>
                      <div className="text-xs text-slate-500 font-mono mt-1">3.0B Parameters</div>
                    </button>
                  </div>
                </div>

                <div className="space-y-3">
                  <label className="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center gap-2"><HardDrive size={14} /> Memory Constraints</label>
                  <div className="bg-[#1E293B]/50 p-4 rounded-xl border border-white/5 space-y-4">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-slate-300">VRAM Budget Limit</span>
                      <span className="text-xs font-mono text-cyan-400">{systemConfig.vramLimit} GB</span>
                    </div>
                    <input type="range" min="2" max="12" step="0.5" value={systemConfig.vramLimit} onChange={(e) => setSystemConfig({...systemConfig, vramLimit: parseFloat(e.target.value)})} className="w-full accent-cyan-400 bg-white/10 h-1.5 rounded-lg appearance-none cursor-pointer" />
                  </div>
                </div>

                <div className="space-y-3">
                  <label className="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center gap-2"><ShieldCheck size={14} /> Reflector Agent Loop</label>
                  <div className="bg-[#1E293B]/50 p-4 rounded-xl border border-white/5">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium text-slate-300">Max Iterations</span>
                      <span className="text-xs font-mono text-emerald-400">{systemConfig.maxReflexion} Passes</span>
                    </div>
                    <input type="range" min="1" max="5" step="1" value={systemConfig.maxReflexion} onChange={(e) => setSystemConfig({...systemConfig, maxReflexion: parseInt(e.target.value)})} className="w-full accent-emerald-400 bg-white/10 h-1.5 rounded-lg appearance-none cursor-pointer mt-2" />
                  </div>
                </div>
              </div>

              <div className="p-5 border-t border-white/5 bg-white/[0.02] flex justify-end gap-3">
                <button onClick={() => setIsSettingsOpen(false)} className="px-4 py-2 rounded-lg text-sm font-bold text-slate-400 hover:text-white transition-colors">Cancel</button>
                <button onClick={() => setIsSettingsOpen(false)} className="px-6 py-2 rounded-lg text-sm font-bold bg-[#22D3EE] hover:bg-[#06B6D4] text-[#0F172A] transition-colors shadow-[0_0_15px_rgba(34,211,238,0.3)]">Apply Configuration</button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}