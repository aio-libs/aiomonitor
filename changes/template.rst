{# TOWNCRIER TEMPLATE #}
{% for section, _ in sections.items() %}

{% if sections[section] %}
{% for category, val in definitions.items() if category in sections[section]%}
{% if definitions[category]['showcontent'] %}
{% for text, values in sections[section][category].items() %}
- {{ text }}
  {{ values|join(',\n  ') + '\n' }}
{% endfor %}

{% else %}
- {{ sections[section][category]['']|join(', ') }}

{% endif %}
{% if sections[section][category]|length == 0 %}
No significant changes.

{% else %}
{% endif %}

{% endfor %}
{% else %}
No significant changes.
{% endif %}
{% endfor %}
