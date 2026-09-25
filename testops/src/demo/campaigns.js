/**
 * Campagnes simulées : la campagne enregistrée sur une vraie installation, et celles
 * qu'un visiteur crée pendant sa visite.
 *
 * Un lot rejoue les résultats réels de chaque test sur sa cible, puis bascule les
 * cellules comme services/campaigns/execution.py : on ne touche que les « todo ».
 */
import seed from './campaigns.json';
import { emit } from './bus';
import { json, matching } from './http';
import { nextSessionId, recordedRun, runTimeline, startSession } from './replay';

const campaigns = new Map([[seed.campaign.id, { ...seed.campaign }]]);
const cells = new Map([[seed.campaign.id, seed.cells.map((cell) => ({ ...cell }))]]);
let created = 0;

const now = () => new Date().toISOString().slice(0, 19);

const progress = (id) => {
  const counts = { todo: 0, passed: 0, failed: 0 };
  cells.get(id).forEach((cell) => {
    counts[cell.status] += 1;
  });
  const total = counts.todo + counts.passed + counts.failed;
  const played = counts.passed + counts.failed;
  const pct = (n) => (total ? Math.round((1000 * n) / total) / 10 : 0);
  return { total, ...counts, played, pct_played: pct(played), pct_passed: pct(counts.passed) };
};

const view = (id) => ({ ...campaigns.get(id), progress: progress(id) });

const notFound = () => json({ error: 'Campagne introuvable' }, 404);

const create = (body) => {
  const name = (body?.name || '').trim();
  if (!name) return json({ error: 'Le nom de la campagne est requis.' }, 400);

  const targets = (body.targets || []).map((target) => ({
    platform: String(target.platform || 'web').toLowerCase(),
    browser: String(target.browser || '').toLowerCase(),
    device: String(target.device || '').toLowerCase(),
  }));
  created += 1;
  const id = `camp_demo${String(created).padStart(7, '0')}`;
  const stamp = now();
  campaigns.set(id, {
    id,
    name,
    status: 'created',
    tags_include: body.include_tags || [],
    tags_exclude: body.exclude_tags || [],
    targets,
    config: body.config || {},
    created_at: stamp,
    updated_at: stamp,
  });

  let cellId = 0;
  cells.set(
    id,
    matching(body.include_tags, body.exclude_tags).flatMap((test) =>
      targets.map((target) => ({
        id: (cellId += 1),
        campaign_id: id,
        test_name: test.name,
        test_file: test.file,
        ...target,
        status: 'todo',
        last_session_id: null,
        report_path: null,
        updated_at: stamp,
      }))
    )
  );
  return json({ campaign: view(id) }, 201);
};

const apply = (id, browser, device, tests, sessionId) => {
  const verdicts = new Map(tests.map((t) => [t.name, t.status === 'PASS' ? 'passed' : 'failed']));
  const stamp = now();
  cells.get(id).forEach((cell) => {
    if (cell.browser !== browser || cell.device !== device || cell.status !== 'todo') return;
    if (!verdicts.has(cell.test_name)) return;
    Object.assign(cell, {
      status: verdicts.get(cell.test_name),
      last_session_id: sessionId,
      updated_at: stamp,
    });
  });
};

const runBatch = (id, body) => {
  const campaign = campaigns.get(id);
  if (!campaign) return notFound();

  const browser = String(body?.browser || '').toLowerCase();
  const device = String(body?.device || '').toLowerCase();
  const count = Math.max(1, parseInt(body?.count, 10) || 10);
  if (!campaign.targets.some((t) => t.browser === browser && t.device === device)) {
    return json({ error: `Cible hors campagne : ${browser}+${device}` }, 400);
  }

  const sessionId = nextSessionId(`${browser}-${device}`, 3);
  const todo = [
    ...new Set(
      cells
        .get(id)
        .filter((c) => c.browser === browser && c.device === device && c.status === 'todo')
        .map((c) => c.test_name)
    ),
  ]
    .sort()
    .slice(0, count);
  const { tests, notes } = recordedRun(browser, device, todo);

  const updated = () => emit('campaign_updated', { campaign_id: id, session_id: sessionId });
  startSession(
    sessionId,
    runTimeline(sessionId, tests, {
      notes,
      after: [() => apply(id, browser, device, tests, sessionId), updated],
    })
  );
  return json({ status: 'started', session_id: sessionId });
};

const withCampaign =
  (handler) =>
  (body, { params }) =>
    campaigns.has(params[0]) ? handler(params[0], body) : notFound();

const setStatus = (status) =>
  withCampaign((id) => {
    Object.assign(campaigns.get(id), { status, updated_at: now() });
    return json({ campaign: view(id) });
  });

export const campaignRoutes = [
  [
    'GET',
    '/campaigns',
    () =>
      json({
        campaigns: [...campaigns.keys()]
          .map(view)
          .sort((a, b) => b.created_at.localeCompare(a.created_at)),
      }),
  ],
  ['POST', '/campaigns', create],
  ['GET', /^\/campaigns\/([^/]+)$/, withCampaign((id) => json({ campaign: view(id) }))],
  ['GET', /^\/campaigns\/([^/]+)\/cells$/, withCampaign((id) => json({ cells: cells.get(id) }))],
  ['POST', /^\/campaigns\/([^/]+)\/run$/, (body, { params }) => runBatch(params[0], body)],
  ['POST', /^\/campaigns\/([^/]+)\/activate$/, setStatus('active')],
  ['POST', /^\/campaigns\/([^/]+)\/close$/, setStatus('closed')],
  [
    'POST',
    /^\/campaigns\/([^/]+)\/reset-failed$/,
    withCampaign((id) => {
      const failed = cells.get(id).filter((cell) => cell.status === 'failed');
      failed.forEach((cell) => Object.assign(cell, { status: 'todo', updated_at: now() }));
      return json({ status: 'ok', reset: failed.length });
    }),
  ],
  [
    'DELETE',
    /^\/campaigns\/([^/]+)$/,
    withCampaign((id) => {
      campaigns.delete(id);
      cells.delete(id);
      return json({ status: 'deleted' });
    }),
  ],
  [
    'POST',
    /^\/campaigns\/([^/]+)\/report$/,
    withCampaign((id) => {
      if (id === seed.campaign.id) return json(seed.report);
      if (progress(id).played === 0) return json({ error: 'Aucun lot joue a agreger.' }, 400);
      return json(
        { error: 'Démonstration : seul le rapport de la campagne enregistrée est publié.' },
        400
      );
    }),
  ],
];
