// Composants de presentation du module « Campagnes de tests ».
// Reutilise le theme et les cards signature du module « Tests de charge ».
import { Box, Chip, LinearProgress, Stack, Tooltip, Typography } from '@mui/material';
import { ACCENT, GOOD, BAD } from '../load/theme';

// Couleurs semantiques des cellules de la matrice (etat d'un test sur une cible).
export const CELL_COLORS = {
  todo: 'rgba(255,255,255,0.16)',
  passed: GOOD,
  failed: BAD,
};
const CELL_LABELS = { todo: 'À jouer', passed: 'Réussi', failed: 'Échec' };

// Libelle court d'une cible (navigateur + appareil).
export const targetLabel = (t) => `${t.browser}/${t.device}`;
const cellKey = (platform, browser, device, testName) =>
  `${platform}|${browser}|${device}|${testName}`;

// Chip d'etat d'une campagne (created | active | closed).
export function StatusChip({ status }) {
  const meta = {
    created: { label: 'Brouillon', color: 'default' },
    active: { label: 'Active', color: 'primary' },
    closed: { label: 'Clôturée', color: 'success' },
  }[status] || { label: status, color: 'default' };
  return <Chip size="small" label={meta.label} color={meta.color} variant="outlined" />;
}

// Deux barres : couverture (% joue) et succes (% valide).
export function ProgressBars({ progress }) {
  const p = progress || {};
  const played = p.pct_played || 0;
  const passed = p.pct_passed || 0;
  return (
    <Stack spacing={1} sx={{ mt: 1 }}>
      <Box>
        <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.25 }}>
          <Typography variant="caption" color="text.secondary">
            Couverture (joué)
          </Typography>
          <Typography variant="caption" sx={{ color: ACCENT, fontWeight: 600 }}>
            {played}% · {p.played || 0}/{p.total || 0}
          </Typography>
        </Stack>
        <LinearProgress variant="determinate" value={played} sx={{ height: 6, borderRadius: 1 }} />
      </Box>
      <Box>
        <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.25 }}>
          <Typography variant="caption" color="text.secondary">
            Succès (validé)
          </Typography>
          <Typography variant="caption" sx={{ color: GOOD, fontWeight: 600 }}>
            {passed}% · {p.passed || 0}/{p.total || 0}
          </Typography>
        </Stack>
        <LinearProgress
          variant="determinate"
          value={passed}
          color="success"
          sx={{ height: 6, borderRadius: 1 }}
        />
      </Box>
    </Stack>
  );
}

// Chips des cibles d'une campagne.
export function TargetChips({ targets }) {
  return (
    <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
      {(targets || []).map((t, i) => (
        <Chip
          key={i}
          size="small"
          variant="outlined"
          label={targetLabel(t)}
          sx={{ borderColor: 'rgba(255,255,255,0.18)' }}
        />
      ))}
    </Stack>
  );
}

// Point de couleur = etat d'une cellule (test x cible).
function CellDot({ status }) {
  return (
    <Tooltip title={CELL_LABELS[status] || status} arrow>
      <Box
        sx={{
          width: 14,
          height: 14,
          borderRadius: '50%',
          mx: 'auto',
          background: CELL_COLORS[status] || CELL_COLORS.todo,
          border: '1px solid rgba(0,0,0,0.25)',
        }}
      />
    </Tooltip>
  );
}

// Matrice de couverture : lignes = tests, colonnes = cibles, cellule = etat.
export function CoverageMatrix({ cells, targets }) {
  const list = cells || [];
  const cols = targets || [];
  const byKey = {};
  const testNames = [];
  const seen = new Set();
  for (const c of list) {
    byKey[cellKey(c.platform, c.browser, c.device, c.test_name)] = c.status;
    if (!seen.has(c.test_name)) {
      seen.add(c.test_name);
      testNames.push(c.test_name);
    }
  }
  testNames.sort();

  if (testNames.length === 0) {
    return <Typography color="text.secondary">Aucune cellule.</Typography>;
  }

  const th = {
    p: 1,
    textAlign: 'center',
    fontSize: 12,
    fontWeight: 600,
    color: 'text.secondary',
    whiteSpace: 'nowrap',
    borderBottom: '1px solid rgba(255,255,255,0.1)',
  };
  const td = {
    p: 1,
    textAlign: 'center',
    borderBottom: '1px solid rgba(255,255,255,0.05)',
  };

  return (
    <Box sx={{ overflowX: 'auto' }}>
      <Box component="table" sx={{ borderCollapse: 'collapse', width: '100%', minWidth: 480 }}>
        <Box component="thead">
          <Box component="tr">
            <Box component="th" sx={{ ...th, textAlign: 'left' }}>
              Test
            </Box>
            {cols.map((t, i) => (
              <Box component="th" key={i} sx={th}>
                {targetLabel(t)}
              </Box>
            ))}
          </Box>
        </Box>
        <Box component="tbody">
          {testNames.map((name) => (
            <Box component="tr" key={name}>
              <Box
                component="td"
                sx={{
                  ...td,
                  textAlign: 'left',
                  fontSize: 13,
                  maxWidth: 340,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {name}
              </Box>
              {cols.map((t, i) => (
                <Box component="td" key={i} sx={td}>
                  <CellDot
                    status={byKey[cellKey(t.platform, t.browser, t.device, name)] || 'todo'}
                  />
                </Box>
              ))}
            </Box>
          ))}
        </Box>
      </Box>
    </Box>
  );
}
