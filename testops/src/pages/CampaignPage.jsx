import { useCallback, useEffect, useRef, useState } from 'react';
import { io } from 'socket.io-client';
import {
  Autocomplete,
  Box,
  CardContent,
  Chip,
  Divider,
  Grid,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { ThemeProvider } from '@mui/material/styles';
import { FiFileText, FiGrid } from 'react-icons/fi';
import { API_BASE_URL, SOCKET_URL } from '../config/api';
import { theme, ACCENT, ACCENT_GRADIENT } from '../components/load/theme';
import { SignatureCard, SectionTitle } from '../components/load/common';
import ActionButton from '../components/ActionButton';
import {
  CoverageMatrix,
  ProgressBars,
  StatusChip,
  TargetChips,
  targetLabel,
} from '../components/campaign/parts';

const BROWSERS = ['chromium', 'firefox', 'webkit'];
const DEVICES = ['desktop', 'tablet', 'mobile'];

// Bouton bascule (chip) reutilise pour choisir navigateurs et appareils.
function ToggleChip({ label, active, onClick }) {
  return (
    <Chip
      label={label}
      onClick={onClick}
      variant={active ? 'filled' : 'outlined'}
      sx={
        active
          ? { background: ACCENT_GRADIENT, color: '#04121f', fontWeight: 700 }
          : { borderColor: 'rgba(255,255,255,0.2)', color: 'text.secondary' }
      }
    />
  );
}

export default function CampaignPage({ onRunCampaign }) {
  const [view, setView] = useState('list'); // list | create | detail
  const [campaigns, setCampaigns] = useState([]);
  const [allTags, setAllTags] = useState([]);

  // Formulaire de creation
  const [name, setName] = useState('');
  const [includeTags, setIncludeTags] = useState([]);
  const [excludeTags, setExcludeTags] = useState([]);
  const [browsers, setBrowsers] = useState(['chromium']);
  const [devices, setDevices] = useState(['desktop']);
  const [testCount, setTestCount] = useState(0);
  const [createErr, setCreateErr] = useState('');

  // Vue detail
  const [detail, setDetail] = useState(null); // { campaign, cells }
  const [batchCount, setBatchCount] = useState(10);
  const [buildingReport, setBuildingReport] = useState(false);

  const detailIdRef = useRef(null);

  // ===== Chargements =====
  const loadCampaigns = useCallback(() => {
    fetch(`${API_BASE_URL}/campaigns`)
      .then((r) => r.json())
      .then((d) => setCampaigns(d.campaigns || []))
      .catch(() => setCampaigns([]));
  }, []);

  useEffect(() => {
    loadCampaigns();
  }, [loadCampaigns]);

  useEffect(() => {
    fetch(`${API_BASE_URL}/available-tags`)
      .then((r) => r.json())
      .then((d) => setAllTags((d.tags || []).map((t) => t.name)))
      .catch(() => setAllTags([]));
  }, []);

  // Compte des tests correspondant aux tags (apercu de la matrice).
  useEffect(() => {
    fetch(`${API_BASE_URL}/matching-tests`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ include_tags: includeTags, exclude_tags: excludeTags }),
    })
      .then((r) => r.json())
      .then((d) => setTestCount(d.count || 0))
      .catch(() => setTestCount(0));
  }, [includeTags, excludeTags]);

  const loadDetail = useCallback((id) => {
    Promise.all([
      fetch(`${API_BASE_URL}/campaigns/${id}`).then((r) => r.json()),
      fetch(`${API_BASE_URL}/campaigns/${id}/cells`).then((r) => r.json()),
    ])
      .then(([c, cells]) => setDetail({ campaign: c.campaign, cells: cells.cells || [] }))
      .catch(() => {});
  }, []);

  // ===== Socket (une fois) : rafraichit la campagne ouverte en direct =====
  useEffect(() => {
    const socket = io(SOCKET_URL);

    socket.on('campaign_updated', (d) => {
      if (detailIdRef.current && d.campaign_id === detailIdRef.current) {
        loadDetail(detailIdRef.current);
      }
      loadCampaigns();
    });

    return () => socket.disconnect();
  }, [loadCampaigns, loadDetail]);

  // ===== Actions =====
  const openCampaign = (id) => {
    detailIdRef.current = id;
    setDetail(null);
    setView('detail');
    loadDetail(id);
  };

  const backToList = () => {
    detailIdRef.current = null;
    setView('list');
    loadCampaigns();
  };

  const createCampaign = async () => {
    setCreateErr('');
    const targets = [];
    for (const b of browsers)
      for (const dv of devices) {
        targets.push({ platform: 'web', browser: b, device: dv });
      }
    try {
      const res = await fetch(`${API_BASE_URL}/campaigns`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name,
          include_tags: includeTags,
          exclude_tags: excludeTags,
          targets,
          config: {},
        }),
      });
      const data = await res.json();
      if (!res.ok || data.error) {
        setCreateErr(data.error || 'Échec de la création');
        return;
      }
      setName('');
      setIncludeTags([]);
      setExcludeTags([]);
      setBrowsers(['chromium']);
      setDevices(['desktop']);
      openCampaign(data.campaign.id);
    } catch (e) {
      setCreateErr(String(e));
    }
  };

  const deleteCampaign = async (id, e) => {
    if (e) e.stopPropagation();
    if (!window.confirm('Supprimer cette campagne et sa matrice ?')) return;
    await fetch(`${API_BASE_URL}/campaigns/${id}`, { method: 'DELETE' }).catch(() => {});
    loadCampaigns();
  };

  const setCampaignStatus = async (id, action) => {
    await fetch(`${API_BASE_URL}/campaigns/${id}/${action}`, { method: 'POST' }).catch(() => {});
    loadDetail(id);
    loadCampaigns();
  };

  const resetFailed = async (id) => {
    await fetch(`${API_BASE_URL}/campaigns/${id}/reset-failed`, { method: 'POST' }).catch(() => {});
    loadDetail(id);
    loadCampaigns();
  };

  const openReport = async (id) => {
    setBuildingReport(true);
    try {
      const res = await fetch(`${API_BASE_URL}/campaigns/${id}/report`, { method: 'POST' });
      const data = await res.json();
      if (res.ok && data.url) window.open(`${API_BASE_URL}${data.url}`, '_blank', 'noopener');
    } catch {
      /* ignore */
    }
    setBuildingReport(false);
  };

  // Nombre de cellules « todo » pour une cible donnee (vue detail).
  const todoForTarget = (t) =>
    (detail?.cells || []).filter(
      (c) =>
        c.platform === t.platform &&
        c.browser === t.browser &&
        c.device === t.device &&
        c.status === 'todo'
    ).length;

  const targetCount = browsers.length * devices.length;

  return (
    <ThemeProvider theme={theme}>
      <Box sx={{ minHeight: '100%', py: 4, px: 2 }}>
        <Box sx={{ maxWidth: 960, mx: 'auto' }}>
          {/* En-tete */}
          <Stack direction="row" alignItems="center" justifyContent="space-between" mb={3}>
            <Stack direction="row" alignItems="center" spacing={1.5}>
              <Box
                sx={{
                  width: 48,
                  height: 48,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  borderRadius: 2.5,
                  color: ACCENT,
                  background: 'rgba(255,255,255,0.05)',
                }}
              >
                <FiGrid size={24} />
              </Box>
              <Box>
                <Typography variant="h4" fontWeight={700} sx={{ lineHeight: 1.1 }}>
                  Campagnes de tests
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Joue tout le parc de tests en plusieurs passes, sans rejouer ce qui est déjà
                  validé.
                </Typography>
              </Box>
            </Stack>
            <Stack direction="row" spacing={1}>
              {view === 'list' && (
                <ActionButton
                  onClick={() => {
                    setView('create');
                    setCreateErr('');
                  }}
                >
                  + Nouvelle campagne
                </ActionButton>
              )}
              {view !== 'list' && (
                <ActionButton className="ghost" onClick={backToList}>
                  ← Campagnes
                </ActionButton>
              )}
            </Stack>
          </Stack>

          {/* ===== Vue LISTE ===== */}
          {view === 'list' &&
            (campaigns.length === 0 ? (
              <SignatureCard>
                <CardContent>
                  <Typography color="text.secondary">
                    Aucune campagne. Crée ta première campagne pour couvrir un parc de tests par
                    passes.
                  </Typography>
                </CardContent>
              </SignatureCard>
            ) : (
              <Grid container spacing={2}>
                {campaigns.map((c) => (
                  <Grid item xs={12} sm={6} key={c.id}>
                    <SignatureCard sx={{ cursor: 'pointer', height: '100%' }}>
                      <CardContent onClick={() => openCampaign(c.id)}>
                        <Stack direction="row" alignItems="center" justifyContent="space-between">
                          <Typography variant="h6" fontWeight={600} sx={{ pr: 1 }}>
                            {c.name}
                          </Typography>
                          <StatusChip status={c.status} />
                        </Stack>
                        <Box sx={{ mt: 1 }}>
                          <TargetChips targets={c.targets} />
                        </Box>
                        <ProgressBars progress={c.progress} />
                        <Stack direction="row" justifyContent="flex-end" sx={{ mt: 1 }}>
                          <ActionButton
                            className="small ghost"
                            tone="danger"
                            onClick={(e) => deleteCampaign(c.id, e)}
                          >
                            Supprimer
                          </ActionButton>
                        </Stack>
                      </CardContent>
                    </SignatureCard>
                  </Grid>
                ))}
              </Grid>
            ))}

          {/* ===== Vue CREATION ===== */}
          {view === 'create' && (
            <SignatureCard>
              <CardContent>
                <SectionTitle
                  index="1"
                  title="Nouvelle campagne"
                  hint="Les tests et les cibles sont figés à la création."
                />

                <TextField
                  label="Nom de la campagne"
                  fullWidth
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  sx={{ mb: 2.5 }}
                />

                <Autocomplete
                  multiple
                  options={allTags}
                  value={includeTags}
                  onChange={(e, v) => setIncludeTags(v)}
                  filterSelectedOptions
                  renderInput={(p) => (
                    <TextField {...p} label="Tags inclus" placeholder="Ajouter un tag" />
                  )}
                  sx={{ mb: 2 }}
                />
                <Autocomplete
                  multiple
                  options={allTags}
                  value={excludeTags}
                  onChange={(e, v) => setExcludeTags(v)}
                  filterSelectedOptions
                  renderInput={(p) => (
                    <TextField {...p} label="Tags exclus" placeholder="Ajouter un tag" />
                  )}
                  sx={{ mb: 2 }}
                />

                <Typography variant="overline" color="text.secondary">
                  Navigateurs
                </Typography>
                <Stack
                  direction="row"
                  spacing={1}
                  flexWrap="wrap"
                  useFlexGap
                  sx={{ mt: 0.5, mb: 2 }}
                >
                  {BROWSERS.map((b) => (
                    <ToggleChip
                      key={b}
                      label={b}
                      active={browsers.includes(b)}
                      onClick={() =>
                        setBrowsers((prev) =>
                          prev.includes(b) ? prev.filter((x) => x !== b) : [...prev, b]
                        )
                      }
                    />
                  ))}
                </Stack>

                <Typography variant="overline" color="text.secondary">
                  Appareils
                </Typography>
                <Stack
                  direction="row"
                  spacing={1}
                  flexWrap="wrap"
                  useFlexGap
                  sx={{ mt: 0.5, mb: 2 }}
                >
                  {DEVICES.map((dv) => (
                    <ToggleChip
                      key={dv}
                      label={dv}
                      active={devices.includes(dv)}
                      onClick={() =>
                        setDevices((prev) =>
                          prev.includes(dv) ? prev.filter((x) => x !== dv) : [...prev, dv]
                        )
                      }
                    />
                  ))}
                </Stack>

                <Divider sx={{ my: 2, borderColor: 'rgba(255,255,255,0.08)' }} />
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  Matrice : <b style={{ color: ACCENT }}>{testCount}</b> tests ×{' '}
                  <b style={{ color: ACCENT }}>{targetCount}</b> cibles ={' '}
                  <b style={{ color: ACCENT }}>{testCount * targetCount}</b> cellules.
                </Typography>

                {createErr && (
                  <Typography color="error" variant="body2" sx={{ mb: 1.5 }}>
                    {createErr}
                  </Typography>
                )}
                <Stack direction="row" spacing={2} justifyContent="flex-end">
                  <ActionButton className="ghost" onClick={backToList}>
                    Annuler
                  </ActionButton>
                  <ActionButton
                    onClick={createCampaign}
                    disabled={!name.trim() || testCount === 0 || targetCount === 0}
                  >
                    Créer la campagne
                  </ActionButton>
                </Stack>
              </CardContent>
            </SignatureCard>
          )}

          {/* ===== Vue DETAIL ===== */}
          {view === 'detail' && detail && (
            <>
              <SignatureCard sx={{ mb: 2 }}>
                <CardContent>
                  <Stack direction="row" alignItems="center" justifyContent="space-between">
                    <Stack direction="row" alignItems="center" spacing={1.5}>
                      <Typography variant="h5" fontWeight={700}>
                        {detail.campaign.name}
                      </Typography>
                      <StatusChip status={detail.campaign.status} />
                    </Stack>
                    <Stack direction="row" spacing={1}>
                      {detail.campaign.progress && detail.campaign.progress.played > 0 && (
                        <ActionButton
                          className="small ghost"
                          disabled={buildingReport}
                          icon={FiFileText}
                          onClick={() => openReport(detail.campaign.id)}
                        >
                          {buildingReport ? 'Génération…' : 'Rapport'}
                        </ActionButton>
                      )}
                      {detail.campaign.progress && detail.campaign.progress.failed > 0 && (
                        <ActionButton
                          className="small"
                          tone="danger"
                          onClick={() => resetFailed(detail.campaign.id)}
                        >
                          Rejouer les échecs ({detail.campaign.progress.failed})
                        </ActionButton>
                      )}
                      {detail.campaign.status !== 'active' && (
                        <ActionButton
                          className="small"
                          tone="accent"
                          onClick={() => setCampaignStatus(detail.campaign.id, 'activate')}
                        >
                          Activer
                        </ActionButton>
                      )}
                      {detail.campaign.status !== 'closed' && (
                        <ActionButton
                          className="small ghost"
                          onClick={() => setCampaignStatus(detail.campaign.id, 'close')}
                        >
                          Clôturer
                        </ActionButton>
                      )}
                    </Stack>
                  </Stack>
                  <Box sx={{ mt: 1 }}>
                    <ProgressBars progress={detail.campaign.progress} />
                  </Box>
                </CardContent>
              </SignatureCard>

              <SignatureCard sx={{ mb: 2 }}>
                <CardContent>
                  <SectionTitle
                    index="▶"
                    title="Jouer un lot"
                    hint="Joue les tests encore « à jouer » d'une cible, par paquets."
                  />
                  <Box sx={{ mb: 2 }}>
                    <TextField
                      label="Nombre de tests à jouer"
                      type="number"
                      size="small"
                      value={batchCount}
                      onChange={(e) => setBatchCount(e.target.value)}
                      inputProps={{ min: 1 }}
                      sx={{ width: 200 }}
                    />
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{ display: 'block', mt: 0.5 }}
                    >
                      À chaque clic sur « Jouer »
                    </Typography>
                  </Box>
                  <Grid container spacing={1.5}>
                    {(detail.campaign.targets || []).map((t, i) => {
                      const todo = todoForTarget(t);
                      return (
                        <Grid item xs={12} sm={6} md={4} key={i}>
                          <Box
                            sx={{
                              p: 1.5,
                              borderRadius: 2,
                              border: '1px solid rgba(255,255,255,0.1)',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'space-between',
                            }}
                          >
                            <Box>
                              <Typography variant="body2" fontWeight={600}>
                                {targetLabel(t)}
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                {todo} à jouer
                              </Typography>
                            </Box>
                            <ActionButton
                              className="small"
                              disabled={todo === 0}
                              onClick={() =>
                                onRunCampaign(
                                  detail.campaign.id,
                                  t.browser,
                                  t.device,
                                  Number(batchCount) || 10
                                )
                              }
                            >
                              Jouer
                            </ActionButton>
                          </Box>
                        </Grid>
                      );
                    })}
                  </Grid>
                </CardContent>
              </SignatureCard>

              <SignatureCard>
                <CardContent>
                  <SectionTitle
                    index="▦"
                    title="Matrice de couverture"
                    hint="Ligne = test, colonne = cible."
                  />
                  <CoverageMatrix cells={detail.cells} targets={detail.campaign.targets} />
                </CardContent>
              </SignatureCard>
            </>
          )}
        </Box>
      </Box>
    </ThemeProvider>
  );
}
