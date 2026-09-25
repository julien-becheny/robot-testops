// Cartes de resultats du run : live, resume, analyse, detail par etape.
import {
  Box,
  CardContent,
  Typography,
  Stack,
  Chip,
  Alert,
  Divider,
  Grid,
  Tooltip,
} from '@mui/material';
import { FiAlertOctagon, FiAlertTriangle, FiCheckCircle, FiInfo } from 'react-icons/fi';
import {
  ACCENT,
  ACCENT2,
  BAD,
  GOOD,
  WARN,
  STATUS_META,
  statusOf,
  fmtMs,
  fmtPct,
  fmtRps,
  fmtMb,
  fmtKbs,
  fmtNum,
  fmtCpu,
  fmtShortfall,
  colorError,
  colorChecks,
  colorCpu,
  colorShortfall,
} from './theme';
import { SignatureCard } from './common';

export function LiveBand({ live }) {
  const val = (v, suffix = '') => (typeof v === 'number' ? `${v}${suffix}` : '-');
  const pct = (v) => (typeof v === 'number' ? `${(v * 100).toFixed(2)} %` : '-');
  const vus =
    typeof live.vus_target === 'number' ? `${val(live.vus)} / ${live.vus_target}` : val(live.vus);
  const items = [
    ['VUs actifs', vus, live.vus_lagging ? WARN : undefined],
    ['Débit', val(live.reqs_per_sec, ' req/s')],
    ['p95', val(live.p95_ms, ' ms')],
    ['Erreurs', pct(live.error_rate)],
    ['CPU injecteur', fmtCpu(live.cpu), colorCpu(live.cpu)],
  ];
  // Modèle ouvert : ce que l'injecteur n'a pas pu envoyer, à lire avec le CPU ci-dessus.
  if (typeof live.dropped === 'number') {
    items.push(['Non parties', fmtNum(live.dropped), live.dropped > 0 ? WARN : undefined]);
  }
  return (
    <SignatureCard sx={{ mb: 2 }}>
      <CardContent>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1.5 }}>
          <Box
            sx={{
              width: 9,
              height: 9,
              borderRadius: '50%',
              bgcolor: '#ff5252',
              animation: 'pulse 1.4s infinite',
              '@keyframes pulse': {
                '0%': { boxShadow: '0 0 0 0 rgba(255,82,82,0.5)' },
                '70%': { boxShadow: '0 0 0 8px rgba(255,82,82,0)' },
                '100%': { boxShadow: '0 0 0 0 rgba(255,82,82,0)' },
              },
            }}
          />
          <Typography variant="subtitle2">En direct</Typography>
        </Stack>
        <Grid container spacing={2}>
          {items.map(([label, value, color]) => (
            <Grid item xs={6} sm={3} key={label}>
              <Typography variant="caption" color="text.secondary">
                {label}
              </Typography>
              <Typography variant="h6" sx={{ color: color || ACCENT }}>
                {value}
              </Typography>
            </Grid>
          ))}
        </Grid>
        {live.vus_lagging && (
          <Typography variant="caption" sx={{ color: WARN, display: 'block', mt: 1 }}>
            Moins d&apos;utilisateurs actifs que demandé : l&apos;injecteur peine à suivre le plan.
          </Typography>
        )}
      </CardContent>
    </SignatureCard>
  );
}

