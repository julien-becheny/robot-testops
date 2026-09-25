import { useEffect, useRef, useState } from 'react';
import { io } from 'socket.io-client';
import {
  Box,
  Card,
  CardContent,
  Typography,
  TextField,
  Stack,
  Chip,
  LinearProgress,
  Divider,
  Grid,
  Collapse,
} from '@mui/material';
import { ThemeProvider } from '@mui/material/styles';
import { FiActivity, FiClock, FiExternalLink, FiEye, FiTarget } from 'react-icons/fi';
import { API_BASE_URL, SOCKET_URL, withCurrentHost } from '../config/api';
import { theme, ACCENT, TYPE_ICONS, PARAM_LABELS } from '../components/load/theme';
import {
  SignatureCard,
  SectionTitle,
  StepBar,
  TargetCard,
  TypeCard,
  ParamField,
} from '../components/load/common';
import { ProfileChart } from '../components/load/ProfileChart';
import ActionButton from '../components/ActionButton';
import {
  LiveBand,
  ResultCard,
  AnalysisCard,
  BreachCard,
  TimelineCard,
} from '../components/load/results';
import { HistoryCard } from '../components/load/history';

/**
 * Page "Tests de charge" : flux en 3 etapes (cible -> profil -> execution) et
 * vue historique. Ne contient que l'etat, la logique socket et le lancement du run ;
 * les composants de presentation vivent dans components/load/.
 */
