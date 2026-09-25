const CHANGES = {
  regression: {
    label: 'Régression',
    tally: ['régression', 'régressions'],
    color: '#fb7185',
    hint: 'Passait au run de référence, échoue maintenant.',
  },
  fixed: {
    label: 'Réparé',
    tally: ['réparé', 'réparés'],
    color: '#34d399',
    hint: 'Échouait au run de référence, passe maintenant.',
  },
  new: {
    label: 'Nouveau',
    tally: ['nouveau', 'nouveaux'],
    color: '#38bdf8',
    hint: 'Absent du run de référence : test nouveau, ou revenu dans le périmètre.',
  },
  known_failure: {
    label: 'Échec connu',
    tally: ['échec connu', 'échecs connus'],
    color: '#94a3b8',
    hint: 'Échouait déjà au run de référence : rien de neuf, mais rien de réglé.',
  },
  out_of_scope: {
    label: 'Hors périmètre',
    tally: ['hors périmètre', 'hors périmètre'],
    color: '#94a3b8',
    hint: "Joué au run de référence, pas cette fois : filtré, ignoré ou supprimé. Ce n'est pas une réparation.",
  },
};

const ORDER = ['regression', 'fixed', 'new', 'known_failure', 'out_of_scope'];

const formatMoment = (ts) =>
  typeof ts === 'number'
    ? new Date(ts * 1000).toLocaleString('fr-FR', {
        day: 'numeric',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
      })
    : 'un run précédent';

/**
 * Nombre de changements qui méritent d'interrompre quelqu'un : les régressions dont on
 * est sûr. Une transition portée par un test instable n'en fait pas partie - c'est
 * précisément ce que cette page cherche à ne plus faire sonner.
 */
export function alertCount(diff) {
  if (!diff || !Array.isArray(diff.changes)) return 0;
  return diff.changes.filter((change) => change.change === 'regression' && !change.flaky).length;
}

function ChangeRow({ change }) {
  const meta = CHANGES[change.change] || CHANGES.known_failure;
  return (
    <article className="health-row diff-row" style={{ '--verdict': meta.color }}>
      <span className="health-verdict" title={meta.hint}>
        {meta.label}
      </span>
      <span className="health-id">
        <strong>{change.name}</strong>
        <em>{change.source}</em>
      </span>
      {change.flaky && (
        <span
          className="diff-flaky"
          title="Ce test alterne sans que le code ait bougé : la transition ne prouve rien."
        >
          Instable
        </span>
      )}
      {change.message && <p className="health-message">{change.message}</p>}
    </article>
  );
}

function Reference({ diff }) {
  const { run, baseline, same_commit: sameCommit } = diff;
  return (
    <p className="diff-reference">
      Face au run du <strong>{formatMoment(baseline.ts)}</strong>
      {baseline.commit && run.commit && (
        <>
          {' · '}
          {sameCommit ? (
            <span className="diff-commit">même commit {run.commit}</span>
          ) : (
            <span className="diff-commit">
              {baseline.commit} → {run.commit}
            </span>
          )}
        </>
      )}
    </p>
  );
}

/**
 * Vue « Ce qui a changé » : les transitions du dernier run face au dernier run de même
 * périmètre. Lecture seule.
 */
export default function DiffView({ diff }) {
  if (!diff) return <p className="health-empty">Chargement…</p>;
  if (!diff.run) {
    return (
      <p className="health-empty">
        Aucun run enregistré pour l&apos;instant : il n&apos;y a rien à comparer.
      </p>
    );
  }
  if (!diff.baseline) {
    return (
      <p className="health-empty">
        Premier run de cette configuration - environnement, navigateur, appareil et périmètre
        doivent concorder pour qu&apos;une comparaison veuille dire quelque chose.
      </p>
    );
  }

  const changes = diff.changes || [];
  const counts = diff.counts || {};

  return (
    <>
      <Reference diff={diff} />

      {diff.same_commit && counts.regression > 0 && (
        <p className="diff-warning">
          Le code n&apos;a pas bougé entre les deux runs : cette différence vient de
          l&apos;environnement, de la donnée ou du test lui-même, pas du produit.
        </p>
      )}

      {changes.length === 0 ? (
        <p className="health-empty">Rien n&apos;a changé depuis ce run.</p>
      ) : (
        <>
          <div className="diff-counts">
            {ORDER.filter((kind) => counts[kind] > 0).map((kind) => (
              <span key={kind} style={{ '--verdict': CHANGES[kind].color }}>
                <b>{counts[kind]}</b> {CHANGES[kind].tally[counts[kind] > 1 ? 1 : 0]}
              </span>
            ))}
          </div>

          <div className="health-list">
            {changes.map((change) => (
              <ChangeRow key={change.test} change={change} />
            ))}
          </div>
        </>
      )}
    </>
  );
}
