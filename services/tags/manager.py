"""
Gestion du filtrage et du matching des tests par tags.

Améliorations par rapport à RFEM :
- get_available_tags retourne tags + compteurs + tests associés
- Filtrage simplifié sans dépendances OS/bench complexes
"""

from .parser import build_tests_list, get_robot_files

PERMANENT_EXCLUDE_TAGS = ['not_ready', 'in_dev', 'blocked', 'deprecated', 'quarantaine']


def get_available_tags() -> dict:
    """
    Récupère tous les tags disponibles avec leurs compteurs et tests associés.
    
    Returns:
        dict: {
            'tags': [{'name': str, 'count': int, 'tests': [str]}],
            'total_tests': int,
            'total_tags': int
        }
    """
    robot_files = get_robot_files()
    tests = build_tests_list(robot_files)
    
    tag_map = {}
    
    for test in tests:
        for tag in test.get('tags', []):
            tag_lower = tag.lower()
            if tag_lower not in tag_map:
                tag_map[tag_lower] = {'name': tag, 'count': 0, 'tests': []}
            tag_map[tag_lower]['count'] += 1
            tag_map[tag_lower]['tests'].append(test['name'])
    
    tags_list = sorted(tag_map.values(), key=lambda x: (-x['count'], x['name']))
    
    return {
        'tags': tags_list,
        'total_tests': len(tests),
        'total_tags': len(tags_list)
    }


def get_matching_tests(include_tags: list, exclude_tags: list = None) -> list:
    """
    Retourne les tests correspondant aux critères de tags.
    
    Args:
        include_tags: Tags à inclure (au moins un doit matcher)
        exclude_tags: Tags à exclure
    
    Returns:
        list[dict]: Tests matchant les critères
    """
    if exclude_tags is None:
        exclude_tags = []
    
    # Ajouter les exclusions permanentes
    effective_exclude = list(set(exclude_tags + PERMANENT_EXCLUDE_TAGS))
    
    robot_files = get_robot_files()
    all_tests = build_tests_list(robot_files)
    
    matching = []
    
    for test in all_tests:
        tags = [t.lower() for t in test.get('tags', [])]
        
        # Vérifier inclusion (au moins un tag doit matcher)
        has_include = True
        if include_tags:
            include_lower = [t.lower() for t in include_tags]
            has_include = bool(set(include_lower) & set(tags))
        
        # Vérifier exclusion (aucun tag exclu ne doit être présent)
        exclude_lower = [t.lower() for t in effective_exclude]
        has_exclude = bool(set(exclude_lower) & set(tags))
        
        if has_include and not has_exclude:
            matching.append(test)
    
    return matching


def count_tests_matching_tags(include_tags: list, exclude_tags: list = None) -> int:
    """Compte les tests matchant les critères de tags."""
    return len(get_matching_tests(include_tags, exclude_tags))
