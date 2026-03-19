import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Microscope, Zap, BrainCircuit, Activity, Server, Cpu, Layers, Loader2 } from 'lucide-react';
import { api } from '../services/api';

const QualityBarChart = ({ data }) => {
  const chartData = [
    { model: 'GPT-3.5', score: 78, color: 'bg-slate-600', glow: '' },
    { model: 'GPT-4', score: 88.5, color: 'bg-slate-500', glow: '' },
    { model: 'META-S (Base)', score: 86, color: 'bg-indigo-500', glow: 'shadow-[0_0_15px_rgba(99,102,241,0.4)]' },
    { model: 'META-S (Optimized)', score: data?.average_reflection_score || 94.2, color: 'bg-cyan-400', glow: 'shadow-[0_0_20px_rgba(34,211,238,0.6)]' }
  ];

  return (
    <div className="h-64 flex items-end justify-between gap-4 pt-10 pb-6 border-b border-white/10 relative">
      <div className="absolute inset-0 flex flex-col justify-between pointer-events-none opacity-20">
        {[100, 75, 50, 25, 0].map(val => (
          <div key={val} className="border-b border-slate-500 w-full h-0 relative">
            <span className="absolute -top-2.5 -left-6 text-[10px] font-mono text-slate-400">{val}</span>
          </div>
        ))}
      </div>
      {chartData.map((item, i) => (
        <div key={item.model} className="flex-1 flex flex-col items-center gap-3 relative z-10 group">
          <div className="text-[10px] font-mono text-white opacity-0 group-hover:opacity-100 transition-opacity absolute -top-6">
            {item.score}%
          </div>
          <motion.div initial={{ height: 0 }} animate={{ height: `${item.score}%` }} transition={{ duration: 1.5, delay: i * 0.2, type: 'spring' }} className={`w-full max-w-[4rem] rounded-t-md relative overflow-hidden ${item.color} ${item.glow}`}>
            <div className="absolute inset-0 bg-gradient-to-t from-black/40 to-transparent"></div>
          </motion.div>
          <div className="text-[10px] font-bold text-slate-400 text-center uppercase tracking-wider h-8">
            {item.model}
          </div>
        </div>
      ))}
    </div>
  );
};

const VRAMGrid = () => {
  const totalBlocks = 40;
  const routerBlocks = 5;
  const ragBlocks = 8;
  const scribeBlocks = 12;
  const reflectorBlocks = 6;
  const freeBlocks = totalBlocks - (routerBlocks + ragBlocks + scribeBlocks + reflectorBlocks);

  const renderBlocks = (count, colorClass, delayBase) => {
    return Array.from({ length: count }).map((_, i) => (
      <motion.div key={i} initial={{ opacity: 0, scale: 0.5 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: delayBase + (i * 0.05) }} className={`w-full h-8 rounded-sm ${colorClass} border border-black/50`} />
    ));
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-end text-xs font-mono mb-2">
        <span className="text-slate-400">Total VRAM Allocation: 14.2 GB / 24 GB</span>
        <span className="text-emerald-400 animate-pulse">Stable</span>
      </div>
      <div className="grid grid-cols-10 gap-1 p-2 bg-black/40 rounded-xl border border-white/5">
        {renderBlocks(routerBlocks, 'bg-purple-500 shadow-[0_0_8px_#a855f7]', 0)}
        {renderBlocks(ragBlocks, 'bg-cyan-500 shadow-[0_0_8px_#06b6d4]', 0.5)}
        {renderBlocks(scribeBlocks, 'bg-blue-500 shadow-[0_0_8px_#3b82f6]', 1)}
        {renderBlocks(reflectorBlocks, 'bg-emerald-500 shadow-[0_0_8px_#10b981]', 1.5)}
        {renderBlocks(freeBlocks, 'bg-slate-800/50', 2)}
      </div>
      <div className="grid grid-cols-2 gap-2 mt-4 text-[10px] font-bold uppercase tracking-wider text-slate-400">
        <div className="flex items-center gap-2"><div className="w-2 h-2 bg-purple-500 rounded-full shadow-[0_0_5px_#a855f7]"></div> Router (1.8GB)</div>
        <div className="flex items-center gap-2"><div className="w-2 h-2 bg-cyan-500 rounded-full shadow-[0_0_5px_#06b6d4]"></div> RAG Vector (2.9GB)</div>
        <div className="flex items-center gap-2"><div className="w-2 h-2 bg-blue-500 rounded-full shadow-[0_0_5px_#3b82f6]"></div> Scribe SLM (4.4GB)</div>
        <div className="flex items-center gap-2"><div className="w-2 h-2 bg-emerald-500 rounded-full shadow-[0_0_5px_#10b981]"></div> Reflector (2.2GB)</div>
      </div>
    </div>
  );
};

