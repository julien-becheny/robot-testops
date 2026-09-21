import { useState, useEffect, useRef, useCallback } from 'react';
import {
  FiGlobe,
  FiList,
  FiMonitor,
  FiPlay,
  FiPlus,
  FiRefreshCw,
  FiSearch,
  FiSettings,
  FiShuffle,
  FiSlash,
  FiSmartphone,
  FiTablet,
  FiTag,
} from 'react-icons/fi';
import { API_BASE_URL } from '../config/api';
import ActionButton from '../components/ActionButton';
import '../css/TagSelector.css';
import chromiumLogo from '../assets/chromium.svg';
import firefoxLogo from '../assets/firefox.svg';
import safariLogo from '../assets/safari.svg';

const BROWSER_LABELS = {
  chromium: { label: 'Chromium', icon: chromiumLogo },
  firefox: { label: 'Firefox', icon: firefoxLogo },
  webkit: { label: 'Safari', icon: safariLogo },
};

const DEVICE_LABELS = {
  desktop: { label: 'Desktop', icon: FiMonitor },
  tablet: { label: 'Tablette', icon: FiTablet },
  mobile: { label: 'Mobile', icon: FiSmartphone },
};

const SUGGESTION_COUNT = 6;

// Les deux panneaux se distinguent par leur teinte, comme les blocs de l'accueil.
const TINTS = {
  include: { color: 'var(--accent)', rgb: 'var(--accent-rgb)' },
  exclude: { color: '#fb7185', rgb: '251, 113, 133' },
};
const tintVars = (kind) => ({ '--tint': TINTS[kind].color, '--tint-rgb': TINTS[kind].rgb });

