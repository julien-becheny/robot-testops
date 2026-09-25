"""Analyse de couverture fonctionnelle : référentiel déclaré × code des tests.

Deux niveaux, deux sources - rien n'est deviné :

- ce qu'un test **vérifie**  → tag `feat:<id>` porté par le test
- ce qu'un test **traverse** → appel `Wait For Screen  <id>  <locator>`

Le référentiel `functional_map/` est le dénominateur : une fonctionnalité qu'aucun
test ne déclare apparaît « non couverte » au lieu d'être absente du rapport. Une
référence à un identifiant inconnu est une erreur, jamais un silence.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from difflib import get_close_matches
from pathlib import Path

import yaml
from robot.api import get_model, get_resource_model
from robot.api.parsing import ModelVisitor

from core.paths import paths

SCREEN_MARKER = "waitforscreen"
FEATURE_TAG_PREFIX = "feat:"
DYNAMIC_CALL_PREFIXES = ("runkeyword", "waituntilkeywordsucceeds")


# --- Modèle ----------------------------------------------------------------
@dataclass
class Finding:
    level: str
    code: str
    location: str
    message: str


@dataclass
class Entry:
    """Un écran/popup ou une fonctionnalité déclarée dans le référentiel."""

    id: str
    label: str
    module: str
    type: str = ""
    criticite: str = ""


@dataclass
class Module:
    id: str
    label: str
    plateformes: list[str]


@dataclass
class Referentiel:
    modules: list[Module] = field(default_factory=list)
    ecrans: dict[str, Entry] = field(default_factory=dict)
    fonctionnalites: dict[str, Entry] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)


@dataclass
class ScreenRef:
    screen_id: str
    source: str
    line: int


@dataclass
class CodeUnit:
    """Un test ou un keyword, avec ce qu'il appelle et les écrans qu'il marque."""

    name: str
    source: str
    line: int
    doc: str = ""
    # Les arguments déclarés, quand l'unité est un keyword : son contrat d'appel.
    args: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    # Les mêmes appels, dans leur orthographe d'origine : `calls` est normalisé pour la
    # résolution, `calls_raw` reste lisible et garde l'ordre d'écriture.
    calls_raw: list[str] = field(default_factory=list)
    # Les arguments de chaque appel, alignés sur `calls`. Ce sont les données du test :
    # c'est ce qui sépare deux tests jumeaux d'un même test joué sur deux jeux de valeurs.
    calls_args: list[list[str]] = field(default_factory=list)
    screens: list[ScreenRef] = field(default_factory=list)
    # Pour un test : son fichier et ses ressources importées, là où Robot cherche un keyword.
    namespace: frozenset[str] = frozenset()


# --- Helpers ---------------------------------------------------------------
def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(paths.PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _norm(name: str) -> str:
    """Normalise un nom de keyword comme Robot le fait (casse, espaces, underscores)."""
    name = name.strip()
    if "." in name:  # appel préfixé par la resource : `kw_browser.Wait For Screen`
        name = name.rsplit(".", 1)[-1]
    return name.lower().replace(" ", "").replace("_", "")


def _suggest(value: str, known: list[str]) -> str:
    match = get_close_matches(value, known, n=1, cutoff=0.6)
    return f" - proche de : {match[0]}" if match else ""


# --- Référentiel -----------------------------------------------------------
def load_referentiel(map_dir: Path | None = None) -> Referentiel:
    map_dir = map_dir or paths.FUNCTIONAL_MAP
    ref = Referentiel()
    files = sorted([*map_dir.glob("*.yaml"), *map_dir.glob("*.yml")])
    if not files:
        ref.findings.append(
            Finding("error", "MAP_VIDE", _rel(map_dir), "aucun fichier de référentiel trouvé")
        )
        return ref
    for path in files:
        _load_module(path, ref)
    return ref


def _load_module(path: Path, ref: Referentiel) -> None:
    location = _rel(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        ref.findings.append(Finding("error", "MAP_INVALIDE", location, f"YAML illisible : {exc}"))
        return

    module_id = data.get("module")
    if not module_id:
        ref.findings.append(Finding("error", "MAP_INVALIDE", location, "champ 'module' manquant"))
        return

    ref.modules.append(
        Module(module_id, data.get("label") or module_id, list(data.get("plateformes") or []))
    )
    _load_entries(data.get("ecrans"), "ecran", module_id, location, ref)
    _load_entries(data.get("fonctionnalites"), "fonctionnalite", module_id, location, ref)


def _load_entries(raw: object, kind: str, module_id: str, location: str, ref: Referentiel) -> None:
    target = ref.ecrans if kind == "ecran" else ref.fonctionnalites
    for item in raw or []:
        if not isinstance(item, dict) or not item.get("id") or not item.get("label"):
            ref.findings.append(
                Finding("error", "MAP_INVALIDE", location, f"{kind} sans 'id' ou 'label' : {item}")
            )
            continue
        entry_id = str(item["id"])
        if not entry_id.startswith(f"{module_id}."):
            ref.findings.append(
                Finding(
                    "error",
                    "MAP_INVALIDE",
                    location,
                    f"'{entry_id}' doit commencer par '{module_id}.'",
                )
            )
            continue
        if entry_id in target:
            ref.findings.append(
                Finding("error", "MAP_INVALIDE", location, f"identifiant en double : '{entry_id}'")
            )
            continue
        target[entry_id] = Entry(
            id=entry_id,
            label=str(item["label"]),
            module=module_id,
            type=str(item.get("type") or ""),
            criticite=str(item.get("criticite") or ""),
        )


# --- Lecture du code -------------------------------------------------------
class _RobotVisitor(ModelVisitor):
    def __init__(self, source: str) -> None:
        self.source = source
        self.tests: list[CodeUnit] = []
        self.keywords: list[CodeUnit] = []
        self.suite_tags: list[str] = []
        self.imports: list[str] = []
        self.dynamic_calls: list[tuple[str, int]] = []
        self._current: CodeUnit | None = None

    def visit_ResourceImport(self, node) -> None:  # noqa: N802
        self.imports.append(node.name)

    def visit_TestTags(self, node) -> None:  # noqa: N802 - nom imposé par ModelVisitor
        self.suite_tags.extend(node.values)

    def visit_Tags(self, node) -> None:  # noqa: N802
        if self._current is not None:
            self._current.tags.extend(node.values)

    def visit_Documentation(self, node) -> None:  # noqa: N802
        if self._current is not None:  # sinon c'est la documentation de la suite
            self._current.doc = node.value

    def visit_Arguments(self, node) -> None:  # noqa: N802
        if self._current is not None:
            self._current.args.extend(node.values)

    def visit_TestCase(self, node) -> None:  # noqa: N802
        self._visit_container(node, self.tests)

    def visit_Keyword(self, node) -> None:  # noqa: N802
        self._visit_container(node, self.keywords)

    def visit_KeywordCall(self, node) -> None:  # noqa: N802
        if self._current is None or not node.keyword:
            return
        norm = _norm(node.keyword)
        self._current.calls.append(norm)
        self._current.calls_raw.append(node.keyword)
        self._current.calls_args.append(list(node.args))
        if norm.startswith(DYNAMIC_CALL_PREFIXES):
            self.dynamic_calls.append((self._current.name, node.lineno))
        elif norm == SCREEN_MARKER:
            screen_id = node.args[0] if node.args else ""
            self._current.screens.append(ScreenRef(screen_id, self.source, node.lineno))

    def _visit_container(self, node, bucket: list[CodeUnit]) -> None:
        self._current = CodeUnit(name=node.name, source=self.source, line=node.lineno)
        bucket.append(self._current)
        self.generic_visit(node)
        self._current = None


def _source_models(suites_dir: Path, resources_dir: Path) -> list[tuple[Path, object]]:
    sources = [(p, get_model) for p in sorted(suites_dir.rglob("*.robot"))]
    sources += [(p, get_resource_model) for p in sorted(resources_dir.rglob("*.resource"))]
    return sources


def _imported_files(path: Path, names: list[str]) -> list[Path]:
    """Les ressources importées par un fichier, en chemins résolus sur le disque.

    Un import par variable (`${ACTIONS}`) ne se résout qu'au lancement : il est ignoré, et
    ses keywords restent trouvables par la résolution de repli.
    """
    files = []
    for name in names:
        name = name.replace("${CURDIR}", path.parent.as_posix())
        if "${" not in name:
            files.append((path.parent / name).resolve())
    return files


def _namespace(source: str, imports: dict[str, list[str]]) -> frozenset[str]:
    """Le fichier et toutes les ressources qu'il importe, directement ou non."""
    seen: set[str] = set()
    stack = [source]
    while stack:
        current = stack.pop()
        if current not in seen:
            seen.add(current)
            stack.extend(imports.get(current, []))
    return frozenset(seen)


