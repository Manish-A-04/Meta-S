import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Network, Database, PenTool, ShieldCheck, Mail, Play, FileJson, FileText, CheckCircle2, Loader2, Cpu } from 'lucide-react';

const AGENTS = [
  { id: 'router', name: 'Router Agent', icon: Network, color: 'text-purple-400', border: 'border-purple-500/50', bg: 'bg-purple-500/10' },
  { id: 'search', name: 'Search (RAG)', icon: Database, color: 'text-cyan-400', border: 'border-cyan-500/50', bg: 'bg-cyan-500/10' },
  { id: 'scribe', name: 'Scribe Agent', icon: PenTool, color: 'text-blue-400', border: 'border-blue-500/50', bg: 'bg-blue-500/10' },
  { id: 'reflector', name: 'Reflector', icon: ShieldCheck, color: 'text-emerald-400', border: 'border-emerald-500/50', bg: 'bg-emerald-500/10' }
];

const MOCK_OUTPUTS = {
  router: { type: 'json', title: 'Classification Matrix', data: "{\n  \"intent\": \"support_request\",\n  \"urgency\": \"high\",\n  \"domain\": \"billing\",\n  \"route_to\": \"rag_search\",\n  \"confidence_score\": 0.94\n}" },
  search: { type: 'docs', title: 'Vector Retrieval', data: "CHUNK [ID: 8472]: 'Refund policies dictate that enterprise tier users are eligible for pro-rated refunds if downtime exceeds 4 hours...'\n\nCHUNK [ID: 9102]: 'To process a high-urgency billing tier adjustment, refer to internal doc #A-14...'" },
  scribe: { type: 'text', title: 'Initial Draft Generation', data: "Dear Customer,\n\nWe apologize for the inconvenience regarding your billing tier. Based on our SLA, you are eligible for a pro-rated refund due to the recent 4-hour downtime. I have initiated this process for you.\n\nBest,\nSupport Team" },
  reflector: { type: 'score', title: 'Quality Evaluation', data: "SCORE: 92/100\n\nCRITIQUE: The tone is appropriately empathetic and directly addresses the high urgency intent classified by the Router. It accurately utilizes CHUNK 8472 from the knowledge base.\n\nACTION: Approved for dispatch." }
};

const DataTransferLine = ({ isActive, isPast }) => (
  <div className="flex-1 h-1 mx-2 relative bg-white/5 rounded-full overflow-hidden min-w-[40px]">
    <div className={`absolute inset-0 transition-colors duration-500 ${isPast ? 'bg-cyan-500/30' : 'bg-transparent'}`} />
    {isActive && (
      <motion.div initial={{ x: '-100%' }} animate={{ x: '400%' }} transition={{ repeat: Infinity, duration: 1.2, ease: "linear" }} className="absolute top-0 bottom-0 w-1/3 bg-gradient-to-r from-transparent via-cyan-400 to-transparent shadow-[0_0_10px_#22d3ee]" />
    )}
  </div>
);

const OutputDisplay = ({ output }) => {
  if (!output) return (
    <div className="h-full flex flex-col items-center justify-center text-slate-600 space-y-3">
      <Cpu size={32} className="opacity-20" />
      <p className="text-sm">Awaiting telemetry data...</p>
    </div>
  );

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="h-full flex flex-col">
      <div className="flex items-center gap-2 mb-3 pb-2 border-b border-white/10">
        {output.type === 'json' && <FileJson size={16} className="text-purple-400" />}
        {output.type === 'docs' && <Database size={16} className="text-cyan-400" />}
        {output.type === 'text' && <FileText size={16} className="text-blue-400" />}
        {output.type === 'score' && <CheckCircle2 size={16} className="text-emerald-400" />}
        <span className="text-xs font-bold text-slate-300 uppercase tracking-widest">{output.title}</span>
      </div>
      <div className="flex-1 bg-[#060913] rounded-xl p-4 overflow-y-auto custom-scrollbar border border-white/5 shadow-inner">
        <pre className={`text-sm font-mono whitespace-pre-wrap leading-relaxed ${output.type === 'json' ? 'text-purple-300' : output.type === 'docs' ? 'text-cyan-300' : output.type === 'score' ? 'text-emerald-300' : 'text-slate-300'}`}>
          {output.data}
        </pre>
      </div>
    </motion.div>
  );
};

