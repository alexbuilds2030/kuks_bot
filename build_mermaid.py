"""Рисует схему сценария (Mermaid) из scenario.json → docs/SCENARIO.md"""
import json
from pathlib import Path

ROOT = Path(__file__).parent
NAV = {"Назад", "В начало", "Заявка в Service Desk"}  # навигационные кнопки: в упрощённой схеме скрыты
RENAME = {("step.messages", "Назад"): "Главное меню", ("step.messages", "Старт"): "Старт"}


def esc(s):
    return s.replace('"', "'").replace("\n", " ")


def build(scn, full):
    N = {n["id"]: n for n in scn["nodes"]}
    sid = {n["id"]: f"s{i}" for i, n in enumerate(scn["nodes"])}

    # Robochat обрезает названия шагов до 20 символов — полное название берём из кнопки, ведущей в шаг
    full_name = {}
    for m in scn["nodes"]:
        for b in m["blocks"]:
            for row in b.get("buttons", []):
                for bt in row:
                    if bt.get("to"):
                        full_name.setdefault(bt["to"], set()).add(bt["text"])

    def fix_title(n):
        t = n["title"]
        if t.startswith("Сообщение #"):
            msg = next((b["text"] for b in n["blocks"] if b["type"] == "block.message" and b["text"]), t)
            return msg.split("\n")[0][:30]
        if len(t) >= 20:
            cand = [x for x in full_name.get(n["id"], ()) if x.startswith(t)]
            if cand:
                return cand[0]
        return t

    def label(n):
        # у шага с картинками текст сообщения часто = названию; для заглушек показываем число картинок
        if n["step"] == "step.actions":
            return f"🔔 Уведомление: {fix_title(n)}"
        if n["step"] == "step.keywords":
            return "Ключевые слова"
        name = RENAME.get((n["step"], n["title"])) or fix_title(n)
        imgs = sum(len(b.get("images", [])) + b.get("hidden_count", 0) for b in n["blocks"] if b["type"] == "block.image")
        return esc(name) + (f" 🖼×{imgs}" if imgs else "")

    # две вершины с одинаковым названием «Проблемы с интернето»: сообщение про роутер отличаем
    for n in scn["nodes"]:
        if n["step"] == "step.messages" and n["title"] == "Проблемы с интернето":
            n["title"] = "Индикация на роутере?"

    lines = ["flowchart LR"]
    for n in scn["nodes"]:
        if n["step"] == "step.keywords":
            lines.append(f'  {sid[n["id"]]}{{{{"{label(n)}"}}}}')
        elif n["is_start"]:
            lines.append(f'  {sid[n["id"]]}(["{label(n)}"])')
        elif n["step"] == "step.actions":
            lines.append(f'  {sid[n["id"]]}[/"{label(n)}"/]')
        else:
            lines.append(f'  {sid[n["id"]]}["{label(n)}"]')

    seen = set()
    def edge(a, b, text=None):
        if (a, b, text) in seen:
            return
        seen.add((a, b, text))
        arrow = f' -->|"{esc(text)}"| ' if text else " --> "
        lines.append(f"  {sid[a]}{arrow}{sid[b]}")

    menu = next(n["id"] for n in scn["nodes"] if n["title"] == "Назад" and n["step"] == "step.messages")
    for n in scn["nodes"]:
        for k in n["keywords"]:
            if k.get("to"):
                edge(n["id"], k["to"], k["word"] if full else None)
        for b in n["blocks"]:
            for row in b.get("buttons", []):
                for bt in row:
                    if not bt.get("to"):
                        continue
                    if not full and bt["text"] in NAV and n["id"] != menu:
                        continue
                    edge(n["id"], bt["to"], bt["text"])
        if n.get("next"):
            edge(n["id"], n["next"], "далее")
    return "\n".join(lines)


def main():
    scn = json.loads((ROOT / "scenario.json").read_text(encoding="utf-8"))
    simple = build(json.loads(json.dumps(scn)), full=False)
    full = build(json.loads(json.dumps(scn)), full=True)
    md = f"""# Схема сценария

Формы: стадион — старт, шестиугольник — ключевые слова (запускают шаг из любого места), параллелограмм — уведомление,
🖼×N — число картинок в шаге (пока не перенесены в n8n).

## Упрощённая
Кнопки «Назад», «В начало» и «Заявка в Service Desk» скрыты: они есть почти в каждом шаге и ведут в главное меню,
в начало и в шаги заявки.

```mermaid
{simple}
```

## Полная
```mermaid
{full}
```
"""
    out = ROOT / "docs/SCENARIO.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print("готово:", out, "| связей в упрощённой:", simple.count("-->"), "| в полной:", full.count("-->"))


if __name__ == "__main__":
    main()
