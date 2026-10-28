/** Accessible progress indicator: measured upload/ASR coverage or named graph stages. */
'use client';
import { useEffect, useState } from 'react';
import type { AgentRun } from '@/api/client';

export const graphStages = [
  ['queued', '等待执行'], ['summary', '提炼要点'], ['extractor', '抽取关系'],
  ['reviewer', '核对证据'], ['convergence', '收敛与聚类'], ['commit', '保存图谱'],
] as const;

/** Percent represents completed stage boundaries, never a prediction of model runtime. */
export function graphProgress(run: AgentRun): { percent: number; index: number; label: string } {
  if (run.status === 'completed') return { percent: 100, index: 6, label: '卡片与知识图谱已生成' };
  if (run.current_step === 'restore') return { percent: 55, index: 3, label: '恢复候选与人工校正' };
  const index = Math.max(0, graphStages.findIndex(([key]) => key === run.current_step));
  return { percent: [0, 10, 30, 55, 80, 95][index], index, label: graphStages[index][1] };
}

/** Render live stage, optional known percentage, elapsed time and a compact step list. */
export default function ProcessingProgress({ title, detail, percent, stages, activeIndex = 0, failed = false, running = true }: {
  title: string; detail: string; percent: number | null; stages: readonly string[];
  activeIndex?: number; failed?: boolean; running?: boolean;
}) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => setElapsed(s => s + 1), 1000);
    return () => clearInterval(timer);
  }, [running]);
  return <section className={`processing-progress${failed ? ' has-error' : ''}`} aria-label="处理进度" data-testid="processing-progress">
    <div className="processing-heading"><strong role="status" aria-live="polite">{title}</strong><span>{failed ? '已停止' : percent === null ? '准备中' : `${Math.round(percent)}%`}{running && <small> · 已用时 {elapsed}s</small>}</span></div>
    <div className={`processing-track${percent === null && running ? ' is-indeterminate' : ''}`} role="progressbar" aria-label={title}
      aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent ?? undefined} aria-valuetext={`${title}。${detail}`}>
      <div className="processing-fill" style={{ width: percent === null ? '32%' : `${percent}%` }} />
    </div>
    <p className="processing-detail">{detail}</p>
    <ol className="processing-steps">{stages.map((label, index) => <li key={label} className={index < activeIndex ? 'done' : index === activeIndex ? 'current' : ''}
      aria-current={index === activeIndex ? 'step' : undefined}><i>{index < activeIndex ? '✓' : index + 1}</i>{label}</li>)}</ol>
  </section>;
}

/** Keep graph processing visible above all workspace tabs, including after refresh. */
export function GraphProcessingProgress({ run }: { run: AgentRun }) {
  const view = graphProgress(run), running = ['queued', 'running'].includes(run.status);
  const failed = !running && run.status !== 'completed';
  return <ProcessingProgress title={failed ? '图谱整理未完成' : view.label} percent={view.percent} failed={failed} running={running}
    stages={graphStages.map(([, label]) => label)} activeIndex={view.index}
    detail={failed ? run.error || '请检查整理记录后重试。' : run.status === 'completed' ? '结果已保存，可在图谱与卡片视图查看。' :
      `阶段进度，非剩余时间估算${run.rounds ? ` · 第 ${run.rounds + 1} 轮核对` : ''}。可以切换标签，刷新后也能恢复图谱整理进度。`} />;
}