/** Chemin de suite lisible : le dossier racine est le meme pour tous, il n'apprend rien. */
const shortFile = (file) =>
  String(file)
    .replace(/\\/g, '/')
    .replace(/^test_suites\//, '');

const groupByFile = (tests) => {
  const groups = new Map();
  tests.forEach((test) => {
    const file = shortFile(test.file || '');
    groups.set(file, [...(groups.get(file) || []), test.name]);
  });
  return [...groups.entries()];
};

/**
 * Choix de tags : recherche, liste deroulante au clavier, jetons retirables.
 * Inclure et exclure ne different que par leur libelle et leur teinte : un seul
 * composant, sinon chaque correction serait a faire deux fois.
 */
const TagPicker = ({ kind, title, Icon, available, suggestions, selected, onAdd, onRemove }) => {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const rootRef = useRef(null);

  const matches = query.trim()
    ? available.filter((tag) => tag.toLowerCase().includes(query.toLowerCase()))
    : available;

  useEffect(() => {
    if (!open) return undefined;
    const close = (event) => {
      if (rootRef.current && !rootRef.current.contains(event.target)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open]);

  const add = (tag) => {
    onAdd(tag);
    setQuery('');
    setActiveIndex(-1);
    setOpen(false);
  };

  const handleKeyDown = (event) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      setOpen(true);
      const step = event.key === 'ArrowDown' ? 1 : -1;
      setActiveIndex(Math.min(Math.max(activeIndex + step, 0), matches.length - 1));
    } else if (event.key === 'Enter' && matches[activeIndex]) {
      event.preventDefault();
      add(matches[activeIndex]);
    } else if (event.key === 'Escape') {
      setOpen(false);
      setActiveIndex(-1);
    }
  };

  const listId = `tag-list-${kind}`;

  return (
    <section className={`tag-panel ${kind}-panel`} aria-label={title} style={tintVars(kind)}>
      <h2 className="tag-panel-title">
        <Icon className="tag-panel-icon" size={17} />
        {title}
      </h2>

      <div className="tag-search" ref={rootRef}>
        <FiSearch className="tag-search-icon" size={15} aria-hidden="true" />
        <input
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={open && activeIndex >= 0 ? `${listId}-${activeIndex}` : undefined}
          aria-label={title}
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setActiveIndex(-1);
            setOpen(true);
          }}
          onClick={() => setOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder="Rechercher un tag..."
        />
        {open && (
          <ul className="tag-dropdown" id={listId} role="listbox" aria-label={title}>
            {matches.length > 0 ? (
              matches.map((tag, index) => (
                <li
                  key={tag}
                  id={`${listId}-${index}`}
                  role="option"
                  aria-selected={index === activeIndex}
                  className={index === activeIndex ? 'hovered' : ''}
                  onMouseDown={() => add(tag)}
                  onMouseEnter={() => setActiveIndex(index)}
                >
                  {tag}
                </li>
              ))
            ) : (
              <li className="no-results">Aucun tag correspondant</li>
            )}
          </ul>
        )}
      </div>

      <div className="tag-chips-container">
        {selected.length > 0 ? (
          selected.map((tag) => (
            <div key={tag} className={`tag-chip ${kind}-chip`}>
              <span className="tag-chip-text">{tag}</span>
              <button
                onClick={() => onRemove(tag)}
                className="tag-chip-remove"
                aria-label={`Retirer ${tag}`}
              >
                ×
              </button>
            </div>
          ))
        ) : (
          <p className="tag-empty-message">
            {kind === 'include' ? 'Aucun tag inclus' : 'Aucun tag exclu'}
          </p>
        )}
      </div>

      {suggestions.length > 0 && (
        <div className="tag-suggestions">
          <p className="tag-suggestions-title">Les plus portés - à ajouter d’un clic :</p>
          <div className="tag-suggestions-list">
            {suggestions.map((tag) => (
              <button
                key={tag.name}
                type="button"
                className="tag-suggestion"
                onClick={() => add(tag.name)}
                title={`Ajouter « ${tag.name} »`}
              >
                <FiPlus size={11} aria-hidden="true" />
                {tag.name}
                <span>{tag.count}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </section>
  );
};

const TagSelectorPage = ({
  onRunByTags,
  initialTags = [],
  selectedBrowsers = ['chromium'],
  selectedDevices = ['desktop'],
}) => {
  const [catalog, setCatalog] = useState([]);
  const [selectedIncludeTags, setSelectedIncludeTags] = useState(initialTags);
  const [selectedExcludeTags, setSelectedExcludeTags] = useState([]);
  const [matchingTests, setMatchingTests] = useState([]);
  const [testCaseCount, setTestCaseCount] = useState(0);
  const [isRandomExecution, setIsRandomExecution] = useState(false);
  const [nbSelection, setNbSelection] = useState('');
  const [rerunFailed, setRerunFailed] = useState(false);

  const fetchTags = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/available-tags`);
      const data = await res.json();
      setCatalog(data.tags || []);
    } catch (err) {
      console.error('Erreur chargement tags:', err);
    }
  }, []);

  useEffect(() => {
    fetchTags();
  }, [fetchTags]);

  useEffect(() => {
    const fetchCount = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/matching-tests`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            include_tags: selectedIncludeTags,
            exclude_tags: selectedExcludeTags,
          }),
        });
        const data = await res.json();
        setMatchingTests(data.tests || []);
        setTestCaseCount(data.count || 0);
      } catch (err) {
        console.error('Erreur comptage tests:', err);
        setMatchingTests([]);
        setTestCaseCount(0);
      }
    };
    fetchCount();
  }, [selectedIncludeTags, selectedExcludeTags]);

  const tagNames = catalog.map((tag) => tag.name);
  const availableFor = (taken, other) =>
    tagNames.filter((tag) => !taken.includes(tag) && !other.includes(tag));
  const suggestionsFor = (taken, other) =>
    catalog
      .filter((tag) => !taken.includes(tag.name) && !other.includes(tag.name))
      .slice(0, SUGGESTION_COUNT);

  const sessions = selectedBrowsers.length * selectedDevices.length;
  const willRun = isRandomExecution ? parseInt(nbSelection, 10) || testCaseCount : testCaseCount;
  const suites = groupByFile(matchingTests);

  const handleSubmit = () => {
    if (testCaseCount > 0) {
      const nb = isRandomExecution ? parseInt(nbSelection, 10) || testCaseCount : 0;
      onRunByTags(selectedIncludeTags, selectedExcludeTags, rerunFailed, isRandomExecution, nb);
    }
  };

  const tirageAuSort = isRandomExecution && willRun < testCaseCount;
  const heroLabel = () => {
    if (testCaseCount === 0) return 'Aucun test ne correspond à ces critères.';
    if (tirageAuSort) return `tests tirés au sort parmi les ${testCaseCount} correspondants`;
    return `${testCaseCount > 1 ? 'tests correspondent' : 'test correspond'} aux tags choisis`;
  };

  return (
    <div className="tag-selection-page">
      <div className="tag-body">
        <section className="tag-hero" aria-label="Périmètre du run">
          <div className="tag-hero-scope">
            <p className="tag-hero-eyebrow">Sélection des tags</p>
            <p className="tag-hero-count">
              <span className="tag-hero-figure">{willRun}</span>
              <span className="tag-hero-label">{heroLabel()}</span>
            </p>
          </div>

          <div className="tag-hero-run">
            {testCaseCount > 0 && (
              <div className="tag-browsers-summary">
                <div className="tag-browsers-pills">
                  {selectedBrowsers.map((b) => {
                    const info = BROWSER_LABELS[b];
                    return (
                      <span key={b} className="tag-browser-pill">
                        {info ? (
                          <img className="tag-browser-icon" src={info.icon} alt={info.label} />
                        ) : (
                          <span className="tag-browser-icon">
                            <FiGlobe size={13} />
                          </span>
                        )}
                        {info ? info.label : b}
                      </span>
                    );
                  })}
                </div>
                <span className="tag-browsers-label">×</span>
                <div className="tag-browsers-pills">
                  {selectedDevices.map((d) => {
                    const info = DEVICE_LABELS[d] || { label: d, icon: FiGlobe };
                    const DeviceIcon = info.icon;
                    return (
                      <span key={d} className="tag-browser-pill tag-device-pill">
                        <span className="tag-browser-icon">
                          <DeviceIcon size={13} />
                        </span>
                        {info.label}
                      </span>
                    );
                  })}
                </div>
                <span className="tag-sessions-count">
                  = {sessions} session{sessions > 1 ? 's' : ''}
                </span>
              </div>
            )}

            <ActionButton
              className="tag-run-button"
              tone="accent"
              icon={FiPlay}
              onClick={handleSubmit}
              disabled={testCaseCount === 0}
            >
              Lancer l’exécution
            </ActionButton>
          </div>
        </section>

        <div className="tag-panels-container">
          <TagPicker
            kind="include"
            title="Tags à inclure"
            Icon={FiTag}
            available={availableFor(selectedIncludeTags, selectedExcludeTags)}
            suggestions={suggestionsFor(selectedIncludeTags, selectedExcludeTags)}
            selected={selectedIncludeTags}
            onAdd={(tag) => setSelectedIncludeTags([...selectedIncludeTags, tag])}
            onRemove={(tag) => setSelectedIncludeTags(selectedIncludeTags.filter((t) => t !== tag))}
          />

          <TagPicker
            kind="exclude"
            title="Tags à exclure"
            Icon={FiSlash}
            available={availableFor(selectedExcludeTags, selectedIncludeTags)}
            suggestions={suggestionsFor(selectedExcludeTags, selectedIncludeTags)}
            selected={selectedExcludeTags}
            onAdd={(tag) => setSelectedExcludeTags([...selectedExcludeTags, tag])}
            onRemove={(tag) => setSelectedExcludeTags(selectedExcludeTags.filter((t) => t !== tag))}
          />
        </div>

        <section className="tag-panel options-panel" aria-label="Configuration">
          <h2 className="tag-panel-title">
            <FiSettings className="tag-panel-icon" size={17} />
            Configuration
          </h2>

          <div className="tag-options">
            <div className="tag-option">
              <div className="tag-option-label">
                <span className="tag-option-icon">
                  <FiShuffle size={15} />
                </span>
                <span className="tag-option-text">
                  Exécution aléatoire
                  <small>Débusque les dépendances d’ordre entre tests</small>
                </span>
              </div>
              <label className="tag-toggle">
                <input
                  type="checkbox"
                  aria-label="Exécution aléatoire"
                  checked={isRandomExecution}
                  onChange={(e) => {
                    setIsRandomExecution(e.target.checked);
                    // Un echec en ordre aleatoire est ambigu : le rejeu tranche.
                    if (e.target.checked) setRerunFailed(true);
                  }}
                />
                <span className="tag-toggle-slider"></span>
              </label>
            </div>

            <div className="tag-option">
              <div className="tag-option-label">
                <span className="tag-option-icon">
                  <FiRefreshCw size={15} />
                </span>
                <span className="tag-option-text">
                  Rejouer les échecs
                  <small>
                    {isRandomExecution
                      ? 'Activé avec l’aléatoire : un échec peut venir de l’ordre'
                      : 'Relance les tests tombés, puis fusionne les rapports'}
                  </small>
                </span>
              </div>
              <label className="tag-toggle">
                <input
                  type="checkbox"
                  aria-label="Rejouer les échecs"
                  checked={rerunFailed}
                  onChange={(e) => setRerunFailed(e.target.checked)}
                />
                <span className="tag-toggle-slider"></span>
              </label>
            </div>

            {isRandomExecution && (
              <div className="tag-number-input">
                <label htmlFor="nb-selection">Nombre de tests à sélectionner</label>
                <input
                  id="nb-selection"
                  type="number"
                  value={nbSelection}
                  onChange={(e) => {
                    let value = parseInt(e.target.value);
                    if (value > testCaseCount) {
                      value = testCaseCount;
                    }
                    setNbSelection(value || '');
                  }}
                  placeholder={`Tous (${testCaseCount})`}
                  min="1"
                  max={testCaseCount}
                />
              </div>
            )}
          </div>
        </section>

        <section
          className="tag-panel tag-preview"
          aria-label="Tests correspondants"
          style={tintVars('include')}
        >
          <h2 className="tag-panel-title">
            <FiList className="tag-panel-icon" size={17} />
            Ce que le run va jouer
          </h2>

          {tirageAuSort && (
            <p className="tag-preview-note">
              {willRun} tests seront tirés au sort parmi ceux-ci : la liste montre le vivier, pas la
              sélection finale.
            </p>
          )}

          {suites.length > 0 ? (
            <ul className="tag-preview-suites">
              {suites.map(([file, names]) => (
                <li key={file} className="tag-preview-suite">
                  <p className="tag-preview-file" title={file}>
                    {file}
                  </p>
                  <ul>
                    {names.map((name) => (
                      <li key={name}>{name}</li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          ) : (
            <p className="tag-empty-message">Aucun test ne correspond à ces critères.</p>
          )}
        </section>
      </div>
    </div>
  );
};

export default TagSelectorPage;