def collect_code(
    suites_dir: Path | None = None, resources_dir: Path | None = None
) -> tuple[list[CodeUnit], dict[str, list[CodeUnit]], list[Finding]]:
    """Retourne (tests, définitions de keywords par nom normalisé, avertissements)."""
    suites_dir = suites_dir or paths.TEST_SUITES
    resources_dir = resources_dir or paths.RESOURCES
    tests: list[CodeUnit] = []
    keywords: dict[str, list[CodeUnit]] = {}
    sources: dict[Path, str] = {}
    imported: dict[str, list[Path]] = {}
    findings: list[Finding] = []

    for path, parser in _source_models(suites_dir, resources_dir):
        visitor = _RobotVisitor(_rel(path))
        visitor.visit(parser(str(path)))
        sources[path.resolve()] = visitor.source
        imported[visitor.source] = _imported_files(path, visitor.imports)
        for test in visitor.tests:
            test.tags.extend(visitor.suite_tags)
            tests.append(test)
        for keyword in visitor.keywords:
            keywords.setdefault(_norm(keyword.name), []).append(keyword)
        findings += [
            Finding(
                "warning",
                "APPEL_DYNAMIQUE",
                f"{_rel(path)}:{line}",
                f"'{name}' fait un appel dynamique : les écrans atteints par ce chemin "
                "échappent à l'analyse",
            )
            for name, line in visitor.dynamic_calls
        ]
    imports = {source: [sources[f] for f in files if f in sources]
               for source, files in imported.items()}
    for test in tests:
        test.namespace = _namespace(test.source, imports)
    return tests, keywords, findings


