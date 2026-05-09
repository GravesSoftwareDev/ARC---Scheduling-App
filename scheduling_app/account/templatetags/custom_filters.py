from django import template

register = template.Library()

@register.filter
def dict_lookup(dictionary, key):
    if dictionary is None:
        return None
    return dictionary.get(key, [])

_DEPT_COLORS = [
    ('#1565C0', '#0D47A1'),  # blue
    ('#6A1B9A', '#4A148C'),  # purple
    ('#00695C', '#004D40'),  # teal
    ('#C62828', '#B71C1C'),  # red
    ('#E65100', '#BF360C'),  # orange
    ('#37474F', '#263238'),  # blue-grey
    ('#4527A0', '#311B92'),  # indigo
    ('#558B2F', '#33691E'),  # green
]

@register.filter
def dept_color(department):
    if department is None or department.pk is None:
        return '#37474F'
    bg, _ = _DEPT_COLORS[department.pk % len(_DEPT_COLORS)]
    return bg

@register.filter
def dept_border_color(department):
    if department is None or department.pk is None:
        return '#263238'
    _, border = _DEPT_COLORS[department.pk % len(_DEPT_COLORS)]
    return border


# Location-based colors for schedule blocks (light bg, dark border)
_LOCATION_NAMED = {
    'WC':      ('#BBDEFB', '#1565C0'),  # blue
    'TLC':     ('#C8E6C9', '#2E7D32'),  # green
    'ZOOM':    ('#E1BEE7', '#6A1B9A'),  # purple
    'Drop-in': ('#FFF9C4', '#F57F17'),  # amber
    'Coach':   ('#F8BBD0', '#AD1457'),  # pink
}
_LOCATION_PALETTE = [
    ('#BBDEFB', '#1565C0'),
    ('#C8E6C9', '#2E7D32'),
    ('#E1BEE7', '#6A1B9A'),
    ('#FFF9C4', '#F57F17'),
    ('#F8BBD0', '#AD1457'),
    ('#B2EBF2', '#00695C'),
    ('#FFE0B2', '#E65100'),
    ('#D7CCC8', '#4E342E'),
]

def _loc_colors(location):
    if not location:
        return ('#E3F2FD', '#1565C0')
    if location in _LOCATION_NAMED:
        return _LOCATION_NAMED[location]
    idx = sum(ord(c) for c in location) % len(_LOCATION_PALETTE)
    return _LOCATION_PALETTE[idx]

@register.filter
def location_bg(location):
    return _loc_colors(location)[0]

@register.filter
def location_border(location):
    return _loc_colors(location)[1]
