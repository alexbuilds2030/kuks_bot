"""Собирает «визуальный» workflow для n8n: по ноде на каждый шаг сценария, кнопки — настоящие связи.

    python build_visual.py   # -> n8n/kuks_bot.visual.workflow.json

Устройство (бот без состояния, каждое нажатие кнопки — отдельный запуск):
  Webhook → Разбор update → Маршрутизатор (Code) → «Куда» (Switch)
      ├─ «▶ Шаг»   — показать шаг (старт и ключевые слова входят сюда)
      └─ «🔘 Кнопки: Шаг» (Switch по номеру кнопки) → выходы = кнопки → «▶ Шаг-получатель»
  «▶ Шаг» → (если есть «Следующий шаг») → «▶ следующий шаг», иначе → цикл отправки.
"""
import json
from pathlib import Path

from build_n8n import API, CRED_ID, ROOT, code_node, compact, http_node

WORKFLOW_ID = "kuksbotvisual0001"
SCALE = 0.55

HELPER = r"""
const upd = $('Маршрутизатор').first().json;
const store = $getWorkflowStaticData('global');
store.users = store.users || {};
const user = (store.users[upd.user_id] = store.users[upd.user_id] || { vars: {} });
if (upd.first_name) user.vars['first name'] = upd.first_name;
const fill = t => t.replace(/\{\{([^}]+)\}\}/g, (_, k) => user.vars[k.trim()] ?? '');
let adminIds = '';
try { adminIds = $env.ADMIN_USER_IDS || ''; } catch (e) { /* env заблокирован: впишите id сюда, например '111,222' */ }
const ADMIN_USER_IDS = String(adminIds || '').split(',').map(s => s.trim()).filter(Boolean).map(Number);
const out = $input.all().map(i => i.json).filter(j => j.kind); // действия предыдущего шага цепочки
if (upd.callback_id && !out.length) out.push({ kind: 'ack', callback_id: upd.callback_id });
const say = (text, buttons) => {
  const body = { text };
  if (buttons && buttons.length) body.attachments = [{ type: 'inline_keyboard', payload: {
    buttons: buttons.map(b => [{ type: 'callback', text: b.text, payload: STEP + ':b' + b.k }]) } }];
  out.push({ kind: 'send', user_id: upd.user_id, body });
};
function play(blocks) {
  for (const b of blocks) {
    if (b.t === 'delay') out.push({ kind: 'delay', seconds: b.seconds });
    else if (b.t === 'msg') { if (b.text.trim()) say(fill(b.text), b.buttons); else if (b.buttons.length) say('Выберите пункт', b.buttons); }
    else if (b.t === 'input') { say(fill(b.text)); user.resume = { step: STEP, save_to: b.save_to }; return; }
    else if (b.t === 'notify') {
      const info = `Заявка из бота: ${TITLE}\nПользователь: ${upd.first_name || ''} (id ${upd.user_id})\nМагазин/обращение: ${user.vars.NameShop || '—'}`;
      for (const id of ADMIN_USER_IDS) out.push({ kind: 'send', user_id: id, body: { text: info } });
    }
  }
}
"""

DISPATCH = r"""
const SC = __SC__;
const upd = $input.first().json;
const store = $getWorkflowStaticData('global');
store.users = store.users || {};
const user = (store.users[upd.user_id] = store.users[upd.user_id] || { vars: {} });
const pass = extra => [{ json: { ...upd, ...extra } }];

if (upd.type === 'callback') {
  const m = String(upd.payload || '').match(/^(s\d+):b(\d+)$/);
  if (!m) return [];
  delete user.resume;
  return pass({ target: 'btn:' + m[1], k: Number(m[2]) });
}
if (upd.type === 'start') { delete user.resume; return pass({ target: 'show:' + SC.start }); }
const text = (upd.text || '').trim();
const low = text.toLowerCase();
const kw = SC.keywords.find(k => low.includes(k.word.toLowerCase()));
if (kw) { delete user.resume; return pass({ target: 'show:' + kw.to }); }
if (user.resume) {
  const r = user.resume;
  delete user.resume;
  user.vars[r.save_to] = text;
  return pass({ target: 'cont:' + r.step });
}
return pass({ target: 'show:' + SC.start }); // непонятный текст — сначала
"""


