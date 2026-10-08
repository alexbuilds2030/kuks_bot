// Движок сценария Robochat → n8n. Сценарий подставляется генератором build_n8n.py.
const SCENARIO = __SCENARIO__;

// Кому слать уведомления «Заявка в Service Desk»: user_id в MAX через запятую в .env (ADMIN_USER_IDS). Пусто = не слать.
const ADMIN_USER_IDS = String($env.ADMIN_USER_IDS || '').split(',').map(s => s.trim()).filter(Boolean).map(Number);
const MAX_CHAIN = 25; // защита от зацикливания «Следующий шаг»

const upd = $input.first().json;
const store = $getWorkflowStaticData('global');
store.users = store.users || {};
const user = (store.users[upd.user_id] = store.users[upd.user_id] || { vars: {} });
if (upd.first_name) user.vars['first name'] = upd.first_name;

const actions = [];
const say = (text, buttons) => {
  const body = { text };
  if (buttons && buttons.length) {
    body.attachments = [{
      type: 'inline_keyboard',
      payload: { buttons: buttons.map(b => [{ type: 'callback', text: b.text, payload: 'go:' + b.to }]) },
    }];
  }
  actions.push({ kind: 'send', user_id: upd.user_id, body });
};
const fill = t => t.replace(/\{\{([^}]+)\}\}/g, (_, k) => user.vars[k.trim()] ?? '');

// Выполняет блоки шага начиная с индекса from; идёт по «Следующему шагу».
function run(stepId, from = 0, depth = 0) {
  const step = SCENARIO.steps[stepId];
  if (!step || depth > MAX_CHAIN) return;
  for (let i = from; i < step.blocks.length; i++) {
    const b = step.blocks[i];
    if (b.t === 'delay') {
      actions.push({ kind: 'delay', seconds: b.seconds });
    } else if (b.t === 'msg') {
      if (b.text.trim()) say(fill(b.text), b.buttons);
      else if (b.buttons.length) say('Выберите пункт', b.buttons);
    } else if (b.t === 'input') {
      say(fill(b.text));
      user.resume = { step: stepId, block: i + 1, save_to: b.save_to };
      return; // ждём ответ пользователя
    } else if (b.t === 'notify') {
      const info = `Заявка из бота: ${step.title}\nПользователь: ${upd.first_name || ''} (id ${upd.user_id})\n` +
        `Магазин/обращение: ${user.vars.NameShop || '—'}`;
      for (const id of ADMIN_USER_IDS) actions.push({ kind: 'send', user_id: id, body: { text: info } });
    }
  }
  if (step.next) run(step.next, 0, depth + 1);
}

const text = (upd.text || '').trim();
if (upd.type === 'callback') {
  if (upd.callback_id) actions.push({ kind: 'ack', callback_id: upd.callback_id });
  const target = String(upd.payload || '').replace(/^go:/, '');
  if (SCENARIO.steps[target]) { delete user.resume; run(target); }
} else {
  const low = text.toLowerCase();
  const kw = upd.type === 'start'
    ? { to: SCENARIO.start }
    : SCENARIO.keywords.find(k => low.includes(k.word.toLowerCase()));
  if (kw) {
    delete user.resume;
    run(kw.to);
  } else if (user.resume) {
    const r = user.resume;
    delete user.resume;
    user.vars[r.save_to] = text;
    run(r.step, r.block);
  } else {
    run(SCENARIO.start); // непонятный текст — начинаем сначала
  }
}

return actions.map(a => ({ json: a }));
