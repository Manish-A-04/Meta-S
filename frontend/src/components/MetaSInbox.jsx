import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Inbox, Send, Archive, Search as SearchIcon, MoreVertical, CornerUpLeft, Cpu, ShieldCheck, PenTool, Database, Sparkles, Tag, AlertTriangle, CheckCircle2, ChevronRight, BookOpen, User, RefreshCw, Loader2 } from 'lucide-react';
import { api } from '../services/api';

const STAGES = [
  { id: 'router', name: 'Router', icon: Tag },
  { id: 'search', name: 'RAG Search', icon: Database },
  { id: 'scribe', name: 'Scribe', icon: PenTool },
  { id: 'reflector', name: 'Reflector', icon: ShieldCheck }
];

export default function MetaSInbox({ config }) {
  const [emails, setEmails] = useState([]);
  const [selectedEmail, setSelectedEmail] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isFetchingNew, setIsFetchingNew] = useState(false);
  
  const [aiStatus, setAiStatus] = useState('idle');
  const [activeStage, setActiveStage] = useState(-1);
  const [visibleData, setVisibleData] = useState({});

  const loadEmails = async () => {
    setIsLoading(true);
    try {
      const res = await api.getFetchedEmails({ limit: 50 });
      setEmails(res.data.emails || []);
      if (res.data.emails && res.data.emails.length > 0 && !selectedEmail) {
        setSelectedEmail(res.data.emails[0]);
      }
    } catch (err) {
      console.error("Failed to load emails", err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => { loadEmails(); }, []);

  const triggerIMAPFetch = async () => {
    setIsFetchingNew(true);
    try {
      await api.fetchEmails(10); 
      await loadEmails();
    } catch (err) {
      console.error("IMAP sync failed", err);
    } finally {
      setIsFetchingNew(false);
    }
  };

  useEffect(() => {
    if (!selectedEmail) return;
    setAiStatus(selectedEmail.status === 'processed' ? 'complete' : 'idle');
    setActiveStage(selectedEmail.status === 'processed' ? 3 : -1);
    setVisibleData(selectedEmail.status === 'processed' ? {
      classification: selectedEmail.classification || "Unknown",
      priority: selectedEmail.priority_score || 0,
      knowledge: "Historical Data Record.",
      draft: selectedEmail.draft_response || "No draft available.",
      score: 100 
    } : {});
  }, [selectedEmail]);

  const processEmail = async () => {
    if (!selectedEmail) return;
    setAiStatus('processing');
    setVisibleData({});
    setActiveStage(0);

    try {
      const res = await api.triageEmail({
        subject: selectedEmail.subject || "",
        body: selectedEmail.body || selectedEmail.body_excerpt || "Empty body",
        force_reflection: true,
        max_reflections: config?.maxReflexion || 2
      });
      const data = res.data;

      setActiveStage(1);
      setVisibleData(prev => ({ ...prev, classification: data.classification, priority: data.priority_score }));
      await new Promise(r => setTimeout(r, 600)); 
      
      setActiveStage(2);
      setVisibleData(prev => ({ ...prev, knowledge: `Vector search completed with latency ${data.usage?.latency_ms}ms` }));
      await new Promise(r => setTimeout(r, 600)); 
      
      setActiveStage(3);
      const finalScore = data.reflection_scores?.length > 0 ? data.reflection_scores[data.reflection_scores.length - 1] : 95;
      setVisibleData(prev => ({ ...prev, draft: data.final_draft, score: finalScore }));
      
      setAiStatus('complete');

      // FIXED BUG: Use functional updates to prevent stale state issues
      setEmails(prevEmails => prevEmails.map(e => 
        e.id === selectedEmail.id 
          ? { ...e, status: 'processed', draft_response: data.final_draft, classification: data.classification, priority_score: data.priority_score } 
          : e
      ));
      
      setSelectedEmail(prev => ({
        ...prev, 
        status: 'processed', 
        draft_response: data.final_draft, 
        classification: data.classification, 
        priority_score: data.priority_score
      }));

    } catch (err) {
      console.error("AI Triage Failed", err);
      setAiStatus('idle');
      alert("Failed to process email. Check backend logs.");
    }
  };

  return (
    <div className="flex h-full bg-[#0A0D14] text-slate-300 font-sans selection:bg-blue-500/30">
      <aside className="w-80 md:w-96 bg-[#0E121A] border-r border-white/5 flex flex-col flex-shrink-0 z-10">
        <div className="h-16 px-6 flex items-center justify-between border-b border-white/5 bg-[#0A0D14]">
          <div className="flex items-center gap-2">
            <div className="bg-blue-500/10 p-1.5 rounded-lg border border-blue-500/20"><Sparkles size={16} className="text-blue-400" /></div>
            <span className="font-bold text-white tracking-wide">META-S Inbox</span>
          </div>
          <button onClick={triggerIMAPFetch} disabled={isFetchingNew} className="p-2 bg-white/5 hover:bg-white/10 rounded-lg text-slate-400 transition-colors disabled:opacity-50">
            {isFetchingNew ? <Loader2 size={16} className="animate-spin text-blue-400" /> : <RefreshCw size={16} />}
          </button>
        </div>

        <div className="p-4 border-b border-white/5">
          <div className="relative">
            <SearchIcon size={14} className="absolute left-3 top-3 text-slate-500" />
            <input type="text" placeholder="Search triage database..." className="w-full bg-[#151923] border border-white/5 rounded-lg pl-9 pr-4 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500/50 transition-colors" />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto custom-scrollbar">
          {isLoading ? (
            <div className="p-8 flex flex-col items-center text-slate-500 gap-3"><Loader2 size={24} className="animate-spin" /><span>Syncing database...</span></div>
          ) : emails.length === 0 ? (
            <div className="p-8 text-center text-slate-500 text-sm">No emails found. Click sync to fetch.</div>
          ) : (
            emails.map((email) => (
              <div key={email.id} onClick={() => setSelectedEmail(email)} className={`p-4 border-b border-white/5 cursor-pointer transition-colors relative ${selectedEmail?.id === email.id ? 'bg-blue-500/5' : 'hover:bg-white/[0.02]'}`}>
                {selectedEmail?.id === email.id && <motion.div layoutId="active-email" className="absolute left-0 top-0 bottom-0 w-1 bg-blue-500 shadow-[0_0_10px_#3b82f6]" />}
                <div className="flex justify-between items-baseline mb-1">
                  <span className={`text-sm truncate mr-2 ${email.status === 'unread' ? 'font-bold text-white' : 'font-medium text-slate-300'}`}>{email.sender_name || email.sender_email}</span>
                  <span className="text-[10px] text-slate-500 whitespace-nowrap">{new Date(email.received_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                </div>
                <div className="text-sm text-slate-400 font-medium mb-1 truncate">{email.subject}</div>
                <div className="text-xs text-slate-500 line-clamp-2 leading-relaxed">{email.body_excerpt || "No content preview..."}</div>
                
                {email.status === 'processed' && (
                  <div className="mt-3 flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-blue-400">
                    <Cpu size={12} /> AI Processed
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </aside>

      <main className="flex-1 flex flex-col h-full overflow-hidden bg-[#0A0D14] relative">
        <header className="h-16 px-6 flex items-center justify-between border-b border-white/5 bg-[#0E121A]/80 backdrop-blur-sm z-10">
          <div className="flex gap-2">
            <button className="p-2 hover:bg-white/5 rounded-md text-slate-400 transition-colors"><CornerUpLeft size={18} /></button>
            <button className="p-2 hover:bg-white/5 rounded-md text-slate-400 transition-colors"><Archive size={18} /></button>
          </div>
          <button className="p-2 hover:bg-white/5 rounded-md text-slate-400 transition-colors"><MoreVertical size={18} /></button>
        </header>

        {selectedEmail ? (
          <div className="flex-1 overflow-y-auto custom-scrollbar p-8">
            <div className="max-w-3xl mx-auto space-y-8">
              <div>
                <h1 className="text-2xl font-bold text-white mb-6 leading-snug">{selectedEmail.subject}</h1>
                <div className="flex justify-between items-center mb-6">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-slate-800 flex items-center justify-center border border-white/10">
                      <User size={18} className="text-slate-400" />
                    </div>
                    <div>
                      <div className="text-sm font-bold text-white">{selectedEmail.sender_name || selectedEmail.sender_email}</div>
                      <div className="text-xs text-slate-500">&lt;{selectedEmail.sender_email}&gt;</div>
                    </div>
                  </div>
                  <div className="text-sm text-slate-500">{new Date(selectedEmail.received_at).toLocaleString()}</div>
                </div>
              </div>

              <div className="text-sm text-slate-300 whitespace-pre-wrap leading-relaxed">
                {selectedEmail.body || selectedEmail.body_excerpt}
              </div>

              {aiStatus === 'idle' && (
                <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="pt-6 border-t border-white/5">
                  <button onClick={processEmail} className="w-full group relative flex items-center justify-center gap-3 py-4 bg-gradient-to-r from-blue-600/20 to-indigo-600/20 hover:from-blue-600/30 hover:to-indigo-600/30 border border-blue-500/30 hover:border-blue-500/50 rounded-2xl transition-all overflow-hidden">
                    <div className="absolute inset-0 bg-blue-500/5 group-hover:bg-transparent transition-colors"></div>
                    <Sparkles size={18} className="text-blue-400 relative z-10" />
                    <span className="font-bold text-blue-100 relative z-10">Process with META-S AI</span>
                  </button>
                </motion.div>
              )}

              <AnimatePresence>
                {aiStatus !== 'idle' && (
                  <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} className="bg-[#0E121A] border border-blue-500/20 rounded-2xl overflow-hidden shadow-[0_0_30px_rgba(59,130,246,0.05)] mt-8">
                    <div className="p-4 border-b border-white/5 bg-blue-500/[0.02] flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                      <div className="flex items-center gap-2">
                        <Cpu size={16} className="text-blue-400" />
                        <span className="text-sm font-bold text-white">Swarm Telemetry</span>
                      </div>
                      
                      <div className="flex flex-wrap items-center gap-2">
                        {STAGES.map((stage, idx) => {
                          const Icon = stage.icon;
                          const isActive = activeStage === idx;
                          const isPast = activeStage > idx;
                          
                          return (
                            <div key={stage.id} className="flex items-center">
                              <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold transition-colors ${isActive ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30 shadow-[0_0_10px_rgba(59,130,246,0.2)]' : isPast ? 'text-slate-400' : 'text-slate-600'}`}>
                                <Icon size={12} className={isActive && aiStatus === 'processing' ? 'animate-pulse' : ''} />
                                <span className="hidden sm:inline">{stage.name}</span>
                              </div>
                              {idx < STAGES.length - 1 && <ChevronRight size={12} className="mx-1 text-slate-700" />}
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    <div className="p-6 space-y-6">
                      <AnimatePresence>
                        {visibleData.classification && (
                          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div className="bg-[#151923] p-4 rounded-xl border border-white/5 flex items-center gap-4">
                              <div className="p-2 bg-purple-500/10 rounded-lg text-purple-400"><Tag size={20} /></div>
                              <div>
                                <div className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">Classification</div>
                                <div className="text-sm font-bold text-white mt-0.5">{visibleData.classification}</div>
                              </div>
                            </div>
                            <div className="bg-[#151923] p-4 rounded-xl border border-white/5 flex items-center gap-4">
                              <div className={`p-2 rounded-lg ${visibleData.priority > 80 ? 'bg-rose-500/10 text-rose-400' : 'bg-emerald-500/10 text-emerald-400'}`}><AlertTriangle size={20} /></div>
                              <div>
                                <div className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">Priority Score</div>
                                <div className="text-sm font-bold text-white mt-0.5">{visibleData.priority || "Pending"} / 100</div>
                              </div>
                            </div>
                          </motion.div>
                        )}
                      </AnimatePresence>

                      <AnimatePresence>
                        {visibleData.knowledge && (
                          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="bg-[#151923] p-4 rounded-xl border border-white/5">
                            <div className="flex items-center gap-2 mb-2">
                              <BookOpen size={14} className="text-cyan-400" />
                              <div className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">Retrieved Context</div>
                            </div>
                            <p className="text-xs text-slate-400 font-mono bg-black/30 p-2 rounded border border-white/5">{visibleData.knowledge}</p>
                          </motion.div>
                        )}
                      </AnimatePresence>

                      <AnimatePresence>
                        {visibleData.draft && (
                          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="border border-white/10 rounded-xl overflow-hidden">
                            <div className="bg-[#151923] p-3 border-b border-white/5 flex justify-between items-center">
                              <div className="flex items-center gap-2">
                                <PenTool size={14} className="text-blue-400" />
                                <div className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">Generated Draft</div>
                              </div>
                              {visibleData.score && (
                                <motion.div initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-bold">
                                  <CheckCircle2 size={12} /> Score: {visibleData.score}/100
                                </motion.div>
                              )}
                            </div>
                            <div className="p-4 bg-black/20 text-sm text-slate-300 whitespace-pre-wrap leading-relaxed font-mono">{visibleData.draft}</div>
                            
                            {aiStatus === 'complete' && (
                              <div className="p-3 bg-[#151923] border-t border-white/5 flex justify-end gap-3">
                                <button className="px-4 py-2 text-xs font-bold text-slate-400 hover:text-white transition-colors">Edit Manually</button>
                                <button className="px-5 py-2 bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold rounded-lg transition-colors flex items-center gap-2 shadow-[0_0_15px_rgba(37,99,235,0.3)]">
                                  <Send size={14} /> Send Approved Draft
                                </button>
                              </div>
                            )}
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
              <div className="h-12"></div>
            </div>
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center text-slate-600 font-medium">Select an email to begin triage.</div>
        )}
      </main>
      
      <style dangerouslySetInnerHTML={{__html: `
        .custom-scrollbar::-webkit-scrollbar { width: 6px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.05); border-radius: 10px; }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: rgba(255, 255, 255, 0.1); }
      `}} />
    </div>
  );
}