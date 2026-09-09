import { useEffect, useState } from 'react';
import { FiArrowRight, FiPlay } from 'react-icons/fi';
import { API_BASE_URL } from '../config/api';
import ActionButton from '../components/ActionButton';
import { findNavItem } from '../config/navigation';
import '../css/HomePage.css';

const SMOKE = findNavItem('smoke');
const TAGS = findNavItem('tags');

const getJson = async (path) => {
  try {
    const res = await fetch(`${API_BASE_URL}${path}`);
    return res.ok ? await res.json() : null;
  } catch {
    return null;
  }
};

const plural = (n, word) => `${n} ${word}${n > 1 ? 's' : ''}`;

const Block = ({ item, meta, actions, children }) => {
  const Icon = item.icon;
  return (
    <article className="home-block" style={{ '--tint': item.color }}>
      <span className="home-block-halo" aria-hidden="true" />
      <span className="home-block-icon">
        <Icon size={21} />
      </span>
      <h2 className="home-block-title">{item.label}</h2>
      <p className="home-block-desc">{item.desc}</p>
      <p className="home-block-meta">{meta}</p>
      {children}
      <div className="home-block-actions">{actions}</div>
    </article>
  );
};

const MenuPage = ({
  setPage,
  onLaunchSmoke,
  onOpenTags,
  runningCount = 0,
  environmentStatus = 'loading',
}) => {
  const [catalog, setCatalog] = useState(null);
  const [smoke, setSmoke] = useState(null);

  // Le backend demarre parfois apres l'interface : attendre qu'il reponde plutot qu'un vide definitif.
  useEffect(() => {
    if (environmentStatus !== 'ready') return undefined;
    let alive = true;
    getJson('/available-tags').then((data) => alive && data && setCatalog(data));
    getJson('/smoke-suite').then((data) => alive && data && setSmoke(data));
    return () => {
      alive = false;
    };
  }, [environmentStatus, runningCount]);

  const openTags = (tags = []) => (onOpenTags ? onOpenTags(tags) : setPage('tags'));

  const running = runningCount > 0;

  return (
    <div className="home-page">
      <div className="home-body">
        {running && (
          <button type="button" className="home-live" onClick={() => setPage('execution')}>
            <span className="home-live-dot" aria-hidden="true" />
            <span className="home-live-text">
              <strong>Exécution en cours</strong>
              <span>{plural(runningCount, 'run')} en cours</span>
            </span>
            <span className="home-live-go">
              Voir l’exécution
              <FiArrowRight size={16} />
            </span>
          </button>
        )}

        <section className="home-blocks">
          <Block
            item={SMOKE}
            meta={smoke?.file ? `Suite fixe · ${smoke.file}` : 'suite en lecture'}
            actions={
              !running && (
                <ActionButton tint={SMOKE.color} icon={FiPlay} onClick={onLaunchSmoke}>
                  Lancer le smoke
                </ActionButton>
              )
            }
          >
            <ul className="home-block-list">
              {(smoke?.tests || []).slice(0, 4).map((name) => (
                <li key={name}>{name}</li>
              ))}
              {(smoke?.tests?.length || 0) > 4 && (
                <li className="more">+{smoke.tests.length - 4} autres</li>
              )}
            </ul>
          </Block>

          <Block
            item={TAGS}
            meta={
              catalog
                ? `${plural(catalog.total_tests, 'test')} · ${plural(catalog.total_tags, 'tag')}`
                : 'catalogue en lecture'
            }
            actions={
              <ActionButton tint={TAGS.color} onClick={() => openTags()}>
                Choisir les tags
                <FiArrowRight size={15} />
              </ActionButton>
            }
          >
            <div className="home-chips">
              {(catalog?.tags || []).slice(0, 6).map((tag) => (
                <button
                  key={tag.name}
                  type="button"
                  className="home-chip"
                  onClick={() => openTags([tag.name])}
                  title={`Lancer la sélection sur « ${tag.name} »`}
                >
                  {tag.name}
                  <span>{tag.count}</span>
                </button>
              ))}
            </div>
          </Block>
        </section>
      </div>
    </div>
  );
};

export default MenuPage;
