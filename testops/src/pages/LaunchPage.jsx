import { FiPlay, FiZap } from 'react-icons/fi';
import { BROWSERS, DEVICES } from '../components/Header';
import ActionButton from '../components/ActionButton';
import '../css/LaunchPage.css';

const labelOf = (list, value) => list.find((entry) => entry.value === value)?.label || value;

const smokeDescriptor = (selectedBrowsers, selectedDevices) => {
  const combos = selectedBrowsers.flatMap((browser) =>
    selectedDevices.map((device) => `${labelOf(BROWSERS, browser)} · ${labelOf(DEVICES, device)}`)
  );

  return {
    icon: FiZap,
    title: 'Smoke test',
    subtitle:
      'Vérifie que la chaîne complète répond : navigateur, application, assertions. À jouer avant tout le reste.',
    cards: [
      {
        label: 'Ce qui va tourner',
        value: '00_smoke.robot',
        hint: 'Suite web SauceDemo',
      },
      {
        label: 'Sur quelles cibles',
        value: `${combos.length} combinaison${combos.length > 1 ? 's' : ''}`,
        hint: combos.join(', '),
      },
      {
        label: 'Pendant le run',
        value: 'Logs en direct',
        hint: 'Un run par combinaison, lancés à la suite',
      },
    ],
    steps: [
      "Ouvre le navigateur sur l'URL cible affichée en haut.",
      'Joue la suite smoke sur chaque combinaison sélectionnée.',
      'Bascule sur « Exécution » : logs en direct, puis rapport.',
    ],
    actionLabel: 'Lancer le smoke test',
  };
};

const LaunchPage = ({ selectedBrowsers = [], selectedDevices = [], onLaunch }) => {
  const descriptor = smokeDescriptor(selectedBrowsers, selectedDevices);
  const Icon = descriptor.icon;

  return (
    <div className="launch-page">
      <header className="launch-head">
        <span className="launch-head-icon">
          <Icon size={26} />
        </span>
        <div>
          <h1 className="launch-title">{descriptor.title}</h1>
          <p className="launch-subtitle">{descriptor.subtitle}</p>
        </div>
      </header>

      <div className="launch-cards">
        {descriptor.cards.map((card) => (
          <div key={card.label} className="launch-card">
            <span className="launch-card-label">{card.label}</span>
            <span className="launch-card-value">{card.value}</span>
            <span className="launch-card-hint">{card.hint}</span>
          </div>
        ))}
      </div>

      <section className="launch-steps">
        <h2 className="launch-section-title">Déroulé</h2>
        <ol>
          {descriptor.steps.map((step, index) => (
            <li key={step}>
              <span className="launch-step-index">{index + 1}</span>
              <span>{step}</span>
            </li>
          ))}
        </ol>
      </section>

      <div className="launch-action">
        <ActionButton icon={FiPlay} onClick={onLaunch}>
          {descriptor.actionLabel}
        </ActionButton>
        <span className="launch-note">
          Plateforme, navigateurs, appareils et URL cible se règlent dans la barre du haut.
        </span>
      </div>
    </div>
  );
};

export default LaunchPage;