export default function LoadTestPage() {
  const [targets, setTargets] = useState([]);
  const [target, setTarget] = useState('');
  const [profiles, setProfiles] = useState([]);
  const [models, setModels] = useState([]);
  const [testType, setTestType] = useState('load');
  const [params, setParams] = useState({});
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [status, setStatus] = useState('idle'); // idle | running | done
  const [sessionId, setSessionId] = useState(null);
  const [result, setResult] = useState(null);
  const [live, setLive] = useState(null);
  const [logs, setLogs] = useState([]);
  const [startedAt, setStartedAt] = useState(null);
  const [history, setHistory] = useState([]);
  const [compare, setCompare] = useState([]); // ids des runs a comparer (max 2)
  const [baselineIds, setBaselineIds] = useState([]); // runs servant de reference
  const [step, setStep] = useState(1); // 1 Cible | 2 Profil | 3 Execution
  const [view, setView] = useState('flow'); // 'flow' | 'history'
  const [targetSearch, setTargetSearch] = useState('');
  const [dashboard, setDashboard] = useState(null); // { url, engine } du run en cours
  const socketRef = useRef(null);
  const dashboardWinRef = useRef(null);

  // k6 ne publie son resume qu'une fois tous les navigateurs deconnectes de son
  // dashboard : sans cette fermeture, le run ne se terminerait jamais cote TestOps.
  const closeDashboard = () => {
    try {
      if (dashboardWinRef.current) dashboardWinRef.current.close();
    } catch {
      // fenetre deja fermee par l'utilisateur
    }
    dashboardWinRef.current = null;
    setDashboard(null);
  };

  // Cibles autorisees (liste blanche)
  useEffect(() => {
    fetch(`${API_BASE_URL}/load-targets`)
      .then((r) => r.json())
      .then((d) => {
        setTargets(d.targets || []);
        if (d.targets && d.targets.length) setTarget(d.targets[0].id);
      })
      .catch(() => setTargets([]));
  }, []);

  // Definitions des types de test (champs par type), groupes par famille de charge
  useEffect(() => {
    fetch(`${API_BASE_URL}/load-profiles`)
      .then((r) => r.json())
      .then((d) => {
        setProfiles(d.types || []);
        setModels(d.models || []);
      })
      .catch(() => setProfiles([]));
  }, []);

  const currentProfile = profiles.find((p) => p.id === testType);

  // Reinitialise les params aux defauts quand le type (ou les profils) change
  useEffect(() => {
    if (!currentProfile) return;
    const defaults = {};
    [...currentProfile.fields, ...currentProfile.advanced].forEach((f) => {
      defaults[f.name] = f.default;
    });
    setParams(defaults);
    setShowAdvanced(false);
  }, [testType, profiles]); // eslint-disable-line react-hooks/exhaustive-deps

  // Socket unique pour la page
  useEffect(() => {
    const socket = io(SOCKET_URL);
    socketRef.current = socket;
    return () => socket.disconnect();
  }, []);

  const loadHistory = () => {
    fetch(`${API_BASE_URL}/load-history`)
      .then((r) => r.json())
      .then((d) => setHistory(d.runs || []))
      .catch(() => {});
  };

  // Charge l'historique au montage (et apres chaque run termine, cf onComplete).
  useEffect(() => {
    loadHistory();
    loadBaselines();
  }, []);

  const toggleCompare = (id) => {
    setCompare((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      if (prev.length >= 2) return [prev[1], id];
      return [...prev, id];
    });
  };

  const clearHistory = () => {
    fetch(`${API_BASE_URL}/load-history`, { method: 'DELETE' })
      .then(() => {
        setHistory([]);
        setCompare([]);
      })
      .catch(() => {});
  };

  // Les references vivent hors de l'historique (qui est borne) : on les recharge
  // depuis le serveur pour que les drapeaux survivent a un rafraichissement.
  const loadBaselines = () => {
    fetch(`${API_BASE_URL}/load-baselines`)
      .then((r) => r.json())
      .then((d) =>
        setBaselineIds(
          Object.values(d.baselines || {})
            .map((b) => b.run_id)
            .filter(Boolean)
        )
      )
      .catch(() => {});
  };

  const toggleBaseline = (run) => {
    const estReference = baselineIds.includes(run.id);
    const requete = estReference
      ? fetch(`${API_BASE_URL}/load-baseline`, {
          method: 'DELETE',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ target: run.target, test_type: run.test_type }),
        })
      : fetch(`${API_BASE_URL}/load-baseline`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ run_id: run.id }),
        });
    requete.then(loadBaselines).catch(() => {});
  };

  const setParam = (name, value) => setParams((prev) => ({ ...prev, [name]: value }));

  const launch = async () => {
    setResult(null);
    setLive(null);
    setLogs([]);
    setDashboard(null);
    setStartedAt(Date.now());
    setStatus('running');
    try {
      const res = await fetch(`${API_BASE_URL}/run-load`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target, test_type: testType, params }),
      });
      const data = await res.json();
      if (!res.ok || data.error) {
        setStatus('done');
        setResult({ error: data.error || 'Échec du lancement' });
        return;
      }

      const sid = data.session_id;
      setSessionId(sid);
      setDashboard(data.dashboard_url ? { url: data.dashboard_url, engine: data.engine } : null);

      const socket = socketRef.current;
      socket.emit('join_session', { session_id: sid });

      const onLog = (d) => {
        if (d.session_id && d.session_id !== sid) return;
        setLogs((prev) => [...prev, d.message]);
      };
      const onResult = (d) => {
        if (d.session_id && d.session_id !== sid) return;
        setResult(d.result || {});
      };
      const onMetrics = (d) => {
        if (d.session_id && d.session_id !== sid) return;
        const metrics = d.metrics || {};
        if (metrics.finished) {
          closeDashboard();
          return;
        }
        setLive(metrics);
      };
      const onComplete = (d) => {
        if (d && d.session_id && d.session_id !== sid) return;
        setStatus('done');
        socket.off('log', onLog);
        socket.off('load-result', onResult);
        socket.off('load-metrics', onMetrics);
        socket.off('execution-complete', onComplete);
        socket.emit('leave_session', { session_id: sid });
        loadHistory();
      };

      socket.on('log', onLog);
      socket.on('load-result', onResult);
      socket.on('load-metrics', onMetrics);
      socket.on('execution-complete', onComplete);
    } catch (e) {
      setStatus('done');
      setResult({ error: String(e) });
    }
  };

  const stop = async () => {
    if (!sessionId) return;
    await fetch(`${API_BASE_URL}/stop-test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId }),
    }).catch(() => {});
  };

  const isRunning = status === 'running';
  const selectedTarget = targets.find((t) => t.id === target);
  const q = targetSearch.trim().toLowerCase();
  const filteredTargets = q
    ? targets.filter((t) => `${t.label} ${t.base_url} ${t.description}`.toLowerCase().includes(q))
    : targets;

  // Lance le test et bascule sur l'etape d'execution.
  const launchAndGo = () => {
    setStep(3);
    launch();
  };
  // Repart configurer un nouveau test (garde la cible + les params en memoire).
  const newTest = () => {
    setStatus('idle');
    setResult(null);
    setLive(null);
    setLogs([]);
    setDashboard(null);
    setStep(1);
  };

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
                <FiActivity size={24} />
              </Box>
              <Box>
                <Typography variant="h4" fontWeight={700} sx={{ lineHeight: 1.1 }}>
                  Tests de charge
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Choisis une cible et un profil, lance le test, suis les métriques en direct.
                </Typography>
              </Box>
            </Stack>
            <Stack direction="row" spacing={1}>
              <ActionButton
                className={`small ${view === 'history' ? '' : 'ghost'}`}
                tone="accent"
                icon={FiClock}
                onClick={() => setView(view === 'history' ? 'flow' : 'history')}
              >
                Historique
              </ActionButton>
            </Stack>
          </Stack>

          {view === 'history' ? (
            history.length > 0 ? (
              <HistoryCard
                runs={history}
                compare={compare}
                onToggle={toggleCompare}
                onClear={clearHistory}
                onSetBaseline={toggleBaseline}
                baselineIds={baselineIds}
              />
            ) : (
              <SignatureCard>
                <CardContent>
                  <Typography color="text.secondary">
                    Aucun run pour le moment. Lance un test de charge : il apparaîtra ici.
                  </Typography>
                </CardContent>
              </SignatureCard>
            )
          ) : (
            <>
              <StepBar step={step} />

              {/* Etape 1 : cible */}
              {step === 1 && (
                <SignatureCard>
                  <CardContent>
                    <SectionTitle
                      index="1"
                      title="Choisis la cible"
                      hint="L'application à mettre sous charge."
                    />
                    {targets.length > 6 && (
                      <TextField
                        size="small"
                        fullWidth
                        placeholder="Rechercher une cible..."
                        value={targetSearch}
                        onChange={(e) => setTargetSearch(e.target.value)}
                        sx={{ mb: 2 }}
                      />
                    )}
                    <Grid container spacing={2}>
                      {filteredTargets.map((t) => (
                        <Grid item xs={12} sm={6} key={t.id}>
                          <TargetCard
                            target={t}
                            selected={t.id === target}
                            onSelect={() => setTarget(t.id)}
                          />
                        </Grid>
                      ))}
                      {filteredTargets.length === 0 && (
                        <Grid item xs={12}>
                          <Typography color="text.secondary" sx={{ p: 1 }}>
                            Aucune cible ne correspond à la recherche.
                          </Typography>
                        </Grid>
                      )}
                    </Grid>
                    <Stack direction="row" justifyContent="flex-end" sx={{ mt: 2.5 }}>
                      <ActionButton disabled={!target} onClick={() => setStep(2)}>
                        Continuer →
                      </ActionButton>
                    </Stack>
                  </CardContent>
                </SignatureCard>
              )}

              {/* Etape 2 : profil (type + parametres) */}
              {step === 2 && (
                <SignatureCard>
                  <CardContent>
                    <SectionTitle
                      index="2"
                      title="Configure le profil de charge"
                      hint={selectedTarget ? `Cible : ${selectedTarget.label}` : ''}
                    />

                    {models.map((model) => {
                      const family = profiles.filter((p) => p.model === model.id);
                      if (!family.length) return null;
                      return (
                        <Box key={model.id} sx={{ mb: 2.5 }}>
                          <Typography
                            variant="overline"
                            sx={{ color: 'text.secondary', letterSpacing: 1 }}
                          >
                            {model.label}
                          </Typography>
                          <Typography
                            variant="caption"
                            color="text.secondary"
                            sx={{ display: 'block', mb: 1 }}
                          >
                            {model.hint}
                          </Typography>
                          <Grid container spacing={2}>
                            {family.map((p) => {
                              const ProfileIcon = TYPE_ICONS[p.id];
                              return (
                                <Grid item xs={12} sm={6} key={p.id}>
                                  <TypeCard
                                    profile={p}
                                    icon={ProfileIcon ? <ProfileIcon size={19} /> : null}
                                    selected={p.id === testType}
                                    disabled={false}
                                    onSelect={() => setTestType(p.id)}
                                  />
                                </Grid>
                              );
                            })}
                          </Grid>
                        </Box>
                      );
                    })}

                    {currentProfile && (
                      <>
                        <ProfileChart testType={testType} params={params} />
                        {currentProfile.engine && (
                          <Typography
                            variant="caption"
                            color="text.secondary"
                            sx={{ display: 'block', mt: 0.75 }}
                          >
                            Exécuté par {currentProfile.engine}
                          </Typography>
                        )}
                        {(currentProfile.goal || currentProfile.watch) && (
                          <Stack spacing={0.75} sx={{ mt: 1.5 }}>
                            {currentProfile.goal && (
                              <Stack direction="row" spacing={1} alignItems="flex-start">
                                <Box
                                  component="span"
                                  sx={{ color: ACCENT, mt: '3px', display: 'flex' }}
                                >
                                  <FiTarget size={15} />
                                </Box>
                                <Typography variant="body2" color="text.secondary">
                                  <Box
                                    component="span"
                                    sx={{ color: 'text.primary', fontWeight: 600 }}
                                  >
                                    Ce qu'on cherche :{' '}
                                  </Box>
                                  {currentProfile.goal}
                                </Typography>
                              </Stack>
                            )}
                            {currentProfile.watch && (
                              <Stack direction="row" spacing={1} alignItems="flex-start">
                                <Box
                                  component="span"
                                  sx={{ color: ACCENT, mt: '3px', display: 'flex' }}
                                >
                                  <FiEye size={15} />
                                </Box>
                                <Typography variant="body2" color="text.secondary">
                                  <Box
                                    component="span"
                                    sx={{ color: 'text.primary', fontWeight: 600 }}
                                  >
                                    À surveiller :{' '}
                                  </Box>
                                  {currentProfile.watch}
                                </Typography>
                              </Stack>
                            )}
                          </Stack>
                        )}
                        <Stack
                          direction="row"
                          spacing={2}
                          flexWrap="wrap"
                          useFlexGap
                          sx={{ mt: 2 }}
                        >
                          {currentProfile.fields.map((f) => (
                            <ParamField
                              key={f.name}
                              field={f}
                              value={params[f.name]}
                              onChange={setParam}
                              disabled={false}
                            />
                          ))}
                        </Stack>
                        {currentProfile.advanced.length > 0 && (
                          <>
                            <ActionButton
                              className="small ghost"
                              onClick={() => setShowAdvanced((v) => !v)}
                              style={{ marginTop: 16 }}
                            >
                              {showAdvanced ? '▾ Options avancées' : '▸ Options avancées'}
                            </ActionButton>
                            <Collapse in={showAdvanced}>
                              <Stack
                                direction="row"
                                spacing={2}
                                flexWrap="wrap"
                                useFlexGap
                                sx={{ mt: 1 }}
                              >
                                {currentProfile.advanced.map((f) => (
                                  <ParamField
                                    key={f.name}
                                    field={f}
                                    value={params[f.name]}
                                    onChange={setParam}
                                    disabled={false}
                                  />
                                ))}
                              </Stack>
                            </Collapse>
                          </>
                        )}
                      </>
                    )}

                    <Divider sx={{ my: 2.5, borderColor: 'rgba(255,255,255,0.08)' }} />
                    <Stack direction="row" spacing={2} justifyContent="space-between">
                      <ActionButton className="ghost" onClick={() => setStep(1)}>
                        ← Retour
                      </ActionButton>
                      <ActionButton onClick={launchAndGo} disabled={!target}>
                        ▶ Lancer le test
                      </ActionButton>
                    </Stack>
                  </CardContent>
                </SignatureCard>
              )}

              {/* Etape 3 : execution + resultats */}
              {step === 3 && (
                <>
                  <SignatureCard sx={{ mb: 2 }}>
                    <CardContent>
                      <Stack
                        direction="row"
                        alignItems="center"
                        justifyContent="space-between"
                        sx={{ mb: 1 }}
                      >
                        <SectionTitle
                          index="3"
                          title={isRunning ? 'Exécution en cours' : 'Exécution terminée'}
                        />
                        {isRunning && (
                          <ActionButton tone="danger" className="small" onClick={stop}>
                            Arrêter
                          </ActionButton>
                        )}
                      </Stack>
                      <Stack
                        direction="row"
                        spacing={1}
                        flexWrap="wrap"
                        useFlexGap
                        sx={{ mb: 1.5 }}
                      >
                        <Chip
                          size="small"
                          icon={<FiTarget size={13} />}
                          label={selectedTarget ? selectedTarget.label : target}
                        />
                        <Chip
                          size="small"
                          color="primary"
                          variant="outlined"
                          label={
                            currentProfile ? currentProfile.label.split('-')[0].trim() : testType
                          }
                        />
                        {Object.entries(params)
                          .filter(([k]) =>
                            [
                              'vus',
                              'ramp_up',
                              'steady',
                              'peak_hold',
                              'ramp_down',
                              'duration',
                            ].includes(k)
                          )
                          .map(([k, v]) => (
                            <Chip
                              key={k}
                              size="small"
                              variant="outlined"
                              label={`${PARAM_LABELS[k] || k} : ${v}`}
                            />
                          ))}
                      </Stack>
                      {/* Le dashboard k6 s'eteint avec le run ; celui de Locust survit un moment. */}
                      {dashboard && (isRunning || dashboard.engine !== 'k6') && (
                        <ActionButton
                          className="small"
                          tone="accent"
                          icon={FiExternalLink}
                          onClick={() => {
                            // Reference gardee (donc sans noopener) pour pouvoir refermer
                            // l'onglet a la fin du run : k6 y retient son resume.
                            dashboardWinRef.current = window.open(
                              withCurrentHost(dashboard.url),
                              '_blank'
                            );
                          }}
                          style={{ marginBottom: 12 }}
                        >
                          Ouvrir le dashboard {dashboard.engine === 'k6' ? 'k6' : 'Locust'} (temps
                          réel)
                        </ActionButton>
                      )}
                      {currentProfile && (
                        <ProfileChart
                          testType={testType}
                          params={params}
                          running={isRunning}
                          startedAt={startedAt}
                        />
                      )}
                      {isRunning && <LinearProgress sx={{ mt: 2, borderRadius: 1 }} />}
                    </CardContent>
                  </SignatureCard>

                  {isRunning && live && <LiveBand live={live} />}
                  {result && <ResultCard result={result} />}
                  {result && result.summary_report_url && (
                    <ActionButton
                      className="small"
                      tone="accent"
                      icon={FiExternalLink}
                      onClick={() =>
                        window.open(
                          withCurrentHost(`${API_BASE_URL}${result.summary_report_url}`),
                          '_blank',
                          'noopener'
                        )
                      }
                      style={{ marginTop: 12 }}
                    >
                      Ouvrir le rapport partageable
                    </ActionButton>
                  )}
                  {result && result.report_url && (
                    <ActionButton
                      className="small"
                      tone="accent"
                      icon={FiExternalLink}
                      onClick={() =>
                        window.open(`${API_BASE_URL}${result.report_url}`, '_blank', 'noopener')
                      }
                      style={{ marginTop: 12 }}
                    >
                      Ouvrir le rapport k6 (courbes du run)
                    </ActionButton>
                  )}
                  {result && result.breach && (
                    <BreachCard
                      breach={result.breach}
                      seuil={result.seuil_p95_ms || params.p95_ms}
                    />
                  )}
                  {result && result.timeline && result.timeline.length > 1 && (
                    <TimelineCard
                      timeline={result.timeline}
                      seuil={result.seuil_p95_ms || params.p95_ms}
                      breach={result.breach}
                    />
                  )}
                  {result && result.analysis && result.analysis.length > 0 && (
                    <AnalysisCard findings={result.analysis} />
                  )}

                  {logs.length > 0 && (
                    <Card sx={{ mt: 2 }}>
                      <CardContent>
                        <Typography variant="subtitle2" gutterBottom>
                          Journal
                        </Typography>
                        <Box
                          sx={{
                            fontFamily: 'monospace',
                            fontSize: 13,
                            whiteSpace: 'pre-wrap',
                            color: 'rgba(255,255,255,0.8)',
                            maxHeight: 260,
                            overflow: 'auto',
                          }}
                        >
                          {logs.map((l, i) => (
                            <div key={i}>{l}</div>
                          ))}
                        </Box>
                      </CardContent>
                    </Card>
                  )}

                  {!isRunning && (
                    <Stack direction="row" spacing={2} sx={{ mt: 2 }} flexWrap="wrap" useFlexGap>
                      <ActionButton className="ghost" onClick={() => setStep(2)}>
                        ← Ajuster le profil
                      </ActionButton>
                      <ActionButton onClick={launch}>↺ Relancer</ActionButton>
                      <ActionButton className="ghost" onClick={newTest}>
                        Nouveau test
                      </ActionButton>
                    </Stack>
                  )}
                </>
              )}
            </>
          )}
        </Box>
      </Box>
    </ThemeProvider>
  );
}
