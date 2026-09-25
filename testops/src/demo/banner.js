/**
 * Ruban de démonstration.
 *
 * Sans lui, un visiteur croit piloter une installation réelle : le bandeau dit
 * ce qui est rejoué et renvoie au dépôt. Il vit hors de React - tout le dossier
 * `demo/` disparaît du bundle de production, l'application n'en sait rien.
 */
const STYLE = `
.demo-ribbon {
  position: fixed;
  left: 50%;
  bottom: 14px;
  transform: translateX(-50%);
  z-index: 9999;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 14px;
  border-radius: 999px;
  border: 1px solid rgba(238, 67, 209, 0.35);
  background: rgba(10, 14, 22, 0.92);
  box-shadow: 0 8px 26px rgba(0, 0, 0, 0.5);
  font-family: var(--font-ui, system-ui), sans-serif;
  font-size: 0.78rem;
  color: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(6px);
}
.demo-ribbon strong {
  color: #ee43d1;
  font-weight: 600;
  letter-spacing: 0.02em;
}
.demo-ribbon a {
  color: #38bdf8;
  text-decoration: none;
  border-bottom: 1px solid rgba(56, 189, 248, 0.4);
}
.demo-ribbon a:hover {
  border-bottom-color: #38bdf8;
}
.demo-ribbon button {
  border: 0;
  background: none;
  color: rgba(255, 255, 255, 0.45);
  cursor: pointer;
  font-size: 1rem;
  line-height: 1;
  padding: 0 0 0 4px;
}
.demo-ribbon button:hover {
  color: rgba(255, 255, 255, 0.9);
}
@media (max-width: 720px) {
  .demo-ribbon {
    font-size: 0.72rem;
    max-width: 92vw;
  }
}
`;

export const mountDemoRibbon = () => {
  const style = document.createElement('style');
  style.textContent = STYLE;
  document.head.appendChild(style);

  const ribbon = document.createElement('div');
  ribbon.className = 'demo-ribbon';
  ribbon.innerHTML = `
    <strong>Démonstration</strong>
    <span>aucun test n'est réellement exécuté - des runs enregistrés sont rejoués.</span>
    <a href="https://github.com/julien-becheny/robot-testops" target="_blank" rel="noreferrer">
      Voir le code
    </a>
  `;

  const close = document.createElement('button');
  close.type = 'button';
  close.setAttribute('aria-label', 'Masquer le bandeau de démonstration');
  close.textContent = '×';
  close.addEventListener('click', () => ribbon.remove());
  ribbon.appendChild(close);

  document.body.appendChild(ribbon);
};