def collect_keyword_definitions(
    suites_dir: Path | None = None, resources_dir: Path | None = None
) -> list[CodeUnit]:
    """Toutes les définitions de keywords, homonymes compris, en liste plate.

    `collect_code` les indexe par nom pour résoudre un appel. Un catalogue, lui, doit
    montrer chaque définition là où elle est visible.
    """
    definitions: list[CodeUnit] = []
    for path, parser in _source_models(
        suites_dir or paths.TEST_SUITES, resources_dir or paths.RESOURCES
    ):
        visitor = _RobotVisitor(_rel(path))
        visitor.visit(parser(str(path)))
        definitions += visitor.keywords
    return definitions


def _resolve(
    name: str, caller: str, namespace: frozenset[str], keywords: dict[str, list[CodeUnit]]
) -> CodeUnit | None:
    """La définition qu'exécuterait Robot : celle du fichier appelant, puis d'une ressource importée.

    À défaut (import par variable, suite sans import), la première définition connue.
    """
    candidates = keywords.get(name) or []
    for keyword in candidates:
        if keyword.source == caller:
            return keyword
    for keyword in candidates:
        if keyword.source in namespace:
            return keyword
    return candidates[0] if candidates else None


def reachable_screens(test: CodeUnit, keywords: dict[str, list[CodeUnit]]) -> set[str]:
    """Écrans marqués par le test lui-même ou par un keyword qu'il appelle, en transitif."""
    screens = {ref.screen_id for ref in test.screens}
    seen: set[int] = set()
    stack = [(call, test.source) for call in test.calls]
    while stack:
        name, caller = stack.pop()
        keyword = _resolve(name, caller, test.namespace, keywords)
        if keyword is None or id(keyword) in seen:
            continue
        seen.add(id(keyword))
        screens.update(ref.screen_id for ref in keyword.screens)
        stack.extend((call, keyword.source) for call in keyword.calls)
    return screens


