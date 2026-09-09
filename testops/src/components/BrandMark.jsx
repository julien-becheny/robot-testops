import '../css/BrandMark.css';

const BrandMark = ({ size = 34, showWord = true, className = '' }) => (
  <span className={`brand ${className}`}>
    <span className="brand-mark" style={{ '--mark': `${size}px` }} aria-hidden="true">
      <span className="brand-ring slow" />
      <span className="brand-ring" />
      <span className="brand-core" />
    </span>
    {showWord && (
      <span className="brand-word">
        Test<b>Ops</b>
      </span>
    )}
  </span>
);

export default BrandMark;
