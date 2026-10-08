"""Собирает workflow для n8n из scenario.json.

    python build_n8n.py            # -> n8n/kuks_bot.workflow.json

Сценарий целиком зашит в Code-ноду «Сценарий», поэтому правка сценария = перегенерация файла.
"""
import json
from pathlib import Path

ROOT = Path(__file__).parent
API = "https://platform-api.max.ru"
CRED_ID = "maxbot0000000001"      # совпадает с deploy.sh
WORKFLOW_ID = "kuksbot0000000001"  # фиксированный id, чтобы повторный импорт обновлял, а не дублировал


def compact(scn):
    """Выкидывает из разбора всё лишнее и заменяет uuid короткими ключами s0, s1, …"""
    key = {n["id"]: f"s{i}" for i, n in enumerate(scn["nodes"])}
    steps, keywords, start = {}, [], None
    for n in scn["nodes"]:
        if n["is_start"]:
            start = key[n["id"]]
        for k in n["keywords"]:
            if k.get("to"):
                keywords.append({"word": k["word"], "to": key[k["to"]]})
        blocks = []
        for b in n["blocks"]:
            t = b["type"]
            if t == "block.delay":
                blocks.append({"t": "delay", "seconds": b.get("seconds", 0)})
            elif t == "block.message":
                btns = [{"text": bt["text"], "to": key[bt["to"]]}
                        for row in b.get("buttons", []) for bt in row if bt.get("to")]
                blocks.append({"t": "msg", "text": b["text"], "buttons": btns})
            elif t == "block.input":
                blocks.append({"t": "input", "text": b["text"], "save_to": b["save_to"]})
            elif t == "block.send_notification":
                blocks.append({"t": "notify"})
            elif t == "block.image":
                # Картинки пока пропускаем (доработка), но кнопки под фото сохраняем:
                # вешаем их на предыдущее сообщение, а если его нет — на заглушку с названием шага.
                btns = [{"text": bt["text"], "to": key[bt["to"]]}
                        for row in b.get("buttons", []) for bt in row if bt.get("to")]
                if btns:
                    prev = next((x for x in reversed(blocks) if x["t"] == "msg"), None)
                    if prev is None:
                        prev = {"t": "msg", "text": "", "buttons": []}
                        blocks.append(prev)
                    prev["buttons"] += btns
        for b in blocks:  # пустой текст у сообщения с кнопками → название шага
            if b["t"] == "msg" and not b["text"].strip() and b["buttons"]:
                b["text"] = n["title"]
        if n["step"] == "step.keywords":
            continue
        steps[key[n["id"]]] = {
            "title": n["title"],
            "blocks": blocks,
            "next": key.get(n["next"]),
        }
    # длинные слова раньше коротких, чтобы «В начало» не перехватывался словом «начало» иначе
    keywords.sort(key=lambda k: -len(k["word"]))
    return {"start": start, "keywords": keywords, "steps": steps}


def code_node(name, js, pos):
    return {"parameters": {"jsCode": js}, "name": name, "type": "n8n-nodes-base.code",
            "typeVersion": 2, "position": pos}


def http_node(name, url, pos, body_expr, qs=None):
    params = {
        "method": "POST", "url": url,
        "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
        "sendBody": True, "specifyBody": "json", "jsonBody": body_expr,
        "options": {},
    }
    if qs:
        params["sendQuery"] = True
        params["queryParameters"] = {"parameters": [{"name": k, "value": v} for k, v in qs.items()]}
    return {"parameters": params, "name": name, "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2, "position": pos,
            "credentials": {"httpHeaderAuth": {"id": CRED_ID, "name": "MAX Bot Token"}}}


def main():
    scn = compact(json.loads((ROOT / "scenario.json").read_text(encoding="utf-8")))
    engine = (ROOT / "n8n/engine.js").read_text(encoding="utf-8").replace(
        "__SCENARIO__", json.dumps(scn, ensure_ascii=False))
    normalize = (ROOT / "n8n/normalize.js").read_text(encoding="utf-8")

    nodes = [
        {"parameters": {"httpMethod": "POST", "path": "max-bot", "responseMode": "onReceived", "options": {}},
         "name": "MAX Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
         "position": [0, 300], "webhookId": "kuks-max-bot"},
        code_node("Разбор update", normalize, [220, 300]),
        code_node("Сценарий", engine, [440, 300]),
        {"parameters": {"batchSize": 1, "options": {}}, "name": "По одному",
         "type": "n8n-nodes-base.splitInBatches", "typeVersion": 3, "position": [660, 300]},
        {"parameters": {"rules": {"values": [
            {"conditions": {"options": {"caseSensitive": True, "typeValidation": "strict", "version": 2},
                            "combinator": "and",
                            "conditions": [{"leftValue": "={{ $json.kind }}", "rightValue": kind,
                                            "operator": {"type": "string", "operation": "equals"}}]},
             "renameOutput": True, "outputKey": kind}
            for kind in ("send", "delay", "ack")]}, "options": {}},
         "name": "Тип действия", "type": "n8n-nodes-base.switch", "typeVersion": 3.2,
         "position": [880, 300]},
        http_node("Отправить сообщение", f"{API}/messages", [1120, 140],
                  "={{ JSON.stringify($json.body) }}", qs={"user_id": "={{ $json.user_id }}"}),
        {"parameters": {"amount": "={{ $json.seconds }}", "unit": "seconds"},
         "name": "Пауза", "type": "n8n-nodes-base.wait", "typeVersion": 1.1,
         "position": [1120, 300], "webhookId": "kuks-max-wait"},
        http_node("Ответ на нажатие", f"{API}/answers", [1120, 460],
                  "={{ JSON.stringify({ notification: ' ' }) }}", qs={"callback_id": "={{ $json.callback_id }}"}),
    ]
    nodes[-1]["onError"] = "continueRegularOutput"

    def c(*targets):
        return {"main": [[{"node": t, "type": "main", "index": 0} for t in out] for out in targets]}

    connections = {
        "MAX Webhook": c(["Разбор update"]),
        "Разбор update": c(["Сценарий"]),
        "Сценарий": c(["По одному"]),
        "По одному": c([], ["Тип действия"]),  # выход 0 = готово, выход 1 = следующий элемент
        "Тип действия": c(["Отправить сообщение"], ["Пауза"], ["Ответ на нажатие"]),
        "Отправить сообщение": c(["По одному"]),
        "Пауза": c(["По одному"]),
        "Ответ на нажатие": c(["По одному"]),
    }
    wf = {"id": WORKFLOW_ID, "name": "Кукс-бот поддержки (MAX)", "nodes": nodes, "connections": connections,
          "settings": {"executionOrder": "v1"}, "active": False, "pinData": {}}
    out = ROOT / "n8n/kuks_bot.workflow.json"
    out.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"шагов в сценарии: {len(scn['steps'])}, слов-триггеров: {len(scn['keywords'])}, -> {out}")


if __name__ == "__main__":
    main()
