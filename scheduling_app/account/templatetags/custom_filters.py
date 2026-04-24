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
