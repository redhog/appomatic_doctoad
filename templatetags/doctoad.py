from django import template
register = template.Library()

@register.filter
def arg(value, param):
    value['args'].append(param)
    return value

@register.filter
def method(value, param):
    return {'obj': value, 'method': param, 'args': []}

@register.filter
def call(value):
    return getattr(value['obj'], value['method'])(*value['args'])