export function ResultCard({ result }) {
  if (result.error) {
    return (
      <Alert severity="error" sx={{ mt: 2 }}>
        {result.error}
      </Alert>
    );
  }
  if (result.stopped) {
    return (
      <Alert severity="info" sx={{ mt: 2 }}>
        Test arrêté manuellement.
      </Alert>
    );
  }

  const st = STATUS_META[statusOf(result)] || STATUS_META.ok;
  // Comparaison au seuil enregistre PAR LE RUN : les deux moteurs le portent, alors que
  // `failed_thresholds` n'existe que cote k6.
  const over = (v, limit) => typeof v === 'number' && typeof limit === 'number' && v > limit;
  const p95Bad = over(result.p95_ms, result.seuil_p95_ms);
  const p99Bad = over(result.p99_ms, result.seuil_p99_ms);
  const deficit = typeof result.vus_deficit_pct === 'number' && result.vus_deficit_pct >= 5;
  const volume = [
    ['Débit', fmtRps(result.reqs_per_sec)],
    ['Requêtes totales', fmtNum(result.reqs_total)],
    ['VUs max', fmtNum(result.vus_max), deficit ? WARN : undefined],
    ['VUs demandés', fmtNum(result.vus_target_max)],
  ];
  if (typeof result.throughput_shortfall_pct === 'number') {
    volume.push([
      'Charge auto-limitée',
      fmtShortfall(result.throughput_shortfall_pct),
      colorShortfall(result.throughput_shortfall_pct),
    ]);
  }
  // Modèle ouvert : le débit visé et ce que l'injecteur n'a pas pu envoyer.
  if (typeof result.rate_target === 'number') {
    volume.push(['Débit visé', fmtRps(result.rate_target)]);
  }
  if (typeof result.dropped_iterations === 'number') {
    const dropped = result.dropped_iterations;
    volume.push([
      'Non parties',
      dropped ? `${fmtNum(dropped)} (${result.dropped_pct} %)` : '0',
      dropped ? BAD : GOOD,
    ]);
  }

  const sections = [
    [
      'Temps de réponse',
      [
        ['Plancher (min)', fmtMs(result.min_ms)],
        ['p50 (médiane)', fmtMs(result.p50_ms)],
        ['p95', fmtMs(result.p95_ms), p95Bad ? BAD : undefined],
        ['p99', fmtMs(result.p99_ms), p99Bad ? BAD : undefined],
        ['TTFB p95', fmtMs(result.ttfb_p95_ms)],
      ],
    ],
    [
      'Fiabilité',
      [
        ["Taux d'erreur", fmtPct(result.error_rate), colorError(result.error_rate)],
        ['Checks OK', fmtPct(result.checks_rate), colorChecks(result.checks_rate)],
      ],
    ],
    ['Débit & volume', volume],
    [
      'Réseau',
      [
        ['Données reçues', fmtMb(result.data_received)],
        ['Débit reçu', fmtKbs(result.data_received_rate)],
        ['Données envoyées', fmtMb(result.data_sent)],
        ...(typeof result.network_usage_pct === 'number'
          ? [
              [
                'Part du lien',
                result.link_speed_mbps
                  ? `${Math.round(result.network_usage_pct)} % de ${result.link_speed_mbps} Mb/s`
                  : `${Math.round(result.network_usage_pct)} %`,
                result.network_usage_pct >= 70 ? WARN : undefined,
              ],
            ]
          : []),
      ],
    ],
  ];

  if (
    typeof result.injector_cpu_max === 'number' ||
    typeof result.injector_capacity_rps === 'number' ||
    typeof result.injector_processes === 'number' ||
    typeof result.injector_cores === 'number'
  ) {
    const cells = [];
    if (typeof result.injector_cpu_max === 'number') {
      cells.push(['CPU max', fmtCpu(result.injector_cpu_max), colorCpu(result.injector_cpu_max)]);
    }
    if (typeof result.injector_capacity_rps === 'number') {
      cells.push(['Capacité mesurée', fmtRps(result.injector_capacity_rps), ACCENT]);
    }
    // Deux runs du meme scenario peuvent differer d'un facteur cinq selon ce chiffre.
    if (result.injector_processes || result.injector_cores) {
      cells.push([
        'Parallélisme',
        result.injector_processes
          ? `${result.injector_processes} proc. / ${result.injector_cores ?? '?'} cœurs`
          : `${result.injector_cores} cœurs`,
      ]);
    }
    sections.push(['Injecteur (machine de test)', cells]);
  }

  return (
    <SignatureCard sx={{ mt: 2 }}>
      <CardContent>
        <Stack direction="row" alignItems="center" justifyContent="space-between" mb={1.5}>
          <Typography variant="h6">Résultats</Typography>
          <Chip label={st.label} color={st.color} />
        </Stack>
        {!result.thresholds_ok &&
          result.failed_thresholds &&
          result.failed_thresholds.length > 0 && (
            <Alert severity="warning" sx={{ mb: 2 }}>
              Seuil(s) non tenu(s) : {result.failed_thresholds.join(' ; ')}
            </Alert>
          )}
        <Stack spacing={2}>
          {sections.map(([title, items]) => (
            <Box key={title}>
              <Typography variant="overline" sx={{ color: 'text.secondary', letterSpacing: 1 }}>
                {title}
              </Typography>
              <Divider sx={{ mt: 0.5, mb: 1.5, borderColor: 'rgba(255,255,255,0.08)' }} />
              <Grid container spacing={2}>
                {items.map(([label, value, color]) => (
                  <Grid item xs={6} sm={3} key={label}>
                    <Typography variant="caption" color="text.secondary">
                      {label}
                    </Typography>
                    <Typography variant="h6" sx={{ color: color || 'text.primary' }}>
                      {value}
                    </Typography>
                  </Grid>
                ))}
              </Grid>
            </Box>
          ))}
        </Stack>
        {typeof result.max_ms === 'number' && (
          <Tooltip title="Temps d'UN seul appel sur tout le run : un pic isolé (nouvelle connexion, retry réseau, injecteur chargé) suffit à le faire exploser. Les percentiles restent la référence.">
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ display: 'block', mt: 2, cursor: 'help' }}
            >
              Requête la plus lente du run : {fmtMs(result.max_ms)} - valeur isolée, non
              représentative &#9432;
            </Typography>
          </Tooltip>
        )}
      </CardContent>
    </SignatureCard>
  );
}

