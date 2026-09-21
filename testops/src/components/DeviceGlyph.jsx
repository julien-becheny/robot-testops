// Les trois appareils dessinés à la même échelle : c'est leur PROPORTION qui les distingue,
// pas un pictogramme - les icônes tablette et mobile des jeux courants se confondent.
const SHAPES = {
  desktop: { x: 1.5, y: 3, w: 21, h: 13.5, r: 1.6 },
  tablet: { x: 6, y: 1.5, w: 12, h: 18, r: 1.6 },
  mobile: { x: 8.25, y: 1.5, w: 7.5, h: 18, r: 2 },
};

const DeviceGlyph = ({ device, size = 18, className = '' }) => {
  const s = SHAPES[device];
  if (!s) return null;
  const cx = s.x + s.w / 2;

  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 21"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <rect x={s.x} y={s.y} width={s.w} height={s.h} rx={s.r} />
      {device === 'desktop' && (
        <>
          <line x1={cx} y1={s.y + s.h} x2={cx} y2="19" />
          <line x1={cx - 3.5} y1="19.5" x2={cx + 3.5} y2="19.5" />
        </>
      )}
      {device === 'tablet' && (
        <line x1={cx - 1.6} y1={s.y + s.h - 1.6} x2={cx + 1.6} y2={s.y + s.h - 1.6} />
      )}
      {device === 'mobile' && <line x1={cx - 1.2} y1={s.y + 1.8} x2={cx + 1.2} y2={s.y + 1.8} />}
    </svg>
  );
};

export default DeviceGlyph;
