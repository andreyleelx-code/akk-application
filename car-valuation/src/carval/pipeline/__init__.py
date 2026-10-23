"""Конвейер оценки — «команда агентов» из документа:

1. shot_controller — все ли ракурсы есть, пригодны ли фото
2. inspector       — дефектоскопы по зонам (параллельно)
3. pricing         — аналоги, вычет на ремонт, диапазон цены (код, не ИИ)
4. reviewer        — ищет противоречия, помечает неуверенность
5. человек         — подтверждает дефекты и утверждает цену (бот)
"""

from string import Template

from ..settings import Settings


def load_prompt(settings: Settings, name: str, **values: str) -> str:
    text = (settings.prompts_dir / f"{name}.md").read_text(encoding="utf-8")
    return Template(text).safe_substitute(values)