export function AnalysisCard({ findings }) {
  const STYLE = {
    crit: { color: '#ff5252', Icon: FiAlertOctagon },
    warn: { color: '#ffb74d', Icon: FiAlertTriangle },
    info: { color: ACCENT, Icon: FiInfo },
    good: { color: '#4caf50', Icon: FiCheckCircle },
  };
  return (
    <SignatureCard sx={{ mt: 2 }}>
      <CardContent>
        <Typography variant="h6" sx={{ mb: 1.5 }}>
          Analyse
        </Typography>
        <Stack spacing={1.25}>
          {findings.map((f, i) => {
            const s = STYLE[f.level] || STYLE.info;
            return (
              <Box
                key={i}
                sx={{
                  display: 'flex',
                  gap: 1.25,
                  p: 1.25,
                  borderRadius: 2,
                  background: 'rgba(255,255,255,0.03)',
                  borderLeft: `3px solid ${s.color}`,
                }}
              >
                <Box sx={{ color: s.color, display: 'flex', mt: '2px' }}>
                  <s.Icon size={16} />
                </Box>
                <Box>
                  <Typography variant="body2" sx={{ fontWeight: 600, color: s.color }}>
                    {f.title}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {f.detail}
                  </Typography>
                </Box>
              </Box>
            );
          })}
        </Stack>
      </CardContent>
    </SignatureCard>
  );
}

function LegendItem({ color, label, opacity = 1, dashed = false }) {
  return (
    <Stack direction="row" spacing={0.75} alignItems="center">
      <Box
        sx={
          dashed
            ? { width: 16, borderTop: `2px dashed ${color}` }
            : { width: 14, height: 10, bgcolor: color, opacity, borderRadius: 0.5 }
        }
      />
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
    </Stack>
  );
}

// Trois facons d'arreter un run, trois lectures : le seuil de latence (defaut),
// le CPU de l'injecteur (calibrage) et le debit qui ne passe plus (modele ouvert).
const BREACH_VARIANTES = {
  cpu: {
    titre: "Saturation de l'injecteur",
    sous: 'Les conditions exactes au moment où la machine de test a saturé. Au-delà, elle mesure sa propre attente, plus le système testé.',
  },
  dropped: {
    titre: 'Décrochage du débit',
    sous: "Le rythme d'arrivée a dépassé ce que le système traite : la file s'allonge et des requêtes ne partent plus du tout.",
  },
  p95: {
    titre: 'Point de rupture',
    sous: 'Les conditions exactes au moment où le p95 a franchi le seuil. Au-delà, le service se dégrade.',
  },
};

// Test de capacite/charge (Locust) : les conditions EXACTES au moment ou le p95
// a franchi le seuil = le point de rupture. C'est le livrable central.
export function BreachCard({ breach, seuil }) {
  if (!breach) return null;
  const pct = (v) => (typeof v === 'number' ? `${(v * 100).toFixed(2)} %` : '-');
  const parCpu = breach.cause === 'cpu';
  // Modele ouvert : il n'y a pas d'utilisateurs a compter, seulement un debit.
  const parDropped = breach.cause === 'dropped';
  const variante = BREACH_VARIANTES[breach.cause] || BREACH_VARIANTES.p95;
  return (
    <SignatureCard sx={{ mt: 2, border: `1px solid ${BAD}55` }}>
      <CardContent>
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
          <Box sx={{ color: BAD, display: 'flex' }}>
            <FiAlertOctagon size={20} />
          </Box>
          <Typography variant="h6">{variante.titre}</Typography>
        </Stack>
        <Typography variant="caption" color="text.secondary">
          {variante.sous}
        </Typography>
        <Grid container spacing={2} sx={{ mt: 0.5 }}>
          <Grid item xs={12} sm={4}>
            <Typography variant="caption" color="text.secondary">
              {parDropped ? 'Débit absorbé' : 'Utilisateurs actifs'}
            </Typography>
            <Typography variant="h4" sx={{ color: BAD }}>
              {parDropped ? `${Math.round(breach.rps)} req/s` : breach.users}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {parDropped ? "capacité d'absorption" : 'capacité max estimée'}
            </Typography>
          </Grid>
          <Grid item xs={6} sm={2}>
            <Typography variant="caption" color="text.secondary">
              Instant
            </Typography>
            <Typography variant="h6">{Math.round(breach.t)} s</Typography>
          </Grid>
          <Grid item xs={6} sm={2}>
            <Typography variant="caption" color="text.secondary">
              {parCpu ? 'CPU injecteur' : 'p95 au fail'}
            </Typography>
            <Typography variant="h6" sx={{ color: BAD }}>
              {parCpu ? `${Math.round(breach.cpu)} %` : `${breach.p95_ms} ms`}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {parCpu ? 'saturation atteinte' : `seuil ${Math.round(seuil)} ms`}
            </Typography>
          </Grid>
          <Grid item xs={6} sm={2}>
            <Typography variant="caption" color="text.secondary">
              {parDropped ? 'Non parties' : 'Débit'}
            </Typography>
            <Typography variant="h6" sx={{ color: parDropped ? BAD : undefined }}>
              {parDropped ? fmtNum(breach.dropped) : `${Math.round(breach.rps)} req/s`}
            </Typography>
          </Grid>
          {typeof breach.error_rate === 'number' && (
            <Grid item xs={6} sm={2}>
              <Typography variant="caption" color="text.secondary">
                Erreurs
              </Typography>
              <Typography variant="h6" sx={{ color: colorError(breach.error_rate) }}>
                {pct(breach.error_rate)}
              </Typography>
            </Grid>
          )}
        </Grid>
      </CardContent>
    </SignatureCard>
  );
}

