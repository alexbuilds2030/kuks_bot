"""Парсер снимка холста Robochat (HTML/DOM) в структурированный сценарий.

Использование:
    python parse_robochat.py kuks.xml -o scenario.json
"""
import argparse
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

PX = re.compile(r"(left|top|width):\s*(-?[\d.]+)px")
NUM = re.compile(r"-?\d+(?:\.\d+)?")


def text_of(el):
    """Текст блока с подстановкой переменных вида {{first name}}."""
    parts = []
    for child in el.children:
        if getattr(child, "name", None) is None:
            parts.append(str(child))
        elif "js-field" in child.get("class", []):
            parts.append("{{" + child.get_text() + "}}")
        else:
            parts.append(text_of(child))
    return "".join(parts)


def parse_buttons(li):
    rows = []
    for row in li.select(".flow__node-block-button-row"):
        cur = []
        for btn in row.select(".flow__node-block-button"):
            port = btn.select_one(".flow__port")
            cur.append({
                "text": btn.select_one(".flow__button-label").get_text(),
                "port": port.get("data-port-id") if port else None,
                "source": port.get("data-source") if port else None,
            })
        rows.append(cur)
    return rows


def parse_block(li):
    kind = li.get("data-block")
    b = {"type": kind}
    if kind == "block.message":
        copy = li.select_one(".flow__canvas-copy")
        b["text"] = text_of(copy).strip() if copy else ""
    elif kind == "block.image":
        b["images"] = [{"name": img.get("alt"), "url": img.get("src")} for img in li.select("img")]
        name = li.select_one(".flow__canvas-image-name")
        b["caption"] = name.get_text() if name else None
        more = li.select_one("[data-more]")
        b["hidden_count"] = int(more["data-more"].lstrip("+")) if more else 0
    elif kind == "block.delay":
        d = li.select_one(".flow__canvas-delay")
        b["text"] = d.get_text(" ", strip=True).rstrip("…")
        m = re.search(r"(\d+)\s*(сек|мин|час|ч)", b["text"])
        if m:
            mult = {"сек": 1, "мин": 60, "час": 3600, "ч": 3600}[m.group(2)]
            b["seconds"] = int(m.group(1)) * mult
    elif kind == "block.input":
        copy = li.select_one(".flow__canvas-copy")
        b["text"] = text_of(copy).strip()
        var = li.select_one(".flow__canvas-wait .js-field")
        b["save_to"] = var.get_text() if var else None
        b["save_scope"] = var.get("data-scope") if var else None
        to = li.select_one('[data-port="input-timeout"] .flow__out-label')
        b["timeout_label"] = to.get("title") if to else None
        b["ports"] = {
            p.get("data-port-id"): p.get("data-source")
            for p in li.select(".flow__node-block-port .flow__port")
        }
    elif kind == "block.send_notification":
        b["title"] = li.select_one(".flow__canvas-action-title").get_text()
        b["body"] = li.select_one(".flow__canvas-action-body").get_text()
    buttons = parse_buttons(li)
    if buttons:
        b["buttons"] = buttons
    return b


def parse_node(div):
    style = dict((k, float(v)) for k, v in PX.findall(div.get("style", "")))
    title_el = div.select_one(".flow__node-type")
    node = {
        "id": div["data-node-id"],
        "step": div["data-step"],
        "title": title_el.get_text().strip() if title_el else "",
        "is_start": bool(div.select_one(".flow__node-type.is-start")),
        "pos": {"x": style.get("left"), "y": style.get("top")},
        "blocks": [],
        "keywords": [],
        "next_source": None,
    }
    head = div.select_one(".flow__node-select")
    if head and not node["title"]:
        node["title"] = head.get("aria-label", "").split(": ", 1)[-1]
    for li in div.select(".flow__node-block"):
        node["blocks"].append(parse_block(li))
    for case in div.select(".flow__branch-case"):
        port = case.select_one(".flow__port")
        node["keywords"].append({
            "condition": case.select_one(".flow__branch-heading").get_text(),
            "word": case.select_one(".flow__branch").get_text(),
            "port": port.get("data-port-id"),
            "source": port.get("data-source"),
        })
    foot = div.select_one(".flow__node-foot .flow__port--out")
    if foot:
        node["next_source"] = foot.get("data-source")
        node["next_linked"] = "is-linked" in foot.get("class", [])
    return node


def parse_edges(soup, nodes):
    """Цель связи определяется по конечной точке кривой — она упирается в шапку шага."""
    edges = []
    for path in soup.select("svg.flow__edges path.flow__edge-path"):
        nums = [float(n) for n in NUM.findall(path["d"])]
        ex, ey = nums[-2], nums[-1]
        label = path.find_previous_sibling("path", class_="flow__edge-hit")
        target_title = label["aria-label"].split("→", 1)[-1].strip() if label else None

        def dist(n):
            return abs(n["pos"]["x"] - 14 - ex) + abs(n["pos"]["y"] + 15 - ey)

        target = min(nodes, key=dist)
        edges.append({
            "owner": path.get("data-owner"),
            "source": path.get("data-from"),
            "port": path.get("data-port"),
            "to": target["id"],
            "to_title": target["title"],
            "label_title": target_title,
            "match_error": round(dist(target), 1),
        })
    return edges


def link_targets(nodes, edges):
    """Проставляет цели переходов в кнопки, ключевые слова, ввод и «Следующий шаг».

    У связи data-from — шаг, data-owner — блок-владелец порта (для «next» они совпадают),
    а data-port-id порта в блоке совпадает с data-port связи.
    """
    by_port = {(e["owner"], e["port"]): e["to"] for e in edges}
    used = set()

    def target(source, port):
        key = (source, port)
        if key in by_port:
            used.add(key)
        return by_port.get(key)

    for n in nodes:
        n["next"] = target(n["id"], "next")
        for k in n["keywords"]:
            k["to"] = target(k["source"], k["port"])
        for b in n["blocks"]:
            for row in b.get("buttons", []):
                for bt in row:
                    bt["to"] = target(bt["source"], bt["port"])
            if b["type"] == "block.input":
                b["targets"] = {p: target(s, p) for p, s in b["ports"].items()}
    lost = set(by_port) - used
    if lost:
        print("связи без источника:", lost)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("-o", "--out", default="scenario.json")
    args = ap.parse_args()

    soup = BeautifulSoup(Path(args.src).read_text(encoding="utf-8"), "html.parser")
    nodes = [parse_node(d) for d in soup.select("div.flow__node[data-node-id]")]
    edges = parse_edges(soup, nodes)
    link_targets(nodes, edges)

    Path(args.out).write_text(
        json.dumps({"nodes": nodes, "edges": edges}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    bad = [e for e in edges if e["match_error"] > 5 or e["label_title"] != e["to_title"]]
    print(f"шагов: {len(nodes)}, связей: {len(edges)}, сомнительных связей: {len(bad)}")
    for e in bad:
        print("  ?", e)


if __name__ == "__main__":
    main()
