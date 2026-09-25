import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { ThemeProvider } from '@mui/material/styles';
import { API_BASE_URL } from '../config/api';
import { theme, ACCENT_GRADIENT } from '../components/load/theme';
import ActionButton from '../components/ActionButton';

const GOOD = '#4caf50';
const BAD = '#f44336';

const FILTERS = [
  { id: 'all', label: 'Tout' },
  { id: 'non_couvert', label: 'Non couvert' },
  { id: 'couvert', label: 'Couvert' },
];

// La recherche porte sur le vocabulaire fonctionnel, jamais sur les noms de tests :
// sinon un ecran remonte pour un mot present dans un test qui ne fait que le traverser.
const matches = (item, q) =>
  !q ||
  `${item.label} ${item.id} ${item.type || ''} ${item.criticite || ''}`.toLowerCase().includes(q);

function EntryRow({ item, testsKey }) {
  const [open, setOpen] = useState(false);
  const covered = item.statut === 'couvert';
  const tests = item[testsKey] || [];
  return (
    <Card sx={{ mb: 0.75 }}>
      <CardContent
        onClick={() => setOpen((v) => !v)}
        sx={{ cursor: 'pointer', py: 1.25, '&:last-child': { pb: 1.25 } }}
      >
        <Stack direction="row" alignItems="center" spacing={1.5}>
          <Box
            sx={{ width: 9, height: 9, borderRadius: '50%', background: covered ? GOOD : BAD }}
          />
          <Typography sx={{ flex: 1 }}>
            {item.label}{' '}
            <Typography
              component="span"
              variant="caption"
              color="text.secondary"
              sx={{ fontFamily: 'monospace' }}
            >
              {item.id}
            </Typography>
          </Typography>
          {item.type && <Chip label={item.type} size="small" variant="outlined" />}
          {item.criticite && <Chip label={item.criticite} size="small" variant="outlined" />}
          <Typography variant="caption" color="text.secondary">
            {covered ? `${tests.length} test${tests.length > 1 ? 's' : ''}` : 'non couvert'}
          </Typography>
        </Stack>
        {open && (
          <Box sx={{ mt: 1.5, ml: 2.5, pl: 1.75, borderLeft: '1px solid rgba(255,255,255,0.12)' }}>
            {covered ? (
              tests.map((name) => (
                <Typography key={name} variant="body2" color="text.secondary">
                  {name}
                </Typography>
              ))
            ) : (
              <Typography variant="body2" sx={{ color: BAD }}>
                Aucun test automatisé.
              </Typography>
            )}
          </Box>
        )}
      </CardContent>
    </Card>
  );
}

/**
 * Page "Couverture fonctionnelle" : croise le referentiel functional_map/ avec le
 * code des tests. Lecture seule ; l'analyse est refaite a chaque ouverture.
 */
