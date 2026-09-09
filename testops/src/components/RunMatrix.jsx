import { useMemo } from 'react';
import { FiCheck, FiX, FiMinus } from 'react-icons/fi';
import '../css/RunMatrix.css';

const STATES = {
  PASS: { className: 'pass', label: 'Réussi', Icon: FiCheck },
  FAIL: { className: 'fail', label: 'Échec', Icon: FiX },
  SKIP: { className: 'skip', label: 'Ignoré', Icon: FiMinus },
  ABSENT: { className: 'absent', label: 'Non joué', Icon: FiMinus },
  PENDING: { className: 'pending', label: 'En attente', Icon: null },
};

const TERMINAL = ['PASS', 'FAIL', 'SKIP'];

/** Union des tests vus, dans l'ordre où chaque configuration les a rencontrés. */
const buildRows = (sessions, results) => {
  const rows = new Map();
  sessions.forEach((session) => {
    Object.entries(results[session.sessionId] || {}).forEach(([longname, result]) => {
      if (!rows.has(longname)) rows.set(longname, { longname, name: result.name || longname });
    });
  });
  return [...rows.values()];
};

/** Une cellule vide ne vaut pas un succès : distinguer « pas encore » de « jamais joué ». */
const cellState = (results, session, longname) => {
  const found = results[session.sessionId]?.[longname];
  if (found && STATES[found.status]) return found.status;
  if (found) return 'ABSENT';
  return session.completed ? 'ABSENT' : 'PENDING';
};

const RunMatrix = ({ sessions = [], results = {} }) => {
  const rows = useMemo(() => buildRows(sessions, results), [sessions, results]);

  if (sessions.length === 0) return null;

  return (
    <section className="run-matrix" aria-label="Comparaison des configurations">
      <header className="run-matrix-head">
        <h2>Comparaison des configurations</h2>
        <p>
          Une ligne entièrement rouge désigne le produit ; une colonne entière, la configuration ;
          une cellule isolée, une spécificité du navigateur — ou une machine saturée.
        </p>
      </header>

      {rows.length === 0 ? (
        <p className="run-matrix-empty">Aucun test terminé pour l'instant.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th scope="col">Test</th>
              {sessions.map((session) => (
                <th scope="col" key={session.sessionId}>
                  {session.browser}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(({ longname, name }) => {
              const states = sessions.map((session) => cellState(results, session, longname));
              const seen = new Set(states.filter((state) => TERMINAL.includes(state)));
              return (
                <tr key={longname} className={seen.size > 1 ? 'diverging' : undefined}>
                  <th scope="row" title={longname}>
                    {name}
                  </th>
                  {sessions.map((session, index) => {
                    const { className, label, Icon } = STATES[states[index]];
                    return (
                      <td
                        key={session.sessionId}
                        className={className}
                        title={`${name} · ${session.browser} : ${label}`}
                      >
                        {Icon ? <Icon aria-hidden="true" /> : null}
                        <span className="run-matrix-sr">{label}</span>
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
};

export default RunMatrix;
