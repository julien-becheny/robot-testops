// Un bloc = un test. Le direct envoie des lignes déjà typées, mais à plat : on les replie ici.
import { useMemo, useState } from 'react';
import { FiChevronRight, FiCopy } from 'react-icons/fi';

const SLOW_MS = 30000;

// « 🧪 Test: Connexion » → « Connexion ». Le listener préfixe, l'écran n'a pas à le répéter.
const testName = (text) =>
  text
    .replace(/^[^\p{L}]+/u, '')
    .replace(/^Test\s*(n°\s*\d+)?\s*:\s*/iu, '')
    .trim() || text;

const VERDICTS = { success: 'pass', error: 'fail', skip: 'skip' };
const STEP_TYPES = ['keyword', 'keyword-failed'];

export const groupLogs = (logs) => {
  const preamble = [];
  const blocks = [];
  let current = null;

  for (const log of logs) {
    if (log.type === 'test-start') {
      current = {
        id: log.executionId || `bloc-${blocks.length}`,
        name: testName(log.text),
        lines: [],
        verdict: null,
        startedAt: log.timestamp,
        endedAt: null,
      };
      blocks.push(current);
      continue;
    }
    if (!current) {
      preamble.push(log);
      continue;
    }
    current.lines.push(log);
    const verdict = VERDICTS[log.type];
    // La durée s'arrête au verdict : ce qui suit (le message d'erreur) n'est plus du test.
    if (verdict && !current.verdict) {
      current.verdict = verdict;
      current.endedAt = log.timestamp;
    }
  }

  const totals = blocks.reduce((acc, b) => acc.set(b.name, (acc.get(b.name) || 0) + 1), new Map());
  const seen = new Map();
  for (const block of blocks) {
    const n = (seen.get(block.name) || 0) + 1;
    seen.set(block.name, n);
    block.attempt = n;
    block.attempts = totals.get(block.name);
    block.ms =
      block.endedAt && block.startedAt ? new Date(block.endedAt) - new Date(block.startedAt) : null;
    block.steps = block.lines.filter((l) => STEP_TYPES.includes(l.type)).length;
  }

  return { preamble, blocks };
};

const formatMs = (ms) => {
  if (ms == null) return null;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  const m = Math.floor(ms / 60000);
  return `${m}m${String(Math.round((ms % 60000) / 1000)).padStart(2, '0')}`;
};

const errorText = (block) =>
  block.lines
    .filter((l) => l.type === 'error-detail' || l.type === 'error')
    .map((l) => l.text)
    .join('\n');

const VERDICT_MARK = { pass: '✓', fail: '✕', skip: '–' };

const LogBlock = ({ block, open, onToggle }) => {
  const running = block.verdict === null;
  const duration = formatMs(block.ms);
  const failed = block.verdict === 'fail';

  return (
    <div
      className={`log-block ${block.verdict || 'running'} ${open ? 'open' : ''} ${
        block.ms >= SLOW_MS ? 'slow' : ''
      }`}
    >
      <button
        type="button"
        className="log-block-head"
        aria-expanded={open}
        onClick={() => onToggle(block.id)}
      >
        <FiChevronRight size={13} className="log-block-chevron" />
        <span className="log-block-verdict" aria-hidden="true">
          {running ? <span className="log-block-dot" /> : VERDICT_MARK[block.verdict]}
        </span>
        <span className="log-block-name">{block.name}</span>
        {block.attempts > 1 && (
          <span className="log-block-attempt">
            essai {block.attempt}/{block.attempts}
          </span>
        )}
        {block.steps > 0 && (
          <span className="log-block-steps">
            {block.steps} étape{block.steps > 1 ? 's' : ''}
          </span>
        )}
        {duration && (
          <span
            className="log-block-time"
            title={block.ms >= SLOW_MS ? 'Nettement plus long que la moyenne' : undefined}
          >
            {duration}
          </span>
        )}
      </button>

      {open && (
        <div className="log-block-body">
          {block.lines.map((line, i) => (
            <div key={i} className={`log-block-line ${line.type}`}>
              {line.text}
            </div>
          ))}
          {failed && (
            <button
              type="button"
              className="log-block-action"
              onClick={() => navigator.clipboard?.writeText(`${block.name}\n${errorText(block)}`)}
            >
              <FiCopy size={12} /> Copier l&apos;erreur
            </button>
          )}
        </div>
      )}
    </div>
  );
};

export const LogBlockList = ({ logs, running = false }) => {
  const { preamble, blocks } = useMemo(() => groupLogs(logs), [logs]);
  // Un choix explicite prime toujours sur la règle d'ouverture par défaut.
  const [overrides, setOverrides] = useState({});

  // Un échec s'impose, un succès se tait, et le test en cours reste sous les yeux.
  const isOpen = (block) =>
    block.id in overrides
      ? overrides[block.id]
      : block.verdict === 'fail' || (running && block.verdict === null);

  const toggle = (block) => setOverrides((prev) => ({ ...prev, [block.id]: !isOpen(block) }));

  return (
    <>
      {preamble.map((log, i) => (
        <div key={`pre-${i}`} className={`log-line ${log.type}`}>
          {log.text}
        </div>
      ))}
      {blocks.map((block) => (
        <LogBlock
          key={block.id}
          block={block}
          open={isOpen(block)}
          onToggle={() => toggle(block)}
        />
      ))}
    </>
  );
};