def labels(scn):
    """Читаемые уникальные названия шагов (Robochat режет их до 20 символов)."""
    key = {n["id"]: f"s{i}" for i, n in enumerate(scn["nodes"])}
    btn_names = {}
    for m in scn["nodes"]:
        for b in m["blocks"]:
            for row in b.get("buttons", []):
                for bt in row:
                    if bt.get("to"):
                        btn_names.setdefault(bt["to"], set()).add(bt["text"])
    out, used = {}, {}
    for n in scn["nodes"]:
        t = n["title"]
        if t.startswith("Сообщение #"):
            t = next((b["text"] for b in n["blocks"] if b["type"] == "block.message" and b["text"]), t).split("\n")[0][:30]
        elif len(t) >= 20:
            cand = [x for x in btn_names.get(n["id"], ()) if x.startswith(t)]
            t = cand[0] if cand else t
        if n["step"] == "step.messages" and n["title"] == "Назад":
            t = "Главное меню"
        if n["step"] == "step.messages" and n["title"] == "Проблемы с интернето":
            t = "Индикация на роутере?"
        if n["step"] == "step.actions":
            t = "Уведомление: " + t
        used[t] = used.get(t, 0) + 1
        out[key[n["id"]]] = t if used[t] == 1 else f"{t} ({used[t]})"
    return out