// Evolution dans le temps : le p95 (turquoise) grimpe avec la charge (utilisateurs).
// La ligne rouge = seuil, le point rouge = rupture. Rend visible « quand ca casse ».
export function TimelineCard({ timeline, seuil, breach }) {
  if (!timeline || timeline.length < 2) return null;

  const W = 640,
    H = 220,
    L = 44,
    R = 16,
    T = 16,
    B = 30;
  const pw = W - L - R,
    ph = H - T - B,
    bottom = T + ph;
  const tMax = Math.max(...timeline.map((p) => p.t), 1);
  const p95Max = Math.max(...timeline.map((p) => p.p95_ms || 0), seuil || 0, 1) * 1.15;
  const uMax = Math.max(...timeline.map((p) => p.users || 0), 1);
  const x = (t) => L + (t / tMax) * pw;
  const yP = (v) => bottom - (v / p95Max) * ph;
  const yU = (v) => bottom - (v / uMax) * ph;
  const p95Pts = timeline.map((p) => `${x(p.t)},${yP(p.p95_ms || 0)}`).join(' ');
  const uPts = timeline.map((p) => `${x(p.t)},${yU(p.users || 0)}`).join(' ');
  const thY = seuil ? yP(seuil) : null;

  return (
    <SignatureCard sx={{ mt: 2 }}>
      <CardContent>
        <Typography variant="h6">Évolution dans le temps</Typography>
        <Typography variant="caption" color="text.secondary">
          Le p95 (turquoise) grimpe avec la charge (utilisateurs, gris). Ligne rouge = seuil ; point
          rouge = rupture.
        </Typography>
        <Box sx={{ mt: 1.5, overflowX: 'auto' }}>
          <Box
            component="svg"
            viewBox={`0 0 ${W} ${H}`}
            sx={{ width: '100%', minWidth: 420, height: 'auto', display: 'block' }}
          >
            <line x1={L} y1={bottom} x2={W - R} y2={bottom} stroke="rgba(255,255,255,0.15)" />
            {thY != null && (
              <line
                x1={L}
                y1={thY}
                x2={W - R}
                y2={thY}
                stroke={BAD}
                strokeDasharray="5 4"
                strokeWidth="1.5"
                opacity="0.85"
              />
            )}
            <polyline points={uPts} fill="none" stroke="rgba(255,255,255,0.4)" strokeWidth="1.5" />
            <polyline points={p95Pts} fill="none" stroke={ACCENT2} strokeWidth="2" />
            {breach && <circle cx={x(breach.t)} cy={yP(breach.p95_ms)} r="5" fill={BAD} />}
            <text x={L} y={H - 8} fill="rgba(255,255,255,0.5)" fontSize="10">
              0 s
            </text>
            <text x={W - R} y={H - 8} textAnchor="end" fill="rgba(255,255,255,0.5)" fontSize="10">
              {Math.round(tMax)} s
            </text>
          </Box>
        </Box>
        <Stack direction="row" spacing={2} sx={{ mt: 0.5, flexWrap: 'wrap' }}>
          <LegendItem color={ACCENT2} label="p95 (ms)" />
          <LegendItem color="rgba(255,255,255,0.5)" label="Utilisateurs" />
          <LegendItem color={BAD} label="Seuil p95" dashed />
        </Stack>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
          À chaque hausse de charge, les nouveaux utilisateurs doivent ouvrir une connexion (TCP +
          TLS) : le pic qui suit est ce coût d&apos;entrée, pas une dégradation. Juge sur les
          paliers stabilisés.
        </Typography>
      </CardContent>
    </SignatureCard>
  );
}
