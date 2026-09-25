// Tokens de design, theme MUI et helpers partages du module « Tests de charge ».
import { createTheme } from '@mui/material/styles';
import {
  FiBarChart2,
  FiChevronsUp,
  FiClock,
  FiSliders,
  FiTrendingUp,
  FiWind,
  FiZap,
} from 'react-icons/fi';

// Couleurs signature de TestOps. ACCENT2 est volontairement plus clair : c'est lui
// qui trace les courbes, il doit rester lisible sur fond sombre.
export const ACCENT = '#69b6d6';
export const ACCENT2 = '#8fd6ea';
export const ACCENT_GRADIENT = `linear-gradient(90deg, ${ACCENT}, ${ACCENT2})`;
// Voile d'accent des elements selectionnes (equivalent JS de --accent-rgb).
export const ACCENT_SOFT = 'rgba(105,182,214,0.10)';
export const ACCENT_SOFT_HOVER = 'rgba(105,182,214,0.16)';

// Theme sombre aligne sur l'identite visuelle de TestOps (cards translucides).
// Les valeurs litterales reprennent les variables de src/index.css : MUI calcule
// des variantes (hover, contraste) et n'accepte pas var() pour les couleurs.
export const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: ACCENT },
    background: { default: '#182433', paper: 'rgba(255,255,255,0.035)' },
    text: { primary: '#ffffff', secondary: 'rgba(255,255,255,0.72)' },
  },
  typography: { fontFamily: 'var(--font-ui)' },
  shape: { borderRadius: 14 },
  components: {
    MuiCard: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
          background: 'rgba(255,255,255,0.035)',
          border: '1px solid rgba(255,255,255,0.07)',
          boxShadow: '0 4px 20px rgba(0,0,0,0.2)',
        },
      },
    },
  },
});

// Icones par type de test (presentation cote UI).
export const TYPE_ICONS = {
  smoke: FiZap,
  load: FiTrendingUp,
  stress: FiChevronsUp,
  endurance: FiClock,
  capacity: FiBarChart2,
  calibration: FiSliders,
  open_load: FiWind,
  open_stress: FiChevronsUp,
  open_endurance: FiClock,
  open_capacity: FiBarChart2,
};

// Libelles lisibles des parametres d'entree (pour la comparaison).
export const PARAM_LABELS = {
  vus: 'VUs',
  ramp_up: 'Montée',
  steady: 'Palier',
  peak_hold: 'Maintien pic',
  ramp_down: 'Descente',
  duration: 'Durée',
  think_time: 'Think time',
  p95_ms: 'Seuil p95',
  p99_ms: 'Seuil p99',
  error_pct: 'Seuil err %',
  processes: "Processus d'injection",
  cpu_max_pct: 'Seuil CPU injecteur',
  rate: 'Débit cible',
  max_vus: 'VUs max',
  rate_start: 'Débit de départ',
  rate_max: 'Débit max',
  rate_step: 'Pas de débit',
};

// Formatteurs partages (resultats, historique, comparaison).
export const fmtMs = (v) => (typeof v === 'number' ? `${v} ms` : '-');
export const fmtPct = (v) => (typeof v === 'number' ? `${(v * 100).toFixed(2)} %` : '-');
export const fmtRps = (v) => (typeof v === 'number' ? `${v} req/s` : '-');
export const fmtMb = (v) => (typeof v === 'number' ? `${(v / 1e6).toFixed(1)} MB` : '-');
export const fmtKbs = (v) => {
  if (typeof v !== 'number') return '-';
  return v >= 1e6 ? `${(v / 1e6).toFixed(1)} MB/s` : `${Math.round(v / 1e3)} kB/s`;
};
export const fmtNum = (v) => (typeof v === 'number' ? v : '-');
export const fmtCpu = (v) => (typeof v === 'number' ? `${Math.round(v)} %` : '-');
// Écart entre le débit produit et celui que les mêmes VUs auraient produit sans
// ralentissement (modèle fermé). Au-delà de 20 %, le p95 du run est optimiste.
export const fmtShortfall = (v) => (typeof v === 'number' ? `-${Math.round(v)} %` : '-');
// Couleurs semantiques : les valeurs problematiques ressortent.
export const GOOD = '#4caf50';
export const WARN = '#ffb74d';
export const BAD = '#ff5252';
export const colorError = (v) =>
  typeof v !== 'number' ? undefined : v <= 0 ? GOOD : v < 0.01 ? WARN : BAD;
export const colorChecks = (v) =>
  typeof v !== 'number' ? undefined : v >= 1 ? GOOD : v >= 0.99 ? WARN : BAD;
// Au-dela de 90 % de CPU, l'injecteur fausse ses propres mesures de latence.
export const colorCpu = (v) =>
  typeof v !== 'number' ? undefined : v >= 90 ? BAD : v >= 75 ? WARN : GOOD;
export const colorShortfall = (v) => (typeof v !== 'number' ? undefined : v >= 20 ? WARN : GOOD);

// Verdict global du run (calcule par le backend) -> presentation.
export const STATUS_META = {
  ok: { label: 'Réussi', short: 'OK', color: 'success' },
  warn: { label: 'À surveiller', short: 'WARN', color: 'warning' },
  fail: { label: 'Échec', short: 'KO', color: 'error' },
  // Un stress depasse volontairement la capacite : « Reussi » y serait trompeur.
  surcharge: { label: 'Surcharge explorée', short: 'INFO', color: 'info' },
};
export const statusOf = (result) => {
  const status = (result && result.status) || (result && result.thresholds_ok ? 'ok' : 'fail');
  if (!result || (result.test_type !== 'stress' && result.test_type !== 'open_stress')) {
    return status;
  }
  // Depasser les seuils EST l'objectif d'un stress : seules de vraies erreurs alertent.
  return result.error_rate > 0.01 ? 'fail' : 'surcharge';
};

// Convertit une duree ("1m30s", "45s", "2m") en secondes. Tolerant.
export function toSeconds(value) {
  if (value == null) return 0;
  if (typeof value === 'number') return value;
  const mult = { ms: 0.001, s: 1, m: 60, h: 3600 };
  let total = 0;
  const re = /(\d+)(ms|s|m|h)/g;
  let m;
  while ((m = re.exec(String(value)))) total += parseInt(m[1], 10) * mult[m[2]];
  return total;
}