def main():
    scn = json.loads((ROOT / "scenario.json").read_text(encoding="utf-8"))
    comp = compact(scn)
    key = {n["id"]: f"s{i}" for i, n in enumerate(scn["nodes"])}
    pos = {key[n["id"]]: (n["pos"]["x"] * SCALE, n["pos"]["y"] * SCALE) for n in scn["nodes"]}
    name = labels(scn)
    steps = comp["steps"]

    # пронумеровать кнопки каждого шага (их порядок = номер выхода в «Кнопки»)
    for sid, st in steps.items():
        k = 0
        for b in st["blocks"]:
            if b["t"] == "msg":
                for bt in b["buttons"]:
                    bt["k"] = k
                    k += 1
        st["nbtn"] = k

    minx = min(p[0] for p in pos.values())
    maxx = max(p[0] for p in pos.values())
    nodes, conns = [], {}

    def add(node):
        nodes.append(node)

    def link(src, dst, out=0):
        outs = conns.setdefault(src, {"main": []})["main"]
        while len(outs) <= out:
            outs.append([])
        outs[out].append({"node": dst, "type": "main", "index": 0})

    def switch(nm, rules, p):
        return {"parameters": {"rules": {"values": [
            {"conditions": {"options": {"caseSensitive": True, "typeValidation": "strict", "version": 2},
                            "combinator": "and",
                            "conditions": [{"leftValue": expr, "rightValue": val,
                                            "operator": {"type": "string", "operation": "equals"}}]},
             "renameOutput": True, "outputKey": out} for out, expr, val in rules]}, "options": {}},
            "name": nm, "type": "n8n-nodes-base.switch", "typeVersion": 3.2, "position": p}

    show = {s: f"▶ {name[s]}" for s in steps}
    btnsw = {s: f"🔘 {name[s]}" for s in steps if steps[s]["nbtn"]}
    cont = {s: f"↪ {name[s]}: после ответа" for s, st in steps.items() if any(b["t"] == "input" for b in st["blocks"])}

    entry = {comp["start"]} | {k["to"] for k in comp["keywords"]}
    sc = {"start": comp["start"], "keywords": comp["keywords"]}

    # --- вход
    lx = minx - 1500
    add({"parameters": {"httpMethod": "POST", "path": "max-bot", "responseMode": "onReceived", "options": {}},
         "name": "MAX Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
         "position": [lx, 300], "webhookId": "kuks-max-bot-visual"})
    add(code_node("Разбор update", (ROOT / "n8n/normalize.js").read_text(encoding="utf-8"), [lx + 220, 300]))
    add(code_node("Маршрутизатор", DISPATCH.replace("__SC__", json.dumps(sc, ensure_ascii=False)), [lx + 440, 300]))
    rules = [(f"▶ {name[s]}", "={{ $json.target }}", f"show:{s}") for s in sorted(entry)]
    rules += [(f"🔘 {name[s]}", "={{ $json.target }}", f"btn:{s}") for s in btnsw]
    rules += [(f"↪ {name[s]}", "={{ $json.target }}", f"cont:{s}") for s in cont]
    add(switch("Куда", rules, [lx + 700, 300]))
    link("MAX Webhook", "Разбор update")
    link("Разбор update", "Маршрутизатор")
    link("Маршрутизатор", "Куда")
    for i, (_, _, val) in enumerate(rules):
        kind, s = val.split(":")
        link("Куда", {"show": show, "btn": btnsw, "cont": cont}[kind][s], i)

    # --- цикл отправки
    rx = maxx + 900
    LOOP = "По одному"
    add({"parameters": {"batchSize": 1, "options": {}}, "name": LOOP,
         "type": "n8n-nodes-base.splitInBatches", "typeVersion": 3, "position": [rx, 300]})
    add(switch("Тип действия", [(k, "={{ $json.kind }}", k) for k in ("send", "delay", "ack")], [rx + 220, 300]))
    add(http_node("Отправить сообщение", f"{API}/messages", [rx + 460, 140],
                  "={{ JSON.stringify($json.body) }}", qs={"user_id": "={{ $json.user_id }}"}))
    add({"parameters": {"amount": "={{ $json.seconds }}", "unit": "seconds"}, "name": "Пауза",
         "type": "n8n-nodes-base.wait", "typeVersion": 1.1, "position": [rx + 460, 300], "webhookId": "kuks-visual-wait"})
    ack = http_node("Ответ на нажатие", f"{API}/answers", [rx + 460, 460],
                    "={{ JSON.stringify({ notification: ' ' }) }}", qs={"callback_id": "={{ $json.callback_id }}"})
    ack["onError"] = "continueRegularOutput"
    add(ack)
    link(LOOP, "Тип действия", 1)
    for i, tgt in enumerate(("Отправить сообщение", "Пауза", "Ответ на нажатие")):
        link("Тип действия", tgt, i)
        link(tgt, LOOP)

    # --- шаги
    for s, st in steps.items():
        x, y = pos[s]
        blocks = st["blocks"]
        input_at = next((i for i, b in enumerate(blocks) if b["t"] == "input"), None)
        body = blocks if input_at is None else blocks[:input_at + 1]
        js = (f"const STEP = {json.dumps(s)}, TITLE = {json.dumps(st['title'], ensure_ascii=False)};\n" + HELPER
              + f"play({json.dumps(body, ensure_ascii=False)});\nreturn out.map(a => ({{ json: a }}));\n")
        add(code_node(show[s], js, [x, y]))
        if input_at is None and st["next"]:
            link(show[s], show[st["next"]])
        else:
            link(show[s], LOOP)
        if s in cont:
            rest = blocks[input_at + 1:]
            js2 = (f"const STEP = {json.dumps(s)}, TITLE = {json.dumps(st['title'], ensure_ascii=False)};\n" + HELPER
                   + f"play({json.dumps(rest, ensure_ascii=False)});\nreturn out.map(a => ({{ json: a }}));\n")
            add(code_node(cont[s], js2, [x, y + 120]))
            link(cont[s], show[st["next"]] if st["next"] else LOOP)
        if s in btnsw:
            order = [bt for b in blocks if b["t"] == "msg" for bt in b["buttons"]]
            add(switch(btnsw[s], [(bt["text"], "={{ String($json.k) }}", str(bt["k"])) for bt in order],
                       [x + 260, y]))
            for bt in order:
                link(btnsw[s], show[bt["to"]], bt["k"])

    # пустые выходы должны существовать у каждого узла-switch: n8n ждёт массив по числу правил
    wf = {"id": WORKFLOW_ID, "name": "Кукс-бот по шагам (MAX)", "nodes": nodes, "connections": conns,
          "settings": {"executionOrder": "v1"}, "active": False, "pinData": {}}
    out = ROOT / "n8n/kuks_bot.visual.workflow.json"
    out.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
    n_links = sum(len(t) for c in conns.values() for t in c["main"])
    print(f"нод: {len(nodes)}, связей: {n_links} -> {out}")


if __name__ == "__main__":
    main()
