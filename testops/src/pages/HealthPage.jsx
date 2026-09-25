import { useEffect, useMemo, useState } from 'react';
import DiffView, { alertCount } from '../components/health/diff';
import { API_BASE_URL } from '../config/api';
import '../css/HealthPage.css';

const VERDICTS = {
  instable: {
    label: 'Instable',
    color: '#fbbf24',
    hint: 'A donné deux verdicts différents sans que le code ait bougé, ou a trop alterné.',
  },
  cassé: {
    label: 'Cassé',
    color: '#fb7185',
    hint: "N'est jamais passé sur la fenêtre : test à réparer, ou vrai défaut du produit.",
  },
  neuf: {
    label: 'Neuf',
    color: '#94a3b8',
    hint: 'Moins de cinq exécutions : aucun verdict rendu.',
  },
  stable: {
    label: 'Stable',
    color: '#34d399',
    hint: 'Rien à signaler.',
  },
};

const STATUS_DOT = {
  PASS: { color: '#34d399', label: 'réussi' },
  FAIL: { color: '#fb7185', label: 'échoué' },
};

// Au-delà, la frise n'apprend plus rien et déborde de la ligne.
const FRIEZE_MAX = 14;

const formatDuration = (ms) => {
  if (ms === null || ms === undefined) return '-';
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${ms} ms`;
};

function Frieze({ statuses }) {
  const shown = statuses.slice(-FRIEZE_MAX);
  return (
    <span className="health-frieze" aria-hidden="true">
      {shown.map((status, index) => {
        const dot = STATUS_DOT[status];
        return (
          <i
            key={`${status}-${index}`}
            className={dot ? '' : 'skipped'}
            style={dot ? { background: dot.color } : undefined}
            title={dot ? dot.label : 'ignoré'}
          />
        );
      })}
    </span>
  );
}

function TestRow({ test }) {
  const meta = VERDICTS[test.verdict] || VERDICTS.neuf;
  return (
    <article className="health-row" style={{ '--verdict': meta.color }}>
      <span className="health-verdict" title={meta.hint}>
        {meta.label}
      </span>
      <span className="health-id">
        <strong>{test.name}</strong>
        <em>{test.source}</em>
      </span>
      <Frieze statuses={test.statuses} />
      <span className="health-score">{`${test.passed}/${test.runs}`}</span>
      <span className="health-duration">{formatDuration(test.median_ms)}</span>
      {test.quarantined && (
        <span className="health-parked" title="Écarté des runs par le tag « quarantaine »">
          En quarantaine · {test.runs_since} run{test.runs_since > 1 ? 's' : ''}
        </span>
      )}
      {test.last_message && <p className="health-message">{test.last_message}</p>}
    </article>
  );
}

/**
 * Page « Santé de la suite » : ce que l'historique des exécutions dit de chaque test.
 * Lecture seule ; l'historique est mis à jour côté serveur à chaque ouverture.
 */
export default function HealthPage() {
  const [data, setData] = useState(null);
  const [diff, setDiff] = useState(null);
  const [error, setError] = useState(null);
  const [view, setView] = useState('health');
  const [filter, setFilter] = useState('all');

  useEffect(() => {
    fetch(`${API_BASE_URL}/suite-health`)
      .then((response) => response.json())
      .then(setData)
      .catch(() => setError("La santé de la suite n'a pas pu être chargée."));
  }, []);

  // Chargé à part : un diff manquant ne doit pas priver la page de son contenu principal.
  useEffect(() => {
    fetch(`${API_BASE_URL}/run-diff`)
      .then((response) => response.json())
      .then(setDiff)
      .catch(() => setDiff({ run: null, baseline: null, changes: [], counts: {} }));
  }, []);

  const filters = useMemo(() => {
    if (!data) return [];
    const entries = Object.entries(VERDICTS)
      .map(([id, meta]) => ({ id, label: meta.label, count: data.counts[id] || 0 }))
      .filter((entry) => entry.count > 0);
    if (data.quarantined) {
      entries.push({ id: 'quarantaine', label: 'Quarantaine', count: data.quarantined });
    }
    return [{ id: 'all', label: 'Tout', count: data.tests.length }, ...entries];
  }, [data]);

  const shown = useMemo(() => {
    if (!data) return [];
    if (filter === 'all') return data.tests;
    if (filter === 'quarantaine') return data.tests.filter((test) => test.quarantined);
    return data.tests.filter((test) => test.verdict === filter);
  }, [data, filter]);

  if (error) return <div className="health-page health-empty">{error}</div>;
  if (!data) return <div className="health-page health-empty">Chargement…</div>;

  const alerts = alertCount(diff);

  return (
    <div className="health-page">
      <header className="health-head">
        <h1>Santé de la suite</h1>
        <p>
          {view === 'health'
            ? `Ce que ${data.runs} run${data.runs > 1 ? 's' : ''} disent de chaque test. Un verdict n'est rendu qu'à partir de cinq exécutions : sur deux points, la stabilité ne veut rien dire.`
            : "Ce que le dernier run a changé, face au dernier run de même périmètre. Un test absent n'est jamais compté comme réparé, et une alternance connue n'est pas une régression."}
        </p>
      </header>

      <div className="health-tabs">
        <button type="button" aria-pressed={view === 'health'} onClick={() => setView('health')}>
          État des tests
        </button>
        <button type="button" aria-pressed={view === 'diff'} onClick={() => setView('diff')}>
          Ce qui a changé
          {alerts > 0 && (
            <span className="health-alert" title="Régressions sûres depuis le run de référence">
              {alerts}
            </span>
          )}
        </button>
        <a
          className="health-trends"
          href={`${API_BASE_URL}/health-dashboard`}
          target="_blank"
          rel="noopener noreferrer"
          title="Ouvre les tendances multi-runs dans un nouvel onglet. Le rapport est autonome : il se joint tel quel à un livrable."
        >
          Tendances ↗
        </a>
      </div>

      {view === 'diff' ? (
        <DiffView diff={diff} />
      ) : data.runs === 0 ? (
        <p className="health-empty">
          Aucun run enregistré pour l&apos;instant. L&apos;historique se remplit tout seul, à chaque
          exécution.
        </p>
      ) : (
        <>
          <div className="health-filters">
            {filters.map((entry) => (
              <button
                key={entry.id}
                type="button"
                aria-pressed={filter === entry.id}
                onClick={() => setFilter(entry.id)}
              >
                {entry.label} <span>{entry.count}</span>
              </button>
            ))}
          </div>

          <div className="health-list">
            {shown.map((test) => (
              <TestRow key={test.test} test={test} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
