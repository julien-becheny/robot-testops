// Composants de presentation reutilisables du module « Tests de charge ».
import { Box, Card, Stack, Typography, TextField } from '@mui/material';
import { FiCheck, FiTarget } from 'react-icons/fi';
import { ACCENT, ACCENT_GRADIENT, ACCENT_SOFT, ACCENT_SOFT_HOVER } from './theme';

// Card avec le lisere signature en haut (identite TestOps).
export function SignatureCard({ children, sx = {}, ...rest }) {
  return (
    <Card
      sx={{
        position: 'relative',
        overflow: 'hidden',
        '&::before': {
          content: '""',
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          height: 3,
          background: ACCENT_GRADIENT,
        },
        ...sx,
      }}
      {...rest}
    >
      {children}
    </Card>
  );
}

export function SectionTitle({ index, title, hint }) {
  return (
    <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 2 }}>
      <Box
        sx={{
          width: 24,
          height: 24,
          borderRadius: '50%',
          flexShrink: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 13,
          fontWeight: 700,
          color: '#04121f',
          background: ACCENT_GRADIENT,
        }}
      >
        {index}
      </Box>
      <Typography variant="h6" fontWeight={600}>
        {title}
      </Typography>
      {hint && (
        <Typography variant="caption" color="text.secondary">
          {hint}
        </Typography>
      )}
    </Stack>
  );
}

export function StepBar({ step }) {
  const steps = [
    [1, 'Cible'],
    [2, 'Profil'],
    [3, 'Exécution'],
  ];
  return (
    <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 3 }}>
      {steps.map(([n, label], i) => {
        const active = step === n;
        const done = step > n;
        return (
          <Stack key={n} direction="row" alignItems="center" spacing={1}>
            <Box
              sx={{
                width: 26,
                height: 26,
                borderRadius: '50%',
                flexShrink: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 13,
                fontWeight: 700,
                color: active || done ? '#04121f' : 'rgba(255,255,255,0.6)',
                background: active || done ? ACCENT_GRADIENT : 'rgba(255,255,255,0.08)',
              }}
            >
              {done ? <FiCheck size={15} /> : n}
            </Box>
            <Typography
              variant="body2"
              sx={{
                fontWeight: active ? 700 : 400,
                color: active ? 'text.primary' : 'text.secondary',
              }}
            >
              {label}
            </Typography>
            {i < steps.length - 1 && (
              <Box
                sx={{
                  width: 28,
                  height: 2,
                  mx: 0.5,
                  borderRadius: 1,
                  background: done ? ACCENT_GRADIENT : 'rgba(255,255,255,0.12)',
                }}
              />
            )}
          </Stack>
        );
      })}
    </Stack>
  );
}

export function TargetCard({ target, selected, onSelect }) {
  return (
    <Box
      onClick={onSelect}
      sx={{
        height: '100%',
        p: 2,
        borderRadius: 3,
        boxSizing: 'border-box',
        cursor: 'pointer',
        background: selected ? ACCENT_SOFT : 'rgba(255,255,255,0.03)',
        border: selected ? `1px solid ${ACCENT}` : '1px solid rgba(255,255,255,0.08)',
        transition: 'all .2s ease',
        '&:hover': {
          background: selected ? ACCENT_SOFT_HOVER : 'rgba(255,255,255,0.06)',
          transform: 'translateY(-2px)',
        },
      }}
    >
      <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 0.75 }}>
        <Box
          sx={{
            fontSize: '1.3rem',
            width: 38,
            height: 38,
            flexShrink: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderRadius: 2,
            color: ACCENT,
            background: 'rgba(255,255,255,0.05)',
          }}
        >
          <FiTarget size={19} />
        </Box>
        <Typography variant="subtitle1" fontWeight={600} sx={{ lineHeight: 1.2 }}>
          {target.label}
        </Typography>
        {selected && (
          <Box sx={{ ml: 'auto', color: ACCENT, display: 'flex' }}>
            <FiCheck size={18} />
          </Box>
        )}
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.45, mb: 0.5 }}>
        {target.description}
      </Typography>
      <Typography variant="caption" sx={{ color: ACCENT, wordBreak: 'break-all' }}>
        {target.base_url}
      </Typography>
    </Box>
  );
}

export function TypeCard({ profile, icon, selected, disabled, onSelect }) {
  return (
    <Box
      onClick={disabled ? undefined : onSelect}
      sx={{
        height: '100%',
        p: 2,
        borderRadius: 3,
        boxSizing: 'border-box',
        cursor: disabled ? 'default' : 'pointer',
        background: selected ? ACCENT_SOFT : 'rgba(255,255,255,0.03)',
        border: selected ? `1px solid ${ACCENT}` : '1px solid rgba(255,255,255,0.08)',
        transition: 'all .2s ease',
        opacity: disabled && !selected ? 0.55 : 1,
        '&:hover': disabled
          ? {}
          : {
              background: selected ? ACCENT_SOFT_HOVER : 'rgba(255,255,255,0.06)',
              transform: 'translateY(-2px)',
            },
      }}
    >
      <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 0.75 }}>
        <Box
          sx={{
            fontSize: '1.3rem',
            width: 38,
            height: 38,
            flexShrink: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderRadius: 2,
            color: ACCENT,
            background: 'rgba(255,255,255,0.05)',
          }}
        >
          {icon}
        </Box>
        <Typography variant="subtitle1" fontWeight={600} sx={{ lineHeight: 1.2 }}>
          {profile.label}
        </Typography>
        {selected && (
          <Box sx={{ ml: 'auto', color: ACCENT, display: 'flex' }}>
            <FiCheck size={18} />
          </Box>
        )}
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.45 }}>
        {profile.description}
      </Typography>
    </Box>
  );
}

export function ParamField({ field, value, onChange, disabled }) {
  const isNumber = field.type === 'int' || field.type === 'float';
  return (
    <TextField
      label={field.label}
      type={isNumber ? 'number' : 'text'}
      value={value ?? ''}
      onChange={(e) => onChange(field.name, e.target.value)}
      disabled={disabled}
      sx={{ flex: '1 1 180px', minWidth: 160 }}
    />
  );
}
