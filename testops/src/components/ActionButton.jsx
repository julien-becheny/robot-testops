// Bouton d'action de run : l'aspect au repos, l'épaisseur qui s'écrase le temps du clic.
import { useEffect, useRef, useState } from 'react';
import '../css/ActionButton.css';

// L'action fait souvent changer de page : sans ce sursis, l'enfoncement n'aurait pas
// le temps d'être vu. Assez court pour ne pas se ressentir comme une latence.
const PRESS_MS = 190;

const ActionButton = ({
  tone = 'signature',
  tint,
  icon: Icon,
  children,
  className = '',
  onClick,
  ...rest
}) => {
  const [pressed, setPressed] = useState(false);
  const timer = useRef(null);

  useEffect(() => () => clearTimeout(timer.current), []);

  const press = (event) => {
    if (!onClick || pressed) return;
    setPressed(true);
    timer.current = setTimeout(() => {
      setPressed(false);
      onClick(event);
    }, PRESS_MS);
  };

  return (
    <button
      type="button"
      className={`action-btn tone-${tone} ${pressed ? 'pressed' : ''} ${className}`}
      style={tint ? { '--tint': tint } : undefined}
      onClick={press}
      {...rest}
    >
      {Icon && <Icon size={15} />}
      {children}
    </button>
  );
};

export default ActionButton;