export default function AgentWorkflowVisualizer() {
  const [email, setEmail] = useState('URGENT: Our production server has been down for 5 hours and we are on the Enterprise billing tier. We need a pro-rated refund processed immediately as per the SLA.');
  const [status, setStatus] = useState('idle'); 
  const [activeStep, setActiveStep] = useState(-1);
  const [currentOutput, setCurrentOutput] = useState(null);

  const startSimulation = async () => {
    if (!email.trim() || status === 'processing') return;
    setStatus('processing');
    setActiveStep(-1);
    setCurrentOutput(null);

    const steps = [
      { agent: 0, delay: 600, key: 'router' },
      { agent: 1, delay: 2000, key: 'search' },
      { agent: 2, delay: 2500, key: 'scribe' },
      { agent: 3, delay: 2000, key: 'reflector' }
    ];

    for (const step of steps) {
      setActiveStep(step.agent);
      await new Promise(r => setTimeout(r, step.delay));
      setCurrentOutput(MOCK_OUTPUTS[step.key]);
      await new Promise(r => setTimeout(r, 1200)); 
    }
    setStatus('complete');
  };

  return (
    <div className="h-full overflow-y-auto bg-[#030509] p-8 text-slate-200 font-sans selection:bg-cyan-500/30">
      <div className="max-w-6xl mx-auto space-y-8">
        <div className="mb-10">
          <h1 className="text-3xl font-black text-transparent bg-clip-text bg-gradient-to-r from-purple-400 via-cyan-400 to-emerald-400 tracking-tight mb-2">META-S Architecture</h1>
          <p className="text-slate-400 text-sm">Real-time Multi-Agent Swarm Visualization</p>
        </div>

        <div className="bg-[#0B0F17]/80 backdrop-blur-xl border border-white/10 rounded-2xl p-1 relative overflow-hidden shadow-2xl">
          <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-purple-500 via-cyan-500 to-emerald-500 opacity-50"></div>
          <div className="p-5 flex flex-col md:flex-row gap-4">
            <div className="flex-1 relative">
              <div className="absolute top-3 left-3 text-slate-500"><Mail size={18} /></div>
              <textarea value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Inject raw email payload..." className="w-full h-24 bg-black/40 border border-white/5 rounded-xl pl-10 pr-4 py-3 text-sm text-slate-300 focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/50 transition-all resize-none custom-scrollbar font-mono" />
            </div>
            <button onClick={startSimulation} disabled={status === 'processing' || !email.trim()} className="md:w-48 h-24 rounded-xl font-bold text-sm text-white bg-white/5 border border-white/10 hover:bg-white/10 transition-all shadow-lg flex flex-col items-center justify-center gap-2 group disabled:opacity-50 disabled:cursor-not-allowed">
              {status === 'processing' ? (<><Loader2 size={24} className="animate-spin text-cyan-400" /> Processing...</>) : status === 'complete' ? (<><CheckCircle2 size={24} className="text-emerald-400" /> Re-run Swarm</>) : (<><Play size={24} className="text-purple-400 group-hover:scale-110 transition-transform" /> Initialize Pipeline</>)}
            </button>
          </div>
        </div>

        <div className="py-12 relative">
          <div className="absolute inset-0 bg-gradient-to-r from-purple-500/5 via-cyan-500/5 to-emerald-500/5 blur-3xl rounded-full pointer-events-none"></div>
          <div className="flex items-center justify-between relative z-10 w-full overflow-x-auto pb-8 custom-scrollbar">
            <div className="flex items-center min-w-max px-4 w-full">
              {AGENTS.map((agent, index) => {
                const isActive = activeStep === index;
                const isPast = activeStep > index || status === 'complete';
                const Icon = agent.icon;

                return (
                  <React.Fragment key={agent.id}>
                    <motion.div animate={{ y: isActive ? [-4, 4, -4] : 0, scale: isActive ? 1.05 : 1 }} transition={{ y: { repeat: Infinity, duration: 2, ease: "easeInOut" }, scale: { duration: 0.3 } }} className={`relative flex flex-col items-center w-36 shrink-0 rounded-2xl p-4 transition-all duration-500 ${isActive ? `bg-[#0B0F17] border ${agent.border} shadow-[0_0_30px_rgba(0,0,0,0.5)] z-20` : isPast ? 'bg-[#0B0F17]/80 border-white/10 opacity-70' : 'bg-[#0B0F17]/40 border-white/5 opacity-50'}`}>
                      {isActive && <div className={`absolute -inset-0.5 rounded-2xl ${agent.bg} blur-md -z-10 animate-pulse`}></div>}
                      <div className={`w-12 h-12 rounded-xl flex items-center justify-center mb-3 ${isActive ? agent.bg : 'bg-white/5'} ${isPast || isActive ? agent.color : 'text-slate-600'} transition-colors duration-500 border border-white/5`}>
                        <Icon size={24} />
                      </div>
                      <div className="text-xs font-bold text-white text-center">{agent.name}</div>
                      <div className="mt-2 text-[10px] font-mono tracking-wider uppercase">
                        {isActive ? (<span className={`${agent.color} flex items-center gap-1`}><Loader2 size={10} className="animate-spin"/> Working</span>) : isPast ? (<span className="text-emerald-500 flex items-center gap-1"><CheckCircle2 size={10}/> Done</span>) : (<span className="text-slate-600">Standby</span>)}
                      </div>
                    </motion.div>
                    {index < AGENTS.length - 1 && <DataTransferLine isActive={isActive && status === 'processing'} isPast={isPast} />}
                  </React.Fragment>
                );
              })}
            </div>
          </div>
        </div>

        <div className="h-80 bg-[#0B0F17]/90 backdrop-blur-xl border border-white/10 rounded-2xl p-6 shadow-2xl relative overflow-hidden flex flex-col">
           <div className="absolute top-0 left-0 right-0 h-1 bg-white/5 shadow-[0_0_15px_rgba(255,255,255,0.1)] animate-[scan_4s_ease-in-out_infinite_alternate] pointer-events-none"></div>
          <OutputDisplay output={currentOutput} />
        </div>
      </div>

      <style dangerouslySetInnerHTML={{__html: `
        .custom-scrollbar::-webkit-scrollbar { width: 6px; height: 6px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.1); border-radius: 10px; }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: rgba(255, 255, 255, 0.2); }
        @keyframes scan { 0% { transform: translateY(0); } 100% { transform: translateY(320px); } }
      `}} />
    </div>
  );
}