def declared_features(test: CodeUnit) -> list[str]:
    return [
        tag.split(":", 1)[1].strip()
        for tag in test.tags
        if tag.strip().lower().startswith(FEATURE_TAG_PREFIX)
    ]


# --- Vérification ----------------------------------------------------------
def check_references(
    ref: Referentiel, tests: list[CodeUnit], keywords: dict[str, list[CodeUnit]]
) -> list[Finding]:
    findings: list[Finding] = []
    known_screens = sorted(ref.ecrans)
    definitions = [keyword for group in keywords.values() for keyword in group]
    for unit in [*tests, *definitions]:
        for screen in unit.screens:
            if screen.screen_id not in ref.ecrans:
                findings.append(
                    Finding(
                        "error",
                        "ECRAN_INCONNU",
                        f"{screen.source}:{screen.line}",
                        f"écran absent du référentiel : '{screen.screen_id}'"
                        + _suggest(screen.screen_id, known_screens),
                    )
                )
    known_features = sorted(ref.fonctionnalites)
    for test in tests:
        for feature_id in declared_features(test):
            if feature_id not in ref.fonctionnalites:
                findings.append(
                    Finding(
                        "error",
                        "FEAT_INCONNU",
                        f"{test.source}:{test.line}",
                        f"fonctionnalité absente du référentiel : '{feature_id}'"
                        + _suggest(feature_id, known_features),
                    )
                )
    return findings


# --- Rapport ---------------------------------------------------------------
def build_report(
    ref: Referentiel, tests: list[CodeUnit], keywords: dict[str, list[CodeUnit]]
) -> dict:
    screen_tests: dict[str, list[str]] = defaultdict(list)
    feature_tests: dict[str, list[str]] = defaultdict(list)
    for test in tests:
        for screen_id in reachable_screens(test, keywords):
            screen_tests[screen_id].append(test.name)
        for feature_id in declared_features(test):
            feature_tests[feature_id].append(test.name)

    modules = [
        {
            "id": module.id,
            "label": module.label,
            "plateformes": module.plateformes,
            "ecrans": _entries_payload(ref.ecrans, module.id, screen_tests, "atteint_par"),
            "fonctionnalites": _entries_payload(
                ref.fonctionnalites, module.id, feature_tests, "verifiee_par"
            ),
        }
        for module in ref.modules
    ]
    return {
        "genere_le": datetime.now().isoformat(timespec="seconds"),
        "perimetre": _perimetre(modules),
        "modules": modules,
    }


def _entries_payload(
    entries: dict[str, Entry], module_id: str, coverage: dict[str, list[str]], tests_key: str
) -> list[dict]:
    payload = []
    for entry in entries.values():
        if entry.module != module_id:
            continue
        covering = sorted(set(coverage.get(entry.id, [])))
        item = {
            "id": entry.id,
            "label": entry.label,
            "statut": "couvert" if covering else "non_couvert",
            tests_key: covering,
        }
        if entry.type:
            item["type"] = entry.type
        if entry.criticite:
            item["criticite"] = entry.criticite
        payload.append(item)
    return payload


def _perimetre(modules: list[dict]) -> dict:
    """Taille de ce qui est DECRIT dans le referentiel.

    Volontairement aucun taux de couverture : il rapporterait le nombre de tests a un
    inventaire qu'on sait incomplet, et ce chiffre serait ensuite cite hors contexte.
    """
    return {
        "modules": len(modules),
        "ecrans": sum(len(m["ecrans"]) for m in modules),
        "fonctionnalites": sum(len(m["fonctionnalites"]) for m in modules),
    }


def analyse() -> tuple[dict, list[Finding]]:
    """Analyse complète : rapport prêt à sérialiser + anomalies détectées."""
    ref = load_referentiel()
    tests, keywords, warnings = collect_code()
    findings = ref.findings + check_references(ref, tests, keywords) + warnings
    return build_report(ref, tests, keywords), findings
