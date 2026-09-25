// Mini-graphe du profil de charge (VUs ou débit dans le temps) + curseur de progression.
import { useEffect, useState } from 'react';
import { Box, Stack, Typography } from '@mui/material';
import { ACCENT, ACCENT2, toSeconds } from './theme';

// Modèle ouvert : mêmes formes (rampe, palier, escalier), mais l'axe porte des
// requêtes par seconde et non des utilisateurs.
const OPEN_TYPES = ['open_load', 'open_stress', 'open_endurance', 'open_capacity'];
const RAMPING_TYPES = ['load', 'stress', 'open_load', 'open_stress'];
const STAIRCASE_TYPES = ['capacity', 'calibration', 'open_capacity'];

export function ProfileChart({ testType, params, running = false, startedAt = null }) {
  const W = 640,
    H = 96,
    pad = 8;
  const isOpen = OPEN_TYPES.includes(testType);
  const isRamping = RAMPING_TYPES.includes(testType);
  const unit = isOpen ? 'req/s' : 'VUs';
  // Le modèle ouvert range ses paliers sous `rate*`, le modèle fermé sous `vus*`.
  const levelOf = (name) => Number(isOpen ? params[`rate${name}`] : params[`vus${name}`]) || 0;

  // Rafraichit un timer local pendant le run pour animer le curseur de phase.
  // 100 % cote client (aucune requete) : le curseur suit le TEMPS ecoule.
  const [nowTs, setNowTs] = useState(Date.now());
  useEffect(() => {
    if (!running || !startedAt) return undefined;
    const id = setInterval(() => setNowTs(Date.now()), 200);
    return () => clearInterval(id);
  }, [running, startedAt]);

  let points;
  let peak;
  if (STAIRCASE_TYPES.includes(testType)) {
    const start = levelOf('_start');
    const vmax = levelOf('_max');
    const step = Math.max(1, levelOf('_step') || 1);
    const ramp = toSeconds(params.ramp);
    const steady = toSeconds(params.steady);
    points = [{ t: 0, v: 0 }];
    let t = 0;
    let level = Math.min(start, vmax);
    let guard = 0;
    while (level <= vmax && guard < 40) {
      t += ramp;
      points.push({ t, v: level });
      t += steady;
      points.push({ t, v: level });
      level += step;
      guard += 1;
    }
    t += ramp;
    points.push({ t, v: 0 });
    peak = points.reduce((mx, pt) => Math.max(mx, pt.v), 0);
  } else if (isRamping) {
    const up = toSeconds(params.ramp_up);
    const hold = toSeconds(params.steady ?? params.peak_hold);
    const down = toSeconds(params.ramp_down);
    const target = levelOf('');
    peak = target;
    points = [
      { t: 0, v: 0 },
      { t: up, v: target },
      { t: up + hold, v: target },
      { t: up + hold + down, v: 0 },
    ];
  } else {
    const dur = toSeconds(params.duration);
    const target = testType === 'smoke' ? 1 : levelOf('');
    peak = target;
    points = [
      { t: 0, v: 0 },
      { t: 0.001, v: target },
      { t: dur, v: target },
      { t: dur, v: 0 },
    ];
  }

  const tMax = points[points.length - 1].t || 1;
  const vMax = peak || 1;
  const px = (t) => pad + (t / tMax) * (W - 2 * pad);
  const py = (v) => H - pad - (v / vMax) * (H - 2 * pad);

  const line = points.map((p) => `${px(p.t)},${py(p.v)}`).join(' ');
  const area = `${px(0)},${H - pad} ${line} ${px(tMax)},${H - pad}`;

  const fmt = (s) => {
    s = Math.round(s);
    if (s < 60) return `${s}s`;
    const m = Math.floor(s / 60),
      r = s % 60;
    return r ? `${m}m${r}s` : `${m}m`;
  };

  // Position du curseur = temps ecoule (borne a la duree du profil).
  const elapsed = running && startedAt ? Math.min((nowTs - startedAt) / 1000, tMax) : null;
  const vAt = (t) => {
    for (let i = 1; i < points.length; i += 1) {
      if (t <= points[i].t) {
        const a = points[i - 1],
          b = points[i];
        const f = b.t === a.t ? 1 : (t - a.t) / (b.t - a.t);
        return a.v + f * (b.v - a.v);
      }
    }
    return points[points.length - 1].v;
  };
  const phase = elapsed == null ? null : phaseLabel(testType, params, elapsed, tMax);

  return (
    <Box
      sx={{
        p: 1.5,
        borderRadius: 2,
        background: 'rgba(0,0,0,0.18)',
        border: '1px solid rgba(255,255,255,0.06)',
      }}
    >
      <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.5 }}>
        <Typography variant="caption" color="text.secondary">
          Profil de charge - {unit} dans le temps
        </Typography>
        <Typography variant="caption" sx={{ color: ACCENT }}>
          {elapsed == null
            ? `pic ${vMax} ${unit} · ${fmt(tMax)}`
            : `${phase} · ${fmt(elapsed)} / ${fmt(tMax)}`}
        </Typography>
      </Stack>
      <Box
        component="svg"
        viewBox={`0 0 ${W} ${H}`}
        sx={{ width: '100%', height: 96, display: 'block' }}
      >
        <defs>
          <linearGradient id="loadArea" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={ACCENT} stopOpacity="0.35" />
            <stop offset="100%" stopColor={ACCENT} stopOpacity="0" />
          </linearGradient>
        </defs>
        <polygon points={area} fill="url(#loadArea)" />
        <polyline
          points={line}
          fill="none"
          stroke={ACCENT}
          strokeWidth="2"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        {points.map((p, i) => (
          <circle key={i} cx={px(p.t)} cy={py(p.v)} r="2.5" fill={ACCENT2} />
        ))}
        {elapsed != null && (
          <g>
            <line
              x1={px(elapsed)}
              y1={pad}
              x2={px(elapsed)}
              y2={H - pad}
              stroke="#ffffff"
              strokeWidth="1.5"
              strokeDasharray="3 3"
              opacity="0.85"
            />
            <circle cx={px(elapsed)} cy={py(vAt(elapsed))} r="4" fill="#ffffff" />
          </g>
        )}
      </Box>
    </Box>
  );
}

function phaseLabel(testType, params, elapsed, tMax) {
  if (RAMPING_TYPES.includes(testType)) {
    const up = toSeconds(params.ramp_up);
    const hold = toSeconds(params.steady ?? params.peak_hold);
    if (elapsed < up) return 'Montée';
    if (elapsed < up + hold) return 'Palier';
    if (elapsed < tMax) return 'Descente';
    return 'Terminé';
  }
  if (STAIRCASE_TYPES.includes(testType)) {
    return elapsed < tMax ? 'En paliers' : 'Terminé';
  }
  return elapsed < tMax ? 'En cours' : 'Terminé';
}
