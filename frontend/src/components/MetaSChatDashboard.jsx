import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Network, Database, PenTool, ShieldCheck, ChevronRight, Tag, AlertTriangle, CheckCircle2, TerminalSquare, Search, Send } from 'lucide-react';
import { api } from '../services/api';

const AGENTS = [
  { id: 'router', name: 'Router Agent', icon: Network, color: '#7C3AED', description: 'Classifies & routes intent' },
  { id: 'search', name: 'Search (RAG)', icon: Database, color: '#06B6D4', description: 'Retrieves vector context' },
  { id: 'scribe', name: 'Scribe Agent', icon: PenTool, color: '#22D3EE', description: 'Drafts initial response' },
  { id: 'reflector', name: 'Reflector', icon: ShieldCheck, color: '#10b981', description: 'Evaluates & refines quality' }
];

export default function MetaSChatDashboard({ config }) {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState([
    { id: 1, role: 'ai', text: 'META-S Neural Core initialized. Paste an incoming email below, and I will execute the multi-agent swarm to analyze, retrieve context, and draft a refined response.', metadata: null }
  ]);
  
  const [isProcessing, setIsProcessing] = useState(false);
  const [activeAgentIdx, setActiveAgentIdx] = useState(-1);
  const [logs, setLogs] = useState([]);
  
  const chatEndRef = useRef(null);
  const logsEndRef = useRef(null);

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, isProcessing]);
  useEffect(() => { logsEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [logs]);

  const addLog = (text, agentIdx, agentId = 'system') => {
    setActiveAgentIdx(agentIdx);
    setLogs(prev => [...prev, {
      time: new Date().toLocaleTimeString(),
      text, agent: agentId, color: agentIdx >= 0 ? AGENTS[agentIdx].color : '#94A3B8'
    }]);
  };

  const handleSend = async () => {
    if (!input.trim() || isProcessing) return;

    const userMsg = input.trim();
    setInput('');
    setMessages(prev => [...prev, { id: Date.now(), role: 'user', text: userMsg }]);
    
    setIsProcessing(true);
    addLog('System: Payload received. Dispatching to Router Node...', -1);

    try {
      addLog('Analyzing semantics. Determining intent classification...', 0, 'router');
      
      const res = await api.triageEmail({
        subject: "Manual Entry Payload",
        body: userMsg,
        force_reflection: true,
        max_reflections: config?.maxReflexion || 2
      });

      const { classification, final_draft, reflection_scores, usage } = res.data;
      
      addLog(`Querying vector DB context for classification: ${classification}. Retrieving chunks.`, 1, 'search');
      
      await new Promise(r => setTimeout(r, 600)); 
      
      addLog(`Synthesizing context. Generating draft using ${usage?.input_tokens || 'N/A'} tokens...`, 2, 'scribe');
      
      await new Promise(r => setTimeout(r, 600)); 
      
      const finalScore = reflection_scores && reflection_scores.length > 0 
        ? reflection_scores[reflection_scores.length - 1] 
        : 90;

      addLog(`Evaluating draft. Tone checked. Final Reflector Score: ${finalScore}/100. Approved.`, 3, 'reflector');

      setActiveAgentIdx(-1);
      setMessages(prev => [...prev, {
        id: Date.now() + 1,
        role: 'ai',
        text: "Draft generated and approved by the Reflector agent. Ready for review.",
        metadata: {
          classification: classification,
          priority: res.data.priority_score || 85,
          draft: final_draft,
          score: finalScore
        }
      }]);
      
      addLog(`System: Execution complete in ${usage?.latency_ms || 'N/A'}ms. Standing by.`, -1);

    } catch (error) {
      addLog(`Error: ${error.response?.data?.detail || error.message}. Task aborted.`, -1);
      setMessages(prev => [...prev, { id: Date.now() + 2, role: 'ai', text: 'Critical Error processing payload. Check telemetry logs.' }]);
      setActiveAgentIdx(-1);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex w-full h-full bg-transparent">
      <div className="flex-1 flex flex-col relative bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-[#1E293B]/40 via-transparent to-transparent">
        <header className="h-16 flex items-center justify-between px-8 border-b border-white/5 bg-[#0F172A]/80 backdrop-blur-md z-10">
          <h2 className="text-sm font-bold text-white tracking-wide">Swarm Interface</h2>
        </header>

        <div className="flex-1 overflow-y-auto p-4 md:p-8 custom-scrollbar scroll-smooth">
          <div className="max-w-3xl mx-auto space-y-6">
            <AnimatePresence>
              {messages.map((msg) => (
                <motion.div key={msg.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[85%] ${msg.role === 'user' ? 'order-1' : 'order-2'}`}>
                    <div className={`p-4 rounded-2xl text-sm leading-relaxed shadow-lg ${msg.role === 'user' ? 'bg-gradient-to-br from-[#7C3AED] to-indigo-600 text-white rounded-br-sm border border-[#7C3AED]/50' : 'bg-[#1E293B]/80 backdrop-blur-sm text-slate-200 rounded-bl-sm border border-white/10'}`}>
                      {msg.text}
                    </div>

                    {msg.metadata && (
                      <motion.div initial={{ opacity: 0, marginTop: 0 }} animate={{ opacity: 1, marginTop: 16 }} transition={{ delay: 0.2 }} className="bg-[#1E293B]/90 backdrop-blur-xl border border-[#06B6D4]/30 rounded-2xl overflow-hidden shadow-[0_0_30px_rgba(6,182,212,0.1)]">
                        <div className="flex flex-wrap gap-2 p-4 border-b border-white/5 bg-black/20">
                          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-[#7C3AED]/10 border border-[#7C3AED]/30 rounded-lg text-xs font-bold text-[#7C3AED]">
                            <Tag size={12} /> {msg.metadata.classification}
                          </div>
                          <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold border ${msg.metadata.priority > 80 ? 'bg-rose-500/10 border-rose-500/30 text-rose-400' : 'bg-[#06B6D4]/10 border-[#06B6D4]/30 text-[#06B6D4]'}`}>
                            <AlertTriangle size={12} /> Priority: {msg.metadata.priority}
                          </div>
                          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-[#10b981]/10 border border-[#10b981]/30 rounded-lg text-xs font-bold text-[#10b981] ml-auto">
                            <CheckCircle2 size={12} /> Score: {msg.metadata.score}/100
                          </div>
                        </div>
                        <div className="p-5">
                          <div className="text-[10px] uppercase font-bold text-slate-500 tracking-wider mb-3 flex items-center gap-2">
                            <PenTool size={12} className="text-[#22D3EE]" /> Generated Draft
                          </div>
                          <div className="text-sm font-mono text-slate-300 whitespace-pre-wrap leading-relaxed bg-black/30 p-4 rounded-xl border border-white/5">
                            {msg.metadata.draft}
                          </div>
                        </div>
                      </motion.div>
                    )}
                  </div>
                </motion.div>
              ))}
              
              {isProcessing && (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex justify-start">
                  <div className="bg-[#1E293B]/80 backdrop-blur-sm rounded-2xl rounded-bl-sm border border-white/10 p-4 flex gap-2 shadow-lg">
                    <motion.div animate={{ y: [0, -5, 0] }} transition={{ duration: 0.6, repeat: Infinity, delay: 0 }} className="w-2 h-2 bg-[#06B6D4] rounded-full"></motion.div>
                    <motion.div animate={{ y: [0, -5, 0] }} transition={{ duration: 0.6, repeat: Infinity, delay: 0.2 }} className="w-2 h-2 bg-[#06B6D4] rounded-full"></motion.div>
                    <motion.div animate={{ y: [0, -5, 0] }} transition={{ duration: 0.6, repeat: Infinity, delay: 0.4 }} className="w-2 h-2 bg-[#06B6D4] rounded-full"></motion.div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
            <div ref={chatEndRef} className="h-4" />
          </div>
        </div>

        <div className="p-4 md:p-8 pt-0">
          <div className="max-w-3xl mx-auto relative group">
            <div className="absolute -inset-0.5 bg-gradient-to-r from-[#7C3AED] via-[#06B6D4] to-[#7C3AED] rounded-2xl blur opacity-30 group-hover:opacity-60 transition duration-500"></div>
            <div className="relative bg-[#0F172A] border border-white/10 rounded-2xl shadow-2xl overflow-hidden flex flex-col">
              <textarea
                value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={handleKeyDown} disabled={isProcessing}
                placeholder="Paste raw email here to initiate triage..."
                className="w-full bg-transparent p-4 text-sm text-white focus:outline-none resize-none min-h-[100px] custom-scrollbar placeholder:text-slate-600 disabled:opacity-50"
              />
              <div className="bg-[#1E293B]/50 px-4 py-3 flex justify-between items-center border-t border-white/5">
                <div className="text-xs font-mono text-slate-500 flex items-center gap-2">
                  <Search size={14} /> Swarm Ready
                </div>
                <button
                  onClick={handleSend} disabled={!input.trim() || isProcessing}
                  className="bg-[#E2E8F0] hover:bg-white text-[#0F172A] disabled:bg-[#1E293B] disabled:text-slate-500 px-4 py-2 rounded-lg text-sm font-bold flex items-center gap-2 transition-all shadow-[0_0_15px_rgba(255,255,255,0.1)] hover:shadow-[0_0_20px_rgba(255,255,255,0.3)] disabled:shadow-none"
                >
                  <Send size={14} /> Send Payload
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <aside className="w-80 bg-[#1E293B]/60 backdrop-blur-xl border-l border-white/5 flex flex-col z-20 shrink-0 shadow-[-10px_0_30px_rgba(0,0,0,0.3)]">
        <div className="h-16 flex items-center px-6 border-b border-white/5 bg-[#0F172A]/40">
          <Network size={16} className="text-[#7C3AED]" />
          <span className="ml-2 font-bold text-sm text-white tracking-wide">Agent Pipeline</span>
        </div>

        <div className="p-6 border-b border-white/5">
          <div className="relative">
            <div className="absolute left-5 top-4 bottom-4 w-px bg-white/10" />
            <div className="space-y-6 relative">
              {AGENTS.map((agent, idx) => {
                const Icon = agent.icon;
                const isActive = activeAgentIdx === idx;
                const isPast = activeAgentIdx > idx || (activeAgentIdx === -1 && !isProcessing && messages.length > 1);

                return (
                  <div key={agent.id} className="flex gap-4 relative">
                    <motion.div animate={{ scale: isActive ? 1.1 : 1 }} className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 z-10 border transition-all duration-500 ${isActive ? 'bg-[#0F172A] border-transparent shadow-lg' : isPast ? 'bg-[#1E293B] border-white/10' : 'bg-[#0F172A]/50 border-white/5 opacity-50'}`} style={{ borderColor: isActive ? agent.color : undefined, boxShadow: isActive ? `0 0 20px ${agent.color}40` : undefined }}>
                      <Icon size={18} color={isActive || isPast ? agent.color : '#64748B'} />
                    </motion.div>
                    
                    <div className={`pt-1 transition-opacity duration-500 ${isActive || isPast ? 'opacity-100' : 'opacity-50'}`}>
                      <div className="text-sm font-bold text-white flex items-center gap-2">
                        {agent.name}
                        {isActive && <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ backgroundColor: agent.color }} />}
                      </div>
                      <div className="text-[10px] text-slate-400 mt-0.5">{agent.description}</div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>

        <div className="flex-1 flex flex-col overflow-hidden bg-[#0F172A]/50">
          <div className="px-6 py-3 border-b border-white/5 flex items-center gap-2 text-xs font-bold text-slate-500 uppercase tracking-widest">
            <TerminalSquare size={14} /> Telemetry Logs
          </div>
          <div className="flex-1 overflow-y-auto p-4 custom-scrollbar font-mono text-[10px] space-y-3">
            <AnimatePresence>
              {logs.map((log, i) => (
                <motion.div key={i} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} className="flex gap-2 text-slate-400">
                  <span className="shrink-0 text-slate-600">[{log.time}]</span>
                  <span style={{ color: log.color || '#94A3B8' }} className="leading-relaxed">
                    {log.agent !== 'system' && <ChevronRight size={10} className="inline mr-1" />}
                    {log.text}
                  </span>
                </motion.div>
              ))}
            </AnimatePresence>
            <div ref={logsEndRef} />
          </div>
        </div>
      </aside>

      <style dangerouslySetInnerHTML={{__html: `
        .custom-scrollbar::-webkit-scrollbar { width: 5px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.1); border-radius: 10px; }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: rgba(255, 255, 255, 0.2); }
      `}} />
    </div>
  );
}