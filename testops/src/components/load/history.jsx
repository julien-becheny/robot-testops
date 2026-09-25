// Historique des runs + comparaison de deux runs.
import { Box, CardContent, Typography, Stack, Chip, Alert, Divider, Grid } from '@mui/material';
import { FiExternalLink, FiFlag } from 'react-icons/fi';
import {
  TYPE_ICONS,
  PARAM_LABELS,
  STATUS_META,
  statusOf,
  ACCENT,
  ACCENT_SOFT,
  ACCENT_SOFT_HOVER,
  fmtMs,
  fmtNum,
  fmtPct,
  fmtRps,
  fmtMb,
  fmtKbs,
  colorError,
  colorChecks,
} from './theme';
import { SignatureCard } from './common';
import ActionButton from '../ActionButton';
import { API_BASE_URL } from '../../config/api';

export function HistoryCard({ runs, compare, onToggle, onClear, onSetBaseline, baselineIds }) {
  const fmtDate = (ts) =>
    new Date(ts * 1000).toLocaleString('fr-FR', {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  const headers = [
    '',
    'Date',
    'Type',
    'Cible',
    'VUs',
    'p95',
    'Débit',
    'Err',
    'Checks',
    'Verdict',
    'Rapport',
    'Réf.',
  ];
  const selectedRuns = compare.map((id) => runs.find((r) => r.id === id)).filter(Boolean);

  return (
    <SignatureCard sx={{ mt: 2 }}>
      <CardContent>
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 0.5 }}>
          <Typography variant="h6">Historique des runs</Typography>
          <ActionButton className="small ghost" onClick={onClear}>
            Vider
          </ActionButton>
        </Stack>
        <Typography variant="caption" color="text.secondary">
          Coche deux runs pour les comparer.
        </Typography>

        {selectedRuns.length === 2 && <CompareBand a={selectedRuns[0]} b={selectedRuns[1]} />}

        <Box sx={{ overflowX: 'auto', mt: 1 }}>
          <Box component="table" sx={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <Box component="thead">
              <Box component="tr" sx={{ color: 'text.secondary' }}>
                {headers.map((h, i) => (
                  <Box
                    component="th"
                    key={i}
                    sx={{
                      py: 0.75,
                      px: 1,
                      textAlign: 'left',
                      fontWeight: 500,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {h}
                  </Box>
                ))}
              </Box>
            </Box>
            <Box component="tbody">
              {runs.map((run) => {
                const r = run.result || {};
                const sel = compare.includes(run.id);
                const isBaseline = (baselineIds || []).includes(run.id);
                return (
                  <Box
                    component="tr"
                    key={run.id}
                    onClick={() => onToggle(run.id)}
                    sx={{
                      cursor: 'pointer',
                      borderTop: '1px solid rgba(255,255,255,0.06)',
                      background: sel ? ACCENT_SOFT : 'transparent',
                      '&:hover': {
                        background: sel ? ACCENT_SOFT_HOVER : 'rgba(255,255,255,0.04)',
                      },
                    }}
                  >
                    <Box component="td" sx={{ px: 1 }}>
                      <input type="checkbox" checked={sel} readOnly />
                    </Box>
                    <Box component="td" sx={{ px: 1, whiteSpace: 'nowrap' }}>
                      {fmtDate(run.ts)}
                    </Box>
                    <Box component="td" sx={{ px: 1, whiteSpace: 'nowrap' }}>
                      <Stack direction="row" spacing={0.75} alignItems="center">
                        {(() => {
                          const RunIcon = TYPE_ICONS[run.test_type];
                          return RunIcon ? (
                            <Box sx={{ color: ACCENT, display: 'flex' }}>
                              <RunIcon size={14} />
                            </Box>
                          ) : null;
                        })()}
                        <span>{run.test_type}</span>
                      </Stack>
                    </Box>
                    <Box component="td" sx={{ px: 1 }}>
                      {run.target_label}
                    </Box>
                    <Box component="td" sx={{ px: 1 }}>
                      {(run.params && run.params.vus) ?? '-'}
                    </Box>
                    <Box component="td" sx={{ px: 1, whiteSpace: 'nowrap' }}>
                      {fmtMs(r.p95_ms)}
                    </Box>
                    <Box component="td" sx={{ px: 1, whiteSpace: 'nowrap' }}>
                      {fmtRps(r.reqs_per_sec)}
                    </Box>
                    <Box component="td" sx={{ px: 1, color: colorError(r.error_rate) }}>
                      {fmtPct(r.error_rate)}
                    </Box>
                    <Box component="td" sx={{ px: 1, color: colorChecks(r.checks_rate) }}>
                      {fmtPct(r.checks_rate)}
                    </Box>
                    <Box component="td" sx={{ px: 1 }}>
                      <Chip
                        size="small"
                        label={(STATUS_META[statusOf(r)] || STATUS_META.ok).short}
                        color={(STATUS_META[statusOf(r)] || STATUS_META.ok).color}
                      />
                    </Box>
                    <Box component="td" sx={{ px: 1 }}>
                      {r.report_url ? (
                        <Box
                          component="a"
                          href={`${API_BASE_URL}${r.report_url}`}
                          target="_blank"
                          rel="noopener"
                          aria-label={`Rapport k6 du run du ${fmtDate(run.ts)}`}
                          onClick={(e) => e.stopPropagation()}
                          sx={{ color: ACCENT, display: 'flex' }}
                        >
                          <FiExternalLink size={14} />
                        </Box>
                      ) : (
                        '-'
                      )}
                    </Box>
                    <Box component="td" sx={{ px: 1 }}>
                      <Box
                        component="button"
                        type="button"
                        title={
                          isBaseline
                            ? 'Référence actuelle - cliquer pour la retirer'
                            : 'Les runs suivants de cette cible et de ce type se compareront à celui-ci'
                        }
                        aria-label={`${isBaseline ? 'Retirer' : 'Définir'} le run du ${fmtDate(run.ts)} comme référence`}
                        onClick={(e) => {
                          e.stopPropagation();
                          onSetBaseline(run);
                        }}
                        sx={{
                          background: 'none',
                          border: 'none',
                          cursor: 'pointer',
                          color: isBaseline ? ACCENT : 'text.secondary',
                          opacity: isBaseline ? 1 : 0.5,
                          display: 'flex',
                          p: 0,
                        }}
                      >
                        <FiFlag size={14} />
                      </Box>
                    </Box>
                  </Box>
                );
              })}
            </Box>
          </Box>
        </Box>
      </CardContent>
    </SignatureCard>
  );
}

function CompareBand({ a, b }) {
  // Ordre chronologique : older = avant, newer = apres. Le delta reflete l'evolution reelle.
  const [older, newer] = a.ts <= b.ts ? [a, b] : [b, a];
  const va = older.result || {};
  const vb = newer.result || {};

  const stamp = (run) =>
    new Date(run.ts * 1000).toLocaleString('fr-FR', {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });

  // Entrees (type + params) : socle de comparabilite.
  const pa = older.params || {};
  const pb = newer.params || {};
  const paramKeys = [...new Set([...Object.keys(pa), ...Object.keys(pb)])];
  const engineOf = (r) => r.engine || 'locust';
  const modelOf = (r) => (r.model === 'open' ? 'flux imposé' : 'utilisateurs');
  const sameEngine = engineOf(va) === engineOf(vb);
  const inputRows = [
    { label: 'Type', xa: older.test_type, xb: newer.test_type },
    { label: 'Charge', xa: modelOf(va), xb: modelOf(vb) },
    ...paramKeys.map((k) => ({ label: PARAM_LABELS[k] || k, xa: pa[k], xb: pb[k] })),
  ];
  const sameProfile = inputRows.every((r) => String(r.xa) === String(r.xb));

  // Le point de rupture EST le resultat d'un test de capacite : sans lui, on compare
  // des percentiles agreges sur des paliers differents, ce qui se lit souvent a l'envers.
  const aplati = (r) => ({
    ...r,
    breach_users: r.breach && r.breach.users,
    breach_rps: r.breach && r.breach.rps,
  });
  const va2 = aplati(va);
  const vb2 = aplati(vb);

  const rows = [
    { key: 'breach_users', label: 'Rupture', lowerBetter: false, fmt: fmtNum, unit: ' VUs' },
    {
      key: 'breach_rps',
      label: 'Débit au plafond',
      lowerBetter: false,
      fmt: fmtRps,
      unit: ' req/s',
    },
    { key: 'min_ms', label: 'Plancher', lowerBetter: true, fmt: fmtMs, unit: ' ms' },
    { key: 'p50_ms', label: 'p50', lowerBetter: true, fmt: fmtMs, unit: ' ms' },
    { key: 'p95_ms', label: 'p95', lowerBetter: true, fmt: fmtMs, unit: ' ms' },
    { key: 'p99_ms', label: 'p99', lowerBetter: true, fmt: fmtMs, unit: ' ms' },
    { key: 'ttfb_p95_ms', label: 'TTFB p95', lowerBetter: true, fmt: fmtMs, unit: ' ms' },
    { key: 'reqs_per_sec', label: 'Débit', lowerBetter: false, fmt: fmtRps, unit: ' req/s' },
    { key: 'error_rate', label: 'Erreurs', lowerBetter: true, fmt: fmtPct, unit: 'pts' },
    { key: 'checks_rate', label: 'Checks', lowerBetter: false, fmt: fmtPct, unit: 'pts' },
    { key: 'data_received_rate', label: 'Débit reçu', neutral: true, fmt: fmtKbs },
    { key: 'data_received', label: 'Données reçues', neutral: true, fmt: fmtMb },
  ];

  return (
    <Box
      sx={{
        mt: 1.5,
        p: 1.5,
        borderRadius: 2,
        background: 'rgba(0,0,0,0.2)',
        border: '1px solid rgba(255,255,255,0.08)',
      }}
    >
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        Comparaison - avant ({stamp(older)}) → après ({stamp(newer)})
      </Typography>

      {!sameEngine && (
        <Alert severity="info" sx={{ mb: 1.5 }}>
          Deux moteurs différents ({engineOf(va)} → {engineOf(vb)}) : ils ne mesurent pas tout à
          fait la même chose. Locust <strong>arrondit</strong> les temps qu&apos;il conserve pour
          ses percentiles (10 ms entre 100 et 1 000 ms, la centaine au-delà), pas k6 ; et leurs
          durées de requête ne recouvrent pas exactement le même périmètre. Un écart de quelques
          pour cent ne dit donc rien du système. Ce qui se compare ici, c&apos;est l&apos;ordre de
          grandeur - et, si les modèles de charge diffèrent, l&apos;écart mesure le biais du modèle
          fermé, pas une régression.
        </Alert>
      )}

      {sameEngine && !sameProfile && (
        <Alert severity="warning" sx={{ mb: 1.5 }}>
          Profils d&apos;entrée différents (VUs, durées ou seuils) : les écarts ci-dessous peuvent
          venir de ces réglages, pas d&apos;une régression réelle. Pour comparer proprement, relance
          le MÊME profil et ne fais varier que la cible/version.
        </Alert>
      )}

      <Typography variant="caption" color="text.secondary">
        Entrées
      </Typography>
      <Grid container spacing={1} sx={{ mb: 1.5 }}>
        {inputRows.map((r) => {
          const diff = String(r.xa) !== String(r.xb);
          return (
            <Grid item xs={6} sm={3} key={r.label}>
              <Typography variant="caption" color="text.secondary">
                {r.label}
              </Typography>
              <Typography variant="body2" sx={{ color: diff ? '#ffb74d' : 'text.primary' }}>
                {String(r.xa ?? '-')} → {String(r.xb ?? '-')}
              </Typography>
            </Grid>
          );
        })}
      </Grid>

      <Divider sx={{ mb: 1.5, borderColor: 'rgba(255,255,255,0.08)' }} />

      <Typography variant="caption" color="text.secondary">
        Résultats (avant → après)
      </Typography>
      <Grid container spacing={1}>
        {rows.map((row) => {
          const x = va2[row.key];
          const y = vb2[row.key];
          const hasBoth = typeof x === 'number' && typeof y === 'number';
          const delta = hasBoth ? y - x : null;
          let color = 'text.secondary';
          if (!row.neutral && hasBoth && delta !== 0) {
            const improved = row.lowerBetter ? delta < 0 : delta > 0;
            color = improved ? '#4caf50' : '#ff5252';
          }
          const deltaText = () => {
            if (!hasBoth) return '';
            if (delta === 0) return '=';
            const arrow = delta > 0 ? '▲' : '▼';
            if (row.unit === 'pts') return `${arrow} ${(Math.abs(delta) * 100).toFixed(2)} pts`;
            if (row.key === 'data_received_rate') return `${arrow} ${fmtKbs(Math.abs(delta))}`;
            if (row.key === 'data_received') return `${arrow} ${fmtMb(Math.abs(delta))}`;
            return `${arrow} ${Math.round(Math.abs(delta) * 10) / 10}${row.unit}`;
          };
          return (
            <Grid item xs={6} sm={4} key={row.key}>
              <Typography variant="caption" color="text.secondary">
                {row.label}
              </Typography>
              <Typography variant="body2">
                {row.fmt(x)} → {row.fmt(y)}
              </Typography>
              <Typography variant="caption" sx={{ color, fontWeight: 600 }}>
                {deltaText()}
              </Typography>
            </Grid>
          );
        })}
      </Grid>
    </Box>
  );
}
