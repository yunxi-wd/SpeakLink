/** Graph progress reports actual pipeline boundaries and never marks failures complete. */
import { describe, expect, it } from 'vitest';
import { graphProgress } from '../src/components/ProcessingProgress';
import type { AgentRun } from '../src/api/client';
const run = (current_step: string, status: AgentRun['status'] = 'running') => ({ current_step, status } as AgentRun);
describe('graph progress boundaries', () => {
  it('only reports 100 after a committed completed run', () => {
    expect(graphProgress(run('commit')).percent).toBe(95);
    expect(graphProgress(run('commit','failed')).percent).toBe(95);
    expect(graphProgress(run('completed','completed')).percent).toBe(100);
  });
  it('shows rework at the current stage rather than invented elapsed progress', () => {
    expect(graphProgress(run('extractor')).index).toBe(2);
    expect(graphProgress(run('restore')).label).toContain('人工校正');
    expect(graphProgress(run('queued','queued')).percent).toBe(0);
  });
});