export default function CoveragePage() {
  const [data, setData] = useState(null);
  const [findings, setFindings] = useState([]);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');

  useEffect(() => {
    fetch(`${API_BASE_URL}/coverage`)
      .then((r) => r.json())
      .then((d) => {
        setData(d.report);
        setFindings(d.findings || []);
      })
      .catch(() => setError("L'analyse de couverture n'a pas pu être chargée."));
  }, []);

  const openReport = async () => {
    await fetch(`${API_BASE_URL}/coverage/export`, { method: 'POST' });
    window.open(`${API_BASE_URL}/coverage/report`, '_blank', 'noopener');
  };

  const modules = useMemo(() => {
    if (!data) return [];
    const q = query.trim().toLowerCase();
    const keep = (item) => matches(item, q) && (filter === 'all' || item.statut === filter);
    return data.modules
      .map((m) => ({
        ...m,
        ecrans: m.ecrans.filter(keep),
        fonctionnalites: m.fonctionnalites.filter(keep),
      }))
      .filter((m) => m.ecrans.length || m.fonctionnalites.length);
  }, [data, query, filter]);

  const errors = findings.filter((f) => f.level === 'error');

  return (
    <ThemeProvider theme={theme}>
      <Box sx={{ p: 4, maxWidth: 1100, mx: 'auto' }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 0.5 }}>
          <Typography variant="h5">Couverture fonctionnelle</Typography>
          <Stack direction="row" spacing={1}>
            <ActionButton className="small" tone="accent" onClick={openReport}>
              Rapport partageable
            </ActionButton>
          </Stack>
        </Stack>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
          Établie à partir du code des tests - pas d&apos;une exécution.
          {data && (
            <>
              {' '}
              Référentiel : {data.perimetre.ecrans} écrans et popups,{' '}
              {data.perimetre.fonctionnalites} fonctionnalités décrits. Ce qui n&apos;y figure pas
              n&apos;est pas évalué.
            </>
          )}
        </Typography>

        {error && <Alert severity="error">{error}</Alert>}
        {errors.length > 0 && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {errors.length} référence(s) invalide(s) - le rapport n&apos;est pas fiable tant
            qu&apos;elles subsistent :
            {errors.slice(0, 5).map((f) => (
              <Box key={`${f.location}${f.message}`} sx={{ fontSize: 13, mt: 0.5 }}>
                {f.location} - {f.message}
              </Box>
            ))}
          </Alert>
        )}

        {!data && !error && <CircularProgress size={24} />}

        {data && (
          <>
            <Stack direction="row" spacing={1} sx={{ mb: 3, flexWrap: 'wrap', gap: 1 }}>
              <TextField
                size="small"
                fullWidth
                sx={{ flex: '1 1 300px' }}
                placeholder="Rechercher un écran, une popup, une fonctionnalité…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
              {FILTERS.map((f) => (
                <Chip
                  key={f.id}
                  label={f.label}
                  onClick={() => setFilter(f.id)}
                  variant={filter === f.id ? 'filled' : 'outlined'}
                  sx={
                    filter === f.id
                      ? { background: ACCENT_GRADIENT, color: '#04121a', fontWeight: 600 }
                      : {}
                  }
                />
              ))}
            </Stack>

            {modules.length === 0 && (
              <Typography color="text.secondary">Aucun résultat pour cette recherche.</Typography>
            )}

            {modules.map((mod) => (
              <Box key={mod.id} sx={{ mb: 4 }}>
                <Typography variant="h6" sx={{ mb: 1 }}>
                  {mod.label}
                </Typography>
                {mod.ecrans.length > 0 && (
                  <>
                    <Typography variant="overline" color="text.secondary">
                      Écrans et popups
                    </Typography>
                    {mod.ecrans.map((item) => (
                      <EntryRow key={item.id} item={item} testsKey="atteint_par" />
                    ))}
                  </>
                )}
                {mod.fonctionnalites.length > 0 && (
                  <>
                    <Typography
                      variant="overline"
                      color="text.secondary"
                      sx={{ display: 'block', mt: 2 }}
                    >
                      Fonctionnalités
                    </Typography>
                    {mod.fonctionnalites.map((item) => (
                      <EntryRow key={item.id} item={item} testsKey="verifiee_par" />
                    ))}
                  </>
                )}
              </Box>
            ))}

            <Divider sx={{ my: 3 }} />
            <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.7 }}>
              <b>Écran ou popup couvert</b> : au moins un test automatisé passe dessus au cours de
              son scénario.
              <br />
              <b>Fonctionnalité couverte</b> : au moins un test déclare la vérifier - plus fort que
              « traverser », le test en contrôle le résultat attendu.
              <br />
              <b>Non couvert</b> : l&apos;élément existe dans le référentiel et aucun test ne
              l&apos;atteint. C&apos;est une absence réelle de test, pas un angle mort de
              l&apos;outil.
            </Typography>
          </>
        )}
      </Box>
    </ThemeProvider>
  );
}