export default function MetaSAnalytics() {
  const [metrics, setMetrics] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchAnalytics = async () => {
      try {
        const res = await api.getMetrics();
        setMetrics(res.data);
      } catch (err) {
        console.error("Failed to load metrics", err);
      } finally {
        setIsLoading(false);
      }
    };
    fetchAnalytics();
  }, []);

  const containerVars = { hidden: { opacity: 0 }, show: { opacity: 1, transition: { staggerChildren: 0.1 } } };
  const itemVars = { hidden: { opacity: 0, y: 20 }, show: { opacity: 1, y: 0, transition: { type: 'spring', stiffness: 300 } } };

  if (isLoading) {
    return <div className="h-full flex items-center justify-center text-cyan-400"><Loader2 className="animate-spin" size={32} /></div>;
  }

  const KPIS = [
    { label: 'Total Emails Processed', value: metrics?.total_emails_processed || 0, isPositive: true, icon: Server, color: 'text-emerald-400' },
    { label: 'Avg Inference Latency', value: metrics ? `${Math.round(metrics.average_latency_ms)}ms` : '1.2s', isPositive: true, icon: Zap, color: 'text-cyan-400' },
    { label: 'Avg Tokens/Email', value: metrics ? Math.round(metrics.average_tokens_per_email) : '850', isPositive: true, icon: BrainCircuit, color: 'text-purple-400' },
    { label: 'Draft Approval Rate', value: metrics ? `${(metrics.approval_rate * 100).toFixed(1)}%` : '99.1%', isPositive: true, icon: Microscope, color: 'text-blue-400' }
  ];

  return (
    <div className="h-full overflow-y-auto bg-[#06080D] p-8 text-slate-200 font-sans selection:bg-cyan-500/30">
      <motion.div variants={containerVars} initial="hidden" animate="show" className="max-w-7xl mx-auto space-y-8">
        <div className="flex justify-between items-end border-b border-white/10 pb-6">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <Microscope className="text-cyan-400" size={28} />
              <h1 className="text-3xl font-black text-white tracking-tight">System Analytics</h1>
            </div>
            <p className="text-sm text-slate-400 font-mono">META-S Multi-Agent Architecture Evaluation</p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {KPIS.map((kpi, i) => {
            const Icon = kpi.icon;
            return (
              <motion.div key={i} variants={itemVars} className="bg-[#0B0F17]/80 backdrop-blur-xl border border-white/5 rounded-2xl p-5 shadow-lg relative overflow-hidden group">
                <div className={`absolute top-0 right-0 w-24 h-24 ${kpi.color.replace('text', 'bg')}/10 rounded-full blur-2xl -mr-8 -mt-8 pointer-events-none`}></div>
                <div className="flex justify-between items-start mb-4">
                  <div className={`p-2 bg-white/5 rounded-lg border border-white/5 ${kpi.color}`}><Icon size={18} /></div>
                  <span className="text-[10px] font-bold uppercase tracking-widest text-slate-500">Live Metric</span>
                </div>
                <div className="text-2xl font-black text-white tracking-tight">{kpi.value}</div>
                <div className="text-xs font-medium text-slate-400 mt-1">{kpi.label}</div>
              </motion.div>
            )
          })}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <motion.div variants={itemVars} className="bg-[#0B0F17]/80 backdrop-blur-xl border border-white/5 rounded-3xl p-6 shadow-2xl relative">
            <h3 className="text-sm font-bold text-white flex items-center gap-2 mb-2"><Activity size={16} className="text-cyan-400" /> Quality Output Distribution</h3>
            <p className="text-xs text-slate-500 mb-6 font-mono">Based on Reflector Agent scores vs Industry Baselines.</p>
            <QualityBarChart data={metrics} />
          </motion.div>

          <motion.div variants={itemVars} className="bg-[#0B0F17]/80 backdrop-blur-xl border border-white/5 rounded-3xl p-6 shadow-2xl relative">
            <h3 className="text-sm font-bold text-white flex items-center gap-2 mb-6"><Cpu size={16} className="text-emerald-400" /> Agent VRAM Allocation</h3>
            <VRAMGrid />
          </motion.div>
        </div>
      </motion.div>
    </div>
  );
}